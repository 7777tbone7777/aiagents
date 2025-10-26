#!/usr/bin/env python3
"""
Bolt AI Group - Multi-Tenant AI Receptionist Platform
Supports unlimited businesses with dynamic phone number routing
"""
import os, hashlib, uuid, io, re, json, random
from datetime import datetime, timedelta
from collections import deque
from dotenv import load_dotenv
from flask import Flask, request, Response, send_file
from twilio.rest import Client as TwilioClient
from twilio.twiml.voice_response import VoiceResponse, Gather
from supabase import create_client, Client as SupabaseClient

load_dotenv()

# -------- Configuration --------
PORT = int(os.getenv("PORT", "5000"))
PUBLIC_BASE = os.getenv("PUBLIC_BASE_URL", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

# Twilio
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")
twilio_client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN) if TWILIO_ACCOUNT_SID else None

# OpenAI
try:
    from openai import OpenAI
    OPENAI = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except:
    OPENAI = None

# ElevenLabs
ELEVEN_KEY = os.getenv("ELEVENLABS_API_KEY")
USE_ELEVEN = bool(ELEVEN_KEY)
if USE_ELEVEN:
    import requests

# Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: SupabaseClient = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google Calendar
calendar_service = None
try:
    from googleapiclient.discovery import build
    from google.oauth2.service_account import Credentials as CalendarCredentials

    def _init_calendar(service_account_file):
        """Initialize calendar service for a specific business"""
        scopes = ["https://www.googleapis.com/auth/calendar"]
        creds = CalendarCredentials.from_service_account_file(service_account_file, scopes=scopes)
        return build('calendar', 'v3', credentials=creds)

    # Default calendar service (using main service account)
    sa_file = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")
    if sa_file:
        calendar_service = _init_calendar(sa_file)
except Exception as e:
    print(f"Calendar init skipped: {e}")

# Email configuration
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@boltaigroup.com")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")

# SMTP configuration (Yahoo, Gmail, etc.)
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mail.yahoo.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

# SMS configuration
USE_SMS = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)

APP = Flask(__name__)
SESSIONS = {}  # call_sid -> session data
AUDIO_CACHE = {}  # audio hash -> MP3 bytes

# Thinking sounds (play while AI is processing)
THINKING_SOUNDS = ['hmm', 'um', 'uh', 'let_me_see', 'okay']

def log(msg, **kwargs):
    """Simple logging"""
    ts = datetime.utcnow().isoformat() + "Z"
    parts = [f"{k}={v}" for k, v in kwargs.items()]
    print(f"{ts} {msg} {' '.join(parts)}")

# -------- Database Helpers --------

def get_business_by_phone(phone_number):
    """Look up business by incoming phone number"""
    try:
        result = supabase.table('phone_numbers')\
            .select('*, businesses(*)')\
            .eq('phone_number', phone_number)\
            .single()\
            .execute()

        if result.data:
            return result.data['businesses']
        return None
    except Exception as e:
        log("Business lookup failed", phone=phone_number, error=str(e))
        return None

def create_call_record(business_id, call_sid, from_number, to_number, direction):
    """Create a call record in the database"""
    try:
        data = {
            'business_id': business_id,
            'call_sid': call_sid,
            'from_number': from_number,
            'to_number': to_number,
            'direction': direction,
            'status': 'in-progress',
            'transcript': []
        }
        result = supabase.table('calls').insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        log("Call record creation failed", error=str(e))
        return None

def update_call_transcript(call_sid, role, text):
    """Add a turn to the call transcript"""
    try:
        # Get current call
        call = supabase.table('calls').select('transcript').eq('call_sid', call_sid).single().execute()
        if not call.data:
            return

        transcript = call.data.get('transcript', [])
        transcript.append({'role': role, 'text': text, 'timestamp': datetime.utcnow().isoformat()})

        supabase.table('calls').update({'transcript': transcript}).eq('call_sid', call_sid).execute()
    except Exception as e:
        log("Transcript update failed", error=str(e))

