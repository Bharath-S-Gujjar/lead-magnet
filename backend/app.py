from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import pandas as pd
from flask_socketio import SocketIO
import os
import re
import bcrypt
import jwt
import datetime
import time
from dotenv import load_dotenv
from pymongo import MongoClient
from action_recommendations import get_next_action
from auth_middleware import admin_required
from identity_service import generate_anonymous_id, resolve_anonymous_identity
from lead_processing_service import process_session
from behavior_event_service import BehaviorEventError, log_behavior_event
from customer_profile_service import build_profile_update, apply_profile_update, get_customer_profile
from seed_clothing_products import seed_clothing_products_if_empty
from cart_service import get_user_cart, add_to_cart, update_cart_quantity, remove_from_cart, clear_cart
from wishlist_service import get_user_wishlist, add_to_wishlist, remove_from_wishlist, clear_wishlist
from order_service import create_order as create_order_from_cart, get_user_orders, get_order_by_id
from recommendation_service import get_personalized_recommendations
from marketing_service import get_all_campaigns, create_campaign, get_campaign_logs, evaluate_campaign_triggers
import certifi

load_dotenv()

app = Flask(__name__)
FRONTEND_URL = os.getenv("FRONTEND_URL")
CORS(app, origins=FRONTEND_URL or "*")
socketio = SocketIO(app, cors_allowed_origins=FRONTEND_URL or "*")


def create_mongo_client():
    uri = os.getenv("MONGO_URI", "")
    if uri:
        # Attempt 1: Standard MongoClient (PyMongo handles TLS automatically for mongodb+srv://)
        try:
            client = MongoClient(uri, serverSelectionTimeoutMS=5000)
            client.admin.command("ping")
            print("Successfully connected to MongoDB Atlas (Standard).")
            return client, True
        except Exception as e:
            print(f"MongoDB Atlas connection attempt 1 failed: {e}")

        # Attempt 2: Explicit certifi CA bundle
        try:
            client = MongoClient(
                uri,
                tls=True,
                tlsCAFile=certifi.where(),
                serverSelectionTimeoutMS=5000,
            )
            client.admin.command("ping")
            print("Successfully connected to MongoDB Atlas (Certifi).")
            return client, True
        except Exception as e:
            print(f"MongoDB Atlas connection attempt 2 failed: {e}")

        # Attempt 3: tlsAllowInvalidCertificates fallback
        try:
            client = MongoClient(
                uri,
                tls=True,
                tlsAllowInvalidCertificates=True,
                serverSelectionTimeoutMS=5000,
            )
            client.admin.command("ping")
            print("Successfully connected to MongoDB Atlas (tlsAllowInvalidCertificates).")
            return client, True
        except Exception as e:
            print(f"MongoDB Atlas connection attempt 3 failed: {e}")

    # Fallback to local MongoDB
    try:
        client = MongoClient("mongodb://localhost:27017/leadmagnet", serverSelectionTimeoutMS=2000)
        client.admin.command("ping")
        print("Successfully connected to local MongoDB.")
        return client, True
    except Exception as e:
        print(f"Local MongoDB connection failed: {e}")

    fallback_uri = uri if uri else "mongodb://localhost:27017/leadmagnet"
    return MongoClient(fallback_uri, serverSelectionTimeoutMS=2000), False


def ensure_product_indexes(products_collection):
    """Create the minimal indexes used by the existing product queries, safely idempotently."""
    existing = {index["name"] for index in products_collection.list_indexes()}
    for index_name, fields in [
        ("category_1", [("category", 1)]),
        ("name_1", [("name", 1)]),
        ("brand_1", [("brand", 1)]),
        ("gender_1", [("gender", 1)]),
    ]:
        if index_name not in existing:
            products_collection.create_index(fields, name=index_name, background=True)


def bind_collections(client):
    global db, profiles_collection, legacy_users_collection, products_collection, sessions_collection, events_collection, leads_collection, orders_collection, cart_collection, wishlist_collection, campaigns_collection, campaign_logs_collection
    db = client["leadmagnet"]
    profiles_collection = db["user_profiles"]
    legacy_users_collection = db["users"]
    products_collection = db["products"]
    sessions_collection = db["sessions"]
    events_collection = db["events"]
    leads_collection = db["leads"]
    orders_collection = db["orders"]
    cart_collection = db["cart"]
    wishlist_collection = db["wishlist"]
    campaigns_collection = db["campaigns"]
    campaign_logs_collection = db["campaign_logs"]
    ensure_product_indexes(products_collection)


