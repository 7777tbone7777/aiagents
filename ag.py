#!/usr/bin/env python3
"""
AI Sales Agent — Sheets + SMS/Email follow-ups (Flask + Twilio + OpenAI + ElevenLabs + gspread)

ENDPOINTS
- /outbound?to=+1...&lead_name=...&company=...&email=...  -> place a call
- /voice   -> Twilio webhook (greeting + Gather speech)
- /ai      -> Twilio webhook (handles speech, calls OpenAI, TTS, continue)
- /audio/<token>.mp3 -> serve ElevenLabs TTS audio to Twilio
- /health  -> health check

LOGGING
- Appends a row to Google Sheets on each assistant turn (and final disposition).
- Columns (default): timestamp, call_sid, lead_phone, lead_name, lead_company, lead_email,
                     role, text, disposition, followup_link

CALENDAR INTEGRATION
- Automatically detects appointment times in conversation (e.g., "tomorrow at 3pm")
- Creates Google Calendar events using the same service account as Sheets
- Parses natural language times: "tomorrow at 3pm", "Friday at 2:30pm", "next Tuesday at 10am"
- Sends calendar invites to leads and includes event link in follow-up email

FOLLOW-UPS
- SMS via Twilio (optional)
- Email via SendGrid (preferred) or SMTP fallback
- Includes appointment details and calendar link if appointment was booked

ENV VARS (required unless noted)
  OPENAI_API_KEY=sk-...
  TWILIO_ACCOUNT_SID=AC...
  TWILIO_AUTH_TOKEN=...
  TWILIO_NUMBER=+1XXXXXXXXXX
  PUBLIC_BASE_URL=https://xxxx.ngrok.app

  # Google Sheets (one of the two must be set)
  GOOGLE_SERVICE_ACCOUNT_JSON='{"type":"service_account", ... }'   # inline JSON
  GOOGLE_SERVICE_ACCOUNT_FILE=/path/to/sa.json                     # file path
  GOOGLE_SHEET_ID=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx     # spreadsheet ID
  GOOGLE_WORKSHEET_NAME=Calls                                      # (optional; default 'Calls')

  # Google Calendar (uses same service account as Sheets)
  GOOGLE_CALENDAR_ID=primary                                       # (optional; default 'primary')

  # ElevenLabs (optional; falls back to <Say> if missing)
  ELEVENLABS_API_KEY=eleven_...
  ELEVENLABS_VOICE_ID=21m00Tcm4TlvDq8ikWAM

  # SendGrid (optional; else SMTP fallback)
  SENDGRID_API_KEY=SG.xxxxx
  FROM_EMAIL=sales@yourdomain.com

  # SMTP fallback (optional)
  SMTP_HOST=smtp.yourdomain.com
  SMTP_PORT=587
  SMTP_USER=sales@yourdomain.com
  SMTP_PASS=yourpassword
  SMTP_TLS=1

  # Agent config
  AGENT_NAME=Ava
  COMPANY_NAME=XR Pay
  PRODUCT_PITCH="One-liner value prop..."
  DO_NOT_CALL_WORDS="stop,cancel,remove,do not call"

RUN
  python app.py
  ngrok http 5000  (then set PUBLIC_BASE_URL to the https URL)
"""
import os, io, time, uuid, json, hashlib, smtplib, re
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from collections import defaultdict, deque

from dotenv import load_dotenv
load_dotenv()

from flask import Flask, request, Response, send_file, abort
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.rest import Client as TwilioClient

import requests

# OpenAI (2024+ SDK)
try:
    from openai import OpenAI
    OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    OPENAI = None

# -------- Config --------
APP = Flask(__name__)

AGENT_NAME   = os.getenv("AGENT_NAME", "Ava")
COMPANY_NAME = os.getenv("COMPANY_NAME", "XR Pay")
PRODUCT_PITCH= os.getenv("PRODUCT_PITCH", "We provide film & TV payroll with modern tooling that cuts invoice time in half and tightens compliance.")
DO_NOT_CALL_WORDS = {w.strip().lower() for w in os.getenv("DO_NOT_CALL_WORDS","stop,cancel,remove,do not call,do not contact").split(",")}