def finalize_call(call_sid, disposition=None):
    """Mark call as completed"""
    try:
        updates = {'status': 'completed'}
        if disposition:
            updates['disposition'] = disposition

        supabase.table('calls').update(updates).eq('call_sid', call_sid).execute()
    except Exception as e:
        log("Call finalization failed", error=str(e))

def create_appointment_record(business_id, call_id, customer_name, customer_email, customer_phone,
                              appointment_time, service_type=None, event_id=None, event_link=None):
    """Create appointment in database"""
    try:
        data = {
            'business_id': business_id,
            'call_id': call_id,
            'customer_name': customer_name,
            'customer_email': customer_email,
            'customer_phone': customer_phone,
            'appointment_time': appointment_time.isoformat(),
            'service_type': service_type,
            'google_event_id': event_id,
            'google_event_link': event_link,
            'status': 'scheduled'
        }
        result = supabase.table('appointments').insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        log("Appointment creation failed", error=str(e))
        return None

# -------- Email & SMS Functions --------

def send_email(to_email, subject, body_html):
    """Send email via SendGrid or SMTP (Yahoo, Gmail, etc.)"""
    print(f"DEBUG: send_email called with to={to_email}")

    if not to_email:
        print("DEBUG: No recipient email provided")
        log("Email send skipped - no recipient")
        return False

    try:
        if SENDGRID_API_KEY:
            print(f"DEBUG: Using SendGrid to send email")
            # Use SendGrid
            import requests
            url = "https://api.sendgrid.com/v3/mail/send"
            headers = {
                "Authorization": f"Bearer {SENDGRID_API_KEY}",
                "Content-Type": "application/json"
            }
            data = {
                "personalizations": [{"to": [{"email": to_email}]}],
                "from": {"email": FROM_EMAIL, "name": "Bolt AI Group"},
                "subject": subject,
                "content": [{"type": "text/html", "value": body_html}]
            }
            response = requests.post(url, headers=headers, json=data)
            response.raise_for_status()
            print(f"✓ SendGrid email sent successfully to {to_email}")
            log("Email sent via SendGrid", to=to_email)
            return True
        elif SMTP_USER and SMTP_PASS:
            print(f"DEBUG: Using SMTP ({SMTP_HOST}) to send email from {FROM_EMAIL}")
            # Use SMTP (Yahoo, Gmail, etc.)
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = FROM_EMAIL
            msg['To'] = to_email

            html_part = MIMEText(body_html, 'html')
            msg.attach(html_part)

            print(f"DEBUG: Connecting to {SMTP_HOST}:{SMTP_PORT}")
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
                server.starttls()
                print(f"DEBUG: Logging in as {SMTP_USER}")
                server.login(SMTP_USER, SMTP_PASS)
                print(f"DEBUG: Sending email...")
                server.sendmail(FROM_EMAIL, to_email, msg.as_string())

            print(f"✓ SMTP email sent successfully to {to_email}")
            log("Email sent via SMTP", to=to_email, host=SMTP_HOST)
            return True
        else:
            print(f"DEBUG: No email service configured (SENDGRID_API_KEY={bool(SENDGRID_API_KEY)}, SMTP_USER={bool(SMTP_USER)}, SMTP_PASS={bool(SMTP_PASS)})")
            # No email service configured
            log("Email would be sent (no service configured)", to=to_email, subject=subject)
            return False
    except Exception as e:
        print(f"✗ Email send failed: {e}")
        log("Email send failed", error=str(e), to=to_email)
        return False

def send_sms(to_phone, message):
    """Send SMS via Twilio"""
    if not to_phone or not USE_SMS:
        log("SMS send skipped")
        return False

    try:
        twilio_client.messages.create(
            body=message,
            from_=TWILIO_NUMBER,
            to=to_phone
        )
        log("SMS sent", to=to_phone)
        return True
    except Exception as e:
        log("SMS send failed", error=str(e), to=to_phone)
        return False

