import requests
import json
import base64
import os
import openai


client = openai.OpenAI(
    base_url="https://api.cerebras.ai/v1",
    api_key=os.environ.get("CEREBRAS_API_KEY")
)

def generate_speech(content):
    """Generates a narrative speech from the given content."""

    intructions = """
    Your task is to convert given content into a narrative speech 
    so that anyone can understand the information easily.
    Avoid all the legislative jargon to make it simpler for normal users 
    to understand.
    """

    completion = client.chat.completions.create(
      model="llama3.1-70b",
      temperature=0.7,
      stream=False,
      messages=[
        {"role": "system", "content": intructions},
        {"role": "user", "content": content} 
      ],
      
    )

    return completion.choices[0].message.content


def generate_audio(text):
    """Generates audio and SRT subtitles from the given text."""

    voice_id="21m00Tcm4TlvDq8ikWAM" 

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"

    headers = {
        "Content-Type": "application/json",
        "xi-api-key": os.getenv("ELEVENLABS_API_KEY")
    }

    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75
        }
    }

    response = requests.post(url, json=data, headers=headers)

    if response.status_code != 200:
        raise Exception(
            f"Error encountered, status: {response.status_code}, content: {response.text}")

    response_dict = json.loads(response.content.decode("utf-8"))

    audio_bytes = base64.b64decode(response_dict["audio_base64"])
    timestamps = response_dict['alignment']

    # Convert timestamps to SRT format
    srt_subtitles = ""
    for i, segment in enumerate(timestamps):
        start_time_ms = segment['start']
        end_time_ms = segment['end']

        # Convert milliseconds to SRT timestamp format (HH:MM:SS,mmm)
        start_time_srt = milliseconds_to_srt_timestamp(start_time_ms)
        end_time_srt = milliseconds_to_srt_timestamp(end_time_ms)

        srt_subtitles += f"{i+1}\n"
        srt_subtitles += f"{start_time_srt} --> {end_time_srt}\n"
        srt_subtitles += f"{segment['text']}\n\n"

    return audio_bytes, srt_subtitles


def milliseconds_to_srt_timestamp(milliseconds):
    """Converts milliseconds to SRT timestamp format (HH:MM:SS,mmm)."""
    seconds, milliseconds = divmod(milliseconds, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def main(content):
    """Takes content, generates speech, generates audio, and saves files."""

    speech_text = generate_speech(content)
    print("Generated Speech Text:\n", speech_text) 

    audio_data, subtitles = generate_audio(speech_text)

    # Save the audio file
    with open('output.mp3', 'wb') as f:
        f.write(audio_data)

    # Save the subtitles to a file
    with open('output.srt', 'w') as f:
        f.write(subtitles)

    print("Audio and subtitles generated successfully!")


if __name__ == "__main__":
    input_content = (
        "The quick brown fox jumps over the lazy dog. "
        "This is a test sentence to demonstrate the functionality."
    )
    main(input_content)