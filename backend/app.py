from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import pandas as pd
from flask_socketio import SocketIO
import os
import bcrypt
import jwt
import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from action_recommendations import get_next_action
from auth_middleware import admin_required
from identity_service import generate_anonymous_id, resolve_anonymous_identity
from lead_processing_service import process_session
from behavior_event_service import BehaviorEventError, log_behavior_event
from customer_profile_service import build_profile_update, apply_profile_update
from seed_clothing_products import seed_clothing_products_if_empty
import certifi

load_dotenv()

app = Flask(__name__)
FRONTEND_URL = os.getenv("FRONTEND_URL")
CORS(app, origins=FRONTEND_URL or "*")
socketio = SocketIO(app, cors_allowed_origins=FRONTEND_URL or "*")


def create_mongo_client():
    uri = os.getenv("MONGO_URI", "")
    if uri.startswith("mongodb+srv://"):
        return MongoClient(
            uri,
            tls=True,
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            socketTimeoutMS=5000,
        )
    elif uri.startswith("mongodb://localhost") or uri.startswith("mongodb://127.0.0.1"):
        return MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
        )
    elif uri:
        return MongoClient(
            uri,
            serverSelectionTimeoutMS=5000,
        )
    else:
        return MongoClient(
            "mongodb://localhost:27017/leadmagnet",
            serverSelectionTimeoutMS=5000,
        )


mongo_client = create_mongo_client()
MONGO_AVAILABLE = False

try:
    mongo_client.admin.command("ping")
    MONGO_AVAILABLE = True
except Exception as e:
    MONGO_AVAILABLE = False
    print(f"Warning: MongoDB connection failed ({e}). Running in fallback mode.")

db = mongo_client["leadmagnet"]
profiles_collection = db["user_profiles"]
legacy_users_collection = db["users"]
products_collection = db["products"]
sessions_collection = db["sessions"]
events_collection = db["events"]
leads_collection = db["leads"]
orders_collection = db["orders"]

from bson import ObjectId

LEAD_STATUSES = {"New", "Contacted", "Qualified", "Converted", "Lost"}


def serialize_mongo_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, bytes):
        # Bytes fields (e.g., bcrypt hashes) are not JSON serializable — omit them.
        return None
    if isinstance(value, datetime.datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: serialize_mongo_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_mongo_value(item) for item in value]
    return value


SAFE_PROFILE_FIELDS = {
    "_id", "email", "role", "full_name", "username", "age", "gender", "dob", "phone",
    "created_at", "updated_at", "last_active_at", "visitor_id", "user_id",
    "engagement_score", "page_view_count", "session_count", "cart_add_count",
    "wishlist_add_count", "favorite_categories",
}


def serialize_profile(profile):
    """Serialize a profile document, excluding sensitive fields like password."""
    return serialize_mongo_value({k: v for k, v in profile.items() if k in SAFE_PROFILE_FIELDS})




def migrate_users_to_profiles_once():
    if not MONGO_AVAILABLE:
        return
    try:
        if "users" not in db.list_collection_names():
            return
        if profiles_collection.count_documents({}) > 0:
            return

        users = list(legacy_users_collection.find({}))
        if users:
            profiles_collection.insert_many(users)
    except Exception as e:
        print(f"Warning: MongoDB migration skipped: {e}")


def initialize_database():
    global MONGO_AVAILABLE
    try:
        mongo_client.admin.command("ping")
        MONGO_AVAILABLE = True
    except Exception as e:
        MONGO_AVAILABLE = False
        print(f"Warning: MongoDB startup check failed ({e}).")
        return

    migrate_users_to_profiles_once()
    try:
        seed_clothing_products_if_empty(products_collection)
    except Exception as e:
        print(f"Warning: Automatic product seeding failed: {e}")


JWT_SECRET = os.getenv("JWT_SECRET")
app.config["JWT_SECRET"] = JWT_SECRET

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Load everything saved from the notebook
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.abspath(os.path.join(BASE_DIR, "..", "model"))

model = joblib.load(os.path.join(MODEL_DIR, "xgb_model.pkl"))
scaler = joblib.load(os.path.join(MODEL_DIR, "scaler.pkl"))
feature_columns = joblib.load(os.path.join(MODEL_DIR, "feature_columns.pkl"))
kmeans = joblib.load(os.path.join(MODEL_DIR, "kmeans_model.pkl"))
segment_map = joblib.load(os.path.join(MODEL_DIR, "segment_map.pkl"))