def send_demo_follow_up(customer_name, customer_email, business_type):
    """Send follow-up email after sales call"""
    subject = f"Your Bolt AI Group Demo - Custom AI Agent for {business_type}"

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2>Hi {customer_name}!</h2>

        <p>Thanks for your interest in Bolt AI Group! I'm excited to show you how our custom AI agents can transform your {business_type}.</p>

        <h3>What We'll Cover in Your Demo:</h3>
        <ul>
            <li><strong>Live Demo:</strong> See your AI agent answer calls in real-time</li>
            <li><strong>Custom Setup:</strong> We'll configure it specifically for your {business_type}</li>
            <li><strong>Integration:</strong> Connect to your calendar and booking system</li>
            <li><strong>Pricing:</strong> Simple, transparent pricing starting at $199/month</li>
        </ul>

        <h3>What You Get:</h3>
        <ul>
            <li>24/7 call answering - never miss a customer again</li>
            <li>Automatic appointment booking directly into your calendar</li>
            <li>Customer questions answered instantly</li>
            <li>SMS and email confirmations</li>
            <li>Full call transcripts and analytics</li>
        </ul>

        <p><strong>I'll be reaching out shortly to schedule your personalized demo.</strong></p>

        <p>In the meantime, feel free to reply to this email with any questions!</p>

        <p>Best regards,<br>
        Bolt<br>
        Bolt AI Group<br>
        {FROM_EMAIL}</p>
    </body>
    </html>
    """

    return send_email(customer_email, subject, body_html)

# -------- Industry Templates --------

INDUSTRY_PROMPTS = {
    "sales": """You are {agent_name}, a friendly sales agent for {business_name}.

GREETING: Start by introducing yourself and what Bolt AI Group does:
"Hi! This is {agent_name} from Bolt AI Group. We build custom AI agents for small businesses that answer every call 24/7, book appointments automatically, handle customer questions, and ensure you never lose business to a missed call—starting at just $199 a month. What type of business are you calling about?"