mongo_client, MONGO_AVAILABLE = create_mongo_client()
bind_collections(mongo_client)


def ensure_mongo_connection():
    global mongo_client, MONGO_AVAILABLE
    if MONGO_AVAILABLE:
        try:
            mongo_client.admin.command("ping")
            return True
        except Exception:
            MONGO_AVAILABLE = False

    client, available = create_mongo_client()
    mongo_client = client
    MONGO_AVAILABLE = available
    bind_collections(mongo_client)
    return MONGO_AVAILABLE

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
    "order_count", "total_spent", "last_order_at",
}


def serialize_profile(profile):
    """Serialize a profile document, excluding sensitive fields like password."""
    return serialize_mongo_value({k: v for k, v in profile.items() if k in SAFE_PROFILE_FIELDS})


def resolve_persistence_identity(user_id=None, anonymous_id=None):
    """Resolve a cart or wishlist owner without trusting a spoofed user id."""
    authorization = request.headers.get("Authorization", "")
    token_user_id = None
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return None, (jsonify({"success": False, "message": "Invalid authorization token", "errors": []}), 401)
        try:
            claims = jwt.decode(token, app.config["JWT_SECRET"], algorithms=["HS256"])
            token_user_id = claims.get("sub")
            if not token_user_id:
                return None, (jsonify({"success": False, "message": "Invalid authorization token", "errors": []}), 401)
        except jwt.ExpiredSignatureError:
            return None, (jsonify({"success": False, "message": "Token has expired", "errors": []}), 401)
        except jwt.InvalidTokenError:
            return None, (jsonify({"success": False, "message": "Invalid authorization token", "errors": []}), 401)

    if user_id is not None:
        if not isinstance(user_id, str) or not ObjectId.is_valid(user_id):
            return None, (jsonify({"success": False, "message": "Invalid user_id", "errors": []}), 400)
        if token_user_id and token_user_id != user_id:
            return None, (jsonify({"success": False, "message": "User ownership mismatch", "errors": []}), 403)
        if not token_user_id:
            return None, (jsonify({"success": False, "message": "Authorization token required", "errors": []}), 401)
        return {"user_id": user_id, "anonymous_id": None}, None

    if token_user_id:
        if not ObjectId.is_valid(token_user_id):
            return None, (jsonify({"success": False, "message": "Invalid authenticated user", "errors": []}), 401)
        return {"user_id": token_user_id, "anonymous_id": None}, None

    if anonymous_id is not None:
        if not isinstance(anonymous_id, str) or not anonymous_id.strip():
            return None, (jsonify({"success": False, "message": "Invalid anonymous_id", "errors": []}), 400)
        return {"user_id": None, "anonymous_id": anonymous_id}, None

    return None, (jsonify({"success": False, "message": "user_id or anonymous_id is required", "errors": []}), 400)




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
    if not ensure_mongo_connection():
        print("Warning: MongoDB startup check failed. DB features will attempt auto-reconnect on request.")
        return

    migrate_users_to_profiles_once()
    if os.getenv("AUTO_SEED_PRODUCTS", "false").lower() == "true":
        try:
            seed_clothing_products_if_empty(products_collection)
        except Exception as e:
            print(f"Warning: Automatic product seeding failed: {e}")


@app.before_request
def auto_reconnect_db():
    if not MONGO_AVAILABLE:
        ensure_mongo_connection()


