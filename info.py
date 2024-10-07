import requests
import os
import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory
import re
import json
import hashlib
import http.client

session = requests.Session()

def process_bill_url(url):
    """Processes a bill URL and returns a JSON object with bill info and summary."""
    try:
        # Check if bill info already exists in KV
        existing_bill_info = get_bill_info_from_kv(url)
        if existing_bill_info:
            print("Bill info retrieved from KV.")
            return existing_bill_info

        # Extract bill info from URL
        congress, bill_type, bill_number = extract_bill_info_from_url(url)

        # Get bill information
        bill_info = get_bill_info(congress, bill_type, bill_number)
        if not bill_info:
            return {'error': 'Failed to retrieve bill information'}

        # Get and summarize bill text
        htm_links = get_bill_text_links(congress, bill_type, bill_number)
        bill_info['summary'] = summarize_bill_text(htm_links) if htm_links else "No HTML links found for bill text."

        # Store bill info in KV
        store_bill_info_in_kv(bill_info, url)

        return bill_info

    except ValueError as e:
        return {'error': str(e)}
    except requests.exceptions.RequestException as e:
        return {'error': f'API request error: {e}'}
    except Exception as e:
        return {'error': f'An unexpected error occurred: {e}'}

# Helper functions

def configure_generative_model():
    """Configures the generative AI model for summarization."""
    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    return genai.GenerativeModel(
        model_name="gemini-1.5-flash-exp-0827",
        generation_config={
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 64,
            "max_output_tokens": 1000,
            "response_mime_type": "text/plain",
        },
        safety_settings={
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
        },
        system_instruction=(
            "Your task is to analyze the legislative data provided to you and rewrite it into a detailed summary without any legislative jargon "
            "so that a normal citizen can understand what it is about. Be clear and concise. Write a 5-7 point summary."
        ),
    )

# Cache the model configuration for reuse
model = configure_generative_model()

def get_api_params():
    """Returns the common API parameters for requests."""
    return {
        "format": "json",
        "api_key": os.getenv("CONGRESS_API_KEY"),
    }

def get_bill_info(congress, bill_type, bill_number):
    """Retrieves information about a specific bill."""
    bill_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}"
    params = get_api_params()
    try:
        response = session.get(bill_url, params=params)
        response.raise_for_status()
        bill_data = response.json().get("bill", {})
        return parse_bill_info(bill_data)
    except requests.exceptions.RequestException as e:
        print(f"Error getting bill information: {e}")
        return None

def parse_bill_info(bill_data):
    """Parses bill information from API response data."""
    info = {
        "title": bill_data.get("title"),
        "number": bill_data.get("number"),
        "introduced_date": bill_data.get("introducedDate"),
        "latest_action": bill_data.get("latestAction", {}).get("text"),
        "latest_action_date": bill_data.get("latestAction", {}).get("actionDate"),
        "origin_chamber": bill_data.get("originChamber"),
        "policy_area": bill_data.get("policyArea", {}).get("name"),
        "sponsor": bill_data.get("sponsors", [{}])[0].get("fullName"),
        "sponsor_id": bill_data.get("sponsors", [{}])[0].get("bioguideId"),
        "type": "bill"
    }

    if "laws" in bill_data and bill_data["laws"]:
        info["type"] = "law"
        info["law_number"] = bill_data["laws"][0].get("number")
        info["law_type"] = bill_data["laws"][0].get("type")

    return info

def get_bill_text_links(congress, bill_type, bill_number):
    """Gets links to the HTML content of the bill text."""
    text_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/text"
    params = get_api_params()
    try:
        response = session.get(text_url, params=params)
        response.raise_for_status()
        text_data = json.dumps(response.json())
        return re.findall(r'https://www\.congress\.gov/\S+\.htm', text_data)
    except requests.exceptions.RequestException as e:
        print(f"Error getting bill text: {e}")
        return []

def summarize_bill_text(htm_links):
    """Loads and summarizes the content of the bill text."""
    combined_content = ""
    for link in htm_links:
        try:
            response = session.get(link)
            response.raise_for_status()
            combined_content += response.text + "\n\n" 
        except requests.exceptions.RequestException as e:
            print(f"Error loading {link}: {e}")

    if combined_content:
        summary = model.generate_content(combined_content)
        return summary.text if summary else "No summary generated."
    else:
        return "No content available for summarization."

def extract_bill_info_from_url(url):
    """Extracts congress, bill type, and bill number from a congress.gov or api.congress.gov URL."""
    pattern = r"https?://(?:www\.)?congress\.gov/bill/(\d+)(?:th|rd|nd|st)-congress/(senate|house)-bill/(\d+)"
    match = re.search(pattern, url)

    if match:
        congress = match.group(1)
        bill_type = "s" if match.group(2) == "senate" else "hr"
        bill_number = match.group(3)
        return congress, bill_type, bill_number
    else:
        raise ValueError("Invalid URL format. Must be a Congress.gov URL.")

def generate_uid_from_url(url):
    """Generates a unique ID (UID) from a URL using SHA-256 hashing."""
    return hashlib.sha256(url.encode('utf-8')).hexdigest()

def store_bill_info_in_kv(bill_info, url):
    """Stores bill information in Cloudflare Workers KV using the API."""
    uid = generate_uid_from_url(url)

    conn = http.client.HTTPSConnection("api.cloudflare.com")

    payload = json.dumps(bill_info)

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"
    }

    api_url = f"/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/storage/kv/namespaces/{os.environ['CLOUDFLARE_KV_NAMESPACE_ID']}/values/{uid}"

    conn.request("PUT", api_url, payload, headers)

    res = conn.getresponse()
    data = res.read()

    if res.status == 200:
        print(f"Successfully stored bill info with UID: {uid}")
    else:
        print(f"Error storing bill info: {data.decode('utf-8')}")

def get_bill_info_from_kv(url):
    """Retrieves bill information from Cloudflare Workers KV if it exists."""
    uid = generate_uid_from_url(url)

    conn = http.client.HTTPSConnection("api.cloudflare.com")

    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"
    }

    api_url = f"/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/storage/kv/namespaces/{os.environ['CLOUDFLARE_KV_NAMESPACE_ID']}/values/{uid}"

    conn.request("GET", api_url, headers=headers)

    res = conn.getresponse()
    data = res.read()

    if res.status == 200:
        return json.loads(data.decode("utf-8"))
    elif res.status == 404:
        return None
    else:
        print(f"Error retrieving bill info from KV: {data.decode('utf-8')}")
        return None