TWILIO_SID   = os.getenv("TWILIO_ACCOUNT_SID","")
TWILIO_TOKEN = os.getenv("TWILIO_AUTH_TOKEN","")
TWILIO_NUMBER= os.getenv("TWILIO_NUMBER","")
PUBLIC_BASE  = os.getenv("PUBLIC_BASE_URL","").rstrip("/")

USE_ELEVEN   = bool(os.getenv("ELEVENLABS_API_KEY"))
ELEVEN_KEY   = os.getenv("ELEVENLABS_API_KEY","")
ELEVEN_VOICE = os.getenv("ELEVENLABS_VOICE_ID","21m00Tcm4TlvDq8ikWAM")

SENDGRID_KEY = os.getenv("SENDGRID_API_KEY")
FROM_EMAIL   = os.getenv("FROM_EMAIL","noreply@example.com")

SMTP_HOST=os.getenv("SMTP_HOST"); SMTP_PORT=int(os.getenv("SMTP_PORT","587"))
SMTP_USER=os.getenv("SMTP_USER"); SMTP_PASS=os.getenv("SMTP_PASS")
SMTP_TLS = os.getenv("SMTP_TLS","1") == "1"

assert PUBLIC_BASE.startswith("https://") or PUBLIC_BASE=="", "PUBLIC_BASE_URL must be an https URL (ngrok etc.)"

twilio_client = TwilioClient(TWILIO_SID, TWILIO_TOKEN)

# -------- In-memory session & audio --------
SESSIONS = defaultdict(lambda: {
    "history": deque(maxlen=40),  # (role, text)
    "lead": {"name":"","company":"","email":"","phone":""},
    "created_at": time.time(),
    "disposition": "",
    "appointment": None,  # Will store: {'time': datetime, 'event_id': str, 'event_link': str}
})
AUDIO_CACHE = {}  # token -> bytes

def log(*a, **k): print(datetime.utcnow().isoformat()+"Z", *a, *[f"{kk}={vv}" for kk,vv in k.items()])

# -------- Google Sheets (gspread) --------
gspread = None; sheet = None
try:
    import gspread
    from google.oauth2.service_account import Credentials
    def _open_sheet():
        global sheet
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        info_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
        if info_json:
            info = json.loads(info_json)
            creds = Credentials.from_service_account_info(info, scopes=scopes)
        elif info_file:
            creds = Credentials.from_service_account_file(info_file, scopes=scopes)
        else:
            return None
        gc = gspread.authorize(creds)
        sid = os.getenv("GOOGLE_SHEET_ID")
        wsname = os.getenv("GOOGLE_WORKSHEET_NAME","Calls")
        sh = gc.open_by_key(sid)
        try:
            sheet = sh.worksheet(wsname)
        except gspread.WorksheetNotFound:
            sheet = sh.add_worksheet(wsname, rows=1000, cols=12)
            sheet.append_row(["timestamp","call_sid","lead_phone","lead_name","lead_company","lead_email","role","text","disposition","followup_link"])
        return sheet
    sheet = _open_sheet()
except Exception as e:
    log("Sheets init skipped", error=str(e))

def sheet_append(row:list):
    if sheet is None: return
    try:
        sheet.append_row(row, value_input_option="USER_ENTERED")
    except Exception as e:
        log("Sheets append failed", error=str(e))

# -------- Google Calendar Integration --------
calendar_service = None
try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials as CalendarCredentials

    def _init_calendar():
        global calendar_service
        scopes = ["https://www.googleapis.com/auth/calendar"]
        info_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        info_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

        if info_json:
            info = json.loads(info_json)
            creds = CalendarCredentials.from_service_account_info(info, scopes=scopes)
        elif info_file:
            creds = CalendarCredentials.from_service_account_file(info_file, scopes=scopes)
        else:
            return None

        calendar_service = build('calendar', 'v3', credentials=creds)
        return calendar_service

    calendar_service = _init_calendar()
except Exception as e:
    log("Calendar init skipped", error=str(e))

