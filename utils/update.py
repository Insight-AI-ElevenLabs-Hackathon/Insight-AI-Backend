import requests
import json
import time
import os
from tqdm import tqdm
from datetime import datetime, timedelta
from requests.exceptions import RequestException, ConnectionError, HTTPError
import boto3
from botocore.exceptions import BotoCoreError, NoCredentialsError
import random

# Cloudflare R2 (AWS S3 compatible) configuration
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_BUCKET = "elevenlabs-hackathon"
R2_PACKAGES_FILE_KEY = "bills.json"

# API endpoint and parameters
base_url = "https://api.govinfo.gov/collections/BILLS/2018-01-28T20%3A18%3A10Z"
params = {
    "pageSize": 1000,
    "congress": 118,
    "offsetMark": "*",
    "api_key": "He7pQCphxtdIziKbNImyaDlelS2W5oXwgb8qKtg4"
}

# Initialize S3 client
s3 = boto3.client(
    's3',
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    endpoint_url=R2_ENDPOINT
)

def load_existing_data(file_key):
    """Load existing data from Cloudflare R2."""
    try:
        response = s3.get_object(Bucket=R2_BUCKET, Key=file_key)
        data = json.loads(response['Body'].read())
        return data.get("packages", [])
    except s3.exceptions.NoSuchKey:
        print(f"Data file {file_key} not found in R2. Starting fresh.")
        return []
    except (KeyError, json.JSONDecodeError) as e:
        print(f"Error loading existing data from {file_key}: {e}. Starting fresh.")
        return []

def save_data(items, file_key):
    """Save the updated and sorted data to Cloudflare R2."""
    try:
        s3.put_object(
            Bucket=R2_BUCKET,
            Key=file_key,
            Body=json.dumps({"packages": items}, indent=4)
        )
        print(f"Data saved successfully to R2 ({file_key}). Total packages: {len(items)}")
    except (BotoCoreError, NoCredentialsError) as e:
        print(f"Error saving data to R2 ({file_key}): {e}")

def fetch_data_from_api(url, params, retries=3):
    """Fetch data from the API and handle rate limiting with retries and exponential backoff."""
    attempt = 0
    backoff_time = 2  # Initial backoff time in seconds

    while attempt < retries:
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()

            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", 60))
                print(f"Rate limited! Retrying after {retry_after} seconds...")
                time.sleep(retry_after)
                continue

            return response.json()

        except HTTPError as e:
            if e.response.status_code == 500:
                print(f"Server error (500) on attempt {attempt + 1}: {e}. Increasing backoff time...")
                backoff_time *= 4  # More aggressive backoff for 500 errors
            else:
                print(f"HTTP error or timeout on attempt {attempt + 1}: {e}. Retrying in {backoff_time} seconds...")
                backoff_time *= 2
            time.sleep(backoff_time + random.uniform(0, 1))  # Jitter
            attempt += 1

        except ConnectionError as e:
            print(f"Connection error on attempt {attempt + 1}: {e}. Retrying in {backoff_time} seconds...")
            time.sleep(backoff_time + random.uniform(0, 1))  # Jitter
            backoff_time *= 2
            attempt += 1

        except RequestException as e:
            print(f"Request failed: {e}")
            return None

    print(f"Failed to fetch data after {retries} attempts.")
    return None

def update_items(existing_items, new_items, key_field="packageId"):
    """Update the existing items with new data and stop if a match without updates is found."""
    updated = False  # Flag to indicate if any updates were made
    stop_early = False  # Flag to indicate if a match with no updates was found

    for new_item in new_items:
        found_match = False
        for i, existing_item in enumerate(existing_items):
            if new_item[key_field] == existing_item[key_field]:
                if new_item["lastModified"] > existing_item["lastModified"]:
                    existing_items[i] = new_item  # Update existing item
                    print(f"Updated item: {new_item[key_field]}")
                    updated = True 
                found_match = True
                break  # Exit inner loop if a match is found
        if not found_match:
            existing_items.insert(0, new_item)  # Add new item at the beginning
            updated = True
            print(f"Added new item: {new_item[key_field]}")
        elif found_match and not updated:
            # If a matching item is found and no updates were needed, stop further processing
            print("Match found with no updates needed. Stopping early to avoid unnecessary downloads.")
            stop_early = True
            break # Exit outer loop if no update needed

    return updated, stop_early 

def sort_items_by_date(items):
    """Sort items by lastModified in descending order."""
    return sorted(items, key=lambda item: item['lastModified'], reverse=True)


def fetch_and_update_data(base_url, file_key):
    """Fetches data from the API and updates the existing data in Cloudflare R2."""

    # Load existing data
    all_items = load_existing_data(file_key)

    # Get the last modified date from the existing data (or a default date)
    if all_items:
        last_modified_date = datetime.fromisoformat(all_items[0]["lastModified"].replace("Z", "+00:00"))
    else:
        last_modified_date = datetime(2018, 1, 28, 20, 18, 10)  # Default start date

    # Set fromDateTime parameter based on the last modified date
    params["fromDateTime"] = (last_modified_date + timedelta(seconds=1)).isoformat() + "Z"

    url = base_url
    updated = False

    with tqdm(desc="Updating packages", unit="package") as pbar:
        while url:
            data = fetch_data_from_api(url, params)
            if data is None:
                break  # Exit if the request failed

            new_items = data.get("packages", [])
            if not new_items:
                print("No new packages found.")
                break

            # Check for matching items and update/add as needed
            updated, stop_early = update_items(all_items, new_items)

            # Stop fetching if a match with no update is found
            if stop_early:
                break

            # Update progress bar
            pbar.update(len(new_items))

            # Get the next page URL
            next_page_url = data.get("nextPage")
            if next_page_url:
                # Merge nextPage URL with api_key to avoid duplicates
                url += f"&{params['api_key']}"
            else:
                url = None

            time.sleep(1)

    # Sort the items by lastModified in descending order
    all_items = sort_items_by_date(all_items)

    # Save the updated and sorted data
    if updated:
        save_data(all_items, file_key)

    if all_items:
        print(f"Data updated successfully. Last updated package: {all_items[0]['lastModified']}")
    else:
        print("No package data available.")

# Run the update function for packages
fetch_and_update_data(base_url, R2_PACKAGES_FILE_KEY)