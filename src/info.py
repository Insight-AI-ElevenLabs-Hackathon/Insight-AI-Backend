import hashlib
import http.client
import json
import logging
import os
import re
from functools import lru_cache
from src.audio import audio

import google.generativeai as genai
import requests
from google.generativeai.types import HarmBlockThreshold, HarmCategory

# Constants
GOVINFO_API_KEY = os.getenv("GOVINFO_API_KEY")
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
CLOUDFLARE_API_TOKEN = os.environ["CLOUDFLARE_API_TOKEN"]
CLOUDFLARE_ACCOUNT_ID = os.environ["CLOUDFLARE_ACCOUNT_ID"]
CLOUDFLARE_KV_NAMESPACE_ID = os.environ["CLOUDFLARE_KV_NAMESPACE_ID"]

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure session for API requests
session = requests.Session()

def process_bill_url(url):
    """Process a bill URL and return a JSON object with bill info, summary, and audio files."""
    try:
        if not is_valid_govinfo_url(url):
            raise ValueError("Invalid URL format. Must be a Govinfo API URL.")

        # Check KV for existing entry before doing anything else
        uid = generate_uid_from_url(url)
        if existing_info := get_bill_info_from_kv(uid):
            return existing_info

        bill_type = get_bill_type_from_url(url)  # Determine if it's a bill or law

        if bill_type == "bill":
            bill_info = get_bill_info(url)  # No need for download_links anymore
        elif bill_type == "law":
            bill_info = get_law_info(url)  # No need for download_links anymore
        else:
            return {'error': 'Unsupported bill type'}

        if not bill_info:
            return {'error': 'Failed to retrieve bill information'}

        # Construct htm and pdf links directly from the input URL
        base_url = url.replace("/summary", "")
        htm_link = f"{base_url}/htm?api_key={GOVINFO_API_KEY}"
        pdf_link = f"{base_url}/pdf?api_key={GOVINFO_API_KEY}"

        summary, _ = summarize_bill_text(htm_link, url)  # UID already generated
        bill_info['summary'] = summary

        # Add download links to bill_info
        bill_info['htm_link'] = htm_link
        bill_info['pdf_link'] = pdf_link

        # Generate audio and subtitles
        audio_path, srt_path = audio(summary, uid)
        if audio_path and srt_path:
            bill_info['audio_path'] = audio_path
            bill_info['srt_path'] = srt_path
        else:
            bill_info['audio_path'] = None
            bill_info['srt_path'] = None
            logger.warning("Failed to generate audio and subtitles")

        # Add json_type to the final output
        bill_info['json_type'] = bill_type
        bill_info['id'] = uid

        store_bill_info_in_kv(bill_info, url)
        return bill_info

    except ValueError as e:
        logger.error(f"Value error: {e}")
        return {'error': str(e)}
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return {'error': f'API request error: {e}'}
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {'error': f'An unexpected error occurred: {e}'}


def get_bill_info(url):
    """Retrieve information about a specific bill from Govinfo API."""
    try:
        response = session.get(f"{url}?api_key={GOVINFO_API_KEY}")
        response.raise_for_status()
        return parse_bill_info(response.json())  # Return only bill_info
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting bill information: {e}")
        return None


def parse_bill_info(bill_data):
    """Parse bill information from Govinfo API response data (for bills)."""
    info = {
        "introduced_date": bill_data.get("dateIssued"),
        "origin_chamber": bill_data.get("originChamber"),
        "currentChamber": bill_data.get("currentCHamber"),
        "session": bill_data.get("session"),
        "policy_area": bill_data.get("branch"),
        "type": "bill",  # Explicitly set type to "bill"
    }

    if members := bill_data.get("members"):
        sponsor = members[0]
        info.update({
            "sponsor": sponsor.get("memberName"),
            "sponsor_state": sponsor.get("state"),
            "sponsor_party": sponsor.get("party"),
            "sponsor_id": sponsor.get("bioGuideId"),
        })

    return info  # Return only bill_info


