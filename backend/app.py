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
import certifi

load_dotenv()

print("DEBUG MONGO_URI =", os.getenv("MONGO_URI"))
app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
# mongo_client = MongoClient(os.getenv("MONGO_URI"))
mongo_client = MongoClient(
    os.getenv("MONGO_URI"),
    tls=True,
    tlsCAFile=certifi.where(),
    serverSelectionTimeoutMS=5000,
)
db = mongo_client["leadmagnet"]
users_collection = db["users"]

JWT_SECRET = os.getenv("JWT_SECRET")
app.config["JWT_SECRET"] = JWT_SECRET

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")

# Load everything saved from the notebook
model = joblib.load("../model/xgb_model.pkl")
scaler = joblib.load("../model/scaler.pkl")
feature_columns = joblib.load("../model/feature_columns.pkl")
kmeans = joblib.load("../model/kmeans_model.pkl")
segment_map = joblib.load("../model/segment_map.pkl")

@app.route("/")
def home():
    return jsonify({"status": "Lead Magnet API is running"})

@app.route("/predict", methods=["POST"])
def predict():
    data = request.get_json()

    # Wrap the incoming lead as a single-row DataFrame
    lead_df = pd.DataFrame([data])

    # One-hot encode the same way training data was encoded
    lead_encoded = pd.get_dummies(lead_df)

    # Align columns to match training exactly (missing cols = 0, extra cols dropped)
    lead_encoded = lead_encoded.reindex(columns=feature_columns, fill_value=0)

    # Scale
    lead_scaled = scaler.transform(lead_encoded)

    # Predict conversion probability
    prob = model.predict_proba(lead_scaled)[0][1]

    # Predict segment
    segment_id = kmeans.predict(lead_scaled)[0]
    segment = segment_map[segment_id]

    return jsonify({
        "score": round(float(prob), 2),
        "segment": segment,
        "reason": f"Scored based on submitted lead behavior"
    })

@app.route("/api/auth/signup", methods=["POST"])
def signup():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({"success": False, "message": "Email and password required", "errors": []}), 400

    if users_collection.find_one({"email": email}):
        return jsonify({"success": False, "message": "User already exists", "errors": []}), 400

    hashed_pw = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())

    user_result = users_collection.insert_one({
        "email": email,
        "password": hashed_pw,
        "role": "user"
    })

    anonymous_id = data.get("anonymous_id") or data.get("visitor_id")
    resolution = resolve_anonymous_identity(
        anonymous_id,
        user_result.inserted_id,
        users_collection,
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


@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data.get("email")
    password = data.get("password")

    user = users_collection.find_one({"email": email})
    if not user or not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
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
        users_collection,
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

products_collection = db["products"]

sessions_collection = db["sessions"]
events_collection = db["events"]

leads_collection = db["leads"]
profiles_collection = db["user_profiles"]

from bson import ObjectId

LEAD_STATUSES = {"New", "Contacted", "Qualified", "Converted", "Lost"}


def serialize_mongo_value(value):
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, dict):
        return {key: serialize_mongo_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_mongo_value(item) for item in value]
    return value

@app.route("/api/products", methods=["GET"])
def get_products():
    category = request.args.get("category")
    query = {"category": category} if category else {}

    items = list(products_collection.find(query))
    for item in items:
        item["_id"] = str(item["_id"])

    return jsonify({"success": True, "message": "Products fetched", "data": items})


@app.route("/api/products/<product_id>", methods=["GET"])
def get_product(product_id):
    item = products_collection.find_one({"_id": ObjectId(product_id)})
    if not item:
        return jsonify({"success": False, "message": "Product not found", "errors": []}), 404

    item["_id"] = str(item["_id"])
    return jsonify({"success": True, "message": "Product fetched", "data": item})

# ---- Session Tracking (Module 3) ----

@app.route("/api/session/start", methods=["POST"])
def start_session():
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
    data = request.get_json(force=True)
    try:
        event_id = log_behavior_event(data, sessions_collection, events_collection)
    except BehaviorEventError as error:
        return jsonify({"success": False, "message": error.message, "errors": []}), error.status_code

    return jsonify({"success": True, "message": "Event logged", "data": {"event_id": event_id}})


@app.route("/api/session/end", methods=["POST"])
def end_session():
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

        print("DEBUG 1: ending session", session_id)

        session = sessions_collection.find_one({"_id": session_object_id})

        print("DEBUG 2: session fetched", session)

        if not session:
            return jsonify({
                "success": False,
                "message": "Session not found",
                "errors": []
            }), 404

        now = datetime.datetime.utcnow()
        total_time_seconds = (now - session["started_at"]).total_seconds()

        print("DEBUG 3: total time", total_time_seconds)

        sessions_collection.update_one(
            {"_id": session_object_id},
            {"$set": {"status": "ended", "total_time_seconds": total_time_seconds}}
        )

        print("DEBUG 4: session updated")

        lead = process_session(
            session_object_id,
            sessions_collection,
            events_collection,
            leads_collection,
        )

        print("DEBUG 5: lead processed", lead)

        session_doc = sessions_collection.find_one({"_id": session_object_id})

        print("DEBUG 6: session doc reloaded")

        events = list(events_collection.find({"session_id": session_object_id}))

        print("DEBUG 7: events loaded", len(events))

        profile_update = build_profile_update(session_doc, events)

        print("DEBUG 8: profile built")

        apply_profile_update(profiles_collection, profile_update)

        print("DEBUG 9: profile applied")

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
        print("DEBUG ERROR:", repr(e))
        return jsonify({
            "success": False,
            "message": str(e),
            "errors": []
        }), 500


# ---- Admin Dashboard (Module 6) ----

@app.route("/api/admin/leads", methods=["GET"])
@admin_required
def get_admin_leads():
    lead_cursor = leads_collection.find({}).sort("prediction_time", -1)
    leads = [serialize_mongo_value(lead) for lead in lead_cursor]

    return jsonify({"success": True, "message": "Leads fetched", "data": leads})


@app.route("/api/admin/leads/<lead_id>", methods=["GET"])
@admin_required
def get_admin_lead(lead_id):
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


@app.route("/api/admin/leads/<lead_id>/status", methods=["PUT"])
@admin_required
def update_admin_lead_status(lead_id):
    data = request.get_json(force=True)
    status = data.get("status")

    if status not in LEAD_STATUSES:
        return jsonify({
            "success": False,
            "message": "Invalid lead status",
            "errors": [],
        }), 400

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


@app.route("/api/admin/dashboard", methods=["GET"])
@admin_required
def get_admin_dashboard():
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

@app.route("/api/analytics/summary", methods=["GET"])
def analytics_summary():
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


@app.route("/api/analytics/top-events", methods=["GET"])
def analytics_top_events():
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

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)


    
