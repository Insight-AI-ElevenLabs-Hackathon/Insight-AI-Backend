import requests
import json
import os
import base64
import openai
import boto3

client = openai.OpenAI(
    base_url="https://api.sambanova.ai/v1",
    api_key=os.environ.get("CEREBRAS_API_KEY")
)

# Configure R2 client
s3 = boto3.client(
    's3',
    endpoint_url=os.getenv("R2_ENDPOINT"),
    aws_access_key_id=os.getenv("R2_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("R2_SECRET_KEY"),
)

def generate_speech(content):
    """Generates a narrative speech from the given content."""

    instructions = """
    Your task is to convert the given summary into a narrative speech optimized for audio generation. Specifically:

    1. Remove special characters, abbreviations, and any miscellaneous information that might cause mispronunciations.
    2. Ensure the text flows naturally, with clear and concise phrasing.
    3. Avoid overly complex sentence structures to maintain listener comprehension.
    4. Keep the length suitable for generating an audio file that is approximately two minutes long.
    5. Return a clean, unformatted text ready for smooth audio narration.
    6. Do not include any greetings, pretext or notes at the beginning or end of the content, the provided response is directly used to generate the response.
    """

    completion = client.chat.completions.create(
        model="Meta-Llama-3.1-405B-Instruct",
        temperature=0.7,
        stream=False,
        messages=[
            {"role": "system", "content": instructions},
            {"role": "user", "content": content}
        ],
    )

    return completion.choices[0].message.content

def generate_audio(text, uid):
    """Generates audio and SRT subtitles, uploads to R2, and returns file paths."""

    print(f"Generating audio for UID: {uid}")

    voice_id = "XrExE9yKIg1WjnnlVkGX"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"

    headers = {
        "Content-Type": "application/json",
        "xi-api-key": os.getenv("ELEVENLABS_API_KEY")
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.7,
            "similarity_boost": 0.75
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise Exception(
            f"Error encountered, status: {response.status_code}, content: {response.text}")

    response_dict = json.loads(response.content.decode("utf-8"))

    print("Full API Response:")
    print(json.dumps(response_dict, indent=2))

    if "audio_base64" not in response_dict:
        print("Warning: 'audio_base64' not found in the API response")
        return None, None

    # Access audio_base64 directly from the response dictionary
    audio_bytes = base64.b64decode(response_dict["audio_base64"])
    
    print("Audio Bytes Generated Successfully!")
    print(f"Audio Bytes Length: {len(audio_bytes)}")

    print("Alignment data:")
    print(json.dumps(response_dict.get('alignment', 'Alignment data not found'), indent=2))

    # Generate SRT subtitles using character-level timestamps
    srt_subtitles = ""
    for i, (char, start_time, end_time) in enumerate(zip(
            response_dict['alignment']['characters'],
            response_dict['alignment']['character_start_times_seconds'],
            response_dict['alignment']['character_end_times_seconds'])):

        start_time_srt = milliseconds_to_srt_timestamp(start_time * 1000)
        end_time_srt = milliseconds_to_srt_timestamp(end_time * 1000)

        srt_subtitles += f"{i+1}\n"
        srt_subtitles += f"{start_time_srt} --> {end_time_srt}\n"
        srt_subtitles += f"{char}\n\n"

    print("SRT subtitles generated successfully")

    print("R2 Environment Variables:")
    print(f"R2_BUCKET_NAME: {os.environ.get('R2_BUCKET_NAME')}")
    print(f"R2_ENDPOINT_URL: {os.environ.get('R2_ENDPOINT_URL')}")

    # Upload audio to R2
    audio_key = f"{uid}_en.mp3"
    try:
        s3.put_object(Bucket=os.environ.get("R2_BUCKET_NAME"),
                      Key=audio_key, Body=audio_bytes)
        print(f"Audio file uploaded successfully: {audio_key}")
    except Exception as e:
        print(f"Error uploading audio file: {str(e)}")
        return None, None

    audio_url = f"{os.environ.get('R2_ENDPOINT_URL')}/{os.environ.get('R2_BUCKET_NAME')}/{audio_key}"

    # Upload subtitles to R2
    srt_key = f"{uid}_en.srt"
    try:
        s3.put_object(Bucket=os.environ.get("R2_BUCKET_NAME"),
                      Key=srt_key, Body=srt_subtitles)
        print(f"SRT file uploaded successfully: {srt_key}")
    except Exception as e:
        print(f"Error uploading SRT file: {str(e)}")
        return None, None

    srt_url = f"{os.environ.get('R2_ENDPOINT_URL')}/{os.environ.get('R2_BUCKET_NAME')}/{srt_key}"

    print(f"Audio URL: {audio_url}")
    print(f"SRT URL: {srt_url}")

    return audio_url, srt_url

def milliseconds_to_srt_timestamp(milliseconds):
    """Converts milliseconds to SRT timestamp format (HH:MM:SS,mmm)."""
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02.0f}:{minutes:02.0f}:{seconds:02.0f},{milliseconds:03.0f}" 

def audio(content, uid):
    print(f"Starting audio generation for UID: {uid}")
    speech_text = generate_speech(content)
    print("Speech text generated successfully")
    audio_url, srt_url = generate_audio(speech_text, uid)
    print("Audio and subtitles generation completed")
    if audio_url and srt_url:
        print("Audio and subtitles uploaded to R2 successfully!")
        return audio_url, srt_url
    else:
        print("Failed to generate or upload audio and subtitles")
        return None, None