@app.route("/")
def home():
    return jsonify({"status": "Lead Magnet API is running", "mongo_available": MONGO_AVAILABLE})


@app.route("/api/health", methods=["GET"])
def health():
    global MONGO_AVAILABLE
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "mongo": False, "error": "MongoDB unavailable"}), 503
    try:
        mongo_client.admin.command("ping")
        return jsonify({"success": True, "mongo": True}), 200
    except Exception as e:
        MONGO_AVAILABLE = False
        return jsonify({"success": False, "mongo": False, "error": str(e)}), 503


@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()

    lead_df = pd.DataFrame([data])
    lead_encoded = pd.get_dummies(lead_df)
    lead_encoded = lead_encoded.reindex(columns=feature_columns, fill_value=0)
    lead_scaled = scaler.transform(lead_encoded)

    prob = model.predict_proba(lead_scaled)[0][1]
    segment_id = kmeans.predict(lead_scaled)[0]
    segment = segment_map[segment_id]

    return jsonify({
        "score": round(float(prob), 2),
        "segment": segment,
        "reason": f"Scored based on submitted lead behavior"
    })


@app.route("/api/auth/signup", methods=["POST"])
def signup():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required", "errors": []}), 400

    try:
        if profiles_collection.find_one({"email": email}):
            return jsonify({"success": False, "message": "User already exists", "errors": []}), 400

        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

        user_result = profiles_collection.insert_one({
            "email": email,
            "password": hashed_pw,
            "role": "user",
            "full_name": data.get("fullName") or data.get("full_name"),
            "username": data.get("username"),
            "age": data.get("age"),
            "gender": data.get("gender"),
            "dob": data.get("dob"),
            "phone": data.get("phone"),
            "created_at": datetime.datetime.utcnow(),
            "updated_at": datetime.datetime.utcnow(),
        })

        anonymous_id = data.get("anonymous_id") or data.get("visitor_id")
        resolution = resolve_anonymous_identity(
            anonymous_id,
            user_result.inserted_id,
            profiles_collection,
            sessions_collection,
            events_collection,
            leads_collection,
        )

        return jsonify({
            "success": True,
            "message": "Account created successfully",
            "data": {
                "user_id": str(user_result.inserted_id),
                "identity_resolution": resolution,
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/auth/login", methods=["POST"])
def login():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    try:
        user = profiles_collection.find_one({"email": email})
        if not user or not user.get("password") or not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            return jsonify({"success": False, "message": "Invalid credentials", "errors": []}), 401

        token = jwt.encode(
            {
                "sub": str(user["_id"]),
                "email": email,
                "role": user["role"],
                "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)
            },
            JWT_SECRET,
            algorithm="HS256"
        )

        anonymous_id = data.get("anonymous_id") or data.get("visitor_id")
        resolution = resolve_anonymous_identity(
            anonymous_id,
            user["_id"],
            profiles_collection,
            sessions_collection,
            events_collection,
            leads_collection,
        )

        return jsonify({
            "success": True,
            "message": "Login successful",
            "data": {
                "token": token,
                "email": email,
                "role": user["role"],
                "user_id": str(user["_id"]),
                "identity_resolution": resolution,
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/auth/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json()
    username = data.get("username")
    password = data.get("password")

    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Invalid admin credentials", "errors": []}), 401

    token = jwt.encode(
        {
            "username": username,
            "role": "admin",
            "exp": datetime.datetime.utcnow() + datetime.timedelta(days=1)
        },
        JWT_SECRET,
        algorithm="HS256"
    )

    return jsonify({
        "success": True,
        "message": "Admin login successful",
        "data": {"token": token, "role": "admin"}
    })


@app.route("/track", methods=["POST"])
def track():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(force=True)

    lead_df = pd.DataFrame([data])
    lead_encoded = pd.get_dummies(lead_df)
    lead_encoded = lead_encoded.reindex(columns=feature_columns, fill_value=0)
    lead_scaled = scaler.transform(lead_encoded)

    prob = model.predict_proba(lead_scaled)[0][1]
    segment_id = kmeans.predict(lead_scaled)[0]
    segment = segment_map[segment_id]

    action = get_next_action(segment)

    result = {
        "visitor_id": data.get("visitor_id", "unknown"),
        "score": round(float(prob), 2),
        "segment": segment,
        "next_action": action
    }

    leads_collection.insert_one({
        **result,
        "source_data": data,
        "timestamp": datetime.datetime.utcnow()
    })

    socketio.emit("lead_update", result)

    return jsonify(result)


@app.route("/api/products", methods=["GET"])
def get_products():
    if not MONGO_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "Database unavailable",
            "data": []
        }), 500

    try:
        category = request.args.get("category")
        query = {"category": category} if category else {}
        items = list(products_collection.find(query))

        for item in items:
            item["_id"] = str(item["_id"])

        return jsonify({
            "success": True,
            "data": items
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "data": []
        }), 500


@app.route("/api/debug/users-count", methods=["GET"])
def debug_users_count():
    if not MONGO_AVAILABLE:
        return jsonify({
            "success": False,
            "count": 0,
            "error": "Database unavailable",
        }), 500

    try:
        count = profiles_collection.count_documents({})
        return jsonify({
            "success": True,
            "count": count,
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "count": 0,
            "error": str(e)
        }), 500


@app.route("/api/products/<product_id>", methods=["GET"])
def get_product(product_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        item = products_collection.find_one({"_id": ObjectId(product_id)})
        if not item:
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 404

        item["_id"] = str(item["_id"])
        return jsonify({"success": True, "message": "Product fetched", "data": item})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


def update_profile_from_event(session_id, event_id):
    if not MONGO_AVAILABLE:
        return
    try:
        session_object_id = ObjectId(session_id)
        event_object_id = ObjectId(event_id)
    except Exception:
        return

    session_doc = sessions_collection.find_one({"_id": session_object_id})
    event_doc = events_collection.find_one({"_id": event_object_id})
    if not session_doc or not event_doc:
        return

    profile_update = build_profile_update(session_doc, [event_doc])
    apply_profile_update(profiles_collection, profile_update)


# ---- Session Tracking (Module 3) ----

@app.route("/api/session/start", methods=["POST"])
def start_session():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(force=True)
    anonymous_id = data.get("anonymous_id") or data.get("visitor_id") or generate_anonymous_id()
    visitor_id = data.get("visitor_id") or anonymous_id

    session_doc = {
        "visitor_id": visitor_id,
        "anonymous_id": anonymous_id,
        "identity_status": "anonymous",
        "started_at": datetime.datetime.utcnow(),
        "last_active_at": datetime.datetime.utcnow(),
        "total_time_seconds": 0,
        "page_views": 0,
        "status": "active"
    }

    result = sessions_collection.insert_one(session_doc)

    return jsonify({
        "success": True,
        "message": "Session started",
        "data": {
            "session_id": str(result.inserted_id),
            "visitor_id": visitor_id,
            "anonymous_id": anonymous_id,
        },
    })


@app.route("/api/session/event", methods=["POST"])
def log_event():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(force=True)
    try:
        event_id = log_behavior_event(data, sessions_collection, events_collection)
    except BehaviorEventError as error:
        return jsonify({"success": False, "message": error.message, "errors": []}), error.status_code

    update_profile_from_event(data.get("session_id"), event_id)

    return jsonify({"success": True, "message": "Event logged", "data": {"event_id": event_id}})


@app.route("/api/session/end", methods=["POST"])
def end_session():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        data = request.get_json(force=True)
        session_id = data.get("session_id")

        if not session_id:
            return jsonify({
                "success": False,
                "message": "session_id required",
                "errors": []
            }), 400

        try:
            session_object_id = ObjectId(session_id)
        except Exception:
            return jsonify({
                "success": False,
                "message": "Session not found",
                "errors": []
            }), 404

        session = sessions_collection.find_one({"_id": session_object_id})

        if not session:
            return jsonify({
                "success": False,
                "message": "Session not found",
                "errors": []
            }), 404

        now = datetime.datetime.utcnow()
        total_time_seconds = (now - session["started_at"]).total_seconds()

        sessions_collection.update_one(
            {"_id": session_object_id},
            {"$set": {"status": "ended", "total_time_seconds": total_time_seconds}}
        )

        lead = process_session(
            session_object_id,
            sessions_collection,
            events_collection,
            leads_collection,
        )

        session_doc = sessions_collection.find_one({"_id": session_object_id})

        events = list(events_collection.find({"session_id": session_object_id}))

        profile_update = build_profile_update(session_doc, events)

        apply_profile_update(profiles_collection, profile_update)

        return jsonify({
            "success": True,
            "message": "Session ended and lead processed",
            "data": {
                "session_id": str(session_object_id),
                "total_time_seconds": total_time_seconds,
                "score": lead["score"],
                "segment": lead["segment"],
                "next_action": lead["next_action"],
            },
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "errors": []
        }), 500


# ---- Admin Dashboard (Module 6) ----

@app.route("/api/admin/leads", methods=["GET"])
@admin_required
def get_admin_leads():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        lead_cursor = leads_collection.find({}).sort("prediction_time", -1)
        leads = [serialize_mongo_value(lead) for lead in lead_cursor]

        return jsonify({"success": True, "message": "Leads fetched", "data": leads})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/leads/<lead_id>", methods=["GET"])
@admin_required
def get_admin_lead(lead_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        try:
            lead_object_id = ObjectId(lead_id)
        except Exception:
            return jsonify({"success": False, "message": "Lead not found", "errors": []}), 404

        lead = leads_collection.find_one({"_id": lead_object_id})
        if not lead:
            return jsonify({"success": False, "message": "Lead not found", "errors": []}), 404

        return jsonify({
            "success": True,
            "message": "Lead fetched",
            "data": serialize_mongo_value(lead),
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/leads/<lead_id>/status", methods=["PUT"])
@admin_required
def update_admin_lead_status(lead_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(force=True)
    status = data.get("status")

    if status not in LEAD_STATUSES:
        return jsonify({
            "success": False,
            "message": "Invalid lead status",
            "errors": [],
        }), 400

    try:
        try:
            lead_object_id = ObjectId(lead_id)
        except Exception:
            return jsonify({"success": False, "message": "Lead not found", "errors": []}), 404

        result = leads_collection.update_one(
            {"_id": lead_object_id},
            {"$set": {"status": status}},
        )
        if result.matched_count == 0:
            return jsonify({"success": False, "message": "Lead not found", "errors": []}), 404

        return jsonify({
            "success": True,
            "message": "Lead status updated",
            "data": {"lead_id": str(lead_object_id), "status": status},
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/dashboard", methods=["GET"])
@admin_required
def get_admin_dashboard():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        summary_pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_leads": {"$sum": 1},
                    "hot_leads": {"$sum": {"$cond": [{"$eq": ["$segment", "Hot"]}, 1, 0]}},
                    "warm_leads": {"$sum": {"$cond": [{"$eq": ["$segment", "Warm"]}, 1, 0]}},
                    "cold_leads": {"$sum": {"$cond": [{"$eq": ["$segment", "Cold"]}, 1, 0]}},
                    "average_score": {"$avg": "$score"},
                }
            }
        ]
        summary = next(iter(leads_collection.aggregate(summary_pipeline)), {})

        return jsonify({
            "success": True,
            "message": "Dashboard summary fetched",
            "data": {
                "total_leads": summary.get("total_leads", 0),
                "hot_leads": summary.get("hot_leads", 0),
                "warm_leads": summary.get("warm_leads", 0),
                "cold_leads": summary.get("cold_leads", 0),
                "average_score": float(summary.get("average_score") or 0),
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/analytics/overview", methods=["GET"])
@admin_required
def get_analytics_overview():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        total_customers = profiles_collection.count_documents({})
        total_leads = leads_collection.count_documents({})
        active_customers = sessions_collection.count_documents({"status": "active"})
        total_sessions = sessions_collection.count_documents({})
        total_events = events_collection.count_documents({})
        total_profiles = total_customers

        return jsonify({
            "success": True,
            "data": {
                "total_customers": total_customers,
                "total_leads": total_leads,
                "active_customers": active_customers,
                "active_customers_today": active_customers,
                "active_sessions": active_customers,
                "total_sessions": total_sessions,
                "total_events": total_events,
                "total_profiles": total_profiles,
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/analytics/events", methods=["GET"])
@admin_required
def get_analytics_events():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        event_pipeline = [
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        category_pipeline = [
            {"$match": {"entity.category": {"$exists": True, "$ne": None}}},
            {"$group": {"_id": "$entity.category", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]

        return jsonify({
            "success": True,
            "data": {
                "event_counts": [
                    {"event_type": item["_id"], "count": item["count"]}
                    for item in events_collection.aggregate(event_pipeline)
                ],
                "category_counts": [
                    {"category": item["_id"], "count": item["count"]}
                    for item in events_collection.aggregate(category_pipeline)
                ],
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/leads", methods=["GET"])
@admin_required
def get_leads():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        leads = [serialize_mongo_value(lead) for lead in leads_collection.find({}).sort("prediction_time", -1)]
        return jsonify({"success": True, "data": leads})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/sessions", methods=["GET"])
@admin_required
def get_sessions():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        sessions = [serialize_mongo_value(session) for session in sessions_collection.find({}).sort("started_at", -1)]
        return jsonify({"success": True, "data": sessions})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/profiles", methods=["GET"])
@admin_required
def get_profiles():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        profiles = [serialize_profile(profile) for profile in profiles_collection.find({}).sort("updated_at", -1)]
        return jsonify({"success": True, "data": profiles})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/orders", methods=["POST"])
def create_order():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        data = request.get_json(force=True)
        customer_email = data.get("customer_email")
        items = data.get("items") or []

        if not customer_email or not items:
            return jsonify({"success": False, "message": "customer_email and items required", "errors": []}), 400

        customer = profiles_collection.find_one({"email": customer_email})
        total_amount = data.get("total_amount")
        if total_amount is None:
            total_amount = sum((item.get("price", 0) * item.get("quantity", 1)) for item in items)

        now = datetime.datetime.utcnow()
        order_doc = {
            "customer_id": customer.get("_id") if customer else data.get("customer_id"),
            "customer_email": customer_email,
            "items": items,
            "total_amount": total_amount,
            "status": "placed",
            "created_at": now,
        }
        result = orders_collection.insert_one(order_doc)

        session_id = data.get("session_id")
        event_doc = {
            "event_type": "order_placed",
            "event_category": "commerce",
            "event_action": "purchase",
            "visitor_id": customer_email,
            "anonymous_id": customer_email,
            "user_id": customer.get("_id") if customer else None,
            "page": "/orders",
            "timestamp": now,
            "entity": {"type": "order", "id": str(result.inserted_id)},
            "metadata": {"total_amount": total_amount, "item_count": len(items)},
            "context": {},
            "schema_version": 2,
        }

        if session_id:
            try:
                event_doc["session_id"] = ObjectId(session_id)
                sessions_collection.update_one(
                    {"_id": ObjectId(session_id)},
                    {"$set": {"last_active_at": now, "status": "active"}},
                )
            except Exception:
                pass

        event_result = events_collection.insert_one(event_doc)
        if session_id:
            update_profile_from_event(session_id, event_result.inserted_id)

        return jsonify({
            "success": True,
            "data": {
                "order_id": str(result.inserted_id),
                "status": "placed",
            },
        }), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/orders", methods=["GET"])
def get_orders():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        customer_email = request.args.get("customer_email")
        query = {"customer_email": customer_email} if customer_email else {}
        orders = [serialize_mongo_value(order) for order in orders_collection.find(query).sort("created_at", -1)]
        return jsonify({"success": True, "data": orders})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500


@app.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        total_sessions = sessions_collection.count_documents({})
        ended_sessions = sessions_collection.count_documents({"status": "ended"})
        total_events = events_collection.count_documents({})
        total_leads = leads_collection.count_documents({})

        return jsonify({
            "success": True,
            "data": {
                "total_sessions": total_sessions,
                "ended_sessions": ended_sessions,
                "total_events": total_events,
                "total_leads": total_leads
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/analytics/top-events", methods=["GET"])
def analytics_top_events():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        pipeline = [
            {"$group": {"_id": "$event_type", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}}
        ]

        results = list(events_collection.aggregate(pipeline))

        return jsonify({
            "success": True,
            "data": [
                {"event_type": item["_id"], "count": item["count"]}
                for item in results
            ]
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


if __name__ == "__main__":
    initialize_database()
    debug_enabled = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    socketio.run(app, debug=debug_enabled, port=5000, allow_unsafe_werkzeug=True)
