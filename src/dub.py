import os
import time

import boto3
import requests

s3 = boto3.client(
    's3',
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
)


def start_dub(source_url, name, target_language):
    url = "https://api.elevenlabs.io/v1/dubbing"

    headers = {
        "xi-api-key": os.getenv("ELEVENLABS_API_KEY") 
    }

    data = {
        "name": name,
        "source_url": source_url,
        "source_lang": "en",
        "target_lang": target_language,
        "num_speakers": "1",
        "watermark": "false",
        "highest_resolution": "true",
        "drop_background_audio": "false",
        "use_profanity_filter": "false"
    }

    response = requests.post(url, headers=headers, data=data)
    return response.json()

def get_dub_status(dubbing_id):
    url = f"https://api.elevenlabs.io/v1/dubbing/{dubbing_id}"

    headers = {
        "xi-api-key": os.getenv("ELEVENLABS_API_KEY")
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()["status"]

def get_dub_transcript(dubbing_id, language_code):
    url = f"https://api.elevenlabs.io/v1/dubbing/{dubbing_id}/transcript/{language_code}?format_type=srt"

    headers = {
        "xi-api-key": os.getenv("ELEVENLABS_API_KEY")
    }

    response = requests.get(url, headers=headers) 
    response.raise_for_status() 
    return response.text

def get_dubbed_file(dubbing_id, language_code):
    url = f"https://api.elevenlabs.io/v1/dubbing/{dubbing_id}/audio/{language_code}"

    headers = {
        "xi-api-key": os.getenv("ELEVENLABS_API_KEY")
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.content

def upload_to_r2(name, target_lang, transcript, audio_content):

    s3.put_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=f"{name}_{target_lang}.srt", Body=transcript)

    s3.put_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=f"{name}_{target_lang}.mp3", Body=audio_content)

def file_exists_in_r2(name, target_lang):
    try:
        s3.head_object(Bucket=os.getenv("R2_BUCKET_NAME"), Key=f"{name}_{target_lang}.mp3")
        return True
    except:
        return False

def dub(file_url, name, target_lang):
    # Check if the file already exists in R2
    if file_exists_in_r2(name, target_lang):
        print(f"File {name}_{target_lang}.mp3 already exists in R2. Skipping dubbing.")
        return

    dub_info = start_dub(file_url, name, target_lang)
    dubbing_id = dub_info["dubbing_id"]

    timeout = 150
    start_time = time.time()

    while True:

        status = get_dub_status(dubbing_id)

        if status == "dubbed":
            break
        elif status == "failed":
            raise Exception("Dubbing failed")
        elif time.time() - start_time > timeout:
            raise TimeoutError("Dubbing timed out")

        time.sleep(5)

    transcript = get_dub_transcript(dubbing_id, target_lang)
    audio_content = get_dubbed_file(dubbing_id, target_lang)

    upload_to_r2(name, target_lang, transcript, audio_content) 