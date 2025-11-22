from pymongo import MongoClient, ASCENDING
from datetime import datetime, timezone, timedelta
from bson import ObjectId
import os
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGODB_URI")
client = None
db = None

def connect_db():
    # connect to mongodb at startup
    global client, db
    client = MongoClient(MONGO_URI)
    db = client["temperature_db"] # temperature data

    # create indexes
    db.raw_readings.create_index([("patient_id", ASCENDING), ("timestamp", ASCENDING)])
    db.variability_scores.create_index([("patient_id", ASCENDING), ("calculated_at", ASCENDING)])
    db.alerts.create_index([("patient_id", ASCENDING), ("triggered_at", ASCENDING)])
    print("Connected to MongoDB")


# --- TEMPERATURE READINGS ---
# saves arduino temperature reading into database
def insert_reading(patient_id, temperature):
    db.raw_readings.insert_one({
        "patient_id": patient_id,
        "temperature": float(temperature),
        "timestamp": datetime.now(timezone.utc)
    })

def get_readings_24h(patient_id):
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    return list(db.raw_readings.find({
        "patient_id": patient_id,
        "timestamp": {"$gte": twenty_four_hours_ago}
    }).sort("timestamp", -1))


# --- PATIENTS ---
def get_all_patients():
    return list(db.patients.find({"status": "active"}))

# get patient by id
def get_patient(patient_id):
    return db.patients.find_one({"_id": ObjectId(patient_id)})

# creates a new patient
def create_patient(name, room, baseline_temp):
    result = db.patients.insert_one({
        "name": name,
        "room_number": room,
        "baseline_temp": baseline_temp,
        "reason_for_admission": "General",
        "admission_date": datetime.now(timezone.utc),
        "status": "active"
    })
    return str(result.inserted_id)


# --- SCORES ---
def store_score(patient_id, score):
    db.variability_scores.insert_one({
        "patient_id": patient_id,
        "score": float(score),
        "calculated_at": datetime.now(timezone.utc)
    })

def get_latest_score(patient_id):
    return db.variability_scores.find_one(
        {"patient_id": patient_id},
        sort=[("calculated_at", -1)]
    )

def get_scores_7_days(patient_id):
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    return list(db.variability_scores.find({
        "patient_id": patient_id,
        "calculated_at": {"$gte": week_ago}
    }).sort("calculated_at", -1))


# --- ALERTS ---
# creates a new alert
def create_alert(patient_id, alert_type, score):
    recent = db.alerts.find_one({
        "patient_id": patient_id,
        "alert_type": alert_type,
        "triggered_at": {"$gte": datetime.now(timezone.utc) - timedelta(hours=2)}
    })
    
    if recent:
        return  # already alerted recently
    
    db.alerts.insert_one({
        "patient_id": patient_id,
        "alert_type": alert_type,
        "triggered_at": datetime.now(timezone.utc),
        "score": score,
        "acknowledged": False
    })

# marks alert as acknowledged
def ack_alert(alert_id):
    db.alerts.update_one(
        {"_id": ObjectId(alert_id)},
        {"$set": {"acknowledged": True}}
    )

# get alerts from past 7 days
def get_alerts_7_days(patient_id):
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    return list(db.alerts.find({
        "patient_id": patient_id,
        "triggered_at": {"$gte": week_ago}
    }).sort("triggered_at", -1))

# NEW EDITS FOR THE ALERT THING 

# --- BUTTON PRESS ALERTS ---
def create_button_alert(patient_id, message="Patient pressed call button"):
    """
    Creates an immediate alert when patient presses the button
    This is separate from the variability score alerts
    """
    db.button_alerts.insert_one({
        "patient_id": patient_id,
        "alert_type": "button_press",
        "triggered_at": datetime.now(timezone.utc),
        "message": message,
        "acknowledged": False,
        "response_time": None  # Will be set when nurse acknowledges
    })
    print(f"Button alert created for patient {patient_id}")


def acknowledge_button_alert(alert_id, nurse_id=None):
    """
    Acknowledges button press alert and records response time
    """
    alert = db.button_alerts.find_one({"_id": ObjectId(alert_id)})
    
    if alert:
        triggered_at = alert["triggered_at"]
        acknowledged_at = datetime.now(timezone.utc)
        response_time_seconds = (acknowledged_at - triggered_at).total_seconds()
        
        db.button_alerts.update_one(
            {"_id": ObjectId(alert_id)},
            {
                "$set": {
                    "acknowledged": True,
                    "acknowledged_at": acknowledged_at,
                    "response_time": response_time_seconds,
                    "nurse_id": nurse_id
                }
            }
        )
        return response_time_seconds
    return None


def get_unacknowledged_button_alerts(patient_id=None):
    """
    Get all unacknowledged button press alerts
    If patient_id is provided, filter by that patient
    """
    query = {"acknowledged": False}
    if patient_id:
        query["patient_id"] = patient_id
    
    return list(db.button_alerts.find(query).sort("triggered_at", -1))


def get_button_alerts_24h(patient_id):
    """
    Get all button press alerts from last 24 hours for a patient
    """
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    return list(db.button_alerts.find({
        "patient_id": patient_id,
        "triggered_at": {"$gte": twenty_four_hours_ago}
    }).sort("triggered_at", -1))