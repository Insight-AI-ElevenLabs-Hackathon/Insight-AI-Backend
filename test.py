import requests
import json
import time
import os
from tqdm import tqdm
from datetime import datetime, timedelta

# API endpoint and parameters
base_url = "https://api.congress.gov/v3/bill/118"
params = {
    "format": "json",
    "limit": 250,
    "sort": "updateDate+desc",
    "api_key": "TNMSLQibAQP7Lf0NFvypJn5dd8F8hZbwMdyo2Szz"
}

# Data file path
data_file = "all_congress_data.json"

def fetch_and_update_data(data_file):
    """Fetches data from the API and updates the existing data file."""

    # Load existing data
    try:
        with open(data_file, "r") as f:
            existing_data = json.load(f)
            all_bills = existing_data["bills"]
    except FileNotFoundError:
        all_bills = []

    # Get the last update date from the existing data (or a default date)
    if all_bills:
        last_update_date = datetime.fromisoformat(all_bills[0]["updateDate"])  # No need to remove 'Z' anymore
    else:
        last_update_date = datetime(2024, 4, 7)  # Default start date

    # Set fromDateTime parameter based on the last update date
    params["fromDateTime"] = (last_update_date + timedelta(seconds=1)).isoformat() + "Z"

    url = base_url
    updated = False

    with tqdm(desc="Updating bills", unit="bill") as pbar:
        while url:
            try:
                response = requests.get(url, params=params)

                # Check for rate limiting
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    print(f"Rate limited! Retrying after {retry_after} seconds...")
                    time.sleep(retry_after)
                    continue

                response.raise_for_status()
                data = response.json()

                new_bills = data["bills"]

                # Check for matching bills and update/add as needed
                for new_bill in new_bills:
                    found_match = False
                    for i, existing_bill in enumerate(all_bills):
                        if new_bill["number"] == existing_bill["number"] and new_bill["type"] == existing_bill["type"]:  # Match by number and type
                            if new_bill["updateDate"] > existing_bill["updateDate"]:
                                all_bills[i] = new_bill  # Update existing bill
                            found_match = True
                            break
                    if not found_match:
                        all_bills.insert(0, new_bill)  # Add new bill at the beginning
                        updated = True

                # Update progress bar
                pbar.update(len(new_bills))

                # Get the next page URL
                pagination = data.get("pagination")
                if pagination and pagination.get("next"):
                    url = pagination["next"]
                    url += f"&api_key={params['api_key']}"
                    time.sleep(1)
                else:
                    url = None

            except requests.exceptions.RequestException as e:
                print(f"Error during request: {e}")
                break
            except (KeyError, json.JSONDecodeError) as e:
                print(f"Error parsing JSON response: {e}")
                break

            # Stop if no new bills were added in the current page
            if not updated and new_bills:
                break
            updated = False  # Reset for the next page

    # Save the updated data
    with open(data_file, "w") as f:
        json.dump({"bills": all_bills}, f, indent=4)

    if all_bills:
        print(f"Data updated successfully. Last updated bill: {all_bills[0]['updateDate']}")
    else:
        print("No new data found.")


# Run the update function
fetch_and_update_data(data_file)