STEP 1: Once they tell you their business type (barber shop, salon, restaurant, gym, doctor's office, etc.), explain relevant benefits:
- BARBER/SALON: "Perfect! Our AI receptionist books haircut appointments 24/7, sends reminders, and answers questions about your services and hours - so you never miss a booking even when you're busy with clients."
- RESTAURANT: "Great! Our AI assistant takes reservations and takeout orders any time, answers menu questions, and manages your waitlist - even during your busiest dinner rush."
- GYM/FITNESS: "Excellent! Our AI books class reservations, answers membership questions, and schedules personal training sessions - freeing up your front desk staff."
- DOCTOR/DENTAL: "Wonderful! Our AI schedules patient appointments, handles rescheduling, and answers common questions about office hours and insurance - reducing no-shows and phone tag."
- OTHER: "Awesome! Our AI assistant can answer calls 24/7, book appointments, and ensure you never miss a potential customer."

STEP 2: Ask if they'd like a free demo.
If yes, say: "Great! I'll send you demo information right now. What's the best email address for you?"

STEP 3: Get their email address BY ASKING THEM TO SPELL IT.
- Say: "Perfect! What's the best email address for you? Please spell it out letter by letter, and say 'at' for @ and 'dot' for periods."
- Example: If they say "T J V A Z Q U E Z at gmail dot com", you heard "tjvazquez@gmail.com"
- Listen carefully as they spell each letter
- After they finish, repeat it back: "Got it, that's [spell out the email]. I'll send that over right away!"
- Then say: "Perfect! I've sent the demo info to your email. You should see it in the next few minutes. I'll also follow up personally to schedule your live demo. Anything else I can help with today?"

IMPORTANT:
- Keep responses to 1-2 sentences max
- Be conversational and enthusiastic
- ALWAYS ask them to spell the email letter by letter - this is critical for accuracy
- When confirming, spell it back: "T J V A Z Q U E Z at gmail dot com"
- Be patient and encouraging if they need to repeat""",

    "barber": """You are {agent_name}, the AI receptionist for {business_name}.
You help customers book haircut appointments, answer questions about services and hours.
Be friendly and professional. Keep responses to 1-2 sentences.
When booking appointments, get: name, preferred date/time, and service type.
Services available: {services}
Hours: {hours}""",

    "restaurant": """You are {agent_name}, the AI host for {business_name}.
You handle reservations and takeout orders. Be warm and efficient.
When taking reservations, get: name, party size, date/time.
For takeout, get: name, order details, pickup time.
Hours: {hours}""",

    "gym": """You are {agent_name}, the AI receptionist for {business_name}.
You book class reservations and answer membership questions.
Be energetic and helpful. Get: name, class type, date/time.
Hours: {hours}""",

    "medical": """You are {agent_name}, the AI scheduler for {business_name}.
You schedule patient appointments professionally and efficiently.
Get: name, reason for visit, preferred date/time, insurance info.
Hours: {hours}""",

    "default": """You are {agent_name}, the AI assistant for {business_name}.
You answer calls, book appointments, and help customers.
Be friendly and professional.
Hours: {hours}"""
}

def build_system_prompt(business):
    """Build AI system prompt based on business configuration"""
    industry = business.get('industry', 'default')
    template = INDUSTRY_PROMPTS.get(industry, INDUSTRY_PROMPTS['default'])

    # Format business hours
    hours = business.get('business_hours') or {}
    hours_str = ', '.join([f"{day}: {time}" for day, time in hours.items()]) if hours else 'Please call during business hours'

    # Format services
    services = business.get('services', [])
    services_str = ', '.join(services) if services else 'various services'

    return template.format(
        agent_name=business.get('agent_name', 'Alex'),
        business_name=business.get('business_name', 'our business'),
        services=services_str,
        hours=hours_str
    )

# [CONTINUED IN NEXT MESSAGE - File is large, splitting into parts]

# -------- AI & TTS Functions --------

def ai_reply(business, history, user_text):
    """Generate AI response based on business configuration"""
    system_prompt = build_system_prompt(business)

    messages = [{"role": "system", "content": system_prompt}]
    for role, text in history:
        messages.append({"role": role, "content": text})
    if user_text.strip():
        messages.append({"role": "user", "content": user_text.strip()})

    if not OPENAI:
        return "Thanks for calling. How can I help you today?"

    resp = OPENAI.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0.7,
        max_tokens=60,  # Shorter responses = faster
        messages=messages,
    )
    return (resp.choices[0].message.content or "").strip()

def tts_elevenlabs(text, voice_id):
    """Generate TTS audio using ElevenLabs"""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {"xi-api-key": ELEVEN_KEY, "accept": "audio/mpeg", "content-type": "application/json"}
    payload = {"text": text, "model_id": "eleven_turbo_v2_5", "voice_settings": {"stability": 0.5, "similarity_boost": 0.7}}
    r = requests.post(url, headers=headers, json=payload, timeout=60)
    r.raise_for_status()
    return r.content

def put_audio_cache(text, voice_id):
    """Cache TTS audio"""
    token = hashlib.sha1(f"{text}{voice_id}".encode()).hexdigest() + "-" + uuid.uuid4().hex[:6]
    if USE_ELEVEN:
        try:
            AUDIO_CACHE[token] = tts_elevenlabs(text, voice_id)
        except Exception as e:
            log("ElevenLabs failed", error=str(e))
            AUDIO_CACHE[token] = None
    else:
        AUDIO_CACHE[token] = None
    return token

@APP.get("/audio/<token>.mp3")
def audio_stream(token):
    """Serve cached audio"""
    from flask import abort
    data = AUDIO_CACHE.get(token)
    if not data:
        abort(404)
    return send_file(io.BytesIO(data), mimetype="audio/mpeg", as_attachment=False, download_name=f"{token}.mp3")

@APP.get("/thinking/<sound>.mp3")
def thinking_sound(sound):
    """Serve thinking sound audio files"""
    from flask import abort
    if sound not in THINKING_SOUNDS:
        abort(404)
    file_path = f"static/thinking_sounds/{sound}.mp3"
    if not os.path.exists(file_path):
        abort(404)
    return send_file(file_path, mimetype="audio/mpeg", as_attachment=False, download_name=f"{sound}.mp3")

# -------- Webhooks --------

@APP.post("/inbound")
def inbound():
    """Handle incoming calls - look up business by phone number"""
    call_sid = request.values.get("CallSid")
    from_number = request.values.get("From", "")
    to_number = request.values.get("To", "")

    log("Inbound call", call_sid=call_sid, from_number=from_number, to_number=to_number)

    # Look up which business owns this phone number
    business = get_business_by_phone(to_number)

    if not business:
        log("Business not found", phone=to_number)
        resp = VoiceResponse()
        resp.say("Sorry, this number is not configured. Please contact support.", voice="Polly.Matthew")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    # Create call record
    call_record = create_call_record(business['id'], call_sid, from_number, to_number, 'inbound')

    # Initialize session
    SESSIONS[call_sid] = {
        "history": deque(maxlen=40),
        "business": business,
        "call_id": call_record['id'] if call_record else None,
        "caller_phone": from_number
    }

    # Greeting
    agent_name = business.get('agent_name', 'Alex')
    business_name = business.get('business_name', 'our business')
    industry = business.get('industry', 'default')
    custom_greeting = business.get('custom_greeting')

    if custom_greeting:
        greeting = custom_greeting
    elif industry == 'sales':
        # Special greeting for sales calls
        greeting = f"Hi! This is {agent_name} from {business_name}. We build custom AI agents for small businesses that answer every call 24/7, book appointments automatically, handle customer questions, and ensure you never lose business to a missed call—starting at just $199 a month. What type of business are you calling about?"
    else:
        greeting = f"Hi, thanks for calling {business_name}! This is {agent_name}. How can I help you today?"

    SESSIONS[call_sid]["history"].append(("assistant", greeting))
    update_call_transcript(call_sid, "assistant", greeting)

    # Use business's voice or default
    voice_id = business.get('elevenlabs_voice_id', os.getenv('ELEVENLABS_VOICE_ID', 'onwK4e9ZLuTAKqWW03F9'))
    token = put_audio_cache(greeting, voice_id)

    resp = VoiceResponse()
    gather = Gather(
        input="speech",
        action=f"{PUBLIC_BASE}/ai",
        method="POST",
        speech_timeout=2,  # Wait 2 seconds of silence before ending
        timeout=10,  # Wait up to 10 seconds for user to start speaking
        language="en-US"
    )

    if USE_ELEVEN and AUDIO_CACHE.get(token):
        gather.play(f"{PUBLIC_BASE}/audio/{token}.mp3")
    else:
        gather.say(greeting, voice="Polly.Matthew")

    resp.append(gather)
    return Response(str(resp), mimetype="text/xml")

@APP.post("/ai")
def ai_endpoint():
    """Handle conversation turn"""
    call_sid = request.values.get("CallSid")
    user_text = request.values.get("SpeechResult", "").strip()

    if call_sid not in SESSIONS:
        log("Session not found", call_sid=call_sid)
        resp = VoiceResponse()
        resp.say("Sorry, session expired.", voice="Polly.Matthew")
        resp.hangup()
        return Response(str(resp), mimetype="text/xml")

    session = SESSIONS[call_sid]
    business = session['business']
    voice_id = business.get('elevenlabs_voice_id', os.getenv('ELEVENLABS_VOICE_ID', 'onwK4e9ZLuTAKqWW03F9'))

    # Log user input
    if user_text:
        session["history"].append(("user", user_text))
        update_call_transcript(call_sid, "user", user_text)

    # Generate AI response
    agent_line = ai_reply(business, session["history"], user_text)
    session["history"].append(("assistant", agent_line))
    update_call_transcript(call_sid, "assistant", agent_line)

    # Detect email collection for sales calls
    if business.get('industry') == 'sales' and not session.get('email_sent'):
        # Look for email pattern in user's latest message AND full history
        full_conversation = " ".join([text for role, text in session["history"] if role == "user"])

        # Convert spoken email format to actual email
        # "test at gmail dot com" -> "test@gmail.com"
        normalized = full_conversation.lower()
        normalized = re.sub(r'\s+at\s+', '@', normalized)
        normalized = re.sub(r'\s+dot\s+', '.', normalized)
        normalized = re.sub(r'\s+', '', normalized)  # Remove remaining spaces

        email_match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', normalized)

        print(f"DEBUG: Checking for email in conversation...")
        print(f"DEBUG: Original: {full_conversation}")
        print(f"DEBUG: Normalized: {normalized}")
        print(f"DEBUG: Match found: {email_match.group() if email_match else 'None'}")

        if email_match:
            email = email_match.group()
            print(f"DEBUG: Found email: {email}")

            # Extract name and business type from history
            customer_name = None
            business_type = None

            # Look through conversation history for name and business type
            for role, text in session["history"]:
                if role == "user":
                    # Try to detect business type mentions
                    if any(biz in text.lower() for biz in ['barber', 'salon', 'restaurant', 'gym', 'doctor', 'dental', 'medical']):
                        for biz in ['barber', 'salon', 'restaurant', 'gym', 'doctor', 'dental', 'medical']:
                            if biz in text.lower():
                                business_type = biz.title()
                                break

            # Use caller phone as fallback name
            customer_name = customer_name or session.get('caller_phone', 'there')
            business_type = business_type or 'your business'

            print(f"DEBUG: Attempting to send email to {email}, customer={customer_name}, type={business_type}")

            # Send demo email
            if send_demo_follow_up(customer_name, email, business_type):
                session['email_sent'] = True
                session['customer_email'] = email
                print(f"✓ Demo email sent successfully to {email}")
                log("Demo email sent", email=email, business_type=business_type)
            else:
                print(f"✗ Email send failed to {email}")

    # Generate TTS
    token = put_audio_cache(agent_line, voice_id)

    resp = VoiceResponse()

    # Play a random thinking sound first (simulates AI thinking)
    thinking_sound = random.choice(THINKING_SOUNDS)
    resp.play(f"{PUBLIC_BASE}/thinking/{thinking_sound}.mp3")

    gather = Gather(
        input="speech",
        action=f"{PUBLIC_BASE}/ai",
        method="POST",
        speech_timeout=2,  # Wait 2 seconds of silence before ending
        timeout=10,  # Wait up to 10 seconds for user to start speaking
        language="en-US"
    )

    if USE_ELEVEN and AUDIO_CACHE.get(token):
        gather.play(f"{PUBLIC_BASE}/audio/{token}.mp3")
    else:
        gather.say(agent_line, voice="Polly.Matthew")

    resp.append(gather)

    # Graceful close on silence
    close_line = "Thanks for calling. Have a great day!"
    if USE_ELEVEN:
        resp.play(f"{PUBLIC_BASE}/audio/{put_audio_cache(close_line, voice_id)}.mp3")
    else:
        resp.say(close_line, voice="Polly.Matthew")

    resp.hangup()
    return Response(str(resp), mimetype="text/xml")

@APP.post("/status")
def status_callback():
    """Handle call completion"""
    call_sid = request.values.get("CallSid")
    call_status = request.values.get("CallStatus")

    log("Status callback", call_sid=call_sid, status=call_status)

    if call_status == "completed":
        finalize_call(call_sid)

        # Clean up session
        if call_sid in SESSIONS:
            del SESSIONS[call_sid]

    return ("", 204)

@APP.get("/health")
def health():
    return {"ok": True, "time": datetime.utcnow().isoformat() + "Z", "platform": "Bolt AI Group"}

if __name__ == "__main__":
    log("Starting Bolt AI Platform", port=PORT, public_base=PUBLIC_BASE, elevenlabs=USE_ELEVEN)
    APP.run(host="0.0.0.0", port=PORT, debug=True)
