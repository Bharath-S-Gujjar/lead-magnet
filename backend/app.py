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

load_dotenv()


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
mongo_client = MongoClient(os.getenv("MONGO_URI"))
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
    session_id = data.get("session_id")
    event_type = data.get("event_type")

    if not session_id or not event_type:
        return jsonify({"success": False, "message": "session_id and event_type required", "errors": []}), 400

    session = sessions_collection.find_one({"_id": ObjectId(session_id)})
    if not session:
        return jsonify({"success": False, "message": "Session not found", "errors": []}), 404

    event_doc = {
        "session_id": ObjectId(session_id),
        "event_type": event_type,
        "page": data.get("page"),
        "timestamp": datetime.datetime.utcnow(),
        "metadata": data.get("metadata", {})
    }
    events_collection.insert_one(event_doc)

    update_fields = {"last_active_at": datetime.datetime.utcnow()}
    inc_fields = {}
    if event_type == "page_view":
        inc_fields["page_views"] = 1

    sessions_collection.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": update_fields, **({"$inc": inc_fields} if inc_fields else {})}
    )

    return jsonify({"success": True, "message": "Event logged", "data": {}})


@app.route("/api/session/end", methods=["POST"])
def end_session():
    data = request.get_json(force=True)
    session_id = data.get("session_id")

    if not session_id:
        return jsonify({"success": False, "message": "session_id required", "errors": []}), 400

    try:
        session_object_id = ObjectId(session_id)
    except Exception:
        return jsonify({"success": False, "message": "Session not found", "errors": []}), 404

    session = sessions_collection.find_one({"_id": session_object_id})
    if not session:
        return jsonify({"success": False, "message": "Session not found", "errors": []}), 404

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

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)


    