def parse_appointment_time(text: str) -> dict:
    """
    Parse natural language appointment times from conversation text.
    Returns dict with 'datetime' (datetime object) and 'raw_text' (str) if found, else None.

    Handles patterns like:
    - "tomorrow at 3pm", "tomorrow at 3 p.m."
    - "tomorrow at 2:30pm"
    - "next Tuesday at 10am"
    - "Friday at 4 p.m."
    """
    text_lower = text.lower()

    # Pattern: tomorrow at <time>
    tomorrow_pattern = r'tomorrow\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?)'
    match = re.search(tomorrow_pattern, text_lower)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2)) if match.group(2) else 0
        am_pm = match.group(3).replace('.', '').replace(' ', '').strip()

        # Convert to 24-hour format
        if 'p' in am_pm and hour != 12:
            hour += 12
        elif 'a' in am_pm and hour == 12:
            hour = 0

        appointment_dt = datetime.now() + timedelta(days=1)
        appointment_dt = appointment_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return {
            'datetime': appointment_dt,
            'raw_text': match.group(0)
        }

    # Pattern: <day_name> at <time>
    days_of_week = {
        'monday': 0, 'tuesday': 1, 'wednesday': 2, 'thursday': 3,
        'friday': 4, 'saturday': 5, 'sunday': 6
    }

    day_pattern = r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday|next\s+\w+)\s+at\s+(\d{1,2})(?::(\d{2}))?\s*([ap]\.?\s*m\.?)'
    match = re.search(day_pattern, text_lower)
    if match:
        day_str = match.group(1)
        hour = int(match.group(2))
        minute = int(match.group(3)) if match.group(3) else 0
        am_pm = match.group(4).replace('.', '').replace(' ', '').strip()

        # Convert to 24-hour format
        if 'p' in am_pm and hour != 12:
            hour += 12
        elif 'a' in am_pm and hour == 12:
            hour = 0

        # Calculate target day
        current_dt = datetime.now()
        current_weekday = current_dt.weekday()

        # Handle "next <day>" pattern
        if day_str.startswith('next'):
            day_name = day_str.replace('next', '').strip()
            if day_name in days_of_week:
                target_weekday = days_of_week[day_name]
            else:
                return None
        elif day_str in days_of_week:
            target_weekday = days_of_week[day_str]
        else:
            return None

        # Calculate days until target weekday
        days_ahead = target_weekday - current_weekday
        if days_ahead <= 0:  # Target day is today or has passed this week
            days_ahead += 7

        appointment_dt = current_dt + timedelta(days=days_ahead)
        appointment_dt = appointment_dt.replace(hour=hour, minute=minute, second=0, microsecond=0)

        return {
            'datetime': appointment_dt,
            'raw_text': match.group(0)
        }

    return None

def create_calendar_event(lead: dict, appointment_time: datetime, conversation_summary: str = "") -> dict:
    """
    Create a Google Calendar event for the appointment.

    Args:
        lead: dict with name, company, email, phone
        appointment_time: datetime object for the appointment
        conversation_summary: optional summary of the conversation

    Returns:
        dict with 'success' (bool), 'event_id' (str), 'link' (str), 'error' (str)
    """
    if calendar_service is None:
        return {'success': False, 'error': 'Calendar service not initialized'}

    try:
        # Create event details
        event_start = appointment_time.isoformat()
        event_end = (appointment_time + timedelta(minutes=30)).isoformat()  # Default 30-min meeting

        event_title = f"Follow-up: {lead.get('name', 'Lead')} - {lead.get('company', 'Company')}"

        event_description = f"""Follow-up appointment booked via AI sales call.

Lead Details:
- Name: {lead.get('name', 'N/A')}
- Company: {lead.get('company', 'N/A')}
- Email: {lead.get('email', 'N/A')}
- Phone: {lead.get('phone', 'N/A')}

Product Pitch: {PRODUCT_PITCH}
"""

        if conversation_summary:
            event_description += f"\n\nConversation Summary:\n{conversation_summary}"

        event = {
            'summary': event_title,
            'description': event_description,
            'start': {
                'dateTime': event_start,
                'timeZone': 'America/Los_Angeles',  # Adjust as needed
            },
            'end': {
                'dateTime': event_end,
                'timeZone': 'America/Los_Angeles',
            },
            # Note: Removed 'attendees' field because service accounts cannot invite attendees
            # without Domain-Wide Delegation. Lead email is in the description instead.
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                    {'method': 'popup', 'minutes': 30},  # 30 minutes before
                ],
            },
        }

        # Get calendar ID from env or use 'primary'
        calendar_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')

        # Create the event
        # Note: Using sendUpdates='none' because service accounts cannot send invitations
        # without Domain-Wide Delegation. The event will be created in the calendar but
        # attendees won't receive email invitations.
        created_event = calendar_service.events().insert(
            calendarId=calendar_id,
            body=event,
            sendUpdates='none'
        ).execute()

        return {
            'success': True,
            'event_id': created_event.get('id'),
            'link': created_event.get('htmlLink', ''),
            'error': None
        }

    except Exception as e:
        log("Calendar event creation failed", error=str(e))
        return {'success': False, 'error': str(e), 'event_id': None, 'link': None}

