from pymongo import MongoClient

# Replace these with your actual credentials
username = "medha-narumanchi"
password = "ece198"

# Connect to your cluster (replace cluster0.mongodb.net if different)
client = MongoClient(f"mongodb+srv://{username}:{password}@cluster0.mongodb.net/temp_data?retryWrites=true&w=majority")

# Choose database and collection
db = client["temp_data"]          # database name (MongoDB will create if it doesn't exist)
collection = db["sensor_readings"]       # collection name (like a table)