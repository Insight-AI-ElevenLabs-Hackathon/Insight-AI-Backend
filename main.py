import requests
import json

# Replace with your actual API key
api_key = "TNMSLQibAQP7Lf0NFvypJn5dd8F8hZbwMdyo2Szz"

url = "https://api.congress.gov/v3/bill"

params = {
    "format": "json",
    "offset": 0,
    "limit": 250,
    "fromDateTime": "2024-04-06T00:00:00Z",
    "toDateTime": "2024-10-03T23:59:59Z",
    "sort": "updateDate+asc",
    "api_key": api_key
}

response = requests.get(url, params=params)

if response.status_code == 200:
    data = response.json()
    for bill in data["bills"]:
        print(f"Bill Title: {bill['title']}")
        print(f"Latest Action: {bill['latestAction']['text']}")
        print("-" * 20)
else:
    print(f"Error: {response.status_code}")
    print(response.text)