def detect_and_create_appointment(call_sid: str, conversation_text: str) -> dict:
    """
    Detect appointment booking in conversation and create calendar event.

    Args:
        call_sid: Twilio call SID
        conversation_text: Recent conversation text to parse

    Returns:
        dict with 'created' (bool), 'event_link' (str), 'appointment_time' (datetime)
    """
    appointment_info = parse_appointment_time(conversation_text)

    if not appointment_info:
        return {'created': False, 'event_link': None, 'appointment_time': None}

    sess = SESSIONS[call_sid]
    lead = sess['lead']

    # Get conversation summary
    summary = "\n".join([f"{r.upper()}: {t}" for r, t in sess["history"]][-10:])

    # Create calendar event
    result = create_calendar_event(lead, appointment_info['datetime'], summary)

    if result['success']:
        log("Calendar event created", call_sid=call_sid, event_id=result['event_id'],
            appointment_time=appointment_info['datetime'].isoformat())

        # Store appointment info in session
        sess['appointment'] = {
            'time': appointment_info['datetime'],
            'event_id': result['event_id'],
            'event_link': result['link']
        }

        return {
            'created': True,
            'event_link': result['link'],
            'appointment_time': appointment_info['datetime']
        }
    else:
        log("Calendar event creation failed", call_sid=call_sid, error=result['error'])
        return {'created': False, 'event_link': None, 'appointment_time': None}

# -------- AI core --------
SYSTEM_PROMPT = f"""
You are {AGENT_NAME}, a friendly sales agent for {COMPANY_NAME}.
{PRODUCT_PITCH}

Your goal: Understand their business type, then explain how our AI assistant can help them specifically.

STEP 1: Ask what type of business they have (barber shop, salon, restaurant, gym, doctor's office, etc.)

STEP 2: Once you know their industry, explain relevant benefits:
- BARBER/SALON: "Our AI receptionist books haircut appointments 24/7, sends reminders, and answers questions about your services and hours - so you never miss a booking even when you're busy with clients."
- RESTAURANT: "Our AI assistant takes reservations and takeout orders any time, answers menu questions, and manages your waitlist - even during your busiest dinner rush."
- GYM/FITNESS: "Our AI books class reservations, answers membership questions, and schedules personal training sessions - freeing up your front desk staff."
- DOCTOR/DENTAL: "Our AI schedules patient appointments, handles rescheduling, and answers common questions about office hours and insurance - reducing no-shows and phone tag."
- OTHER: "Our AI assistant can answer calls 24/7, book appointments, and ensure you never miss a potential customer."

STEP 3: Ask if they'd like to schedule a demo to see it customized for their business.
If yes, ask for their name and email address to set up the demo (you already have their phone number).

Keep responses to 1-2 sentences. Be conversational and helpful.
If the user opts out (stop/cancel/remove/do not call), apologize and end the call.
Output plain text suitable for TTS; no markdown.
"""

