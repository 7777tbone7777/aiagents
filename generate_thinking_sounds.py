#!/usr/bin/env python3
"""
Generate thinking sound audio clips using ElevenLabs
Run this once to create the audio files
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")

# Create directory for thinking sounds
os.makedirs("static/thinking_sounds", exist_ok=True)

# Different thinking sounds to generate
thinking_sounds = {
    "hmm": "Hmm",
    "um": "Um",
    "uh": "Uh",
    "let_me_see": "Let me see",
    "okay": "Okay"
}

def generate_sound(text, filename):
    """Generate a thinking sound using ElevenLabs"""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}/stream"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": ELEVENLABS_API_KEY
    }

    data = {
        "text": text,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.8,
            "style": 0.5,
            "use_speaker_boost": True
        }
    }

    print(f"Generating '{text}'...")
    response = requests.post(url, json=data, headers=headers, stream=True)

    if response.status_code == 200:
        filepath = f"static/thinking_sounds/{filename}.mp3"
        with open(filepath, 'wb') as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
        print(f"✓ Saved to {filepath}")
        return True
    else:
        print(f"✗ Error: {response.status_code} - {response.text}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("GENERATING THINKING SOUNDS FOR BOLT")
    print("=" * 60)

    if not ELEVENLABS_API_KEY:
        print("✗ Error: ELEVENLABS_API_KEY not found in .env")
        exit(1)

    if not VOICE_ID:
        print("✗ Error: ELEVENLABS_VOICE_ID not found in .env")
        exit(1)

    print(f"Using voice ID: {VOICE_ID}")
    print()

    success_count = 0
    for filename, text in thinking_sounds.items():
        if generate_sound(text, filename):
            success_count += 1
        print()

    print("=" * 60)
    print(f"✓ Generated {success_count}/{len(thinking_sounds)} thinking sounds")
    print("=" * 60)
    print("\nNext: Restart bolt_platform.py to use the new sounds!")
