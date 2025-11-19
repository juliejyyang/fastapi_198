from backend.db import connect_db, create_patient

connect_db()

patient_id = create_patient(
    name = "Naru Crunchy", 
    room = "101",
    baseline_temp = 36.0
) 