def ai_reply(call_sid:str, user_text:str)->str:
    if any(w in user_text.lower() for w in DO_NOT_CALL_WORDS):
        return "Understood. I’ll remove you from our list. Thanks for your time. Goodbye."
    messages=[{"role":"system","content":SYSTEM_PROMPT}]
    for role,text in SESSIONS[call_sid]["history"]:
        messages.append({"role":role,"content":text})
    if user_text.strip():
        messages.append({"role":"user","content":user_text.strip()})
    if OPENAI is None:
        return "Thanks. Would you be open to a 15-minute follow-up so we can show how teams are cutting invoice time in half?"
    resp = OPENAI.chat.completions.create(
        model=os.getenv("OPENAI_MODEL","gpt-4o-mini"),
        temperature=0.5,
        max_tokens=80,
        messages=messages,
    )
    return (resp.choices[0].message.content or "").strip()

# -------- TTS (ElevenLabs) --------
def tts_elevenlabs(text:str)->bytes:
    url=f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVEN_VOICE}"
    headers={"xi-api-key":ELEVEN_KEY,"accept":"audio/mpeg","content-type":"application/json"}
    payload={"text":text,"model_id":"eleven_turbo_v2_5","voice_settings":{"stability":0.5,"similarity_boost":0.7}}
    r=requests.post(url,headers=headers,json=payload,timeout=60); r.raise_for_status()
    return r.content

def put_audio_cache(text:str)->str:
    token = hashlib.sha1(text.encode()).hexdigest()+"-"+uuid.uuid4().hex[:6]
    if USE_ELEVEN:
        try: AUDIO_CACHE[token]=tts_elevenlabs(text)
        except Exception as e:
            log("ElevenLabs failed; falling back", error=str(e)); AUDIO_CACHE[token]=None
    else:
        AUDIO_CACHE[token]=None
    return token

@APP.get("/audio/<token>.mp3")
def audio_stream(token):
    data=AUDIO_CACHE.get(token)
    if not data: abort(404)
    return send_file(io.BytesIO(data), mimetype="audio/mpeg", as_attachment=False,
                     download_name=f"{token}.mp3")

# -------- Utility: follow-ups --------
def send_sms(to:str, body:str):
    if not (to and TWILIO_NUMBER): return
    try:
        twilio_client.messages.create(to=to, from_=TWILIO_NUMBER, body=body)
    except Exception as e:
        log("SMS failed", error=str(e))

def send_email(to:str, subject:str, body:str):
    if not to: return
    # Prefer SendGrid
    if SENDGRID_KEY:
        try:
            import sendgrid
            from sendgrid.helpers.mail import Mail
            sg=sendgrid.SendGridAPIClient(SENDGRID_KEY)
            m=Mail(from_email=FROM_EMAIL, to_emails=to, subject=subject, plain_text_content=body)
            sg.send(m); return
        except Exception as e:
            log("SendGrid failed; trying SMTP", error=str(e))
    # SMTP fallback
    try:
        msg=MIMEText(body, "plain")
        msg["Subject"]=subject; msg["From"]=FROM_EMAIL; msg["To"]=to
        smtp=smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30)
        if SMTP_TLS: smtp.starttls()
        if SMTP_USER: smtp.login(SMTP_USER, SMTP_PASS)
        smtp.sendmail(FROM_EMAIL, [to], msg.as_string())
        smtp.quit()
    except Exception as e:
        log("SMTP failed", error=str(e))

def log_turn(call_sid:str, role:str, text:str, disposition:str=""):
    lead=SESSIONS[call_sid]["lead"]
    sheet_append([
        datetime.utcnow().isoformat()+"Z",
        call_sid, lead.get("phone",""), lead.get("name",""), lead.get("company",""),
        lead.get("email",""), role, text, disposition, ""
    ])

