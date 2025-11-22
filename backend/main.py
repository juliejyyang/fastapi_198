# main.py: all endpoints stored here

# imports + setup
from fastapi import FastAPI
from fastapi.responses import StreamingResponse, HTMLResponse
from contextlib import asynccontextmanager
import asyncio # handles background tasks - allow simultaneous tasks
from datetime import datetime, timezone, timedelta # calculating 24 hours windows
import os
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
import re
from pathlib import Path
from bson import ObjectId

# import function from db.py (database functions)
from backend.db import (
    connect_db, # connects to mongodb
    insert_reading, # saves temp to database when arduino send data
    get_readings_24h, # gets all readings from last 24 hrs - used in background tasks to calculate variability
    get_all_patients, # gets all patients - called in background task and dashboard endpoint
    store_score, # saves variability score - background task
    create_alert, # creates alert - when score is high
    ack_alert, # marks alert as acknolwedge by nurse
    #EDIT FOR THE ALERT SYSTEM FOR HELP 
    create_button_alert,  # ADD THIS LINE
    acknowledge_button_alert,  # ADD THIS LINE
    get_unacknowledged_button_alerts,  # ADD THIS LINE
    get_button_alerts_24h,
    db
)

# imports some more functions
from backend.arduino_handler import connect_arduino, read_temperature, close_arduino
# MIGHT want to delete detect outliers and use ai model
from backend.calculations import calculate_variability, detect_outliers

# runs function - loads .env file into memory so os.getenv() can work w it
load_dotenv()

# setup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    # connects to mongodb and arduino
    connect_db()
    connect_arduino()

    # infinite loop that runs every 6 hours, calculates patient score every 6 hours (15 mins for testing)
    async def background_calc():
        while True:
            # below begins after 6 hours (15 mins)
            patients = get_all_patients() # store patients from database into a list
            
            # files through the list of patients
            for patient in patients:
                # gets last 24 h temp readings for each patient
                # 24h b/c although we calculating score every 6 hours, we need enough data for variability from the last 24 hours
                readings = get_readings_24h(patient["_id"])
                
                # only calculate if more than 10 readings in the past 24 hours
                if len(readings) > 10:
                    # extracts only temperature from readings into a list
                    temps = [r["temperature"] for r in readings]

                    # TENTATIVE - removes outliers from temperature list
                    filtered, outliers = detect_outliers(temps)
                    # second derivative calculation for delirium risk score
                    score = calculate_variability(filtered)
                    # save score - every 6 hours each patient gets a new score
                    store_score(patient["_id"], score)

                    # trigger alert if score too high
                    if score >= 8.0:
                        create_alert(patient["_id"], "red", score)
                    elif score >= 5.0:
                        create_alert(patient["_id"], "yellow", score)
                    
            await asyncio.sleep(900)
    
    # starts the background task while app handles requests
    asyncio.create_task(background_calc())

    yield

    # shutdown
    close_arduino()

app = FastAPI(lifespan=lifespan)


# serve project root (or use a dedicated "static" directory)
app.mount("/static", StaticFiles(directory=Path(__file__).parent.parent /"frontend"), name="static")


# --- endpoints --- #

# home page - shows webpage running
@app.get("/")
async def dashboard():
    # return the dynamic HTML so the page and SSE are same-origin
    base = Path(__file__).parent.parent
    return HTMLResponse(base.joinpath("frontend","dashboard.html").read_text(encoding="utf-8"))

@app.get("/patient")
async def patient():
    base = Path(__file__).parent.parent
    return HTMLResponse(base.joinpath("frontend","patient.html").read_text(encoding="utf-8"))

NUMBER_RE = re.compile(r"-?\d+(\.\d+)?")
patient_id = ObjectId("691bcd11af15fc8ebcb9316a")

# endpoint that streams live temperature data from arduino
@app.get("/stream")
async def stream_data():
    # never stops streaming data until browser closes
    async def generate():
        while True:
            raw_temp = await asyncio.to_thread(read_temperature)

            # normalize bytes -> str
            if isinstance(raw_temp, (bytes, bytearray)):
                raw_temp = raw_temp.decode(errors="ignore")
            
            if not raw_temp:
                yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)
                continue

            #EDIT FOR THE THING ALERT THING 
            if "pressed" in raw_temp.lower():
                # Create button alert in database
                await asyncio.to_thread(create_button_alert, patient_id, raw_temp)
                
                # Send button press event to frontend
                yield f"event: button\ndata: pressed\n\n"
                await asyncio.sleep(0.5)
                continue 

            # split into lines (handle fragmented/concatenated input)
            parts = re.split(r'[\r\n]+', str(raw_temp))
            # pick last non-empty part (most recent complete token)
            token = None
            for p in reversed(parts):
                if p and p.strip():
                    token = p.strip()
                    break
            
            # Extract temperature value after "Temp °C:"
            if token:
                # Look for "Temp °C: " followed by a number
                temp_match = re.search(r'Temp °C:\s*([-\d.]+)', token)
                if temp_match:
                    try:
                        val = float(temp_match.group(1))
                    except Exception:
                        val = None
                else:
                    val = None
            else:
                val = None

            # sanity check: human temps ~30-42 C (adjust for your sensor)
            if val is None or val < 10 or val > 60:
                # ignore bad values, send keep-alive or debug comment
                yield ": invalid\n\n"
                print(f"DEBUG: decoded = {raw_temp}")  # ADD THIS
            else:
                # insert into DB off-loop if needed
                await asyncio.to_thread(insert_reading, patient_id, val)
                yield f"data: {val}\n\n"

            await asyncio.sleep(5)
    return StreamingResponse(generate(), media_type="text/event-stream")

