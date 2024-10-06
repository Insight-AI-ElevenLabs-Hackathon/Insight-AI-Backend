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
R2_BILLS_FILE_KEY = "bills.json"  # File key for bills
R2_LAWS_FILE_KEY = "laws.json"  # File key for laws

# API endpoint and parameters
base_url_bills = "https://api.congress.gov/v3/bill/118"
base_url_laws = "https://api.congress.gov/v3/law/118"  # Changed to law
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


def load_existing_data(file_key, item_type="bill"):
    """Load existing data from Cloudflare R2."""
    try:
        response = s3.get_object(Bucket=R2_BUCKET, Key=file_key)
        data = json.loads(response['Body'].read())
        return data.get(item_type + "s", [])  # Access "bills" or "laws" key
    except s3.exceptions.NoSuchKey:
        print(f"Data file {file_key} not found in R2. Starting fresh.")
        return []
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error loading existing data from {file_key}: {e}. Starting fresh.")
        return []


def save_data(items, file_key, item_type="bill"):
    """Save the updated and sorted data to Cloudflare R2."""
    try:
        s3.put_object(
            Bucket=R2_BUCKET,
            Key=file_key,
            Body=json.dumps({item_type + "s": items}, indent=4)  # Save under "bills" or "laws"
        )
        print(f"Data saved successfully to R2 ({file_key}). Total {item_type}s: {len(items)}")
    except (BotoCoreError, NoCredentialsError) as e:
        print(f"Error saving data to R2 ({file_key}): {e}")


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


def update_items(existing_items, new_items, key_field="number"):
    """Update the existing items with new data and stop if a match without updates is found."""
    updated = False
    for new_item in new_items:
        found_match = False
        for i, existing_item in enumerate(existing_items):
            if new_item[key_field] == existing_item[key_field]:
                if new_item["updateDate"] > existing_item["updateDate"]:
                    existing_items[i] = new_item  # Update existing item
                    print(f"Updated item: {new_item[key_field]}")
                    updated = True
                found_match = True
                break
        if not found_match:
            existing_items.insert(0, new_item)  # Add new item at the beginning
            updated = True
            print(f"Added new item: {new_item[key_field]}")
        elif found_match and not updated:
            # If a matching item is found and no updates were needed, stop further processing
            print("Match found with no updates needed. Stopping early to avoid unnecessary downloads.")
            return updated, True

    return updated, False


def sort_items_by_date(items):
    """Sort items by updateDateIncludingText in descending order."""
    return sorted(items, key=lambda item: item['updateDateIncludingText'], reverse=True)


def fetch_and_update_data(base_url, file_key, item_type="bill"):
    """Fetches data from the API and updates the existing data in Cloudflare R2."""

    # Load existing data
    all_items = load_existing_data(file_key, item_type)

    # Get the last update date from the existing data (or a default date)
    if all_items:
        last_update_date = datetime.fromisoformat(all_items[0]["updateDate"])
    else:
        last_update_date = datetime(2024, 4, 7)  # Default start date

    # Set fromDateTime parameter based on the last update date
    params["fromDateTime"] = (last_update_date + timedelta(seconds=1)).isoformat() + "Z"

    url = base_url
    updated = False

    with tqdm(desc=f"Updating {item_type}s", unit=item_type) as pbar:
        while url:
            data = fetch_data_from_api(url, params)
            if data is None:
                break  # Exit if the request failed

            new_items = data.get("bills" if item_type == "bill" else "laws", [])  # Get bills or laws
            if not new_items:
                print(f"No new {item_type}s found.")
                break

            # Check for matching items and update/add as needed
            updated, stop_early = update_items(all_items, new_items)

            # Stop fetching if a match with no update is found
            if stop_early:
                break

            # Update progress bar
            pbar.update(len(new_items))

            # Get the next page URL
            pagination = data.get("pagination")
            if pagination and pagination.get("next"):
                url = pagination["next"]
                url += f"&api_key={params['api_key']}"
                time.sleep(1)
            else:
                url = None

    # Sort the items by updateDateIncludingText in descending order
    all_items = sort_items_by_date(all_items)

    # Save the updated and sorted data
    if updated:
        save_data(all_items, file_key, item_type)  # Pass item_type to save_data

    if all_items:
        print(f"Data updated successfully. Last updated {item_type}: {all_items[0]['updateDate']}")
    else:
        print(f"No {item_type} data available.")


# Run the update function for bills and laws
fetch_and_update_data(base_url_bills, R2_BILLS_FILE_KEY, "bill")
fetch_and_update_data(base_url_laws, R2_LAWS_FILE_KEY, "law")