def finalize_and_follow_up(call_sid:str):
    sess=SESSIONS[call_sid]; lead=sess["lead"]
    summary = "\n".join([f"{r.upper()}: {t}" for r,t in sess["history"]][-8:])

    # Check if there's an appointment in the session
    appointment = sess.get("appointment")

    # SMS quick thank-you
    sms_message = f"Thanks for your time — {COMPANY_NAME}. I'll follow up by email with details."
    if appointment:
        apt_time = appointment['time'].strftime('%A, %B %d at %I:%M %p')
        sms_message = f"Thanks for your time! Your appointment is scheduled for {apt_time}. Calendar invite sent to your email."
    send_sms(lead.get("phone",""), sms_message)

    # Email recap
    email_body = f"""Hi {lead.get('name','there')},

Thanks for your time today. As discussed:

{PRODUCT_PITCH}

Recent highlights from our call:
{summary}

"""

    # Add appointment details if calendar event was created
    if appointment:
        apt_time = appointment['time'].strftime('%A, %B %d, %Y at %I:%M %p')
        email_body += f"""
APPOINTMENT CONFIRMED
We've scheduled a follow-up meeting for {apt_time}.

Calendar Event: {appointment.get('event_link', 'Check your calendar')}

Looking forward to our conversation!
"""
    else:
        email_body += "Would you be open to a 15-minute walkthrough this week?\n"

    email_body += f"""
Best,
{AGENT_NAME} — {COMPANY_NAME}
"""

    send_email(lead.get("email",""), f"{COMPANY_NAME} — quick recap", email_body)

    # Log final disposition with appointment info
    disposition_text = sess.get("disposition","")
    if appointment:
        disposition_text += f" | Appointment: {appointment['time'].isoformat()}"

    log_turn(call_sid, "system", "followup_sent", disposition=disposition_text)

# -------- Twilio webhooks --------
@APP.post("/outbound")
def outbound():
    to=request.values.get("to","").strip()
    lead_name=request.values.get("lead_name","").strip() or "there"
    company=request.values.get("company","").strip()
    email=request.values.get("email","").strip()
    if not (to and TWILIO_NUMBER and PUBLIC_BASE):
        return {"ok":False,"error":"Missing to/TWILIO_NUMBER/PUBLIC_BASE_URL"},400
    start_url=f"{PUBLIC_BASE}/voice?lead_name={lead_name}&company={company}&email={email}&to={to}"
    call = twilio_client.calls.create(
        to=to, from_=TWILIO_NUMBER, url=start_url,
        status_callback=f"{PUBLIC_BASE}/status",
        status_callback_event=['completed'],
        status_callback_method="POST",
        machine_detection="Enable",
    )
    log("Outbound call placed", to=to, call_sid=call.sid)
    return {"ok":True,"sid":call.sid}

@APP.post("/inbound")
def inbound():
    """Handle incoming calls to the Twilio number"""
    call_sid=request.values.get("CallSid")
    caller_number=request.values.get("From","")

    # Initialize session for inbound call
    SESSIONS[call_sid] = {
        "history": deque(maxlen=40),
        "lead": {"name": "", "company": "", "email": "", "phone": caller_number},
        "disposition": ""
    }

    # Greeting for inbound callers
    greeting = (
        f"Hi, thanks for calling {COMPANY_NAME}! "
        f"This is {AGENT_NAME}. How can I help you today?"
    )
    SESSIONS[call_sid]["history"].append(("assistant", greeting))
    log("Inbound call received", from_number=caller_number, call_sid=call_sid)
    log_turn(call_sid, "assistant", greeting)

    token = put_audio_cache(greeting)
    resp=VoiceResponse()
    gather=Gather(input="speech", action=f"{PUBLIC_BASE}/ai", method="POST",
                  speech_timeout="5", language="en-US")
    if USE_ELEVEN and AUDIO_CACHE.get(token):
        gather.play(f"{PUBLIC_BASE}/audio/{token}.mp3")
    else:
        gather.say(greeting, voice="Polly.Matthew")
    resp.append(gather)

    # Add status callback for follow-ups
    resp.redirect(url=f"{PUBLIC_BASE}/status", method="POST")

    return Response(str(resp), mimetype="text/xml")

@APP.post("/status")
def status_cb():
    call_sid=request.values.get("CallSid")
    call_status=request.values.get("CallStatus")
    log("Status callback", call_sid=call_sid, status=call_status)
    if call_status=="completed":
        finalize_and_follow_up(call_sid)
    return ("",204)

