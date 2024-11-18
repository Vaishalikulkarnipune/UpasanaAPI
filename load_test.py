import requests
import json
from concurrent.futures import ThreadPoolExecutor, as_completed

# Define the API URL
url = "https://upasana-app-gdm2p.ondigitalocean.app/register"

# Base mobile number to start with
base_mobile_number = 1234561295

# Define the payload data template for registration
payload_template = {
    "first_name": "Charlie",
    "middle_name": "C.",
    "last_name": "Brown",
    "email": "charlie.brown@example.com",
    "password": "hashed_password",
    "confirm_password": "hashed_password",
    "alternate_mobile_number": "0987654324",
    "flat_no": "404",
    "full_address": "321 Oak St",
    "area": "Midtown",
    "landmark": "Near the school",
    "city": "Metropolis",
    "state": "Stateland",
    "pincode": "411033",
    "anugrahit": "yes",
    "gender": "male"
}

# Function to send a POST request for registration
def send_register_request(session, mobile_number):
    # Update the mobile_number in the payload
    payload = payload_template.copy()
    payload["mobile_number"] = str(mobile_number)
    
    try:
        response = session.post(url, json=payload)
        if response.status_code == 201:
            return f"Registration successful for {mobile_number} with status code {response.status_code}"
        else:
            return f"Failed to register {mobile_number} with status code {response.status_code}"
    except Exception as e:
        return f"Error during registration for {mobile_number}: {e}"

# Function to perform load testing with concurrent requests
def load_test_concurrent_requests(number_of_requests):
    with ThreadPoolExecutor(max_workers=number_of_requests) as executor:
        with requests.Session() as session:
            futures = []
            for i in range(number_of_requests):
                # Increment mobile number for each request
                mobile_number = base_mobile_number + i
                futures.append(executor.submit(send_register_request, session, mobile_number))
            
            for future in as_completed(futures):
                print(future.result())

if __name__ == "__main__":
    # Set the number of concurrent requests (e.g., 10 requests)
    number_of_requests = 100

    # Run the load test
    load_test_concurrent_requests(number_of_requests)
