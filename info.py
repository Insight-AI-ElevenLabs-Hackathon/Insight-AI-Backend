import requests
import re
import json

# Replace with your actual API key
api_key = "TNMSLQibAQP7Lf0NFvypJn5dd8F8hZbwMdyo2Szz"

# Define API parameters
params = {
    "format": "json",
    "api_key": api_key,
}

# Construct the base API URLs
base_bill_url = "https://api.congress.gov/v3/bill"
base_text_url = "https://api.congress.gov/v3/bill"  # Same base URL, different endpoint

# Specify the bill details
congress = "118"
bill_type = "hr"
bill_number = "7848"

# Construct the complete API URLs
bill_url = f"{base_bill_url}/{congress}/{bill_type}/{bill_number}"
text_url = f"{base_text_url}/{congress}/{bill_type}/{bill_number}/text"


def get_bill_info(bill_url, params):
    """Retrieves and prints bill information from the API."""
    try:
        response_bill = requests.get(bill_url, params=params)
        response_bill.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

        bill_data = response_bill.json()["bill"]

        print(f"Title: {bill_data['title']} ({bill_data['number']})")
        print(f"Introduced Date: {bill_data['introducedDate']}")
        print(f"Latest Action: {bill_data['latestAction']['text']} ({bill_data['latestAction']['actionDate']})")
        print(f"Origin: {bill_data['originChamber']}")

        # Check if policyArea exists before accessing
        if "policyArea" in bill_data:
            print(f"Policy Area: {bill_data['policyArea']['name']}")

        # Check if sponsors list is not empty before accessing
        if bill_data['sponsors']:
            print(f"Sponsor: {bill_data['sponsors'][0]['fullName']} (ID: {bill_data['sponsors'][0]['bioguideId']})")

        return bill_data

    except requests.exceptions.RequestException as e:
        print(f"Error getting bill information: {e}")
        return None


def get_bill_text_links(text_url, params):
    """Retrieves bill text and extracts .htm links."""
    try:
        response_text = requests.get(text_url, params=params)
        response_text.raise_for_status()

        text_data = json.dumps(response_text.json())

        htm_links = re.findall(r'https://www\.congress\.gov/\S+\.htm', text_data)

        print("HTM Links:", htm_links)
        return htm_links

    except requests.exceptions.RequestException as e:
        print(f"Error getting bill text: {e}")
        return []


# --- Main execution ---
if __name__ == "__main__":
    bill_info = get_bill_info(bill_url, params)
    if bill_info:
        get_bill_text_links(text_url, params) 