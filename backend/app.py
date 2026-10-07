from flask import Flask, request, jsonify, g
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
import math
from dotenv import load_dotenv
from pymongo import MongoClient

# Explicitly load backend/.env if present, with fallback to default load_dotenv
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path=dotenv_path, override=True)
else:
    load_dotenv()
from action_recommendations import get_next_action
from auth_middleware import token_required, admin_required
from ecommerce_model_adapter import predict_customer_features
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
from customer_feature_service import ensure_customer_features_indexes, aggregate_customer_features, upsert_customer_features, get_customer_features
from customer_lead_state_service import ensure_customer_lead_state_indexes, get_customer_lead_state, sync_customer_lead_state
from marketing_automation_service import (
    ensure_marketing_automation_indexes,
    create_automation_event_for_qualification,
    process_marketing_automation_event,
    trigger_registration_communication,
    trigger_order_confirmation_communication,
    trigger_cart_abandonment_communication,
    trigger_wishlist_reminder_communication,
)
from admin_intelligence_service import (
    get_intelligence_overview,
    get_qualified_leads_list,
    get_customer_intelligence_detail,
    get_lead_distribution,
    get_recent_leads,
    get_marketing_activity,
    get_admin_notifications_list,
    create_admin_notification,
    mark_notification_read,
    mark_all_notifications_read,
)
from lead_scoring_engine import rescore_customer
from score_history_service import ensure_score_history_indexes, get_score_history
from model_explainability_service import explain_lead_score
from rfm_service import compute_rfm, get_rfm_distribution
from funnel_analytics_service import get_funnel_analytics
from retention_service import compute_retention_signals, get_retention_overview
from product_affinity_service import compute_product_affinity
from whatif_simulator_service import simulate_lead_score
from revenue_attribution_service import compute_lead_revenue_attribution
import certifi

# Environment loaded

app = Flask(__name__)

DEFAULT_ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:3001",
    "http://127.0.0.1:3001",
]

IS_PROD_ENV = os.getenv("FLASK_ENV", "").lower() == "production" or os.getenv("ENV", "").lower() == "production"
FRONTEND_URL = os.getenv("FRONTEND_URL")
if FRONTEND_URL:
    ALLOWED_ORIGINS = [origin.strip() for origin in FRONTEND_URL.split(",") if origin.strip()]
    if not IS_PROD_ENV:
        for default_origin in DEFAULT_ALLOWED_ORIGINS:
            if default_origin not in ALLOWED_ORIGINS:
                ALLOWED_ORIGINS.append(default_origin)
else:
    ALLOWED_ORIGINS = [] if IS_PROD_ENV else DEFAULT_ALLOWED_ORIGINS

cors_origins = ALLOWED_ORIGINS if (ALLOWED_ORIGINS or IS_PROD_ENV) else DEFAULT_ALLOWED_ORIGINS
CORS(app, origins=cors_origins)
socketio = SocketIO(app, cors_allowed_origins=cors_origins)


@app.after_request
def add_security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    return response


@app.errorhandler(404)
def handle_404(e):
    return jsonify({"success": False, "message": "Resource not found", "errors": []}), 404


@app.errorhandler(405)
def handle_405(e):
    return jsonify({"success": False, "message": "Method not allowed", "errors": []}), 405


@app.errorhandler(500)
def handle_500(e):
    return jsonify({"success": False, "message": "Internal server error", "errors": []}), 500


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
    try:
        existing = {index["name"] for index in products_collection.list_indexes()}
        for index_name, fields, unique in [
            ("category_1", [("category", 1)], False),
            ("name_1", [("name", 1)], False),
            ("brand_1", [("brand", 1)], False),
            ("gender_1", [("gender", 1)], False),
            ("price_1", [("price", 1)], False),
            ("product_id_1", [("product_id", 1)], True),
        ]:
            if index_name not in existing:
                try:
                    kwargs = {"background": True}
                    if unique:
                        kwargs["unique"] = True
                        kwargs["sparse"] = True
                    products_collection.create_index(fields, name=index_name, **kwargs)
                except Exception:
                    pass
    except Exception:
        pass


