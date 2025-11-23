# main.py: all endpoints stored here

# imports + setup
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, HTMLResponse
from contextlib import asynccontextmanager
import asyncio # handles background tasks - allow simultaneous tasks
from datetime import datetime, timezone, timedelta # calculating 24 hours windows
import os
from dotenv import load_dotenv
from fastapi.staticfiles import StaticFiles
import re
import time
from pathlib import Path
from bson import ObjectId
from backend.calculations import calculate_variability, detect_outliers


# import function from db.py (database functions)
from backend.db import (
    connect_db, # connects to mongodb
    insert_reading, # saves temp to database when arduino send data
    get_readings_24h, # gets all readings from last 24 hrs - used in background tasks to calculate variability
    get_all_patients, # gets all patients - called in background task and dashboard endpoint
    store_score, # saves variability score - background task
    create_alert, # creates alert - when score is high
    ack_alert, # marks alert as acknolwedge by nurse
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
async def root():
    # return the dynamic HTML so the page and SSE are same-origin
    base = Path(__file__).parent.parent
    return HTMLResponse(base.joinpath("frontend","dashboard.html").read_text(encoding="utf-8"))

@app.get("/patient")
async def patient():
    base = Path(__file__).parent.parent
    return HTMLResponse(base.joinpath("frontend","patient.html").read_text(encoding="utf-8"))

# properly format the tempearture readings
NUMBER_RE = re.compile(r"-?\d+(\.\d+)?")

# real monitor data is going to be stored in this patient ID
patient_id = ObjectId("691bcd11af15fc8ebcb9316a")

# endpoint that streams live temperature data from arduino
@app.get("/stream")
async def stream_data():
    async def generate():
        keepalive_interval = 5.0
        last_keepalive = 0.0

        while True:
            # read from serial off the event loop
            raw = await asyncio.to_thread(read_temperature)

            # normalize bytes -> str
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode(errors="ignore")

            if not raw:
                # occasionally send a comment so the client doesn't time out
                if time.time() - last_keepalive > keepalive_interval:
                    last_keepalive = time.time()
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)
                continue

            # handle fragmented / concatenated input: split on newlines and pick last non-empty chunk
            parts = re.split(r'[\r\n]+', str(raw))
            token = None
            for p in reversed(parts):
                if p and p.strip():
                    token = p.strip()
                    break

            if not token:
                print("DEBUG: empty token from raw:", repr(raw))
                if time.time() - last_keepalive > keepalive_interval:
                    last_keepalive = time.time()
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)
                continue

    #edit for making the button work --------------------------------------------------
            if "HELP_BUTTON_PRESSED" in token:
            # Fetch patient info
                from backend.db import get_patient
                patient = await asyncio.to_thread(get_patient, str(patient_id))
    
                if patient:
                # Send patient info directly to frontend
                    import json
                    alert_data = {
                        "type": "HELP_REQUEST",
                        "name": patient["name"],
                        "room": patient["room_number"]
                    }
                yield f"data: {json.dumps(alert_data)}\n\n"
    
                await asyncio.sleep(0.2)
                continue
    #end of the edit to make the button work   ---------------------------------
            # extract number substring
            m = NUMBER_RE.search(token)
            if not m:
                print("DEBUG: no number found in token:", repr(token), "raw:", repr(raw))
                if time.time() - last_keepalive > keepalive_interval:
                    last_keepalive = time.time()
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)
                continue

            try:
                val = float(m.group(0))
            except Exception:
                print("DEBUG: could not parse float from:", m.group(0), "raw:", repr(raw))
                if time.time() - last_keepalive > keepalive_interval:
                    last_keepalive = time.time()
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)
                continue

            # sanity check the value (adjust min/max for your sensor)
            if val < 10 or val > 60:
                print("DEBUG: out-of-range value:", val, "raw:", repr(raw))
                if time.time() - last_keepalive > keepalive_interval:
                    last_keepalive = time.time()
                    yield ": keep-alive\n\n"
                await asyncio.sleep(0.2)
                continue

            # good value: insert and send to clients
            await asyncio.to_thread(insert_reading, patient_id, val)  # ensure patient_id is set correctly
            yield f"data: {val:.2f}\n\n"

            await asyncio.sleep(0.2)

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

@app.get("/api/patient/{patient_id}/variability")
async def patient_variability(patient_id: str):
    # run DB read in thread to avoid blocking the event loop
    readings = await asyncio.to_thread(get_readings_24h, patient_id)
    temps = [r["temperature"] for r in readings]
    if not temps:
        return {"patient_id": patient_id, "score": None, "count": 0}
    filtered, outliers = detect_outliers(temps)
    score = calculate_variability(filtered)
    return {"patient_id": patient_id, "score": float(score), "count": len(temps)}
