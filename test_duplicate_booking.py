import requests
import threading
import json

API_URL = "http://127.0.0.1:5000/book"  # Flask server

# Same Saturday booking date
BOOKING_DATE = "2026-11-14"

# Two users trying to book the same date
payloads = [
    {"user_id": 2465, "booking_date": BOOKING_DATE, "mahaprasad": False},
    {"user_id": 2466, "booking_date": BOOKING_DATE, "mahaprasad": False},
]

headers = {"Content-Type": "application/json"}

def make_booking(payload):
    response = requests.post(API_URL, data=json.dumps(payload), headers=headers)
    print(f"User {payload['user_id']} -> {response.status_code}: {response.text}")

# Launch both users’ booking requests at the same time
threads = [threading.Thread(target=make_booking, args=(payload,)) for payload in payloads]

for t in threads:
    t.start()

for t in threads:
    t.join()
