#!/usr/bin/env python3
"""
AI Sales Agent (Flask + Twilio + OpenAI + ElevenLabs)

WHAT IT DOES
- /outbound?to=+1XXXXXXXXXX  -> places a call via Twilio
- /voice                      -> Twilio hits this to start the call (greets + Gather speech)
- /ai                         -> Handles user speech, asks OpenAI for the next line, replies via TTS
- /audio/<token>.mp3          -> Streams cached ElevenLabs audio to Twilio <Play>
- /health                     -> quick health check

REQUIRED ENV VARS
  OPENAI_API_KEY=sk-...
  TWILIO_ACCOUNT_SID=AC...
  TWILIO_AUTH_TOKEN=...
  TWILIO_NUMBER=+1XXXXXXXXXX           # your Twilio phone number
  PUBLIC_BASE_URL=https://xxxx.ngrok.app  # public https URL that Twilio can reach
  ELEVENLABS_API_KEY=eleven_...        # (optional; if missing, falls back to <Say>)
  ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM (default Rachel)
  AGENT_NAME="Ava"
  COMPANY_NAME="XR Pay"
  PRODUCT_PITCH="""One-liner value prop..."""
  DO_NOT_CALL_WORDS="stop,cancel,remove,do not call"

RUN
  pip install flask twilio openai requests python-dotenv
  python app.py
  (Expose with ngrok: `ngrok http 5000` and set PUBLIC_BASE_URL to that https URL)

NOTES
- This keeps conversational state in memory keyed by CallSid (fine for demos).
- For production, swap SESSION_STORE with Redis or a DB.
"""

import os
import io
import time
import uuid
import json
import hmac
import hashlib
from collections import defaultdict, deque
from datetime import datetime

from flask import Flask, request, Response, send_file, abort
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client as TwilioClient

import requests

# OpenAI (2024+ SDK)
try:
    from openai import OpenAI
    OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    OPENAI = None  # allow import even if package not installed

APP = Flask(__name__)

# ---------------------------- Config ---------------------------------
AGENT_NAME = os.getenv("AGENT_NAME", "Ava")
COMPANY_NAME = os.getenv("COMPANY_NAME", "XR Pay")
PRODUCT_PITCH = os.getenv(
    "PRODUCT_PITCH",
    "We provide film & TV payroll with white-glove service and modern tooling "
    "like LUCA invoice automation. We reduce errors, speed up approvals, and "
    "keep labor compliance tight so productions move faster."
)
DO_NOT_CALL_WORDS = set(w.strip().lower() for w in os.getenv(
    "DO_NOT_CALL_WORDS", "stop,cancel,remove,do not call,do not contact"
).split(","))

TWILIO_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER", "")
PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
USE_ELEVEN = bool(os.getenv("ELEVENLABS_API_KEY"))
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVEN_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel

# Safety checks
assert PUBLIC_BASE.startswith("https://") or PUBLIC_BASE == "", \
    "PUBLIC_BASE_URL must be your public https URL (ngrok etc.)."

twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

# --------------------- Tiny in-memory stores -------------------------
SESSIONS = defaultdict(lambda: {
    "history": deque(maxlen=20),  # [(role, text)]
    "created_at": time.time(),
    "lead": {},
    "last_tts_token": None,
})
AUDIO_CACHE = {}  # token -> bytes


def log(msg, **kw):
    print(f"[{datetime.utcnow().isoformat()}Z] {msg}", *(f"{k}={v}" for k, v in kw.items()))


# --------------------------- AI logic --------------------------------
SYSTEM_PROMPT = f"""
You are {AGENT_NAME}, a calm, concise sales agent for {COMPANY_NAME}.
Your job: have a short, friendly discovery call, qualify, and book a follow-up.
Be brief (1–2 sentences max per turn). Never ramble. No hype.

Talking points:
- {PRODUCT_PITCH}
- Ask 1 concrete question at a time.
- If they object (busy, using competitor, cost), acknowledge briefly and pivot to value.
- If they say any do-not-call words, apologize and end the call politely.

Style:
- Professional, steady, helpful. Avoid slang. No emojis.
- Use natural contractions (“we’re”, “that’s”).
- NEVER invent facts about pricing or contracts.

Output: plain text for TTS. No markdown.
"""


def ai_reply(call_sid: str, user_text: str) -> str:
    """Get the next agent line from OpenAI, given the session history."""
    sess = SESSIONS[call_sid]
    hist = list(sess["history"])

    # If user opted out, short-circuit
    if any(w in user_text.lower() for w in DO_NOT_CALL_WORDS):
        return "Understood. I’ll remove you from our list right now. Thanks for your time. Goodbye."

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for role, text in hist:
        messages.append({"role": role, "content": text})

    # Add latest user input
    if user_text.strip():
        messages.append({"role": "user", "content": user_text.strip()})

    if OPENAI is None:
        # Fallback canned reply if SDK not available
        return "Thanks. Would you be open to a quick 15-minute follow-up this week so we can show you how productions are cutting invoice time in half?"

    resp = OPENAI.chat.completions.create(
        model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.5,
        max_tokens=180,
        messages=messages,
    )
    out = (resp.choices[0].message.content or "").strip()
    return out or "Thanks. Would you be open to a quick 15-minute follow-up this week?"


