import requests
import json
import time
import os
from tqdm import tqdm

# API endpoint and parameters
base_url = "https://api.congress.gov/v3/bill/118"
params = {
    "format": "json",
    "limit": 250,
    # "fromDateTime": "2024-04-07T00:00:00Z",
    # "toDateTime": "2024-10-04T23:59:59Z",
    "sort": "updateDate+desc",
    "api_key": "TNMSLQibAQP7Lf0NFvypJn5dd8F8hZbwMdyo2Szz"
}

# Create a directory to store data chunks (if it doesn't exist)
data_dir = "congress_data_chunks"
os.makedirs(data_dir, exist_ok=True)

# Check for existing chunks to determine starting point
existing_chunks = [f for f in os.listdir(data_dir) if f.endswith(".json")]
if existing_chunks:
    last_chunk_number = max([int(f.split("_")[1].split(".")[0]) for f in existing_chunks])
    chunk_counter = last_chunk_number + 1
    url = None
else:
    chunk_counter = 0
    url = base_url

response = requests.get(base_url, params=params)
total_bills = response.json()["pagination"]["count"]

# Use tqdm for the progress bar
with tqdm(total=total_bills, desc="Downloading bills", unit="bill") as pbar:
    while url:
        try:
            response = requests.get(url, params=params)

            # Check for rate limiting
            if response.status_code == 429:  # Too Many Requests
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"Rate limited! Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            response.raise_for_status()

            data = response.json()

            # Save the current chunk to a separate file
            chunk_filename = os.path.join(data_dir, f"chunk_{chunk_counter}.json")
            with open(chunk_filename, "w") as f:
                json.dump(data, f, indent=4)

            chunk_counter += 1

            # Update progress bar
            pbar.update(len(data["bills"]))

            # Get the next page URL
            pagination = data.get("pagination")
            if pagination and pagination.get("next"):
                url = pagination["next"]
                url += f"&api_key={params['api_key']}"
                time.sleep(1)  # Optional delay
            else:
                url = None

        except requests.exceptions.RequestException as e:
            print(f"Error during request: {e}")
            break
        except (KeyError, json.JSONDecodeError) as e:
            print(f"Error parsing JSON response: {e}")
            break

# Combine all chunks into a single file
all_bills = []
for chunk_file in os.listdir(data_dir):
    if chunk_file.endswith(".json"):
        with open(os.path.join(data_dir, chunk_file), "r") as f:
            chunk_data = json.load(f)
            all_bills.extend(chunk_data["bills"])

with open("all_congress_data.json", "w") as f:
    json.dump({"bills": all_bills}, f, indent=4)

print("All data successfully saved to all_congress_data.json") 