import json
import os
import boto3
from botocore.exceptions import ClientError

# Cloudflare R2 Configuration (AWS S3 Compatible)
R2_ACCESS_KEY = os.getenv("R2_ACCESS_KEY")
R2_SECRET_KEY = os.getenv("R2_SECRET_KEY")
R2_ENDPOINT = os.getenv("R2_ENDPOINT")
R2_BUCKET_NAME = "elevenlabs-hackathon"
R2_BILLS_KEY = "bills.json"
R2_LAWS_KEY = "laws.json"
R2_DATA_KEY = "data.json"

# Initialize S3 Client for R2
s3_client = boto3.client(
    "s3",
    aws_access_key_id=R2_ACCESS_KEY,
    aws_secret_access_key=R2_SECRET_KEY,
    endpoint_url=R2_ENDPOINT,
)


def load_data_from_r2(key):
    """Loads JSON data from a specified key in the R2 bucket."""
    try:
        response = s3_client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        return json.loads(response["Body"].read())
    except ClientError as e:
        print(f"Error loading data from R2 (key: {key}): {e}")
        return None


def get_top_items(data, item_type, count=10):
    """Extracts the top 'count' items based on updateDateIncludingText or updateDate."""
    if data and item_type + "s" in data:
        items = data[item_type + "s"]
        sort_key = (
            "updateDateIncludingText"
            if "updateDateIncludingText" in items[0]
            else "updateDate"
        )
        sorted_items = sorted(items, key=lambda item: item[sort_key], reverse=True)
        return [
            {
                "congress": item["congress"],
                "number": item["number"],
                "title": item["title"],
                "type": item["type"],
                "updateDate": item["updateDate"],
                "url": item["url"],
                **({"laws": item["laws"]} if item_type == "law" and "laws" in item else {}),
            }
            for item in sorted_items[:count]
        ]
    return []


def update_data_in_r2(data, key):
    """Updates or creates a JSON file in the R2 bucket with the provided data."""
    try:
        s3_client.put_object(
            Bucket=R2_BUCKET_NAME, Key=key, Body=json.dumps(data, indent=4).encode("utf-8")
        )
        print(f"Data successfully updated/created in R2 (key: {key})")
    except ClientError as e:
        print(f"Error updating/creating data in R2 (key: {key}): {e}")


def main():
    """Loads bills and laws data, extracts top items, and updates data.json in R2."""
    bills_data = load_data_from_r2(R2_BILLS_KEY)
    laws_data = load_data_from_r2(R2_LAWS_KEY)

    top_bills = get_top_items(bills_data, "bill")
    top_laws = get_top_items(laws_data, "bill")

    data_to_save = {"top_bills": top_bills, "top_laws": top_laws}
    update_data_in_r2(data_to_save, R2_DATA_KEY)


if __name__ == "__main__":
    main()