# --------------------------- TTS -------------------------------------
def tts_elevenlabs(text: str) -> bytes:
    """Generate mp3 with ElevenLabs; returns raw bytes."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}"
    headers = {
        "xi-api-key": ELEVEN_KEY,
        "accept": "audio/mpeg",
        "content-type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.7},
    }
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.content


def put_audio_cache(text: str) -> str:
    """Cache TTS bytes and return a unique token; Twilio will fetch /audio/<token>.mp3."""
    token = hashlib.sha1(text.encode("utf-8")).hexdigest() + "-" + uuid.uuid4().hex[:6]
    if USE_ELEVEN:
        try:
            AUDIO_CACHE[token] = tts_elevenlabs(text)
        except Exception as e:
            log("ElevenLabs TTS failed; falling back to Say", err=str(e))
            AUDIO_CACHE[token] = None  # signal fallback
    else:
        AUDIO_CACHE[token] = None  # no eleven; use Say
    return token


@APP.get("/audio/<token>.mp3")
def audio_stream(token):
    data = AUDIO_CACHE.get(token)
    if data is None:
        # nothing cached (or we're falling back). return 404 so Twilio falls back to <Say> branch.
        abort(404)
    return send_file(
        io.BytesIO(data),
        mimetype="audio/mpeg",
        as_attachment=False,
        download_name=f"{token}.mp3",
        max_age=0,
        conditional=True,
        etag=False,
        last_modified=datetime.utcnow()
    )


# ------------------------ Twilio webhooks ----------------------------
@APP.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z"}


@APP.post("/outbound")
def outbound():
    """Place an outbound call. Usage: POST or GET /outbound?to=+1XXXXXXXXXX&lead_name=...&company=..."""
    to = request.values.get("to", "").strip()
    lead_name = request.values.get("lead_name", "").strip()
    company = request.values.get("company", "").strip()
    if not (to and TWILIO_NUMBER and PUBLIC_BASE):
        return {"ok": False, "error": "Missing to/TWILIO_NUMBER/PUBLIC_BASE_URL"}, 400

    start_url = f"{PUBLIC_BASE}/voice?lead_name={lead_name}&company={company}"
    call = twilio_client.calls.create(
        to=to,
        from_=TWILIO_NUMBER,
        url=start_url,
        machine_detection="Enable",  # optional
    )
    log("Placed outbound call", to=to, call_sid=call.sid)
    return {"ok": True, "sid": call.sid}


@APP.post("/voice")
def voice():
    """Initial greeting + Gather for speech."""
    call_sid = request.values.get("CallSid")
    lead_name = request.values.get("lead_name", "") or "there"
    company_hint = request.values.get("company", "")

    sess = SESSIONS[call_sid]
    sess["lead"] = {"name": lead_name, "company": company_hint}

    # Compose a short greeting
    greeting = (
        f"Hi {lead_name}, this is {AGENT_NAME} with {COMPANY_NAME}. "
        f"{PRODUCT_PITCH} "
        "Do you have a quick minute?"
    )
    token = put_audio_cache(greeting)
    resp = VoiceResponse()

    if USE_ELEVEN and AUDIO_CACHE.get(token):
        gather = Gather(
            input="speech",
            action=f"{PUBLIC_BASE}/ai",
            method="POST",
            speech_timeout="auto",
            language="en-US"
        )
        gather.play(f"{PUBLIC_BASE}/audio/{token}.mp3")
        resp.append(gather)
    else:
        # fallback to <Say>
        gather = Gather(
            input="speech",
            action=f"{PUBLIC_BASE}/ai",
            method="POST",
            speech_timeout="auto",
            language="en-US"
        )
        gather.say(greeting, voice="Polly.Matthew")  # Twilio Polly voice
        resp.append(gather)

    # If no input…
    resp.say("I didn’t catch that. I’ll try again.", voice="Polly.Matthew")
    resp.redirect(f"{PUBLIC_BASE}/voice")
    return Response(str(resp), mimetype="text/xml")


@APP.post("/ai")
def ai():
    """Handles the user's speech, generates next line, and continues the call."""
    call_sid = request.values.get("CallSid")
    user_text = request.values.get("SpeechResult", "") or request.values.get("TranscriptionText", "")

    sess = SESSIONS[call_sid]
    if user_text:
        sess["history"].append(("user", user_text))

    agent_line = ai_reply(call_sid, user_text)
    sess["history"].append(("assistant", agent_line))

    # Do-not-call quick exit
    if any(w in user_text.lower() for w in DO_NOT_CALL_WORDS):
        resp = VoiceResponse()
        resp.say(agent_line, voice="Polly.Matthew") if not USE_ELEVEN else resp.play(f"{PUBLIC_BASE}/audio/{put_audio_cache(agent_line)}.mp3")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    token = put_audio_cache(agent_line)
    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"{PUBLIC_BASE}/ai",
        method="POST",
        speech_timeout="auto",
        language="en-US"
    )
    if USE_ELEVEN and AUDIO_CACHE.get(token):
        gather.play(f"{PUBLIC_BASE}/audio/{token}.mp3")
    else:
        gather.say(agent_line, voice="Polly.Matthew")
    resp.append(gather)

    # If silence after our reply, give a gentle close
    close_line = "No worries, I’ll send some details by email. Thanks for your time."
    if USE_ELEVEN:
        resp.play(f"{PUBLIC_BASE}/audio/{put_audio_cache(close_line)}.mp3")
    else:
        resp.say(close_line, voice="Polly.Matthew")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")


# --------------------------- Main ------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    log("Starting server", port=port, elevenlabs=USE_ELEVEN, public_base=PUBLIC_BASE)
    APP.run(host="0.0.0.0", port=port, debug=True)

