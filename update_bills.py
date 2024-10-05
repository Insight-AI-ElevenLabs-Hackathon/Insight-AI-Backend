import requests
import json
import time
import os
from tqdm import tqdm
from datetime import datetime, timedelta
from requests.exceptions import RequestException, ConnectionError, HTTPError, Timeout
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError

# Cloudflare R2 (AWS S3 compatible) configuration
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_BUCKET = "elevenlabs-hackathon"
R2_FILE_KEY = "bills.json"

# API endpoint and parameters
base_url = "https://api.congress.gov/v3/bill/118"
params = {
    "format": "json",
    "limit": 250,
    "sort": "updateDate+desc",
    "api_key": "TNMSLQibAQP7Lf0NFvypJn5dd8F8hZbwMdyo2Szz"
}

# Initialize S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    endpoint_url=R2_ENDPOINT
)


def load_existing_data():
    """Load existing data from Cloudflare R2."""
    try:
        response = s3.get_object(Bucket=R2_BUCKET, Key=R2_FILE_KEY)
        return json.loads(response['Body'].read())["bills"]
    except s3.exceptions.NoSuchKey:
        print("Data file not found in R2. Starting fresh.")
        return []
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error loading existing data: {e}. Starting fresh.")
        return []


def save_data(all_bills):
    """Save the updated and sorted data to Cloudflare R2."""
    try:
        s3.put_object(
            Bucket=R2_BUCKET,
            Key=R2_FILE_KEY,
            Body=json.dumps({"bills": all_bills}, indent=4)
        )
        print(f"Data saved successfully to R2. Total bills: {len(all_bills)}")
    except (BotoCoreError, NoCredentialsError) as e:
        print(f"Error saving data to R2: {e}")


def fetch_data_from_api(url, params):
    """Fetch data from the API and handle rate limiting."""
    while True:
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"Rate limited! Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            return response.json()
        except (HTTPError, Timeout) as e:
            print(f"HTTP error or timeout: {e}. Retrying in 60 seconds...")
            time.sleep(60)
        except ConnectionError as e:
            print(f"Connection error: {e}. Retrying in 30 seconds...")
            time.sleep(30)
        except RequestException as e:
            print(f"Request failed: {e}")
            return None


def update_bills(existing_bills, new_bills):
    """Update the existing bills with new data and stop if a match without updates is found."""
    updated = False
    for new_bill in new_bills:
        found_match = False
        for i, existing_bill in enumerate(existing_bills):
            if new_bill["number"] == existing_bill["number"] and new_bill["type"] == existing_bill["type"]:
                if new_bill["updateDate"] > existing_bill["updateDate"]:
                    existing_bills[i] = new_bill  # Update existing bill
                    print(f"Updated bill: {new_bill['number']} ({new_bill['type']})")
                    updated = True
                found_match = True
                break
        if not found_match:
            existing_bills.insert(0, new_bill)  # Add new bill at the beginning
            updated = True
            print(f"Added new bill: {new_bill['number']} ({new_bill['type']})")
        elif found_match and not updated:
            # If a matching bill is found and no updates were needed, stop further processing
            print("Match found with no updates needed. Stopping early to avoid unnecessary downloads.")
            return updated, True

    return updated, False


def sort_bills_by_date(bills):
    """Sort bills by updateDateIncludingText in descending order."""
    return sorted(bills, key=lambda bill: bill['updateDateIncludingText'], reverse=True)


def fetch_and_update_data():
    """Fetches data from the API and updates the existing data in Cloudflare R2."""

    # Load existing data
    all_bills = load_existing_data()

    # Get the last update date from the existing data (or a default date)
    if all_bills:
        last_update_date = datetime.fromisoformat(all_bills[0]["updateDate"])
    else:
        last_update_date = datetime(2024, 4, 7)  # Default start date

    # Set fromDateTime parameter based on the last update date
    params["fromDateTime"] = (last_update_date + timedelta(seconds=1)).isoformat() + "Z"

    url = base_url
    updated = False

    with tqdm(desc="Updating bills", unit="bill") as pbar:
        while url:
            data = fetch_data_from_api(url, params)
            if data is None:
                break  # Exit if the request failed

            new_bills = data.get("bills", [])
            if not new_bills:
                print("No new bills found.")
                break

            # Check for matching bills and update/add as needed
            updated, stop_early = update_bills(all_bills, new_bills)

            # Stop fetching if a match with no update is found
            if stop_early:
                break

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

    # Sort the bills by updateDateIncludingText in descending order
    all_bills = sort_bills_by_date(all_bills)

    # Save the updated and sorted data
    if updated:
        save_data(all_bills)

    if all_bills:
        print(f"Data updated successfully. Last updated bill: {all_bills[0]['updateDate']}")
    else:
        print("No data available.")


# Run the update function
fetch_and_update_data()