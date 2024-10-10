import requests
import json
import time
import os
from tqdm import tqdm

base_url = "https://api.govinfo.gov/collections/BILLS/2018-01-28T20%3A18%3A10Z"
params = {
    "pageSize": 1000,
    "congress": 118,
    "offsetMark": "*",
    "api_key": "He7pQCphxtdIziKbNImyaDlelS2W5oXwgb8qKtg4"
}

data_dir = "chunks"
os.makedirs(data_dir, exist_ok=True)

existing_chunks = [f for f in os.listdir(data_dir) if f.endswith(".json")]
if existing_chunks:
    last_chunk_number = max([int(f.split("_")[1].split(".")[0]) for f in existing_chunks])
    chunk_counter = last_chunk_number + 1
    url = None  
else:
    chunk_counter = 0
    response = requests.get(base_url, params=params)
    response.raise_for_status()
    data = response.json()

    total_bills = data.get("count")
    url = data.get("nextPage")

    if url and "api_key" not in url:
        url += f"&api_key={params['api_key']}"

    # Save the first page data immediately
    chunk_filename = os.path.join(data_dir, f"chunk_{chunk_counter}.json")
    with open(chunk_filename, "w") as f:
        json.dump(data, f, indent=4)
    chunk_counter += 1

    if total_bills:
        pbar = tqdm(total=total_bills, desc="Downloading bills", unit="bill")
        pbar.update(len(data.get("packages", [])))
    else:
        pbar = tqdm(desc="Downloading bills", unit="bill")

while url:
    try:
        response = requests.get(url)

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 60))
            print(f"Rate limited! Retrying after {retry_after} seconds...")
            time.sleep(retry_after)
            continue

        response.raise_for_status()

        data = response.json()

        chunk_filename = os.path.join(data_dir, f"chunk_{chunk_counter}.json")
        with open(chunk_filename, "w") as f:
            json.dump(data, f, indent=4)

        chunk_counter += 1

        if total_bills:
            pbar.update(len(data.get("packages", [])))

        url = data.get("nextPage")
        if url and "api_key" not in url:
            url += f"&api_key={params['api_key']}"

    except requests.exceptions.RequestException as e:
        print(f"Error during request: {e}")
        break
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error parsing JSON response: {e}")
        break

if total_bills:
    pbar.close()

all_packages = []
for chunk_file in os.listdir(data_dir):
    if chunk_file.endswith(".json"):
        with open(os.path.join(data_dir, chunk_file), "r") as f:
            chunk_data = json.load(f)
            all_packages.extend(chunk_data.get("packages", []))

with open("bills.json", "w") as f:
    json.dump({"packages": all_packages}, f, indent=4)

print("All data successfully saved to laws.json")