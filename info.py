import requests
import os
import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory
import re
import json

def process_bill_url(url):
    """Processes a bill URL and returns a JSON object with bill info and summary."""
    try:
        # Extract bill info from URL
        congress, bill_type, bill_number = extract_bill_info_from_url(url)

        # Get bill information
        bill_info = get_bill_info(congress, bill_type, bill_number)

        if bill_info:
            htm_links = get_bill_text_links(congress, bill_type, bill_number)
            if htm_links:
                bill_info['summary'] = summarize_bill_text(htm_links)
            else:
                bill_info['summary'] = "No HTML links found for bill text."

            return bill_info
        else:
            return {'error': 'Failed to retrieve bill information'}

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
            "Your task is to analyze the legislative data provided to you and rewrite it into a detailed summary without any legislative jargon \
                so that a normal citizen can understand what it is about. Be clear and concise. Write a 5-7 point summary."
        ),
    )


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
        response = requests.get(bill_url, params=params)
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
        # Add a field to indicate whether it's a bill or law
        "bill_or_law": "bill"  # Default to "bill"
    }

    # Check if the bill has become a law
    if "laws" in bill_data and bill_data["laws"]:
        info["bill_or_law"] = "law"
        info["law_number"] = bill_data["laws"][0].get("number")
        info["law_type"] = bill_data["laws"][0].get("type")

    return info


def get_bill_text_links(congress, bill_type, bill_number):
    """Gets links to the HTML content of the bill text."""
    text_url = f"https://api.congress.gov/v3/bill/{congress}/{bill_type}/{bill_number}/text"
    params = get_api_params()
    try:
        response = requests.get(text_url, params=params)
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
            response = requests.get(link)
            response.raise_for_status()
            combined_content += response.text + "\n\n" 
        except requests.exceptions.RequestException as e:
            print(f"Error loading {link}: {e}")

    if combined_content:
        model = configure_generative_model()
        summary = model.generate_content(combined_content)
        return summary.text if summary else "No summary generated."
    else:
        return "No content available for summarization."


def extract_bill_info_from_url(url):
    """Extracts congress, bill type, and bill number from a congress.gov or api.congress.gov URL."""
    pattern = r"(?:https?://(?:www\.)?congress\.gov/bill/(\d+)(?:th|rd|nd|st)-congress/(?:senate|house)-bill/(\d+)|https?://api\.congress\.gov/v3/bill/(\d+)/(hr|s)/(\d+))"
    match = re.search(pattern, url)

    if match:
        if match.group(1):  # Congress.gov URL
            congress = match.group(1)
            bill_type = "s" if "senate" in url else "hr"
            bill_number = match.group(2)
        else:  # API URL
            congress = match.group(3)
            bill_type = match.group(4)
            bill_number = match.group(5)
        return congress, bill_type, bill_number
    else:
        raise ValueError("Invalid URL format. Must be a Congress.gov or API URL.")