def bind_collections(client):
    global db, profiles_collection, legacy_users_collection, products_collection, sessions_collection, events_collection, leads_collection, orders_collection, cart_collection, wishlist_collection, campaigns_collection, campaign_logs_collection, customer_features_collection, customer_lead_state_collection, marketing_automation_events_collection, marketing_communications_collection, admin_notifications_collection, lead_score_history_collection
    db_name = os.getenv("MONGO_DB_NAME", "leadmagnet")
    db = client[db_name]
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
    customer_features_collection = db["customer_features"]
    customer_lead_state_collection = db["customer_lead_state"]
    marketing_automation_events_collection = db["marketing_automation_events"]
    marketing_communications_collection = db["marketing_communications"]
    admin_notifications_collection = db["admin_notifications"]
    lead_score_history_collection = db["lead_score_history"]
    ensure_product_indexes(products_collection)
    ensure_customer_features_indexes(customer_features_collection)
    ensure_customer_lead_state_indexes(customer_lead_state_collection)
    ensure_marketing_automation_indexes(db)
    ensure_score_history_indexes(db)


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


JWT_SECRET = os.getenv("JWT_SECRET") or "default_jwt_secret_key_for_lead_magnet"
app.config["JWT_SECRET"] = JWT_SECRET

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin") or "admin"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin12345") or "admin12345"

IS_PRODUCTION = os.getenv("FLASK_ENV", "").lower() == "production" or os.getenv("ENV", "").lower() == "production"
if IS_PRODUCTION:
    if not os.getenv("JWT_SECRET") or JWT_SECRET == "default_jwt_secret_key_for_lead_magnet":
        raise ValueError("Insecure JWT_SECRET detected in production environment. A secure JWT_SECRET environment variable is required.")
    if not os.getenv("ADMIN_PASSWORD") or ADMIN_PASSWORD == "admin12345":
        raise ValueError("Insecure ADMIN_PASSWORD detected in production environment. A secure ADMIN_PASSWORD environment variable is required.")

AUTH_RATE_LIMIT_ATTEMPTS = {}


def is_rate_limited(ip_address, max_requests=10, window_seconds=60):
    """Simple in-memory rate limiter for sensitive authentication endpoints."""
    if app.config.get("TESTING") or app.testing:
        return False
    now = time.time()
    timestamps = [ts for ts in AUTH_RATE_LIMIT_ATTEMPTS.get(ip_address, []) if now - ts < window_seconds]
    AUTH_RATE_LIMIT_ATTEMPTS[ip_address] = timestamps
    if len(timestamps) >= max_requests:
        return True
    AUTH_RATE_LIMIT_ATTEMPTS[ip_address].append(now)
    return False


