from db import connect_db
from datetime import datetime, timezone
import random

connect_db()

from db import db as database

# Create 10 fake patients
fake_patients = [
    {"name": "John Smith", "room": "102"},
    {"name": "Mary Johnson", "room": "103"},
    {"name": "Robert Brown", "room": "104"},
    {"name": "Patricia Davis", "room": "105"},
    {"name": "Michael Wilson", "room": "106"},
    {"name": "Linda Martinez", "room": "107"},
    {"name": "David Anderson", "room": "108"},
    {"name": "Barbara Taylor", "room": "109"},
    {"name": "William Thomas", "room": "110"},
]

for fake in fake_patients:
    # Check if already exists
    existing = database.patients.find_one({"name": fake["name"]})
    if not existing:
        database.patients.insert_one({
            "name": fake["name"],
            "room_number": fake["room"],
            "baseline_temp": 36.5,
            "reason_for_admission": "General",
            "admission_date": datetime.now(timezone.utc),
            "status": "active"
        })
        
        # Add fake variability scores
        score = random.uniform(2, 12)  # Random scores for demo
        database.variability_scores.insert_one({
            "patient_id": database.patients.find_one({"name": fake["name"]})["_id"],
            "score": score,
            "calculated_at": datetime.now(timezone.utc)
        })
        print(f"Created {fake['name']} with score {score:.2f}")

print("✓ Fake patients created!")