# dashboard endpoint that returns all patients organized into the alert tiers
# returns a dictoinary with patients organized in the 3 tiers
# returned to the browser as JSON
@app.get("/api/dashboard")
async def dashboard():
    patients = get_all_patients()
    # organize patients by alter tier
    result = {"red": [], "yellow": [], "green": []}

    for patient in patients:
        from backend.db import get_latest_score
        score_doc = get_latest_score(patient["_id"])
        score = score_doc["score"] if score_doc else 0

        if score >= 8.0:
            tier = "red"
        elif score >= 5.0:
            tier = "yellow"
        else:
            tier = "green"

        admission_date = patient["admission_date"]
        if admission_date.tzinfo is None:
            admission_date = admission_date.replace(tzinfo=timezone.utc)
        
        days = (datetime.now(timezone.utc) - admission_date).days

        result[tier].append({
            "id": str(patient["_id"]),
            "name": patient["name"],
            "room": patient["room_number"],
            "score": round(score, 2),
            "days_admitted": days
        })
    return result

# get one patient's full profile
# returns a patients name room days admitted
# returns a graph for variability over time over a week
# returns alert history (moving between alert tiers) over a week
@app.get("/api/patient/{patient_id}")
async def patient_detail(patient_id: str):
    from backend.db import get_patient, get_scores_7_days, get_alerts_7_days

    patient = get_patient(patient_id)
    if not patient:
        return {"error:" "Patient not found"}
    
    scores = get_scores_7_days(patient_id)
    alerts = get_alerts_7_days(patient_id)

    return {
        "patient": {
            "name": patient["name"],
            "room": patient["room_number"],
            "baseline_temp": patient["baseline_temp"],
            "days_admitted": (datetime.now(timezone.utc) - patient["admission_date"].replace(tzinfo=timezone.utc)).days
        },
        "scores": [{"time": str(s["calculated_at"]), "score": s["score"]} for s in scores],
        "alerts": [{"type": a["alert_type"], "time": str(a["triggered_at"])} for a in alerts]
    }

# collects acknowledge status from browser and posts to server
@app.post("/api/alert/{alert_id}/acknowledge")
async def ack_alert(alert_id: str):
    ack_alert(alert_id)
    return {"status": "acknowledged"}

# EDITS FOR THE NEW ALERT THING 

# NEW: Get unacknowledged button alerts for dashboard
@app.get("/api/button-alerts")
async def get_button_alerts_endpoint():
    """
    Returns all unacknowledged button press alerts
    """
    alerts = get_unacknowledged_button_alerts()
    
    result = []
    for alert in alerts:
        from backend.db import get_patient
        patient = get_patient(str(alert["patient_id"]))
        
        result.append({
            "alert_id": str(alert["_id"]),
            "patient_id": str(alert["patient_id"]),
            "patient_name": patient["name"] if patient else "Unknown",
            "room": patient["room_number"] if patient else "N/A",
            "triggered_at": str(alert["triggered_at"]),
            "message": alert.get("message", "Patient needs assistance"),
            "acknowledged": alert["acknowledged"]
        })
    
    return result


# NEW: Acknowledge button press alert
@app.post("/api/button-alert/{alert_id}/acknowledge")
async def ack_button_alert_endpoint(alert_id: str):
    """
    Acknowledges a button press alert and returns response time
    """
    response_time = acknowledge_button_alert(alert_id)
    
    if response_time is not None:
        return {
            "status": "acknowledged",
            "response_time_seconds": round(response_time, 2),
            "response_time_minutes": round(response_time / 60, 2)
        }
    else:
        return {"error": "Alert not found"}


# NEW: Get patient's button press history
@app.get("/api/patient/{patient_id}/button-alerts")
async def patient_button_history(patient_id: str):
    """
    Returns button press history for a patient (last 24 hours)
    """
    alerts = get_button_alerts_24h(patient_id)
    
    result = []
    for alert in alerts:
        result.append({
            "triggered_at": str(alert["triggered_at"]),
            "acknowledged": alert["acknowledged"],
            "response_time": alert.get("response_time"),
            "acknowledged_at": str(alert.get("acknowledged_at")) if alert.get("acknowledged_at") else None
        })
    
    return {"button_alerts": result}