def parse_pagination_params(default_page=1, default_limit=25, max_limit=100):
    """Safely parse page and limit query parameters."""
    try:
        page = int(request.args.get("page", default_page))
        if page < 1:
            page = default_page
    except (ValueError, TypeError):
        page = default_page

    try:
        limit = int(request.args.get("limit", default_limit))
        if limit < 1:
            limit = default_limit
        elif limit > max_limit:
            limit = max_limit
    except (ValueError, TypeError):
        limit = default_limit

    return page, limit

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
    ip_addr = request.remote_addr or "127.0.0.1"
    if is_rate_limited(f"signup:{ip_addr}", max_requests=10, window_seconds=60):
        return jsonify({"success": False, "message": "Too many requests. Please try again later.", "errors": []}), 429

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
            customer_features_collection,
            db,
        )

        try:
            name_display = full_name or email
            create_admin_notification(
                db,
                notif_type="new_customer",
                title="New Customer",
                message=f"Customer registered: {name_display}",
                customer_id=str(user_id),
                metadata={"email": email, "full_name": full_name},
                socketio=socketio
            )
        except Exception:
            pass

        try:
            if not app.config.get("TESTING"):
                trigger_registration_communication(str(user_id), db)
        except Exception:
            pass

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
    ip_addr = request.remote_addr or "127.0.0.1"
    if is_rate_limited(f"login:{ip_addr}", max_requests=10, window_seconds=60):
        return jsonify({"success": False, "message": "Too many requests. Please try again later.", "errors": []}), 429

    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    data = request.get_json(silent=True) or {}
    email = data.get("email") or data.get("identifier") or data.get("username")
    password = data.get("password")
    anonymous_id = data.get("anonymous_id") if "anonymous_id" in data else data.get("visitor_id")

    if not isinstance(email, str) or not email.strip() or not isinstance(password, str) or not password:
        return jsonify({"success": False, "message": "Email and password required", "errors": []}), 400
    if anonymous_id is not None and (not isinstance(anonymous_id, str) or not anonymous_id.strip()):
        return jsonify({"success": False, "message": "Invalid anonymous identity", "errors": []}), 400

    try:
        user = profiles_collection.find_one({"$or": [{"email": email.strip()}, {"username": email.strip()}, {"phone": email.strip()}]})
        if not user or not user.get("password") or not bcrypt.checkpw(password.encode("utf-8"), user["password"]):
            return jsonify({"success": False, "message": "Invalid credentials", "errors": []}), 401

        user_email = user.get("email") or email
        exp_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)
        expires_at_ts = int(time.time() * 1000) + (3600 * 1000)
        token = jwt.encode(
            {
                "sub": str(user["_id"]),
                "email": user_email,
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
            customer_features_collection,
            db,
        )

        return jsonify({
            "success": True,
            "message": "Login successful",
            "data": {
                "token": token,
                "email": user_email,
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
    ip_addr = request.remote_addr or "127.0.0.1"
    if is_rate_limited(f"admin_login:{ip_addr}", max_requests=10, window_seconds=60):
        return jsonify({"success": False, "message": "Too many requests. Please try again later.", "errors": []}), 429

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
    # Also emit as customer_activity so the Live Feed shows browsing signals
    try:
        socketio.emit("customer_activity", {
            "customer_id": result.get("visitor_id", ""),
            "event": "lead_scored",
            "segment": result.get("segment", ""),
            "score": result.get("score", 0),
            "timestamp": datetime.datetime.utcnow().isoformat(),
        })
    except Exception:
        pass

    return jsonify(result)


@app.route("/api/products", methods=["GET"])
def get_products():
    if not MONGO_AVAILABLE:
        return jsonify({
            "success": False,
            "message": "Database unavailable",
            "data": [],
            "pagination": {"page": 1, "limit": 24, "total": 0, "pages": 0}
        }), 500

    try:
        page_arg = request.args.get("page", 1)
        limit_arg = request.args.get("limit", 24)
        category = request.args.get("category")
        gender = request.args.get("gender")
        brand = request.args.get("brand")
        search = request.args.get("search")
        min_rating = request.args.get("min_rating")
        max_price = request.args.get("max_price")

        try:
            page = max(1, int(page_arg))
        except (ValueError, TypeError):
            page = 1

        try:
            limit = max(1, min(int(limit_arg), 100))
        except (ValueError, TypeError):
            limit = 24

        query = {}
        if category and category.lower() != "all":
            # Match exact or prefix (e.g. "Kurtas" -> "Kurtas & Kurta Sets")
            query["category"] = {"$regex": f"^{re.escape(category)}(?:\\s*&.*)?$", "$options": "i"}
        if gender and gender.lower() != "all":
            query["gender"] = {"$regex": f"^{re.escape(gender)}$", "$options": "i"}
        if brand and brand.lower() != "all":
            query["brand"] = {"$regex": f"^{re.escape(brand)}$", "$options": "i"}
        if min_rating:
            try:
                min_r = float(min_rating)
                if min_r > 0:
                    query["rating"] = {"$gte": min_r}
            except (ValueError, TypeError):
                pass
        if max_price:
            try:
                max_p = float(max_price)
                if max_p > 0:
                    query["price"] = {"$lte": max_p}
            except (ValueError, TypeError):
                pass
        if search and search.strip():
            s = search.strip()
            query["$or"] = [
                {"name": {"$regex": re.escape(s), "$options": "i"}},
                {"brand": {"$regex": re.escape(s), "$options": "i"}},
                {"category": {"$regex": re.escape(s), "$options": "i"}},
            ]

        total = products_collection.count_documents(query)
        pages = math.ceil(total / limit) if total > 0 else 1
        skip = (page - 1) * limit

        if total == 0:
            return jsonify({
                "success": True,
                "data": [],
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": 0,
                    "pages": 0
                }
            })

        cursor = products_collection.find(query).sort("_id", 1).skip(skip).limit(limit)
        items = list(cursor)

        for item in items:
            item["_id"] = str(item["_id"])
            if "id" not in item:
                item["id"] = item["_id"]

        return jsonify({
            "success": True,
            "data": items,
            "pagination": {
                "page": page,
                "limit": limit,
                "total": total,
                "pages": pages
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": str(e),
            "data": [],
            "pagination": {"page": 1, "limit": 24, "total": 0, "pages": 0}
        }), 400


@app.route("/api/products/meta", methods=["GET"])
def get_products_meta():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    try:
        categories = sorted([c for c in products_collection.distinct("category") if c])
        genders = sorted([g for g in products_collection.distinct("gender") if g])
        top_brands_pipeline = [
            {"$group": {"_id": "$brand", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
            {"$limit": 30}
        ]
        top_brands = [b["_id"] for b in products_collection.aggregate(top_brands_pipeline) if b.get("_id")]

        return jsonify({
            "success": True,
            "data": {
                "categories": categories,
                "genders": genders,
                "brands": top_brands,
                "total": products_collection.count_documents({})
            }
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


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
        item = None
        if ObjectId.is_valid(product_id):
            item = products_collection.find_one({"_id": ObjectId(product_id)})
        if not item:
            item = products_collection.find_one({"product_id": str(product_id)})
        if not item:
            return jsonify({"success": False, "message": "Product not found", "errors": []}), 404

        item["_id"] = str(item["_id"])
        if "id" not in item:
            item["id"] = item["_id"]
        return jsonify({"success": True, "message": "Product fetched", "data": item})
    except Exception:
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

    user_id = session_doc.get("user_id") or event_doc.get("user_id")
    if user_id:
        try:
            rescore_customer(user_id, db, socketio=socketio)
        except Exception:
            pass


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
    owner, error = resolve_persistence_identity(None, anonymous_id)
    if error:
        return error

    session_doc = {
        "visitor_id": visitor_id,
        "anonymous_id": anonymous_id,
        "identity_status": "authenticated" if owner.get("user_id") else "anonymous",
        "started_at": datetime.datetime.utcnow(),
        "last_active_at": datetime.datetime.utcnow(),
        "total_time_seconds": 0,
        "page_views": 0,
        "status": "active"
    }
    if owner.get("user_id"):
        session_doc["user_id"] = ObjectId(owner["user_id"])

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

    # Emit live activity to admin dashboard
    try:
        evt_type = data.get("event_type", "page_view")
        visitor = data.get("visitor_id") or data.get("user_id") or ""
        socketio.emit("customer_activity", {
            "customer_id": str(visitor),
            "event": evt_type,
            "page": data.get("page", ""),
            "timestamp": datetime.datetime.utcnow().isoformat(),
        })
    except Exception:
        pass

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

        user_id = session_doc.get("user_id") if session_doc else None
        if user_id:
            try:
                rescore_customer(user_id, db, socketio=socketio)
            except Exception:
                pass

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


@app.route("/api/customer/features", methods=["GET"])
def get_customer_features_endpoint():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        user_id = request.args.get("user_id") or request.args.get("customer_id")
        anonymous_id = request.args.get("anonymous_id") or request.args.get("visitor_id")

        owner, error = resolve_persistence_identity(user_id, anonymous_id)
        if error:
            return error

        target_id = owner.get("user_id") or owner.get("anonymous_id")
        features = upsert_customer_features(target_id, db)
        serialized = serialize_mongo_value(features)

        return jsonify({
            "success": True,
            "message": "Customer features retrieved",
            "data": serialized,
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/customer/lead-score", methods=["GET"])
@token_required
def get_customer_lead_score_endpoint():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        user_id = g.current_user.get("sub") or g.current_user.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "Authenticated user identity required", "errors": []}), 401

        feature_doc = get_customer_features(user_id, customer_features_collection)
        if not feature_doc:
            return jsonify({
                "success": False,
                "message": "Customer feature record not found. Browse or perform actions to generate activity.",
                "errors": []
            }), 404

        result = predict_customer_features(feature_doc)
        return jsonify({
            "success": True,
            "message": "Customer lead score computed",
            "data": result,
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/admin/customer-lead-score/<customer_id>", methods=["GET"])
@admin_required
def get_admin_customer_lead_score_endpoint(customer_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        if not customer_id:
            return jsonify({"success": False, "message": "customer_id required", "errors": []}), 400

        feature_doc = get_customer_features(customer_id, customer_features_collection)
        if not feature_doc:
            return jsonify({
                "success": False,
                "message": f"Customer feature record not found for customer_id: {customer_id}",
                "errors": []
            }), 404

        result = predict_customer_features(feature_doc)
        return jsonify({
            "success": True,
            "message": "Admin customer lead score computed",
            "data": result,
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/customer/lead-state", methods=["GET"])
@token_required
def get_customer_lead_state_endpoint():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        user_id = g.current_user.get("sub") or g.current_user.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "Authenticated user identity required", "errors": []}), 401

        state = get_customer_lead_state(user_id, customer_lead_state_collection)
        if not state:
            return jsonify({
                "success": False,
                "message": "Customer lead state not found",
                "errors": []
            }), 404

        return jsonify({
            "success": True,
            "message": "Customer lead state retrieved",
            "data": serialize_mongo_value(state),
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/customer/lead-state/sync", methods=["POST"])
@token_required
def sync_customer_lead_state_endpoint():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        user_id = g.current_user.get("sub") or g.current_user.get("user_id")
        if not user_id:
            return jsonify({"success": False, "message": "Authenticated user identity required", "errors": []}), 401

        state = sync_customer_lead_state(user_id, db)
        return jsonify({
            "success": True,
            "message": "Customer lead state synchronized",
            "data": serialize_mongo_value(state),
        }), 200
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "errors": []}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/admin/customer-lead-state/<customer_id>", methods=["GET"])
@admin_required
def get_admin_customer_lead_state_endpoint(customer_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        if not customer_id:
            return jsonify({"success": False, "message": "customer_id required", "errors": []}), 400

        state = get_customer_lead_state(customer_id, customer_lead_state_collection)
        if not state:
            return jsonify({
                "success": False,
                "message": f"Customer lead state not found for customer_id: {customer_id}",
                "errors": []
            }), 404

        return jsonify({
            "success": True,
            "message": "Admin customer lead state retrieved",
            "data": serialize_mongo_value(state),
        }), 200
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


@app.route("/api/admin/customer-lead-state/<customer_id>/sync", methods=["POST"])
@admin_required
def sync_admin_customer_lead_state_endpoint(customer_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "errors": []}), 500

    try:
        if not customer_id:
            return jsonify({"success": False, "message": "customer_id required", "errors": []}), 400

        state = sync_customer_lead_state(customer_id, db)
        return jsonify({
            "success": True,
            "message": "Admin customer lead state synchronized",
            "data": serialize_mongo_value(state),
        }), 200
    except ValueError as error:
        return jsonify({"success": False, "message": str(error), "errors": []}), 404
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "errors": []}), 500


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
        overview = get_intelligence_overview(db)
        total_sessions = sessions_collection.count_documents({})
        total_events = events_collection.count_documents({})

        payload = {
            "total_customers": overview["customers"]["total"],
            "total_leads": overview["leads"]["total_qualified"],
            "active_customers": overview["customers"]["active_today"],
            "active_customers_today": overview["customers"]["active_today"],
            "active_sessions": overview["customers"]["active_today"],
            "total_sessions": total_sessions,
            "total_events": total_events,
            "total_profiles": overview["customers"]["total"],
            "predicted_future_leads": None,
            "customers": overview["customers"],
            "leads": overview["leads"],
            "marketing": overview["marketing"],
            "updated_at": overview["updated_at"],
        }
        return jsonify({"success": True, "data": payload})
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
    """Return real admin notifications from canonical admin_notifications."""
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        read_param = request.args.get("read")
        read_status = None
        if read_param is not None:
            read_status = read_param.lower() == "true"
        page, limit = parse_pagination_params(default_page=1, default_limit=25, max_limit=100)

        res = get_admin_notifications_list(db, read_status=read_status, page=page, limit=limit)
        return jsonify({"success": True, "data": res})
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
        if request.headers.get("Authorization") or user_id:
            owner, error = resolve_persistence_identity(user_id, visitor_id)
            if error:
                return error
            user_id = owner.get("user_id")
            visitor_id = owner.get("anonymous_id")

        profile = get_customer_profile(profiles_collection, user_id=user_id, visitor_id=visitor_id)
        if not profile:
            return jsonify({"success": True, "data": None, "message": "Profile not found"}), 200

        return jsonify({"success": True, "data": serialize_profile(profile)})
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


@app.route("/api/admin/marketing/automation-events", methods=["GET"])
@admin_required
def admin_get_marketing_automation_events():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        limit = int(request.args.get("limit", 100))
        customer_id_str = request.args.get("customer_id")
        query = {}
        if customer_id_str and ObjectId.is_valid(customer_id_str):
            query["customer_id"] = ObjectId(customer_id_str)
        events = list(marketing_automation_events_collection.find(query).sort("created_at", -1).limit(limit))
        return jsonify({"success": True, "data": [serialize_mongo_value(e) for e in events]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500


@app.route("/api/admin/marketing/communications", methods=["GET"])
@admin_required
def admin_get_marketing_communications():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500

    try:
        limit = int(request.args.get("limit", 100))
        customer_id_str = request.args.get("customer_id")
        query = {}
        if customer_id_str and ObjectId.is_valid(customer_id_str):
            query["customer_id"] = ObjectId(customer_id_str)
        comms = list(marketing_communications_collection.find(query).sort("created_at", -1).limit(limit))
        return jsonify({"success": True, "data": [serialize_mongo_value(c) for c in comms]})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500


# --- Admin Intelligence APIs (Task 13) ---

@app.route("/api/admin/intelligence/overview", methods=["GET"])
@admin_required
def admin_intelligence_overview_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        data = get_intelligence_overview(db)
        return jsonify({"success": True, "data": data})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500



@app.route("/api/admin/intelligence/leads", methods=["GET"])
@admin_required
def admin_intelligence_leads_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        status_param = request.args.get("qualification_status", "qualified")
        segment_param = request.args.get("segment", "all")
        sort_by = request.args.get("sort_by", "lead_score")
        sort_order = request.args.get("sort_order", "desc")
        page, limit = parse_pagination_params(default_page=1, default_limit=25, max_limit=100)

        res = get_qualified_leads_list(
            db,
            qualification_status=status_param,
            segment=segment_param,
            sort_by=sort_by,
            sort_order=sort_order,
            page=page,
            limit=limit
        )
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/customers/<customer_id>", methods=["GET"])
@admin_required
def admin_intelligence_customer_detail_route(customer_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500

    if not ObjectId.is_valid(customer_id):
        return jsonify({"success": False, "message": "Invalid customer ID format", "errors": []}), 400

    try:
        detail = get_customer_intelligence_detail(db, customer_id)
        if not detail:
            return jsonify({"success": False, "message": "Customer not found", "errors": []}), 404
        return jsonify({"success": True, "data": detail})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/lead-distribution", methods=["GET"])
@admin_required
def admin_intelligence_lead_distribution_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        res = get_lead_distribution(db)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/recent-leads", methods=["GET"])
@admin_required
def admin_intelligence_recent_leads_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        page, limit = parse_pagination_params(default_page=1, default_limit=10, max_limit=100)
        res = get_recent_leads(db, page=page, limit=limit)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/marketing-activity", methods=["GET"])
@admin_required
def admin_intelligence_marketing_activity_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        page, limit = parse_pagination_params(default_page=1, default_limit=25, max_limit=100)
        res = get_marketing_activity(db, page=page, limit=limit)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/notifications", methods=["GET"])
@admin_required
def admin_intelligence_notifications_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        read_param = request.args.get("read")
        read_status = None
        if read_param is not None:
            read_status = read_param.lower() == "true"
        page, limit = parse_pagination_params(default_page=1, default_limit=25, max_limit=100)

        res = get_admin_notifications_list(db, read_status=read_status, page=page, limit=limit)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/notifications/<notification_id>/read", methods=["PATCH", "PUT", "POST"])
@app.route("/api/admin/notifications/<notification_id>/read", methods=["PATCH", "PUT", "POST"])
@admin_required
def mark_admin_notification_read_route(notification_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        res = mark_notification_read(db, notification_id)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/notifications/mark-all-read", methods=["POST", "PUT"])
@app.route("/api/admin/notifications/mark-all-read", methods=["POST", "PUT"])
@admin_required
def mark_all_admin_notifications_read_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        res = mark_all_notifications_read(db)
        return jsonify({"success": True, "data": res})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


# --- Phase 17A: Product Intelligence APIs ---

@app.route("/api/admin/intelligence/customers/<customer_id>/score-history", methods=["GET"])
@admin_required
def admin_intelligence_score_history_route(customer_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    if not ObjectId.is_valid(customer_id):
        return jsonify({"success": False, "message": "Invalid customer ID format"}), 400
    try:
        limit = int(request.args.get("limit", 50))
        history = get_score_history(customer_id, db, limit=limit)
        return jsonify({"success": True, "data": history})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/customers/<customer_id>/360", methods=["GET"])
@admin_required
def admin_intelligence_customer_360_route(customer_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    if not ObjectId.is_valid(customer_id):
        return jsonify({"success": False, "message": "Invalid customer ID format"}), 400
    try:
        detail = get_customer_intelligence_detail(db, customer_id)
        if not detail:
            return jsonify({"success": False, "message": "Customer not found"}), 404
        return jsonify({"success": True, "data": detail})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/customers/<customer_id>/explain", methods=["GET"])
@admin_required
def admin_intelligence_explain_route(customer_id):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    if not ObjectId.is_valid(customer_id):
        return jsonify({"success": False, "message": "Invalid customer ID format"}), 400
    try:
        features = get_customer_features(customer_id, customer_features_collection)
        if not features:
            return jsonify({"success": False, "message": "Customer features not found"}), 404
        explanation = explain_lead_score(features)
        return jsonify({"success": True, "data": explanation})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/funnel", methods=["GET"])
@admin_required
def admin_intelligence_funnel_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        funnel = get_funnel_analytics(db)
        return jsonify({"success": True, "data": funnel})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/rfm", methods=["GET"])
@admin_required
def admin_intelligence_rfm_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        rfm = get_rfm_distribution(db)
        return jsonify({"success": True, "data": rfm})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/retention", methods=["GET"])
@admin_required
def admin_intelligence_retention_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        retention = get_retention_overview(db)
        return jsonify({"success": True, "data": retention})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/revenue-attribution", methods=["GET"])
@admin_required
def admin_intelligence_revenue_attribution_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        attribution = compute_lead_revenue_attribution(db)
        return jsonify({"success": True, "data": attribution})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/simulate", methods=["POST"])
@admin_required
def admin_intelligence_simulate_route():
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    try:
        data = request.get_json(force=True) or {}
        customer_id = data.get("customer_id")
        feature_overrides = data.get("feature_overrides", {})

        if not isinstance(feature_overrides, dict) or not feature_overrides:
            return jsonify({"success": False, "message": "feature_overrides dict required"}), 400

        result = simulate_lead_score(customer_id, feature_overrides, db)
        return jsonify({"success": True, "data": result})
    except ValueError as ve:
        return jsonify({"success": False, "message": str(ve)}), 400
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/customers/<customer_id>/product-affinity", methods=["GET"])
@app.route("/api/admin/intelligence/product-affinity", methods=["GET"])
@admin_required
def admin_intelligence_product_affinity_route(customer_id=None):
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable"}), 500
    target_id = customer_id or request.args.get("customer_id")
    if not target_id:
        return jsonify({"success": False, "message": "customer_id is required"}), 400
    try:
        affinity = compute_product_affinity(target_id, db)
        return jsonify({"success": True, "data": affinity})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@app.route("/api/admin/intelligence/recent-activity", methods=["GET"])
@admin_required
def admin_recent_activity_route():
    """Return recent activity events for the live activity feed's initial history load."""
    if not MONGO_AVAILABLE:
        return jsonify({"success": False, "message": "Database unavailable", "data": []}), 500
    try:
        limit = min(int(request.args.get("limit", 50)), 100)
        history = []
        profiles_col = db["user_profiles"]

        def _get_name(uid):
            if not uid:
                return None
            from customer_feature_service import _to_object_id as _toid
            c_oid = _toid(uid)
            p = profiles_col.find_one({"_id": c_oid}) if c_oid else None
            if p:
                return p.get("full_name") or p.get("username")
            return None

        # Recent behavior events
        for evt in db["events"].find(
            {"event_type": {"$exists": True}},
            sort=[("timestamp", -1)]
        ).limit(limit):
            ts = evt.get("timestamp")
            if isinstance(ts, datetime.datetime):
                ts = ts.isoformat()
            uid = evt.get("user_id")
            history.append({
                "type": evt.get("event_type", "page_view"),
                "category": "behavior",
                "customer_id": str(uid) if uid else None,
                "customer_name": _get_name(uid),
                "description": evt.get("page") or (evt.get("entity") or {}).get("name") or "",
                "timestamp": ts,
            })

        # Recent orders
        for order in db["orders"].find({}, sort=[("created_at", -1)]).limit(20):
            uid = order.get("user_id")
            ts = order.get("created_at")
            if isinstance(ts, datetime.datetime):
                ts = ts.isoformat()
            amt = order.get("total_amount", 0)
            history.append({
                "type": "order_placed",
                "category": "order",
                "customer_id": str(uid) if uid else None,
                "customer_name": _get_name(uid),
                "description": f"\u20b9{amt:,.0f}",
                "timestamp": ts,
            })

        # Recent qualified leads
        for lead in db["customer_lead_state"].find(
            {"qualification_status": "qualified"},
            sort=[("first_qualified_at", -1)]
        ).limit(10):
            c_id = lead.get("customer_id")
            ts = lead.get("first_qualified_at") or lead.get("updated_at")
            if isinstance(ts, datetime.datetime):
                ts = ts.isoformat()
            history.append({
                "type": "lead_qualified",
                "category": "lead",
                "customer_id": str(c_id) if c_id else None,
                "customer_name": _get_name(c_id),
                "description": f"Score: {lead.get('lead_score','?')} \u00b7 {lead.get('lead_segment','?')}",
                "timestamp": ts,
            })

        # Sort all by timestamp desc
        def _ts_key(x):
            t = x.get("timestamp") or ""
            return t if isinstance(t, str) else ""
        history.sort(key=_ts_key, reverse=True)
        history = history[:limit]

        return jsonify({"success": True, "data": history})
    except Exception as e:
        return jsonify({"success": False, "message": str(e), "data": []}), 500



@socketio.on("connect")
def handle_socketio_connect():
    """Acknowledge admin client SocketIO connection."""
    pass


@socketio.on("request_rescore")
def handle_rescore_request(data):
    """Admin-triggered manual rescore for a specific customer."""
    customer_id = data.get("customer_id") if isinstance(data, dict) else None
    if customer_id and MONGO_AVAILABLE:
        try:
            result = rescore_customer(customer_id, db, socketio=socketio)
            if result:
                socketio.emit("rescore_complete", {
                    "customer_id": str(customer_id),
                    "success": True,
                })
        except Exception:
            socketio.emit("rescore_complete", {
                "customer_id": str(customer_id),
                "success": False,
            })



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
            items=data.get("items"),
            product_ids=data.get("product_ids"),
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

        # Trigger rescoring after purchase event
        try:
            rescore_customer(owner["user_id"], db, socketio=socketio)
        except Exception:
            pass

        # Emit real-time order event
        try:
            socketio.emit("order_placed", {
                "customer_id": str(owner["user_id"]),
                "order_id": str(order_doc["_id"]),
                "total_amount": order_doc["total_amount"],
                "timestamp": str(now),
            })
            amt = float(order_doc.get("total_amount", 0))
            create_admin_notification(
                db,
                notif_type="order_placed",
                title="New Order Placed",
                message=f"Order ₹{amt:,.0f} placed",
                customer_id=str(owner["user_id"]),
                metadata={"order_id": str(order_doc["_id"]), "total_amount": amt},
                socketio=socketio,
            )
        except Exception:
            pass

        try:
            if not app.config.get("TESTING"):
                trigger_order_confirmation_communication(str(order_doc["_id"]), db)
        except Exception:
            pass

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
        authorization = request.headers.get("Authorization", "")
        if not authorization:
            return jsonify({"success": False, "message": "Authorization token required", "errors": []}), 401

        scheme, _, token = authorization.partition(" ")
        if scheme.lower() != "bearer" or not token:
            return jsonify({"success": False, "message": "Invalid authorization token", "errors": []}), 401

        try:
            claims = jwt.decode(token, app.config["JWT_SECRET"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify({"success": False, "message": "Token has expired", "errors": []}), 401
        except jwt.InvalidTokenError:
            return jsonify({"success": False, "message": "Invalid token", "errors": []}), 401

        # Admin: return all orders (paginated)
        if claims.get("role") == "admin":
            limit = min(int(request.args.get("limit", 200)), 500)
            all_orders = list(orders_collection.find({}).sort("created_at", -1).limit(limit))
            return jsonify({"success": True, "data": [serialize_mongo_value(o) for o in all_orders]})

        # Customer: return only own orders
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
@admin_required
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
@admin_required
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