def get_law_info(url):
    """Retrieve information about a specific law from Govinfo API."""
    try:
        response = session.get(f"{url}?api_key={GOVINFO_API_KEY}")
        response.raise_for_status()
        return parse_law_info(response.json())  # Return only law_info
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting law information: {e}")
        return None


def parse_law_info(law_data):
    """Parse law information from Govinfo API response data (for laws)."""
    info = {
        "law_type": law_data.get("documentType"),
        "dateIssued": law_data.get("dateIssued"),
        "policy_area": law_data.get("branch")
    }

    return info  # Return only law_info


def summarize_bill_text(htm_link, url):
    """Load and summarize the content of the bill text."""
    try:
        response = session.get(htm_link)
        response.raise_for_status()
        if response.text:
            summary = generate_summary(response.text)
            uid = generate_uid_from_url(url)
            return summary, uid
        return "No content available for summarization.", None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error loading {htm_link}: {e}")
        return "Error loading bill text for summarization.", None


@lru_cache(maxsize=1)
def get_model():
    """Configure and return the generative AI model for summarization."""
    genai.configure(api_key=GEMINI_API_KEY)
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
        system_instruction="""
        1. Analyze the provided legislative data and rewrite it into a clear, detailed summary that any citizen can easily understand.
        2. Explain what are the changes that are happening with this bill/law/amendment.
        3. Stay neutral about the political views and simply be an effective summarizer for normal citizens.
        4. Avoid legislative jargon and focus on simplifying complex terms.
        5. Provide a summary in 5 to 7 bullet points, being concise and highlighting the key aspects.

        Respond in markdown format. Do not add any pretext and greetings at the end or beginning of the summary.
        Just return the points.
        Do not include any backticks (```) for formatting.
        """
    )


def generate_summary(text):
    """Generate a summary using the AI model."""
    model = get_model()
    summary = model.generate_content(text)
    return summary.text if summary else "No summary generated."


def is_valid_govinfo_url(url):
    """Check if the URL is a valid Govinfo API URL for bills or laws."""
    pattern = r"https?://api.govinfo.gov/packages/(BILLS|PLAW)-\S+/summary$"
    return bool(re.match(pattern, url))


def get_bill_type_from_url(url):
    """Determine if the URL refers to a bill or a law."""
    if "BILLS" in url:
        return "bill"
    elif "PLAW" in url:
        return "law"
    else:
        return None


def generate_uid_from_url(url):
    """Generate a unique ID (UID) from a URL using SHA-256 hashing."""
    return hashlib.sha256(url.encode('utf-8')).hexdigest()

def store_bill_info_in_kv(bill_info, url):
    """Store bill information in Cloudflare Workers KV using the API."""
    uid = generate_uid_from_url(url)
    payload = json.dumps(bill_info)
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {CLOUDFLARE_API_TOKEN}"
    }
    api_url = f"/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/{CLOUDFLARE_KV_NAMESPACE_ID}/values/{uid}"

    conn = http.client.HTTPSConnection("api.cloudflare.com")
    conn.request("PUT", api_url, payload, headers)
    res = conn.getresponse()
    if res.status == 200:
        logger.info(f"Successfully stored bill info with UID: {uid}")
    else:
        logger.error(f"Error storing bill info: {res.read().decode('utf-8')}")


def get_bill_info_from_kv(uid):
    """Retrieve bill information from Cloudflare Workers KV if it exists."""
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {CLOUDFLARE_API_TOKEN}"
    }
    api_url = f"/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/storage/kv/namespaces/{CLOUDFLARE_KV_NAMESPACE_ID}/values/{uid}"

    conn = http.client.HTTPSConnection("api.cloudflare.com")
    conn.request("GET", api_url, headers=headers)
    res = conn.getresponse()
    if res.status == 200:
        print("Loaded Info from KV")
        return json.loads(res.read().decode("utf-8"))
    elif res.status == 404:
        return None
    else:
        logger.error(f"Error retrieving bill info from KV: {res.read().decode('utf-8')}")
        return None