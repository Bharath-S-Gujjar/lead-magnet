from flask import Flask, request, jsonify
from flask_cors import CORS
import joblib
import pandas as pd
from flask_socketio import SocketIO


app = Flask(__name__)
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")

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

@app.route("/track", methods=["POST"])
def track():
    data = request.get_json()

    lead_df = pd.DataFrame([data])
    lead_encoded = pd.get_dummies(lead_df)
    lead_encoded = lead_encoded.reindex(columns=feature_columns, fill_value=0)
    lead_scaled = scaler.transform(lead_encoded)

    prob = model.predict_proba(lead_scaled)[0][1]
    segment_id = kmeans.predict(lead_scaled)[0]
    segment = segment_map[segment_id]

    result = {
        "visitor_id": data.get("visitor_id", "unknown"),
        "score": round(float(prob), 2),
        "segment": segment
    }

    # Push live to any connected dashboard
    socketio.emit("lead_update", result)

    return jsonify(result)

if __name__ == "__main__":
    socketio.run(app, debug=True, port=5000)