@APP.post("/voice")
def voice():
    call_sid=request.values.get("CallSid")
    lead_name=request.values.get("lead_name","") or "there"
    company_hint=request.values.get("company","")
    email=request.values.get("email","")
    to=request.values.get("to","")

    SESSIONS[call_sid]["lead"]={"name":lead_name,"company":company_hint,"email":email,"phone":to}

    greeting = (
        f"Hi {lead_name}, this is {AGENT_NAME} with {COMPANY_NAME}. "
        f"{PRODUCT_PITCH} Do you have a quick minute?"
    )
    SESSIONS[call_sid]["history"].append(("assistant", greeting))
    log_turn(call_sid, "assistant", greeting)

    token = put_audio_cache(greeting)
    resp=VoiceResponse()
    gather=Gather(input="speech", action=f"{PUBLIC_BASE}/ai", method="POST",
                  speech_timeout="5", language="en-US")
    if USE_ELEVEN and AUDIO_CACHE.get(token):
        gather.play(f"{PUBLIC_BASE}/audio/{token}.mp3")
    else:
        gather.say(greeting, voice="Polly.Matthew")
    resp.append(gather)

    resp.say("I didn’t catch that. I’ll try again.", voice="Polly.Matthew")
    resp.redirect(f"{PUBLIC_BASE}/voice?lead_name={lead_name}&company={company_hint}&email={email}&to={to}")
    return Response(str(resp), mimetype="text/xml")

@APP.post("/ai")
def ai():
    call_sid=request.values.get("CallSid")
    user_text=request.values.get("SpeechResult","") or request.values.get("TranscriptionText","")
    user_text = user_text.strip()
    if user_text:
        SESSIONS[call_sid]["history"].append(("user", user_text))
        log_turn(call_sid, "user", user_text)

    agent_line = ai_reply(call_sid, user_text)
    SESSIONS[call_sid]["history"].append(("assistant", agent_line))
    log_turn(call_sid, "assistant", agent_line)

    # Check for appointment booking in user speech
    if user_text and not SESSIONS[call_sid].get("appointment"):
        appointment_result = detect_and_create_appointment(call_sid, user_text)
        if appointment_result['created']:
            log("Appointment detected and created", call_sid=call_sid,
                appointment_time=appointment_result['appointment_time'].isoformat())

    # Opt-out check
    if any(w in user_text.lower() for w in DO_NOT_CALL_WORDS):
        SESSIONS[call_sid]["disposition"]="DNC"
        resp=VoiceResponse()
        if USE_ELEVEN and (audio:=AUDIO_CACHE.get(put_audio_cache(agent_line))):
            resp.play(f"{PUBLIC_BASE}/audio/{list(AUDIO_CACHE.keys())[-1]}.mp3")
        else:
            resp.say(agent_line, voice="Polly.Matthew")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    token = put_audio_cache(agent_line)
    resp=VoiceResponse()
    gather=Gather(input="speech", action=f"{PUBLIC_BASE}/ai", method="POST",
                  speech_timeout="5", language="en-US")
    if USE_ELEVEN and AUDIO_CACHE.get(token):
        gather.play(f"{PUBLIC_BASE}/audio/{token}.mp3")
    else:
        gather.say(agent_line, voice="Polly.Matthew")
    resp.append(gather)

    # graceful close on silence
    close_line = "No worries. Thanks for your time. Have a great day!"
    if USE_ELEVEN:
        resp.play(f"{PUBLIC_BASE}/audio/{put_audio_cache(close_line)}.mp3")
    else:
        resp.say(close_line, voice="Polly.Matthew")
    resp.hangup()
    return Response(str(resp), mimetype="text/xml")

@APP.get("/health")
def health(): return {"ok":True,"time":datetime.utcnow().isoformat()+"Z"}

# -------- Main --------
if __name__=="__main__":
    port=int(os.getenv("PORT","5000"))
    log("Starting server", port=port, public_base=PUBLIC_BASE, elevenlabs=USE_ELEVEN)
    APP.run(host="0.0.0.0", port=port, debug=True)