JWT_SECRET = os.getenv("JWT_SECRET")
app.config["JWT_SECRET"] = JWT_SECRET

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin") or "admin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin12345") or "admin12345"

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
    if ensure_mongo_connection():
        return jsonify({"success": True, "mongo": True}), 200
    return jsonify({"success": False, "mongo": False, "error": "MongoDB unavailable"}), 503


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

    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    username = data.get("username")
    anonymous_id = data.get("anonymous_id") if "anonymous_id" in data else data.get("visitor_id")

    if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
        return jsonify({"success": False, "message": "Email and password required", "errors": []}), 400
    if anonymous_id is not None and (not isinstance(anonymous_id, str) or not anonymous_id.strip()):
        return jsonify({"success": False, "message": "Invalid anonymous identity", "errors": []}), 400

    try:
        duplicate_query = [{"email": email}]
        if username:
            duplicate_query.append({"username": username})
        if profiles_collection.find_one({"$or": duplicate_query}):
            return jsonify({"success": False, "message": "User already exists", "errors": []}), 400

        hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        user_doc = {
            "email": email,
            "password": hashed_pw,
            "role": "user",
            "full_name": data.get("fullName") or data.get("full_name"),
            "username": data.get("username"),
            "age": data.get("age"),
            "gender": data.get("gender"),
            "dob": data.get("dob"),
            "phone": data.get("phone"),
            "updated_at": datetime.datetime.utcnow(),
        }

        anon_profile = profiles_collection.find_one({"visitor_id": anonymous_id}) if anonymous_id else None

        if anon_profile and not anon_profile.get("email"):
            profiles_collection.update_one({"_id": anon_profile["_id"]}, {"$set": user_doc})
            user_id = anon_profile["_id"]
        else:
            user_doc["created_at"] = datetime.datetime.utcnow()
            user_result = profiles_collection.insert_one(user_doc)
            user_id = user_result.inserted_id

        resolution = resolve_anonymous_identity(
            anonymous_id,
            user_id,
            profiles_collection,
            sessions_collection,
            events_collection,
            leads_collection,
            cart_collection,
            wishlist_collection,
        )

        return jsonify({
            "success": True,
            "message": "Account created successfully",
            "data": {
                "user_id": str(user_id),
                "identity_resolution": resolution,
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/auth/login", methods=["POST"])
def login():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    data = request.get_json(silent=True) or {}
    email = data.get("email")
    password = data.get("password")
    anonymous_id = data.get("anonymous_id") if "anonymous_id" in data else data.get("visitor_id")

    if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
        return jsonify({"success": False, "message": "Email and password required", "errors": []}), 400
    if anonymous_id is not None and (not isinstance(anonymous_id, str) or not anonymous_id.strip()):
        return jsonify({"success": False, "message": "Invalid anonymous identity", "errors": []}), 400

    try:
        user = profiles_collection.find_one({"email": email})
        if not user or not user.get("password") or not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            return jsonify({"success": False, "message": "Invalid credentials", "errors": []}), 401

        exp_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        expires_at_ts = int(time.time() * 1000) + (3600 * 1000)
        token = jwt.encode(
            {
                "sub": str(user["_id"]),
                "email": email,
                "role": user["role"],
                "exp": exp_time,
            },
            JWT_SECRET,
            algorithm="HS256"
        )

        resolution = resolve_anonymous_identity(
            anonymous_id,
            user["_id"],
            profiles_collection,
            sessions_collection,
            events_collection,
            leads_collection,
            cart_collection,
            wishlist_collection,
        )

        return jsonify({
            "success": True,
            "message": "Login successful",
            "data": {
                "token": token,
                "email": email,
                "role": user["role"],
                "user_id": str(user["_id"]),
                "expires_at": exp_time.isoformat(),
                "expires_at_timestamp": expires_at_ts,
                "full_name": user.get("full_name"),
                "username": user.get("username"),
                "phone": user.get("phone"),
                "gender": user.get("gender"),
                "age": user.get("age"),
                "dob": user.get("dob"),
                "identity_resolution": resolution,
            },
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/auth/admin/login", methods=["POST"])
def admin_login():
    data = request.get_json(silent=True) or {}
    username = data.get("username")
    password = data.get("password")

    if not isinstance(username, str) or not username or not isinstance(password, str) or not password:
        return jsonify({"success": False, "message": "Username and password required", "errors": []}), 400

    if username != ADMIN_USERNAME or password != ADMIN_PASSWORD:
        return jsonify({"success": False, "message": "Invalid admin credentials", "errors": []}), 401

    exp_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
    expires_at_ts = int(time.time() * 1000) + (3600 * 1000)
    token = jwt.encode(
        {
            "username": username,
            "role": "admin",
            "exp": exp_time,
        },
        JWT_SECRET,
        algorithm="HS256"
    )

    return jsonify({
        "success": True,
        "message": "Admin login successful",
        "data": {
            "token": token,
            "role": "admin",
            "expires_at": exp_time.isoformat(),
            "expires_at_timestamp": expires_at_ts,
        }
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
        query = {}
        if category:
            query["category"] = {"$regex": f"^{re.escape(category)}$", "$options": "i"}

        items = list(products_collection.find(query).sort("name", 1))

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
        }), 400


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
        if not ObjectId.is_valid(product_id):
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 404

        item = products_collection.find_one({"_id": ObjectId(product_id)})
        if not item:
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 404

        item["_id"] = str(item["_id"])
        return jsonify({"success": True, "message": "Product fetched", "data": item})
    except Exception:
        # Invalid ObjectId values are not server errors; no product can match them.
        return jsonify({"success": False, "message": "Product not found", "errors": []}), 404


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

    data = request.get_json(silent=True) or {}
    supplied_anonymous_id = data.get("anonymous_id") if "anonymous_id" in data else data.get("visitor_id")
    if supplied_anonymous_id is not None and (not isinstance(supplied_anonymous_id, str) or not supplied_anonymous_id.strip()):
        return jsonify({"success": False, "message": "Invalid anonymous identity", "errors": []}), 400

    anonymous_id = supplied_anonymous_id or generate_anonymous_id()
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


def is_active_session(last_activity):
    """Return True if session activity occurred within the last 15 minutes."""
    if not last_activity:
        return False
    if isinstance(last_activity, str):
        try:
            last_activity = datetime.datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
        except Exception:
            return False
    now = datetime.datetime.now(datetime.timezone.utc) if last_activity.tzinfo else datetime.datetime.utcnow()
    return (now - last_activity).total_seconds() <= 900


@app.route("/api/analytics/overview", methods=["GET"])
@admin_required
def get_analytics_overview():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        total_customers = profiles_collection.count_documents({"$or": [{"email": {"$exists": True, "$ne": None}}, {"role": "user"}]})
        total_leads = leads_collection.count_documents({})
        cutoff_15min = datetime.datetime.utcnow() - datetime.timedelta(minutes=15)
        active_customers = sessions_collection.count_documents({
            "status": "active",
            "last_active_at": {"$gte": cutoff_15min}
        })
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
        all_orders = list(orders_collection.find({}))
        order_stats = {}

        for o in all_orders:
            c_email = (o.get("customer_email") or "").strip().lower()
            c_id = str(o.get("customer_id") or "").strip()
            amt = float(o.get("total_amount") or 0.0)
            created = o.get("created_at")

            for key in [c_email, c_id]:
                if not key:
                    continue
                if key not in order_stats:
                    order_stats[key] = {"order_count": 0, "total_spent": 0.0, "last_order_at": None}
                order_stats[key]["order_count"] += 1
                order_stats[key]["total_spent"] += amt
                if created and (not order_stats[key]["last_order_at"] or created > order_stats[key]["last_order_at"]):
                    order_stats[key]["last_order_at"] = created

        profiles_docs = list(profiles_collection.find({}).sort("updated_at", -1))
        serialized = []
        for profile in profiles_docs:
            p_email = (profile.get("email") or "").strip().lower()
            p_id = str(profile.get("_id") or "").strip()

            stats = order_stats.get(p_email) or order_stats.get(p_id) or {}
            profile["order_count"] = stats.get("order_count", 0)
            profile["total_spent"] = float(stats.get("total_spent", 0.0))
            profile["last_order_at"] = stats.get("last_order_at")
            
            # Ensure gender is properly returned if stored
            if not profile.get("gender") or profile.get("gender") == "Unknown":
                # Check if gender exists in signup or session
                if profile.get("email"):
                    sess = sessions_collection.find_one({"visitor_id": profile["email"]})
                    if sess and sess.get("gender"):
                        profile["gender"] = sess["gender"]

            serialized.append(serialize_profile(profile))

        return jsonify({"success": True, "data": serialized})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/notifications", methods=["GET"])
@admin_required
def get_admin_notifications():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        notifications = []
        
        reg_count = profiles_collection.count_documents({"email": {"$exists": True, "$ne": None}})
        if reg_count > 0:
            latest_user = profiles_collection.find_one({"email": {"$exists": True, "$ne": None}}, sort=[("created_at", -1)])
            user_name = latest_user.get("full_name") or latest_user.get("email") if latest_user else "User"
            notifications.append({
                "id": "notif-reg",
                "type": "user",
                "text": f"We got {reg_count} registered clothing customer{'s' if reg_count != 1 else ''}! Latest: {user_name}",
                "time": "Just now",
                "unread": True
            })
            
        order_count = orders_collection.count_documents({})
        if order_count > 0:
            latest_order = orders_collection.find_one({}, sort=[("created_at", -1)])
            amt = float(latest_order.get("total_amount", 0.0))
            email = latest_order.get("customer_email", "Customer")
            notifications.append({
                "id": "notif-order",
                "type": "order",
                "text": f"New Order Placed: ₹{int(amt):,} order by {email}",
                "time": "Recent",
                "unread": True
            })
            
        lead_count = leads_collection.count_documents({})
        if lead_count > 0:
            notifications.append({
                "id": "notif-leads",
                "type": "mail",
                "text": f"Automated sales campaign: {lead_count} marketing emails dispatched to active prospects",
                "time": "15m ago",
                "unread": True
            })
            
        session_count = sessions_collection.count_documents({})
        if session_count > 0:
            notifications.append({
                "id": "notif-sms",
                "type": "sms",
                "text": f"SMS campaign: 'MAGNET20' discount coupon sent to {max(1, session_count)} shoppers",
                "time": "30m ago",
                "unread": False
            })

        return jsonify({"success": True, "data": notifications})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500


# --- Cart APIs (V2.2) ---

@app.route("/api/cart", methods=["GET"])
def get_cart_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    user_id = request.args.get("user_id")
    anonymous_id = request.args.get("anonymous_id")
    owner, error = resolve_persistence_identity(user_id, anonymous_id)
    if error:
        return error
    try:
        items = get_user_cart(cart_collection, products_collection, **owner)
        return jsonify({"success": True, "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 400


@app.route("/api/cart", methods=["POST"])
def add_to_cart_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    owner, error = resolve_persistence_identity(data.get("user_id"), data.get("anonymous_id"))
    if error:
        return error
    session_id = data.get("session_id")

    if not product_id:
        return jsonify({"success": False, "message": "product_id is required"}), 400

    try:
        if not ObjectId.is_valid(product_id):
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 400
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "quantity must be a positive integer"}), 400
    if quantity <= 0:
        return jsonify({"success": False, "message": "quantity must be a positive integer"}), 400

    try:
        items = add_to_cart(cart_collection, products_collection, product_id, quantity, **owner)
        if session_id:
            try:
                log_behavior_event(
                    events_collection=events_collection,
                    sessions_collection=sessions_collection,
                    session_id=session_id,
                    event_type="add_to_cart",
                    entity={"type": "product", "id": product_id},
                    metadata={"quantity": quantity},
                    **owner
                )
            except Exception:
                pass

        return jsonify({"success": True, "message": "Added to cart", "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/cart/<product_id>", methods=["PUT"])
def update_cart_route(product_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(silent=True) or {}
    owner, error = resolve_persistence_identity(data.get("user_id"), data.get("anonymous_id"))
    if error:
        return error

    try:
        if not ObjectId.is_valid(product_id):
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 400
        if not products_collection.find_one({"_id": ObjectId(product_id)}, {"_id": 1}):
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 400
        quantity = int(data.get("quantity", 1))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "quantity must be an integer"}), 400

    try:
        items = update_cart_quantity(cart_collection, products_collection, product_id, quantity, **owner)
        return jsonify({"success": True, "message": "Cart updated", "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/cart/<product_id>", methods=["DELETE"])
def remove_from_cart_route(product_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    user_id = request.args.get("user_id")
    anonymous_id = request.args.get("anonymous_id")
    session_id = request.args.get("session_id")
    owner, error = resolve_persistence_identity(user_id, anonymous_id)
    if error:
        return error

    try:
        if not ObjectId.is_valid(product_id):
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 400
        items = remove_from_cart(cart_collection, products_collection, product_id, **owner)
        if session_id:
            try:
                log_behavior_event(
                    events_collection=events_collection,
                    sessions_collection=sessions_collection,
                    session_id=session_id,
                    event_type="remove_from_cart",
                    entity={"type": "product", "id": product_id},
                    **owner
                )
            except Exception:
                pass

        return jsonify({"success": True, "message": "Item removed from cart", "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/cart", methods=["DELETE"])
def clear_cart_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    user_id = request.args.get("user_id")
    anonymous_id = request.args.get("anonymous_id")
    owner, error = resolve_persistence_identity(user_id, anonymous_id)
    if error:
        return error

    try:
        clear_cart(cart_collection, **owner)
        return jsonify({"success": True, "message": "Cart cleared", "data": []})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# --- Wishlist APIs (V2.2) ---

@app.route("/api/wishlist", methods=["GET"])
def get_wishlist_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    user_id = request.args.get("user_id")
    anonymous_id = request.args.get("anonymous_id")
    owner, error = resolve_persistence_identity(user_id, anonymous_id)
    if error:
        return error

    try:
        items = get_user_wishlist(wishlist_collection, products_collection, **owner)
        return jsonify({"success": True, "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 400


@app.route("/api/wishlist", methods=["POST"])
def add_to_wishlist_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    owner, error = resolve_persistence_identity(data.get("user_id"), data.get("anonymous_id"))
    if error:
        return error
    session_id = data.get("session_id")

    if not product_id:
        return jsonify({"success": False, "message": "product_id is required"}), 400

    try:
        if not ObjectId.is_valid(product_id):
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 400
        items = add_to_wishlist(wishlist_collection, products_collection, product_id, **owner)
        if session_id:
            try:
                log_behavior_event(
                    events_collection=events_collection,
                    sessions_collection=sessions_collection,
                    session_id=session_id,
                    event_type="wishlist_add",
                    entity={"type": "product", "id": product_id},
                    **owner
                )
            except Exception:
                pass

        return jsonify({"success": True, "message": "Added to wishlist", "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/wishlist/<product_id>", methods=["DELETE"])
def remove_from_wishlist_route(product_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    user_id = request.args.get("user_id")
    anonymous_id = request.args.get("anonymous_id")
    session_id = request.args.get("session_id")
    owner, error = resolve_persistence_identity(user_id, anonymous_id)
    if error:
        return error

    try:
        if not ObjectId.is_valid(product_id):
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 400
        items = remove_from_wishlist(wishlist_collection, products_collection, product_id, **owner)
        if session_id:
            try:
                log_behavior_event(
                    events_collection=events_collection,
                    sessions_collection=sessions_collection,
                    session_id=session_id,
                    event_type="wishlist_remove",
                    entity={"type": "product", "id": product_id},
                    **owner
                )
            except Exception:
                pass

        return jsonify({"success": True, "message": "Removed from wishlist", "data": items})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/wishlist", methods=["DELETE"])
def clear_wishlist_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    user_id = request.args.get("user_id")
    anonymous_id = request.args.get("anonymous_id")
    owner, error = resolve_persistence_identity(user_id, anonymous_id)
    if error:
        return error

    try:
        clear_wishlist(wishlist_collection, **owner)
        return jsonify({"success": True, "message": "Wishlist cleared", "data": []})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# --- Customer Profile API (V2.4) ---

@app.route("/api/profile", methods=["GET"])
def get_profile_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": None}), 500

    user_id = request.args.get("user_id")
    visitor_id = request.args.get("visitor_id") or request.args.get("anonymous_id")

    try:
        profile = get_customer_profile(profiles_collection, user_id=user_id, visitor_id=visitor_id)
        if not profile:
            return jsonify({"success": True, "data": None, "message": "Profile not found"}), 200

        return jsonify({"success": True, "data": serialize_mongo_value(profile)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


# --- Recommendation API (V2.5) ---

@app.route("/api/recommendations", methods=["GET"])
def get_recommendations_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    user_id = request.args.get("user_id")
    visitor_id = request.args.get("visitor_id") or request.args.get("anonymous_id")
    limit = int(request.args.get("limit", 8))

    try:
        recs = get_personalized_recommendations(
            products_collection=products_collection,
            profiles_collection=profiles_collection,
            cart_collection=cart_collection,
            wishlist_collection=wishlist_collection,
            user_id=user_id,
            visitor_id=visitor_id,
            limit=limit
        )
        serialized = [serialize_mongo_value(prod) for prod in recs]
        return jsonify({"success": True, "data": serialized})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 400


# --- Marketing Automation APIs (V2.7) ---

@app.route("/api/campaigns", methods=["GET"])
def get_campaigns_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        camps = get_all_campaigns(campaigns_collection)
        return jsonify({"success": True, "data": [serialize_mongo_value(c) for c in camps]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500


@app.route("/api/campaigns", methods=["POST"])
@admin_required
def create_campaign_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    data = request.get_json(force=True) or {}
    name = data.get("name")
    trigger_type = data.get("trigger_type")
    channel = data.get("channel", "email")
    template = data.get("template", "")

    if not name or not trigger_type:
        return jsonify({"success": False, "message": "name and trigger_type required"}), 400

    try:
        camp = create_campaign(campaigns_collection, name, trigger_type, channel, template)
        return jsonify({"success": True, "message": "Campaign created", "data": serialize_mongo_value(camp)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 400


@app.route("/api/campaigns/logs", methods=["GET"])
@admin_required
def get_campaign_logs_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        logs = get_campaign_logs(campaign_logs_collection)
        return jsonify({"success": True, "data": [serialize_mongo_value(l) for l in logs]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500


@app.route("/api/campaigns/evaluate", methods=["POST"])
@admin_required
def evaluate_campaigns_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        triggered = evaluate_campaign_triggers(
            campaigns_collection=campaigns_collection,
            campaign_logs_collection=campaign_logs_collection,
            cart_collection=cart_collection,
            leads_collection=leads_collection,
            profiles_collection=profiles_collection
        )
        return jsonify({"success": True, "message": f"Evaluated triggers, {len(triggered)} campaigns triggered", "data": [serialize_mongo_value(t) for t in triggered]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/orders", methods=["POST"])
def create_order():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        data = request.get_json(silent=True) or {}
        customer_id = data.get("customer_id") if "customer_id" in data else data.get("user_id")
        if not request.headers.get("Authorization"):
            return jsonify({"success": False, "message": "Authorization token required", "errors": []}), 401
        owner, error = resolve_persistence_identity(customer_id, None)
        if error:
            return error

        customer = profiles_collection.find_one({"_id": ObjectId(owner["user_id"])})
        if not customer:
            return jsonify({"success": False, "message": "User not found", "errors": []}), 404

        order_doc = create_order_from_cart(
            orders_collection=orders_collection,
            cart_collection=cart_collection,
            products_collection=products_collection,
            user_id=owner["user_id"],
            customer_email=customer.get("email"),
            customer_name=customer.get("full_name") or customer.get("username"),
            shipping_address=data.get("shipping_address"),
            payment_method=data.get("payment_method", "Credit Card"),
        )
        now = order_doc["created_at"]

        session_id = data.get("session_id")
        event_doc = {
            "event_type": "order_placed",
            "event_category": "commerce",
            "event_action": "purchase",
            "visitor_id": customer.get("email"),
            "anonymous_id": None,
            "user_id": customer.get("_id"),
            "page": "/orders",
            "timestamp": now,
            "entity": {"type": "order", "id": str(order_doc["_id"])},
            "metadata": {"total_amount": order_doc["total_amount"], "item_count": len(order_doc["items"])},
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
                "order_id": str(order_doc["_id"]),
                "status": "placed",
            },
        }), 201
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "errors": []}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/orders", methods=["GET"])
def get_orders():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        if not request.headers.get("Authorization"):
            return jsonify({"success": False, "message": "Authorization token required", "errors": []}), 401
        owner, error = resolve_persistence_identity(request.args.get("user_id"), None)
        if error:
            return error
        orders = [serialize_mongo_value(order) for order in get_user_orders(orders_collection, user_id=owner["user_id"])]
        return jsonify({"success": True, "data": orders})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500


@app.route("/api/orders/<order_id>", methods=["GET"])
def get_order_detail(order_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        if not request.headers.get("Authorization"):
            return jsonify({"success": False, "message": "Authorization token required", "errors": []}), 401
        owner, error = resolve_persistence_identity(request.args.get("user_id"), None)
        if error:
            return error
        if not ObjectId.is_valid(order_id):
            return jsonify({"success": False, "message": "Order not found", "errors": []}), 404
        order = get_order_by_id(orders_collection, order_id)
        if not order or order.get("user_id") != ObjectId(owner["user_id"]):
            return jsonify({"success": False, "message": "Order not found", "errors": []}), 404
        return jsonify({"success": True, "data": serialize_mongo_value(order)})
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "Order not found", "errors": []}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


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
