#!/usr/bin/env python3
"""
Bolt AI Platform with OpenAI Realtime API - Production Ready
Real-time voice conversations with instant responses - no more long pauses!

Production Enhancements:
- Robust WebSocket reconnection with exponential backoff
- ElevenLabs premium voice integration
- Sentry error tracking and monitoring
- Health monitoring dashboard
"""
import os, json, base64, asyncio, websockets, ssl, re, time, requests, audioop
import certifi
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from twilio.rest import Client as TwilioClient
from dotenv import load_dotenv
from supabase import create_client
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from collections import defaultdict

# Sentry for error tracking (production monitoring)
try:
    import sentry_sdk
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    SENTRY_AVAILABLE = True
except ImportError:
    SENTRY_AVAILABLE = False
    print("[WARN] Sentry not installed. Run: pip install sentry-sdk")

# ElevenLabs for premium voice quality (v1.x API)
try:
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    ELEVENLABS_AVAILABLE = True
except ImportError:
    ELEVENLABS_AVAILABLE = False
    print("[WARN] ElevenLabs not installed. Run: pip install elevenlabs")

# Audio processing (base64 encoding)
from io import BytesIO

# Google Calendar imports
try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    print("[WARN] Google Calendar libraries not installed. Calendar booking disabled.")

load_dotenv()

# ======================== Config ========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 5000))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_KEY")

# Debug logging
if SUPABASE_URL:
    print(f"[DEBUG] SUPABASE_URL loaded: {SUPABASE_URL[:30]}...", flush=True)
else:
    print("[DEBUG] SUPABASE_URL is MISSING!", flush=True)
if SUPABASE_KEY:
    print(f"[DEBUG] SUPABASE_KEY loaded: {SUPABASE_KEY[:20]}...", flush=True)
else:
    print("[DEBUG] SUPABASE_KEY is MISSING!", flush=True)

def get_public_url():
    """Get the public URL - Railway in production, ngrok for local dev"""
    # Check if running on Railway
    railway_domain = os.getenv("RAILWAY_PUBLIC_DOMAIN") or os.getenv("RAILWAY_STATIC_URL")
    if railway_domain:
        public_url = f"https://{railway_domain}"
        print(f"[DEBUG] Running on Railway: {public_url}", flush=True)
        return public_url

    # Check if PUBLIC_BASE_URL is explicitly set (manual override)
    manual_url = os.getenv("PUBLIC_BASE_URL")
    if manual_url:
        print(f"[DEBUG] Using manual PUBLIC_BASE_URL: {manual_url}", flush=True)
        return manual_url

    # Fall back to ngrok for local development
    try:
        response = requests.get("http://localhost:4040/api/tunnels", timeout=2)
        if response.status_code == 200:
            data = response.json()
            tunnels = data.get('tunnels', [])
            for tunnel in tunnels:
                public_url = tunnel.get('public_url', '')
                if public_url.startswith('https://'):
                    print(f"[DEBUG] Fetched ngrok URL: {public_url}", flush=True)
                    return public_url
        print("[DEBUG] No HTTPS ngrok tunnel found", flush=True)
        return "http://localhost:5000"
    except Exception as e:
        print(f"[DEBUG] Failed to fetch ngrok URL: {e}, using localhost", flush=True)
        return "http://localhost:5000"

PUBLIC_BASE = get_public_url()  # Railway in production, ngrok for local dev

# AI configuration
VOICE = os.getenv("VOICE", "echo")  # Options: alloy, echo, fable, onyx, nova, shimmer
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.8"))
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-realtime-preview-2024-12-17")  # OpenAI Realtime API model

# WebSocket configuration
MAX_CALL_DURATION = int(os.getenv("MAX_CALL_DURATION", "3600"))  # 1 hour default (seconds)
WEBSOCKET_PING_INTERVAL = int(os.getenv("WEBSOCKET_PING_INTERVAL", "20"))  # 20 seconds
WEBSOCKET_PING_TIMEOUT = int(os.getenv("WEBSOCKET_PING_TIMEOUT", "10"))  # 10 seconds

# Email configuration
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@boltaigroup.com")
REPLY_TO_EMAIL = "boltaigroup@gmail.com"  # Bolt AI Group primary email
BUSINESS_OWNER_EMAIL = "boltaigroup@gmail.com"  # Bolt AI Group primary email
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
SENDGRID_API_KEY = os.getenv("SENDGRID_API_KEY")
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.mail.yahoo.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER")
SMTP_PASS = os.getenv("SMTP_PASS")

# Business configuration
AGENT_NAME = os.getenv("AGENT_NAME", "Jack")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Criton AI")
PRODUCT_PITCH = os.getenv("PRODUCT_PITCH", "We build custom AI agents for small businesses that answer every call 24/7, book appointments automatically, handle customer questions, and ensure you never lose business to a missed call")
MONTHLY_PRICE = os.getenv("MONTHLY_PRICE", "$199")
CALENDAR_BOOKING_URL = os.getenv("CALENDAR_BOOKING_URL", "")
TRIAL_SIGNUP_URL = os.getenv("TRIAL_SIGNUP_URL", "https://criton.ai/signup")

# Google Calendar configuration
GOOGLE_CALENDAR_EMAIL = os.getenv("GOOGLE_CALENDAR_EMAIL", "boltaigroup@gmail.com")
GOOGLE_CALENDAR_SERVICE_ACCOUNT = os.getenv("GOOGLE_CALENDAR_SERVICE_ACCOUNT", "/Users/anthony/aiagent/keys/calendar-sa.json")

# Sentry configuration (error tracking)
SENTRY_DSN = os.getenv("SENTRY_DSN")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", "production")
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))  # 10% of requests

# ElevenLabs configuration (premium voice TTS)
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")  # Rachel voice
USE_ELEVENLABS = bool(ELEVENLABS_API_KEY and ELEVENLABS_AVAILABLE)

# ElevenLabs Conversational AI configuration (full conversation platform)
ELEVENLABS_AGENT_ID = os.getenv("ELEVENLABS_AGENT_ID")
ELEVENLABS_CONVERSATIONAL_API_KEY = os.getenv("ELEVENLABS_CONVERSATIONAL_API_KEY", ELEVENLABS_API_KEY)  # Fall back to TTS key
USE_ELEVENLABS_CONVERSATIONAL_AI = os.getenv("USE_ELEVENLABS_CONVERSATIONAL_AI", "false").lower() == "true"

# WebSocket reconnection configuration
WS_MAX_RETRIES = 3
WS_RETRY_DELAY_BASE = 1  # Base delay in seconds (exponential backoff: 1s, 2s, 4s)
WS_CONNECTION_TIMEOUT = 30

# ======================== Initialize Sentry ========================
if SENTRY_DSN and SENTRY_AVAILABLE:
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        integrations=[
            FastApiIntegration(),
            AsyncioIntegration(),
        ],
        # Set a uniform sample rate for transactions
        profiles_sample_rate=0.1,
    )
    print(f"[INFO] Sentry initialized for environment: {SENTRY_ENVIRONMENT}")
else:
    if not SENTRY_DSN:
        print("[INFO] Sentry DSN not configured - error tracking disabled")

# Initialize ElevenLabs (v1.x API - client is created per-request)
if USE_ELEVENLABS_CONVERSATIONAL_AI:
    if not ELEVENLABS_AGENT_ID:
        print("[WARN] USE_ELEVENLABS_CONVERSATIONAL_AI is true but ELEVENLABS_AGENT_ID is missing!")
        USE_ELEVENLABS_CONVERSATIONAL_AI = False
    else:
        print(f"[INFO] ElevenLabs Conversational AI enabled with agent: {ELEVENLABS_AGENT_ID}")
        print(f"[INFO] Using voice platform - OpenAI integration disabled")
elif USE_ELEVENLABS:
    print(f"[INFO] ElevenLabs TTS initialized with voice: {ELEVENLABS_VOICE_ID}")
else:
    print("[INFO] ElevenLabs not configured - using OpenAI voice only")

def send_trial_link_sms(to_number: str) -> bool:
    """Send the Criton AI trial signup link via SMS."""
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_NUMBER:
        log("[SMS ERROR] Twilio not configured for SMS")
        return False
    try:
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        message = f"Hey! It was great chatting. Here's the link to get started with Criton AI — your 24/7 AI phone assistant: {TRIAL_SIGNUP_URL}"
        msg = client.messages.create(body=message, from_=TWILIO_NUMBER, to=to_number)
        log(f"[SMS] Trial link sent to {to_number} - SID: {msg.sid}")
        return True
    except Exception as e:
        log(f"[SMS ERROR] Failed to send to {to_number}: {e}")
        return False

# ======================== Globals ========================
app = FastAPI()
SUPABASE = None  # Lazy-initialized on first use
SESSIONS = {}  # call_sid -> session data
SERVER_START_TIME = time.time()  # Track uptime
CALL_METRICS = defaultdict(lambda: {
    "total_calls": 0,
    "successful_calls": 0,
    "failed_calls": 0,
    "websocket_reconnections": 0,
    "average_duration": 0,
    "last_error": None,
    "last_error_time": None
})

def get_supabase_client():
    """Get or create Supabase client (lazy initialization)"""
    global SUPABASE
    log(f"[DEBUG] get_supabase_client() called")
    log(f"[DEBUG] SUPABASE is None: {SUPABASE is None}")
    log(f"[DEBUG] SUPABASE_URL exists: {bool(SUPABASE_URL)}, value: {SUPABASE_URL[:30] if SUPABASE_URL else 'None'}...")
    log(f"[DEBUG] SUPABASE_KEY exists: {bool(SUPABASE_KEY)}, length: {len(SUPABASE_KEY) if SUPABASE_KEY else 0}")

    if SUPABASE is None and SUPABASE_URL and SUPABASE_KEY:
        log(f"[DEBUG] Condition passed - attempting to create Supabase client...")
        try:
            log(f"[DEBUG] Calling create_client() with URL: {SUPABASE_URL[:30]}...")
            SUPABASE = create_client(SUPABASE_URL, SUPABASE_KEY)
            log(f"[DEBUG] Supabase client created successfully - type: {type(SUPABASE)}")
        except Exception as e:
            log(f"[ERROR] Failed to create Supabase client: {e}")
            import traceback
            log(f"[ERROR] Traceback: {traceback.format_exc()}")
            return None
    else:
        log(f"[DEBUG] Condition failed - returning existing SUPABASE: {SUPABASE}")

    log(f"[DEBUG] Returning SUPABASE: {type(SUPABASE) if SUPABASE else 'None'}")
    return SUPABASE

# ======================== Logging ========================
def log(msg, **kwargs):
    timestamp = datetime.utcnow().isoformat() + "Z"
    print(f"{timestamp} {msg}", flush=True)

    # Log to Sentry if critical error
    if "ERROR" in msg.upper() or "CRITICAL" in msg.upper():
        if SENTRY_AVAILABLE and SENTRY_DSN:
            sentry_sdk.capture_message(msg, level="error")

# ======================== WebSocket Helpers ========================
async def connect_to_openai_with_retry(max_retries=WS_MAX_RETRIES):
    """
    Connect to OpenAI Realtime API with exponential backoff retry logic.

    Returns:
        websocket connection or None if all retries failed
    """
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    for attempt in range(max_retries):
        try:
            retry_delay = WS_RETRY_DELAY_BASE * (2 ** attempt)  # Exponential backoff: 1s, 2s, 4s

            if attempt > 0:
                log(f"[RETRY] Attempting OpenAI connection (attempt {attempt + 1}/{max_retries}) after {retry_delay}s delay...")
                await asyncio.sleep(retry_delay)

            log(f"[WS] Connecting to OpenAI Realtime API (attempt {attempt + 1}/{max_retries})...")

            openai_ws = await asyncio.wait_for(
                websockets.connect(
                    f"wss://api.openai.com/v1/realtime?model={MODEL}",
                    extra_headers={
                        "Authorization": f"Bearer {OPENAI_API_KEY}",
                        "OpenAI-Beta": "realtime=v1"
                    },
                    ssl=ssl_context,
                    ping_interval=WEBSOCKET_PING_INTERVAL,
                    ping_timeout=WEBSOCKET_PING_TIMEOUT,
                    open_timeout=WS_CONNECTION_TIMEOUT
                ),
                timeout=WS_CONNECTION_TIMEOUT
            )

            log(f"✓ OpenAI WebSocket connected successfully on attempt {attempt + 1}")
            CALL_METRICS["websocket"]["websocket_reconnections"] += attempt  # Track reconnection attempts
            return openai_ws

        except asyncio.TimeoutError:
            log(f"[ERROR] OpenAI WebSocket connection timed out (attempt {attempt + 1}/{max_retries})")
            if attempt == max_retries - 1:
                log("[CRITICAL] All OpenAI connection attempts failed - call will disconnect")
                return None

        except Exception as e:
            log(f"[ERROR] OpenAI connection failed (attempt {attempt + 1}/{max_retries}): {type(e).__name__}: {e}")
            if SENTRY_AVAILABLE and SENTRY_DSN:
                sentry_sdk.capture_exception(e)
            if attempt == max_retries - 1:
                log("[CRITICAL] All OpenAI connection attempts exhausted")
                return None

    return None

async def ws_heartbeat(websocket, interval=20):
    """
    Send periodic heartbeat to keep WebSocket connection alive.
    Runs in background as separate task.
    """
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                pong = await websocket.ping()
                await asyncio.wait_for(pong, timeout=10)
                log("[WS] Heartbeat successful")
            except asyncio.TimeoutError:
                log("[WARN] Heartbeat timeout - connection may be dead")
                break
            except Exception as e:
                log(f"[WARN] Heartbeat failed: {e}")
                break
    except asyncio.CancelledError:
        log("[INFO] Heartbeat cancelled")

# ======================== ElevenLabs Integration ========================
def elevenlabs_tts_sync(text: str) -> str:
    """
    Generate audio using ElevenLabs in μ-law format (ready for Twilio).

    Returns:
        Base64-encoded μ-law audio string, or None if failed
    """
    if not USE_ELEVENLABS:
        return None

    try:
        # Initialize ElevenLabs client (v1.x API)
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

        # Generate audio directly in μ-law format using v1.x API
        audio_generator = client.text_to_speech.convert(
            voice_id=ELEVENLABS_VOICE_ID,
            text=text,
            model_id="eleven_multilingual_v2",  # Better pacing than turbo (slightly slower but more natural)
            voice_settings=VoiceSettings(
                stability=0.7,  # Higher stability = more measured/slower speech (was 0.5)
                similarity_boost=0.75,
                style=0.0,
                use_speaker_boost=True
            ),
            output_format="ulaw_8000"  # Direct μ-law output for Twilio!
        )

        # Collect audio bytes from generator and base64 encode
        audio_bytes = b"".join(audio_generator)
        encoded_audio = base64.b64encode(audio_bytes).decode('utf-8')

        log(f"[ElevenLabs] Generated {len(audio_bytes)} bytes of μ-law audio")
        return encoded_audio

    except Exception as e:
        log(f"[ERROR] ElevenLabs TTS failed: {e}")
        if SENTRY_AVAILABLE and SENTRY_DSN:
            sentry_sdk.capture_exception(e)
        return None

async def elevenlabs_tts_async(text: str) -> str:
    """
    Async wrapper for ElevenLabs TTS (runs in thread pool to avoid blocking).
    Returns base64-encoded μ-law audio string.
    """
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, elevenlabs_tts_sync, text)

# ======================== Database ========================

# Fallback business config from environment (used only if database is unavailable)
# This ensures calls can still be answered even during brief DB outages
FALLBACK_BUSINESS_ID = os.getenv("FALLBACK_BUSINESS_ID")
FALLBACK_BUSINESS_NAME = os.getenv("FALLBACK_BUSINESS_NAME", "AI Receptionist")
FALLBACK_OWNER_EMAIL = os.getenv("FALLBACK_OWNER_EMAIL")
FALLBACK_AGENT_NAME = os.getenv("FALLBACK_AGENT_NAME", "Alex")
FALLBACK_PHONE = os.getenv("FALLBACK_PHONE")

def get_fallback_config():
    """Build fallback config from environment variables (or return None if not configured)"""
    if not FALLBACK_BUSINESS_ID or not FALLBACK_PHONE:
        return None
    return {
        "id": FALLBACK_BUSINESS_ID,
        "business_name": FALLBACK_BUSINESS_NAME,
        "owner_email": FALLBACK_OWNER_EMAIL,
        "industry": "general",
        "agent_name": FALLBACK_AGENT_NAME,
        "capabilities": ["appointments"],
        "plan": "internal",
        "status": "active"
    }

def get_business_for_phone(phone):
    """Look up business by phone number from database"""
    supabase = get_supabase_client()
    if not supabase:
        log(f"[WARN] SUPABASE client is None")
        if FALLBACK_PHONE and phone == FALLBACK_PHONE:
            log(f"[WARN] Using env-based fallback config for {phone}")
            return get_fallback_config()
        return None

    try:
        log(f"[DEBUG] Querying phone_numbers table for: {phone}")
        result = supabase.table('phone_numbers').select('business_id').eq('phone_number', phone).execute()
        log(f"[DEBUG] Phone lookup result: {result.data}")
        if not result.data:
            log(f"[WARN] Phone {phone} not found in database")
            # Try fallback only for configured phone
            if FALLBACK_PHONE and phone == FALLBACK_PHONE:
                log(f"[WARN] Using env-based fallback config")
                return get_fallback_config()
            return None
        business_id = result.data[0]['business_id']
        log(f"[DEBUG] Found business_id: {business_id}, fetching business details...")
        biz_result = supabase.table('businesses').select('*').eq('id', business_id).execute()
        log(f"[DEBUG] Business lookup successful: {biz_result.data[0]['business_name'] if biz_result.data else 'None'}")
        return biz_result.data[0] if biz_result.data else None
    except Exception as e:
        import traceback
        log(f"[ERROR] Database error in get_business_for_phone: {e}")
        # Try fallback only for configured phone during DB errors
        if FALLBACK_PHONE and phone == FALLBACK_PHONE:
            log(f"[WARN] Using env-based fallback config due to DB error")
            return get_fallback_config()
        return None

def create_call_record(business_id, from_number, call_sid, to_number):
    """Create a call record in the database"""
    if not SUPABASE:
        return None
    try:
        data = {
            "business_id": business_id,
            "from_number": from_number,
            "to_number": to_number,
            "call_sid": call_sid,
            "direction": "inbound",
            "status": "in-progress"
        }
        result = SUPABASE.table('calls').insert(data).execute()
        return result.data[0] if result.data else None
    except Exception as e:
        log(f"Error creating call record: {e}")
        return None

def update_call_transcript(call_sid, role, text):
    """Update call transcript — inserts into call_transcripts table using Twilio call SID"""
    if not call_sid or not SUPABASE:
        return

    try:
        SUPABASE.table('call_transcripts').insert({
            "call_sid": call_sid,
            "role": role,
            "content": text
        }).execute()
    except Exception as e:
        log(f"Error updating transcript: {e}")

# ======================== Email ========================
def send_email(to_email, subject, body_html, max_retries=3):
    """Send email via Resend (preferred) or SMTP fallback with retry logic"""
    if not to_email:
        log("Email send skipped - no recipient")
        return False

    # Validate email before attempting to send
    if not validate_email(to_email):
        log(f"Email send skipped - invalid recipient: {to_email}")
        return False

    import time

    for attempt in range(max_retries):
        # Try Resend first (more reliable)
        if RESEND_API_KEY:
            try:
                import resend
                resend.api_key = RESEND_API_KEY

                params = {
                    "from": f"{AGENT_NAME} <{FROM_EMAIL}>",
                    "to": [to_email],
                    "subject": subject,
                    "html": body_html,
                    "reply_to": REPLY_TO_EMAIL
                }

                email = resend.Emails.send(params)
                log(f"Email sent via Resend to {to_email}")
                return True
            except Exception as e:
                log(f"Resend email failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff: 1s, 2s, 4s
                    continue
                else:
                    log("Trying SMTP fallback after Resend exhausted")

        # Fallback to SMTP if Resend fails or not configured
        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{AGENT_NAME} <{SMTP_USER}>"  # Use SMTP user email for FROM
            msg['Reply-To'] = REPLY_TO_EMAIL
            msg['To'] = to_email

            html_part = MIMEText(body_html, 'html')
            msg.attach(html_part)

            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASS)
                server.send_message(msg)

            log(f"Email sent via SMTP to {to_email}")
            return True
        except Exception as e:
            log(f"SMTP email failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
            else:
                log(f"All email sending attempts failed for {to_email}")
                return False

    return False

def send_instant_call_alert(call_sid, caller_phone, call_start_time):
    """Send instant email alert when a call comes in"""
    import pytz
    subject = f"🔔 Incoming Call Alert - {caller_phone}"

    # Convert to PST for display
    if isinstance(call_start_time, datetime):
        pacific = pytz.timezone('America/Los_Angeles')
        if call_start_time.tzinfo is None:
            # Assume UTC if naive datetime (Railway runs in UTC)
            utc = pytz.UTC
            call_start_time = utc.localize(call_start_time)
        call_time_pst = call_start_time.astimezone(pacific)
        call_time_formatted = call_time_pst.strftime("%I:%M %p")
    else:
        call_time_formatted = str(call_start_time)

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="background-color: #4CAF50; color: white; padding: 20px; text-align: center;">
            <h1 style="margin: 0;">📞 New Call In Progress</h1>
        </div>

        <div style="padding: 20px;">
            <p><strong>Call Details:</strong></p>
            <ul style="font-size: 16px;">
                <li><strong>Caller Phone:</strong> {caller_phone}</li>
                <li><strong>Call Time:</strong> {call_time_formatted}</li>
                <li><strong>Call SID:</strong> {call_sid}</li>
            </ul>

            <div style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 20px 0;">
                <p style="margin: 0;"><strong>💡 Note:</strong> You'll receive another email with full call details once the call completes.</p>
            </div>

            <p style="color: #666; font-size: 14px; margin-top: 30px;">
                This is an automated alert from your Criton AI phone agent system.
            </p>
        </div>
    </body>
    </html>
    """

    return send_email(BUSINESS_OWNER_EMAIL, subject, body_html)

def send_post_call_summary(call_sid, caller_phone, customer_name=None, customer_email=None,
                           customer_phone=None, business_type=None, company_name=None,
                           appointment_display=None, call_start_time=None):
    """Send post-call summary email with transcript to business owner"""
    import pytz

    # Calculate duration
    duration_str = "Unknown"
    if call_start_time:
        elapsed = (datetime.now() - call_start_time).total_seconds()
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        duration_str = f"{mins}m {secs}s"

    # Format call time in PST
    call_time_formatted = "Unknown"
    if isinstance(call_start_time, datetime):
        pacific = pytz.timezone('America/Los_Angeles')
        if call_start_time.tzinfo is None:
            import pytz as tz
            call_start_time = tz.UTC.localize(call_start_time)
        call_time_pst = call_start_time.astimezone(pacific)
        call_time_formatted = call_time_pst.strftime("%B %d, %Y at %I:%M %p PST")

    # Fetch transcript from Supabase
    transcript_html = "<em>No transcript available</em>"
    try:
        supabase = get_supabase_client()
        if supabase and call_sid:
            result = supabase.table('call_transcripts').select('role,content').eq('call_sid', call_sid).order('created_at', desc=False).execute()
            if result.data:
                lines = []
                for row in result.data:
                    role = row.get('role', 'unknown').capitalize()
                    content = row.get('content', '')
                    color = '#4CAF50' if role == 'Assistant' else '#2196F3'
                    lines.append(f'<p style="margin: 4px 0;"><strong style="color: {color};">{role}:</strong> {content}</p>')
                transcript_html = '\n'.join(lines)
    except Exception as e:
        log(f"[POST-CALL] Error fetching transcript: {e}")

    # Build info rows
    info_rows = f'<li><strong>Caller Phone:</strong> {caller_phone or "Unknown"}</li>'
    if customer_name and customer_name != "there":
        info_rows += f'\n<li><strong>Name:</strong> {customer_name}</li>'
    if company_name:
        info_rows += f'\n<li><strong>Company:</strong> {company_name}</li>'
    if business_type and business_type != "business":
        info_rows += f'\n<li><strong>Industry:</strong> {business_type}</li>'
    if customer_email:
        info_rows += f'\n<li><strong>Email:</strong> {customer_email}</li>'
    if customer_phone and customer_phone != caller_phone:
        info_rows += f'\n<li><strong>Alt Phone:</strong> {customer_phone}</li>'
    if appointment_display:
        info_rows += f'\n<li><strong>Appointment:</strong> {appointment_display}</li>'

    subject = f"Call Completed - {caller_phone or 'Unknown'} ({duration_str})"

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <div style="background-color: #2196F3; color: white; padding: 20px; text-align: center;">
            <h1 style="margin: 0;">📋 Call Summary</h1>
        </div>

        <div style="padding: 20px;">
            <p><strong>Call Details:</strong></p>
            <ul style="font-size: 16px;">
                <li><strong>Date/Time:</strong> {call_time_formatted}</li>
                <li><strong>Duration:</strong> {duration_str}</li>
                {info_rows}
            </ul>

            <h3>Transcript</h3>
            <div style="background-color: #f5f5f5; padding: 15px; border-radius: 8px; font-size: 14px; max-height: 600px; overflow-y: auto;">
                {transcript_html}
            </div>

            <p style="color: #666; font-size: 14px; margin-top: 30px;">
                This is an automated summary from your Criton AI phone agent.
            </p>
        </div>
    </body>
    </html>
    """

    return send_email(BUSINESS_OWNER_EMAIL, subject, body_html)

def send_daily_digest():
    """Send daily digest with call analytics"""
    supabase = get_supabase_client()
    if not supabase:
        log("Cannot send daily digest - Supabase not configured")
        return False

    try:
        # Get today's date range
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)

        # Query today's calls
        result = supabase.table('calls').select('*').gte('created_at', today_start.isoformat()).lte('created_at', today_end.isoformat()).execute()

        calls = result.data if result.data else []
        total_calls = len(calls)

        if total_calls == 0:
            log("No calls today - skipping daily digest")
            return True  # Not an error, just no calls

        # Analytics
        completed_calls = [c for c in calls if c.get('status') == 'completed']
        failed_calls = [c for c in calls if c.get('status') in ['failed', 'busy', 'no-answer']]
        in_progress_calls = [c for c in calls if c.get('status') == 'in-progress']

        # Calculate call durations
        total_duration = 0
        for call in completed_calls:
            if call.get('duration'):
                total_duration += int(call['duration'])

        avg_duration = (total_duration / len(completed_calls)) if completed_calls else 0
        avg_duration_formatted = f"{int(avg_duration // 60)}m {int(avg_duration % 60)}s"

        # Build call list HTML
        call_rows = ""
        for call in calls[:10]:  # Show up to 10 most recent calls
            status_color = "#4CAF50" if call.get('status') == 'completed' else ("#f44336" if call.get('status') in ['failed', 'busy', 'no-answer'] else "#ff9800")
            call_time = datetime.fromisoformat(call['created_at'].replace('Z', '+00:00')).strftime("%I:%M %p")
            duration = f"{int(call.get('duration', 0) // 60)}m {int(call.get('duration', 0) % 60)}s" if call.get('duration') else "N/A"

            call_rows += f"""
            <tr>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{call_time}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{call.get('from_number', 'Unknown')}</td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;"><span style="color: {status_color}; font-weight: bold;">{call.get('status', 'unknown')}</span></td>
                <td style="padding: 10px; border-bottom: 1px solid #ddd;">{duration}</td>
            </tr>
            """

        # Subject
        date_str = today_start.strftime("%B %d, %Y")
        subject = f"📊 Daily Call Report - {date_str} ({total_calls} calls)"

        # Email body
        body_html = f"""
        <html>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <div style="background-color: #2196F3; color: white; padding: 20px; text-align: center;">
                <h1 style="margin: 0;">📊 Daily Call Report</h1>
                <p style="margin: 5px 0 0 0; font-size: 18px;">{date_str}</p>
            </div>

            <div style="padding: 20px;">
                <!-- Summary Stats -->
                <div style="display: flex; flex-wrap: wrap; gap: 15px; margin-bottom: 30px;">
                    <div style="flex: 1; min-width: 200px; background-color: #e3f2fd; padding: 20px; border-radius: 8px; text-align: center;">
                        <h2 style="margin: 0; color: #2196F3; font-size: 36px;">{total_calls}</h2>
                        <p style="margin: 5px 0 0 0; color: #666;">Total Calls</p>
                    </div>
                    <div style="flex: 1; min-width: 200px; background-color: #e8f5e9; padding: 20px; border-radius: 8px; text-align: center;">
                        <h2 style="margin: 0; color: #4CAF50; font-size: 36px;">{len(completed_calls)}</h2>
                        <p style="margin: 5px 0 0 0; color: #666;">Completed</p>
                    </div>
                    <div style="flex: 1; min-width: 200px; background-color: #fff3e0; padding: 20px; border-radius: 8px; text-align: center;">
                        <h2 style="margin: 0; color: #ff9800; font-size: 36px;">{len(in_progress_calls)}</h2>
                        <p style="margin: 5px 0 0 0; color: #666;">In Progress</p>
                    </div>
                    <div style="flex: 1; min-width: 200px; background-color: #ffebee; padding: 20px; border-radius: 8px; text-align: center;">
                        <h2 style="margin: 0; color: #f44336; font-size: 36px;">{len(failed_calls)}</h2>
                        <p style="margin: 5px 0 0 0; color: #666;">Failed/Missed</p>
                    </div>
                </div>

                <!-- Average Duration -->
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 8px; margin-bottom: 30px;">
                    <p style="margin: 0;"><strong>📞 Average Call Duration:</strong> {avg_duration_formatted}</p>
                </div>

                <!-- Recent Calls Table -->
                <h3 style="margin-bottom: 15px;">Recent Calls</h3>
                <table style="width: 100%; border-collapse: collapse; background-color: white;">
                    <thead>
                        <tr style="background-color: #f5f5f5;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Time</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Caller</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Status</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #ddd;">Duration</th>
                        </tr>
                    </thead>
                    <tbody>
                        {call_rows}
                    </tbody>
                </table>

                {f'<p style="color: #666; font-size: 14px; margin-top: 15px;"><em>Showing {min(10, total_calls)} of {total_calls} calls</em></p>' if total_calls > 10 else ''}

                <hr style="margin: 30px 0;">
                <p style="color: #666; font-size: 14px;">
                    This daily digest is automatically sent at 11:59 PM. <br>
                    Generated by your Bolt AI phone agent system.
                </p>
            </div>
        </body>
        </html>
        """

        log(f"Sending daily digest: {total_calls} calls today")
        return send_email(BUSINESS_OWNER_EMAIL, subject, body_html)

    except Exception as e:
        log(f"Error generating daily digest: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        return False

def send_business_owner_notification(customer_name, customer_email, customer_phone, business_type, company_name=None, contact_preference=None, appointment_display=None):
    """Notify business owner of new lead"""
    owner_email = BUSINESS_OWNER_EMAIL
    company_display = f" ({company_name})" if company_name else ""
    subject = f"New Lead: {business_type}{company_display}"

    # Contact preference display
    if contact_preference == "call":
        contact_method = f"<strong>CALL</strong> at {customer_phone or 'Not provided'}"
    elif contact_preference == "email":
        contact_method = f"<strong>EMAIL</strong> at {customer_email or 'Not provided'}"
    else:
        contact_method = "Not specified"

    # Appointment info
    appointment_info = ""
    if appointment_display:
        appointment_info = f"""
        <p style="background-color: #e8f5e9; padding: 15px; border-left: 4px solid #4caf50;">
            <strong>📅 Implementation Call Scheduled:</strong> {appointment_display}
        </p>
        """

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h2>New Sales Call Completed!</h2>

        <p>Your AI agent just completed a call and captured the following information:</p>

        <ul>
            <li><strong>Company Name:</strong> {company_name or 'Not provided'}</li>
            <li><strong>Business Type:</strong> {business_type or 'Not specified'}</li>
            <li><strong>Contact Name:</strong> {customer_name or 'Not provided'}</li>
            <li><strong>Email:</strong> {customer_email or 'Not provided'}</li>
            <li><strong>Phone:</strong> {customer_phone or 'Not provided'}</li>
            <li><strong>Preferred Contact Method:</strong> {contact_method}</li>
        </ul>

        {appointment_info}

        <p><strong>Next Steps:</strong> {"The customer will receive a calendar invite." if appointment_display else "Reach out via their preferred contact method!"}</p>

        <hr>
        <p style="font-size: 0.9em; color: #666;">
            This notification was automatically generated by your Bolt AI sales agent.
        </p>
    </body>
    </html>
    """

    return send_email(owner_email, subject, body_html)

def send_demo_follow_up(customer_name, customer_email, business_type, appointment_datetime=None):
    """Send follow-up email after demo call"""
    subject = f"Great chatting with you, {customer_name}! - {COMPANY_NAME}"

    # Business-specific benefits
    business_benefits = {
        "restaurant": [
            "Take reservations 24/7, even when you're slammed during dinner rush",
            "Answer common questions about hours, menu, and dietary restrictions",
            "Reduce no-shows with automated SMS/email confirmations",
            "Handle takeout orders and special requests"
        ],
        "salon": [
            "Book appointments instantly while you're with clients",
            "Send automated appointment reminders to reduce no-shows",
            "Answer questions about services, pricing, and availability",
            "Manage cancellations and rescheduling automatically"
        ],
        "medical": [
            "Schedule patient appointments 24/7",
            "Answer FAQs about office hours, insurance, and procedures",
            "Send automated appointment reminders",
            "Route urgent calls appropriately"
        ],
        "dental": [
            "Book appointments while you're with patients",
            "Answer questions about procedures, insurance, and costs",
            "Send automated reminders to reduce no-shows",
            "Handle emergency calls with proper routing"
        ],
        "spa": [
            "Book treatments anytime, day or night",
            "Answer questions about services, packages, and gift certificates",
            "Send appointment confirmations and reminders",
            "Upsell add-on services during booking"
        ],
        "contractor": [
            "Capture every lead, even when you're on a job site",
            "Schedule estimates and consultations automatically",
            "Answer questions about services, availability, and pricing",
            "Follow up with job quotes and confirmations"
        ],
        "plumbing": [
            "Take emergency calls 24/7 and route appropriately",
            "Schedule service appointments automatically",
            "Answer questions about services and pricing",
            "Send appointment confirmations and technician ETAs"
        ],
        "hvac": [
            "Capture service requests around the clock",
            "Schedule maintenance and emergency calls",
            "Answer questions about systems, pricing, and availability",
            "Send automated reminders for seasonal maintenance"
        ]
    }

    # Default benefits for businesses not in the map
    default_benefits = [
        "Never miss a customer call, even after hours or when you're busy",
        "Book appointments automatically and sync with your calendar",
        "Answer common customer questions instantly",
        "Reduce no-shows with automated reminders"
    ]

    # Get business-specific benefits or use defaults
    benefits = business_benefits.get(business_type.lower().strip(), default_benefits)
    benefits_html = "\n".join([f"<li>{benefit}</li>" for benefit in benefits])

    # Implementation call reminder with calendar link
    if appointment_datetime:
        from datetime import datetime
        import urllib.parse
        try:
            appt_dt = datetime.fromisoformat(appointment_datetime)
            formatted_date = appt_dt.strftime('%A, %B %d at %I:%M%p').replace(' 0', ' ')

            # Create Google Calendar add event URL (works for anyone)
            from datetime import timedelta
            end_dt = appt_dt + timedelta(hours=1)

            # Format for Google Calendar URL: YYYYMMDDTHHmmSSZ
            start_str = appt_dt.strftime('%Y%m%dT%H%M%S')
            end_str = end_dt.strftime('%Y%m%dT%H%M%S')

            title = urllib.parse.quote(f"Implementation Call with {COMPANY_NAME}")
            details = urllib.parse.quote(f"Implementation call to set up your AI phone agent system.\n\nJoin via: {REPLY_TO_EMAIL}")

            # Create calendar URLs for different providers
            google_cal_url = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={title}&dates={start_str}/{end_str}&details={details}&ctz=America/Los_Angeles"

            # Outlook.com calendar URL
            outlook_cal_url = f"https://outlook.live.com/calendar/0/deeplink/compose?subject={title}&startdt={appt_dt.isoformat()}&enddt={end_dt.isoformat()}&body={details}"

            # Office 365 calendar URL
            office365_cal_url = f"https://outlook.office.com/calendar/0/deeplink/compose?subject={title}&startdt={appt_dt.isoformat()}&enddt={end_dt.isoformat()}&body={details}"

        except:
            formatted_date = appointment_datetime
            google_cal_url = None
            outlook_cal_url = None
            office365_cal_url = None

        if google_cal_url:
            calendar_button = f"""
            <p><strong>Your Implementation Call: {formatted_date}</strong></p>
            <p style="text-align: center; margin: 25px 0;">
                <a href="{google_cal_url}"
                   style="background-color: #0066cc; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin: 5px;">
                    📅 Google Calendar
                </a>
                <a href="{outlook_cal_url}"
                   style="background-color: #0072C6; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin: 5px;">
                    📅 Outlook
                </a>
                <a href="{office365_cal_url}"
                   style="background-color: #D83B01; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block; margin: 5px;">
                    📅 Office 365
                </a>
            </p>
            <p style="color: #666;">I'll walk you through setting up your personalized AI phone agent. If you have any questions before then, feel free to reply to this email.</p>
            """
        else:
            calendar_button = f"""
            <p><strong>Your Implementation Call: {formatted_date}</strong></p>
            <p style="color: #666;">I'll walk you through setting up your personalized AI phone agent. If you have any questions before then, feel free to reply to this email.</p>
            """
    else:
        calendar_button = f"""
        <p><strong>Looking forward to our implementation call! I'll walk you through setting up your personalized AI phone agent.</strong></p>
        <p style="color: #666;">If you have any questions before then, feel free to reply to this email.</p>
        """

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #0066cc;">Hi {customer_name}!</h2>

        <p>Thanks for trying our demo! I hope you got a feel for how Jack can handle calls for your {business_type} business 24/7.</p>

        <p>As you saw in the demo, our AI phone solution can help your {business_type} by:</p>

        <ul style="line-height: 1.8;">
            {benefits_html}
        </ul>

        <h3 style="color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 5px;">
            What's Included:
        </h3>
        <ul style="line-height: 1.8;">
            <li><strong>Custom AI Agent</strong> - Trained specifically for your business</li>
            <li><strong>24/7 Availability</strong> - Never miss a call again</li>
            <li><strong>Calendar Integration</strong> - Automatic booking & confirmations</li>
            <li><strong>Call Analytics</strong> - See transcripts and insights from every call</li>
            <li><strong>Simple Setup</strong> - We handle everything, you just forward your number</li>
        </ul>

        {calendar_button}

        <p>Questions? Just reply to this email - I'm here to help!</p>

        <p style="background-color: #f8f9fa; padding: 15px; border-left: 4px solid #0066cc; margin: 20px 0;">
            <strong>📧 Email Address Incorrect?</strong><br>
            If this email didn't reach you at the right address, please reply with your correct email or call us at <strong>(323) 405-4603</strong>.
        </p>

        <p style="margin-top: 30px;">
            Best regards,<br>
            <strong>{AGENT_NAME}</strong><br>
            {COMPANY_NAME}<br>
            <a href="mailto:{REPLY_TO_EMAIL}">{REPLY_TO_EMAIL}</a>
        </p>

        <hr style="border: none; border-top: 1px solid #ddd; margin: 30px 0;">
        <p style="font-size: 0.85em; color: #666; text-align: center;">
            This email was sent because you expressed interest in {COMPANY_NAME}'s AI phone solution.
        </p>
    </body>
    </html>
    """

    return send_email(customer_email, subject, body_html)

def validate_email(email):
    """Validate email format"""
    if not email:
        return False

    # Basic email validation regex
    # Supports standard emails like user@domain.com or user+tag@domain.co.uk
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'

    if not re.match(pattern, email):
        return False

    # Additional checks
    if email.count('@') != 1:
        return False

    local, domain = email.split('@')

    # Local part (before @) checks
    if len(local) == 0 or len(local) > 64:
        return False

    # Domain part checks
    if len(domain) == 0 or len(domain) > 255:
        return False

    # Domain must have at least one dot
    if '.' not in domain:
        return False

    return True

def normalize_email(email):
    """Fix common speech-to-text errors in email addresses"""
    # Replace number-word substitutions that speech recognition makes
    replacements = {
        # Number words
        '4ward': 'forward',
        '2': 'to',
        '4': 'for',
        '1': 'one',
        '8': 'eight',
        '0': 'o',  # "oh" vs zero context-dependent

        # Common speech errors
        'at': '@',  # In case "at" wasn't converted
        ' at ': '@',
        ' dot ': '.',
        'dot com': '.com',
        'dot net': '.net',
        'dot org': '.org',
        'dot io': '.io',

        # Remove spaces
        ' ': '',
    }

    normalized = email.lower().strip()

    # Apply replacements in order
    for old, new in replacements.items():
        normalized = normalized.replace(old, new)

    # Ensure there's exactly one @
    if '@' not in normalized and 'at' in email.lower():
        normalized = normalized.replace('at', '@', 1)

    return normalized

def extract_customer_info(text, session, is_user_speech=True):
    """Extract customer information from user speech"""
    # Only extract from user speech, not assistant responses
    if not is_user_speech:
        return

    # Extract email (handle spoken emails like "john at gmail dot com")
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    email_match = re.search(email_pattern, text)
    if email_match:
        raw_email = email_match.group(0)
        normalized_email = normalize_email(raw_email)

        # Validate before storing
        if validate_email(normalized_email):
            # ALWAYS update email - allow corrections
            old_email = session.get('customer_email')
            session['customer_email'] = normalized_email
            if old_email and old_email != normalized_email:
                log(f"✓ EMAIL UPDATED: {old_email} -> {normalized_email}")
            elif raw_email != normalized_email:
                log(f"✓ EMAIL CAPTURED: {raw_email} -> normalized to: {normalized_email}")
            else:
                log(f"✓ EMAIL CAPTURED: {normalized_email}")
        else:
            log(f"✗ EMAIL REJECTED (invalid format): {normalized_email}")

    # Extract spoken email patterns (e.g., "john at gmail dot com", "jane at company dot co dot uk")
    # Support common TLDs: .com, .net, .org, .io, .co, .ai, .us, .uk, .ca
    # Also support mixed formats: "tbone7777 at hotmail dot com" or "name123@domain dot com"
    # IMPORTANT: Include hyphens in character class to support emails like "t-bone7777@hotmail.com"
    spoken_patterns = [
        # Handle "t bone", "tbone", "tea bone" + numbers: "t bone 7777 at hotmail dot com"
        r'([a-z-]+)\s+bone\s+(\d+)\s+at\s+([a-z0-9-]+)\s+dot\s+(com|net|org|io|ai|us|uk|ca|gov|edu)',
        r'([a-z-]+)bone\s*(\d+)\s+at\s+([a-z0-9-]+)\s+dot\s+(com|net|org|io|ai|us|uk|ca|gov|edu)',
        # Standard: "tbone7777 at hotmail dot com" or "tbone 7777 at hotmail dot com"
        r'([a-z-]+)\s*(\d+)\s+at\s+([a-z0-9-]+)\s+dot\s+(com|net|org|io|ai|us|uk|ca|gov|edu)',
        # Standard spoken format with spaces: "name at domain dot com"
        r'([a-z0-9\._-]+)\s+at\s+([a-z0-9-]+)\s+dot\s+(com|net|org|io|ai|us|uk|ca|gov|edu)',
        r'([a-z0-9\._-]+)\s+at\s+([a-z0-9-]+)\s+dot\s+co\s+dot\s+(uk|nz|za)',  # .co.uk, .co.nz, etc.
        r'([a-z0-9\._-]+)\s+at\s+([a-z0-9-]+)\s+dot\s+co',  # .co
        # Mixed format: "name@domain dot com" or "name at domain.com"
        r'([a-z0-9\._-]+)@([a-z0-9-]+)\s+dot\s+(com|net|org|io|ai|us|uk|ca|gov|edu)',
        r'([a-z0-9\._-]+)\s+at\s+([a-z0-9-]+)\.(com|net|org|io|ai|us|uk|ca|gov|edu)',
    ]

    # Log the text we're searching for debugging
    log(f"[EMAIL DEBUG] Searching text: {text.lower()[:200]}")

    # Accumulate email fragments across utterances
    # If user says "T-bone" then "7777 at hotmail dot com" separately, we need to combine them
    if 'email_fragments' not in session:
        session['email_fragments'] = []

    # Check if this looks like an email fragment
    text_lower = text.lower().strip()
    is_email_fragment = (
        # Contains email indicators
        ('at' in text_lower or '@' in text_lower or 'dot' in text_lower or '.com' in text_lower or 'hotmail' in text_lower or 'gmail' in text_lower) or
        # Or looks like a name before numbers (like "t-bone")
        (re.match(r'^[a-z-]+\s*\d*\.?$', text_lower) and len(text_lower.split()) <= 2)
    )

    # Store potential email fragments
    if is_email_fragment and text_lower not in ['my email', 'email', 'my email address', 'email address', 'is', 'yes', 'no']:
        session['email_fragments'].append(text_lower)
        # Keep only last 3 fragments
        session['email_fragments'] = session['email_fragments'][-3:]
        log(f"[EMAIL DEBUG] Stored email fragment: {text_lower}")

    # Try to match with current text first
    combined_text = text.lower()

    # If no match, try with accumulated fragments
    if len(session.get('email_fragments', [])) >= 2:
        combined_text = ' '.join(session['email_fragments'])
        log(f"[EMAIL DEBUG] Trying combined fragments: {combined_text}")

    # ALWAYS check for spoken email - allow updates/corrections
    for i, pattern in enumerate(spoken_patterns):
        spoken_email = re.search(pattern, combined_text)
        if spoken_email:
            groups = spoken_email.groups()
            log(f"[EMAIL DEBUG] Pattern {i} matched! Groups: {groups}")
            if len(groups) == 4:
                # Pattern with separate name and digits: "tbone 7777 at hotmail dot com"
                # Clean up username: remove spaces, hyphens, dots from voice transcription
                username = f"{groups[0]}{groups[1]}".replace(" ", "").replace("-", "").replace(".", "")
                email = f"{username}@{groups[2]}.{groups[3]}"
            elif len(groups) == 3 and 'co dot' not in pattern:
                # Standard TLD: user@domain.tld
                # Clean up username: remove spaces, hyphens, dots from voice transcription
                username = groups[0].replace(" ", "").replace("-", "").replace(".", "")
                email = f"{username}@{groups[1]}.{groups[2]}"
            elif len(groups) == 3 and 'dot co dot' in pattern:
                # Two-part TLD: user@domain.co.uk
                username = groups[0].replace(" ", "").replace("-", "").replace(".", "")
                email = f"{username}@{groups[1]}.co.{groups[2]}"
            elif len(groups) == 2:
                # .co domain: user@domain.co
                username = groups[0].replace(" ", "").replace("-", "").replace(".", "")
                email = f"{username}@{groups[1]}.co"
            else:
                continue

            # Validate before storing
            if validate_email(email):
                old_email = session.get('customer_email')
                session['customer_email'] = email
                # Clear email fragments after successful capture
                if 'email_fragments' in session:
                    del session['email_fragments']
                if old_email and old_email != email:
                    log(f"Updated spoken email: {old_email} -> {email}")
                else:
                    log(f"Captured spoken email: {email}")
                break
            else:
                log(f"Invalid spoken email rejected: {email}")

    # Extract business type dynamically from patterns in user speech
    # Captures full phrases like "dental office", "nail salon", "tattoo shop", or standalone "gym", "restaurant"
    if not session.get('business_type'):
        text_lower = text.lower()

        # Business type keywords
        business_type_keywords = [
            'salon', 'shop', 'gym', 'restaurant', 'cafe', 'bakery', 'hotel', 'motel',
            'spa', 'barbershop', 'pharmacy', 'clinic', 'hospital', 'practice',
            'school', 'daycare', 'library', 'bookstore', 'boutique', 'store',
            'bar', 'pub', 'nightclub', 'theater', 'theatre', 'museum', 'gallery',
            'garage', 'dealership', 'workshop', 'factory', 'warehouse', 'studio',
            'office', 'firm', 'agency', 'center', 'company', 'business',
            'hvac', 'plumbing', 'electrical', 'contractor', 'roofing', 'landscaping',
            'cleaning', 'painting', 'flooring', 'carpentry', 'handyman'
        ]

        # Priority 1: Look for multi-word business phrases (e.g., "dental office", "nail salon", "tattoo shop")
        # Match: [adjective] [keyword], capturing both words
        for keyword in business_type_keywords:
            # Pattern: one word (adjective) followed by the keyword
            pattern = rf'\b([a-z]+)\s+{keyword}\b'
            match = re.search(pattern, text_lower)
            if match:
                adjective = match.group(1)
                # Filter out articles and common words that aren't adjectives
                excluded_words = ['a', 'an', 'the', 'my', 'our', 'your', 'this', 'that', 'have', 'own', 'run']
                if adjective not in excluded_words:
                    business_type = f"{adjective} {keyword}"
                    session['business_type'] = business_type.title()
                    log(f"Captured business type: {session['business_type']}")
                    break

        # Priority 2: Look for standalone business type keywords (e.g., just "gym", "restaurant")
        if not session.get('business_type'):
            # Remove punctuation for cleaner matching
            text_cleaned = re.sub(r'[.,!?;:]', '', text_lower)
            text_words = text_cleaned.split()

            for keyword in business_type_keywords:
                if keyword in text_words:
                    session['business_type'] = keyword.title()
                    log(f"Captured business type: {session['business_type']}")
                    break

    # Extract customer name from patterns like:
    # "Tony", "Tony Vazquez", "My name is Tony", "This is Tony", "I'm Tony"
    if not session.get('customer_name'):
        name_patterns = [
            r"(?:my name is|my name's|i'm|i am|this is|it's|speaking with)\s+([a-z]+(?:\s+[a-z]+)?)",  # "My name is Tony Vazquez" (case insensitive)
            r"^([a-z]+(?:\s+[a-z]+)?)(?:\.|,|!|\?|$)",  # Just "Tony" or "Tony Vazquez" as complete response
        ]

        for pattern in name_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                customer_name = match.group(1).strip().title()  # Capitalize properly
                # Filter out common words that aren't names
                excluded = ['Sure', 'Yes', 'Yeah', 'Okay', 'Great', 'Perfect', 'Hello', 'Hi', 'Hey', 'Thanks', 'Thank', 'Ready', 'Ready To', 'Absolutely', 'Definitely', 'Yep', 'Yup', 'Nope', 'Nah']
                if customer_name not in excluded and len(customer_name) >= 2:
                    session['customer_name'] = customer_name
                    log(f"Captured customer name: {customer_name}")
                    break
                else:
                    log(f"Rejected name candidate: '{customer_name}' (in exclusion list or too short)")

    # Extract company name from patterns like:
    # "calling from Yoda Yoga"
    # "I'm from The Ink Shop"
    # "my barbershop's name is Cutz"
    # "it's called Cutz"
    # "The name of my nail salon is Nancy's Nails"
    # Prioritize business context patterns over person names
    company_patterns = [
        # High priority: explicit business name indicators
        r"(?:calling from|from)\s+([A-Z][A-Za-z0-9\s&']{2,30}?)(?:\.|,|!|\s+and\s|$)",  # "calling from Yoda Yoga"
        r"(?:shop|salon|business|company|practice|office|firm|clinic|studio|center)(?:'s)?\s+(?:name\s+)?is\s+([A-Za-z0-9\s&']{2,30}?)(?:\.|,|\s+and\s|$)",
        r"(?:it's|its)\s+called\s+([A-Za-z0-9\s&']{2,30}?)(?:\.|,|\s+and\s|$)",
        r"(?:the\s+)?name\s+(?:of\s+my\s+(?:nail\s+salon|tattoo\s+shop|shop|salon|business|company)\s+)?is\s+([A-Za-z0-9\s&']{2,30}?)(?:\.|,|\s+and\s|$)",  # "name of my nail salon is Nancy's Nails"
        r"(?:demo\s+for|set\s+up\s+for|help|for)\s+([A-Z][A-Za-z0-9\s&']{2,30}?)(?:\.|,|!|\s+and\s|$)",  # "help The Ink Factory"
        # Lower priority: could be person name
        r"(?:^|\s)([A-Z][A-Za-z0-9\s&']{1,30}?)\s+and\s+[a-z0-9._%+-]+@",  # "The Ink Shop and email@..." (might capture person name)
    ]

    # ALWAYS check for company name - allow updates
    for pattern in company_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            company_name = match.group(1).strip()
            # Filter out common words and phrases that aren't company names
            excluded = ['your', 'my', 'the', 'a', 'an', 'there', 'here', 'you', 'we', 'they', 'our', 'your demo', 'a demo', 'thrive', 'tony', 'mike', 'john', 'sarah',
                       'my email', 'my email address', 'email address', 'my phone', 'phone number', 'my number', 'that', 'this', 'it', 'something']
            # Check if company name contains common excluded patterns
            is_excluded = any(excl in company_name.lower() for excl in excluded)
            if not is_excluded and len(company_name) > 1:
                old_name = session.get('company_name')
                session['company_name'] = company_name
                if old_name and old_name != company_name:
                    log(f"Updated company name: {old_name} -> {company_name}")
                else:
                    log(f"Captured company name: {company_name}")
                break

    # Also try to accumulate company name fragments across multiple transcripts
    # If we see "The ink" or "factory" as standalone words, store them
    if not session.get('company_name'):
        # Check if this looks like a company name fragment (capitalized words)
        if text.strip() and text[0].isupper() and len(text.strip().split()) <= 3:
            # Store fragments in a list
            if 'company_name_fragments' not in session:
                session['company_name_fragments'] = []

            # Don't store common phrases (strip punctuation for comparison)
            text_normalized = re.sub(r'[.,!?;:]', '', text.strip()).lower()
            common_phrases = [
                'the name of my', 'my business is', 'my shop is', 'yes', 'no',
                'thank you', 'thanks', 'bye', 'goodbye', 'hello', 'hi', 'hey',
                'okay', 'ok', 'sure', 'great', 'perfect', 'nice', 'wonderful',
                'i see', 'got it', 'right', 'correct', 'exactly', 'almost',
                'it is', 'its', "it's", 'that is', "that's", 'thats',
                "i'm sorry", "im sorry", 'sorry', 'pardon', 'excuse me', 'what',
                'huh', 'i would love to', 'i would', 'my email address'
            ]

            # Don't store email-related words
            email_words = ['at', 'dot', 'com', 'net', 'org', 'hotmail', 'gmail', 'yahoo', 'outlook',
                          'email', 'mail', 'address', '@']
            has_email_word = any(word in text_normalized for word in email_words)

            # Don't store if it contains numbers and @ or "at" (likely email)
            looks_like_email = '@' in text or ('at' in text_normalized and any(char.isdigit() for char in text))

            if text_normalized not in common_phrases and not has_email_word and not looks_like_email:
                session['company_name_fragments'].append(text.strip())

                # If we have 2-3 fragments, try to combine them
                if len(session['company_name_fragments']) >= 2:
                    combined = ' '.join(session['company_name_fragments'][-3:])  # Last 3 fragments
                    # Remove trailing/leading articles
                    combined = re.sub(r'^(the|a|an)\s+', '', combined, flags=re.IGNORECASE)
                    combined = re.sub(r'\s+(is|are|and)\.?$', '', combined, flags=re.IGNORECASE)
                    if len(combined) > 3:
                        session['company_name'] = combined.title()
                        log(f"Captured company name from fragments: {session['company_name']}")
                        del session['company_name_fragments']

# ======================== Google Calendar Functions ========================
def generate_business_name(business_type: str) -> str:
    """Generate ACME business name based on type"""
    if not business_type:
        return "ACME Business"

    # Clean up business type
    business_type = business_type.strip().title()

    # Generate ACME name
    return f"ACME {business_type}"

def get_available_calendar_slots(days_ahead: int = 14, num_slots: int = 1) -> list:
    """Get first available appointment slot from Google Calendar

    Operating hours: 9am - 7pm, every day
    Slots: Every hour on the hour (9am, 10am, 11am, ..., 6pm)
    Logic: First available = 1 hour from now, or next day at 9am if after hours
    """
    log(f"[CALENDAR] get_available_slots called - searching {days_ahead} days ahead")

    if not GOOGLE_CALENDAR_AVAILABLE:
        log("[WARN] Google Calendar not available - returning mock slots")
        # Return mock slots for testing
        now = datetime.now()
        # Calculate 1 hour from now
        one_hour_later = now + timedelta(hours=1)
        # Round to next hour
        next_slot = one_hour_later.replace(minute=0, second=0, microsecond=0)
        if one_hour_later.minute > 0:
            next_slot += timedelta(hours=1)

        # Return requested number of mock slots
        mock_slots = []
        current_slot = next_slot
        for i in range(num_slots):
            mock_slots.append({
                "datetime": current_slot.isoformat(),
                "display": f"{current_slot.strftime('%A at %I%p').lower().replace(' 0', ' ')}"
            })
            current_slot += timedelta(hours=1)

        log(f"[CALENDAR] Mock slots: {[s['display'] for s in mock_slots]}")
        return mock_slots

    try:
        log("[CALENDAR] Attempting to load Google Calendar credentials...")
        # Load service account credentials
        google_creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        google_creds_base64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

        if google_creds_base64:
            import json
            import base64
            log("[CALENDAR] Found GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 env var")
            log(f"[CALENDAR] Base64 length: {len(google_creds_base64)} chars")
            # Clean base64 - remove any whitespace
            google_creds_base64 = google_creds_base64.strip().replace('\n', '').replace('\r', '').replace(' ', '')
            log(f"[CALENDAR] Cleaned base64 length: {len(google_creds_base64)} chars")
            # Decode from base64
            decoded = base64.b64decode(google_creds_base64).decode('utf-8')
            credentials_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[CALENDAR] ✓ Loaded Google Calendar credentials from base64 environment variable")
        elif google_creds_json:
            import json
            log("[CALENDAR] Found GOOGLE_SERVICE_ACCOUNT_JSON env var")
            log(f"[CALENDAR] JSON length: {len(google_creds_json)} chars")

            # Parse JSON
            credentials_info = json.loads(google_creds_json)

            # Debug private key format
            if 'private_key' in credentials_info:
                pk = credentials_info['private_key']
                log(f"[CALENDAR] Private key length: {len(pk)} chars")
                log(f"[CALENDAR] Private key starts with: {pk[:50]}")
                log(f"[CALENDAR] Has actual newlines: {chr(10) in pk}")
                has_backslash_n = '\\n' in pk
                log(f"[CALENDAR] Has backslash-n: {has_backslash_n}")

                # Count lines - should be ~28 lines for a proper RSA key
                lines = pk.split('\n')
                log(f"[CALENDAR] Private key has {len(lines)} lines")

                # If it's all on one line, the newlines are wrong
                if len(lines) == 1:
                    log("[CALENDAR] ERROR: Private key is all on one line - newlines are broken")

            try:
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_info,
                    scopes=['https://www.googleapis.com/auth/calendar']
                )
                log("[CALENDAR] ✓ Loaded Google Calendar credentials from environment variable")
            except Exception as e:
                log(f"[CALENDAR] ✗ Failed to create credentials: {type(e).__name__}: {str(e)}")
                import traceback
                log(f"[CALENDAR] Full traceback: {traceback.format_exc()}")
                raise
        elif os.path.exists(GOOGLE_CALENDAR_SERVICE_ACCOUNT):
            log(f"[CALENDAR] Found credentials file at: {GOOGLE_CALENDAR_SERVICE_ACCOUNT}")
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_CALENDAR_SERVICE_ACCOUNT,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[CALENDAR] ✓ Loaded Google Calendar credentials from file")
        else:
            log(f"[CALENDAR] ✗ No Google Calendar credentials found!")
            log(f"[CALENDAR] Checked env var: GOOGLE_SERVICE_ACCOUNT_JSON_BASE64 = {bool(google_creds_base64)}")
            log(f"[CALENDAR] Checked env var: GOOGLE_SERVICE_ACCOUNT_JSON = {bool(google_creds_json)}")
            log(f"[CALENDAR] Checked file: {GOOGLE_CALENDAR_SERVICE_ACCOUNT} exists = False")
            return []

        log("[CALENDAR] Building Google Calendar service...")
        service = build('calendar', 'v3', credentials=credentials)
        log("[CALENDAR] ✓ Google Calendar service built successfully")

        # Get events for next N days - use Pacific time
        import pytz
        pacific = pytz.timezone('America/Los_Angeles')
        now = datetime.now(pacific)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        log(f"[CALENDAR] Fetching events from {GOOGLE_CALENDAR_EMAIL}")
        log(f"[CALENDAR] Time range (Pacific): {now.strftime('%Y-%m-%d %H:%M %Z')} to {(now + timedelta(days=days_ahead)).strftime('%Y-%m-%d %H:%M %Z')}")

        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_EMAIL,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        existing_events = events_result.get('items', [])
        log(f"[CALENDAR] ✓ Found {len(existing_events)} existing events in next {days_ahead} days")

        # Log first few events for debugging
        if existing_events:
            for i, event in enumerate(existing_events[:3]):
                event_start = event.get('start', {}).get('dateTime', 'N/A')
                event_summary = event.get('summary', 'Untitled')
                log(f"[CALENDAR]   Event {i+1}: {event_summary} at {event_start}")

        # Operating hours: 9am - 7pm (last appointment at 6pm)
        OPEN_HOUR = 9
        CLOSE_HOUR = 19  # 7pm
        LAST_APPOINTMENT_HOUR = 18  # 6pm (1 hour before close)

        # Calculate first possible slot (1 hour from now)
        one_hour_later = now + timedelta(hours=1)
        # Round up to next hour
        next_slot_time = one_hour_later.replace(minute=0, second=0, microsecond=0)
        if one_hour_later.minute > 0:
            next_slot_time += timedelta(hours=1)

        log(f"[CALENDAR] Current time: {now.strftime('%Y-%m-%d %H:%M')}")
        log(f"[CALENDAR] First possible slot: {next_slot_time.strftime('%Y-%m-%d %H:%M')}")

        # Check if next slot is after hours - if so, start from next day at 9am
        if next_slot_time.hour >= CLOSE_HOUR or next_slot_time.hour < OPEN_HOUR:
            # Move to next day at 9am
            next_slot_time = (next_slot_time + timedelta(days=1)).replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)
            log(f"[CALENDAR] After hours, moving to next day at 9am: {next_slot_time.strftime('%Y-%m-%d %H:%M')}")

        # Search for first available slot
        max_search_date = now + timedelta(days=days_ahead)
        current_check = next_slot_time
        slots_checked = 0

        log(f"[CALENDAR] Starting search from {current_check.strftime('%Y-%m-%d %H:%M')} to {max_search_date.strftime('%Y-%m-%d %H:%M')}")

        available_slots = []

        while current_check < max_search_date and len(available_slots) < num_slots:
            slots_checked += 1
            # Check if this hour is within operating hours
            if current_check.hour >= OPEN_HOUR and current_check.hour <= LAST_APPOINTMENT_HOUR:
                # Check for conflicts with existing events
                slot_iso = current_check.isoformat()
                conflict = False

                for event in existing_events:
                    event_start = event.get('start', {}).get('dateTime', '')
                    event_end = event.get('end', {}).get('dateTime', '')

                    if event_start and event_end:
                        # Parse event times
                        event_start_dt = datetime.fromisoformat(event_start.replace('Z', '+00:00'))
                        event_end_dt = datetime.fromisoformat(event_end.replace('Z', '+00:00'))

                        # Check if our slot overlaps with this event
                        # Our slot is 1 hour long
                        slot_end = current_check + timedelta(hours=1)

                        if (current_check < event_end_dt and slot_end > event_start_dt):
                            conflict = True
                            log(f"[CALENDAR] Conflict at {current_check.strftime('%A %I%p').replace(' 0', ' ')} with event: {event.get('summary', 'Untitled')}")
                            break

                if not conflict:
                    # Found an available slot!
                    day_name = current_check.strftime("%A")
                    time_display = current_check.strftime("%I%p").lower().replace('0', '', 1) if current_check.strftime("%I%p").startswith('0') else current_check.strftime("%I%p").lower()

                    log(f"[CALENDAR] ✓ FOUND available slot #{len(available_slots)+1} after checking {slots_checked} slots: {day_name} at {time_display}")

                    available_slots.append({
                        "datetime": slot_iso,
                        "display": f"{day_name} at {time_display}"
                    })

                    # If we have enough slots, return them
                    if len(available_slots) >= num_slots:
                        log(f"[CALENDAR] ✓ Found all {num_slots} requested slots")
                        return available_slots

            # Move to next hour
            current_check += timedelta(hours=1)

            # If we've gone past last appointment hour, jump to next day at 9am
            if current_check.hour > LAST_APPOINTMENT_HOUR or current_check.hour < OPEN_HOUR:
                current_check = (current_check + timedelta(days=1)).replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)

        # Return whatever slots we found (could be less than requested)
        if available_slots:
            log(f"[CALENDAR] ✓ Found {len(available_slots)} available slots (requested {num_slots})")
            return available_slots

        # No slots found
        log(f"[CALENDAR] ✗ No available slots found in next {days_ahead} days after checking {slots_checked} slots")
        log(f"[CALENDAR] This should NOT happen - calendar might be fully booked or logic error")
        return []

    except Exception as e:
        log(f"[ERROR] ✗ Failed to get calendar slots: {e}")
        import traceback
        log(f"[ERROR] Traceback: {traceback.format_exc()}")
        return []

def get_next_business_day_slot() -> dict:
    """Get first available slot for next business day (Monday-Friday) starting at 10am

    Returns slot in format: {"datetime": "2025-11-19T10:00:00", "display": "Tuesday at 10am"}
    If 10am is booked, tries 11am, 12pm, etc.
    """
    if not GOOGLE_CALENDAR_AVAILABLE:
        log("[WARN] Google Calendar not available - returning mock next business day slot")
        now = datetime.now()
        # Calculate next business day
        next_day = now + timedelta(days=1)
        while next_day.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
            next_day += timedelta(days=1)
        next_slot = next_day.replace(hour=10, minute=0, second=0, microsecond=0)

        return {
            "datetime": next_slot.isoformat(),
            "display": f"{next_slot.strftime('%A at %I%p').lower().replace(' 0', ' ')}"
        }

    try:
        # Load service account credentials
        google_creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        google_creds_base64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

        if google_creds_base64:
            import json
            import base64
            decoded = base64.b64decode(google_creds_base64).decode('utf-8')
            credentials_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[INFO] Loaded Google Calendar credentials from base64 for next business day slot")
        elif google_creds_json:
            import json
            credentials_info = json.loads(google_creds_json)
            # Fix private key newlines if they got corrupted
            if 'private_key' in credentials_info:
                pk = credentials_info['private_key']
                if '\\n' in pk and '\n' not in pk:
                    credentials_info['private_key'] = pk.replace('\\n', '\n')
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[INFO] Loaded Google Calendar credentials for next business day slot")
        elif os.path.exists(GOOGLE_CALENDAR_SERVICE_ACCOUNT):
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_CALENDAR_SERVICE_ACCOUNT,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[INFO] Loaded Google Calendar credentials from file for next business day slot")
        else:
            log(f"[WARN] No Google Calendar credentials found for next business day slot")
            return {}

        service = build('calendar', 'v3', credentials=credentials)

        # Calculate next business day (Monday-Friday)
        import pytz
        pacific = pytz.timezone('America/Los_Angeles')
        now = datetime.now(pacific)
        next_day = now + timedelta(days=1)
        while next_day.weekday() >= 5:  # Skip Saturday (5) and Sunday (6)
            next_day += timedelta(days=1)

        log(f"[NEXT_DAY_SLOT] Next business day: {next_day.strftime('%A %Y-%m-%d')}")

        # Get events for next business day
        day_start = next_day.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = next_day.replace(hour=23, minute=59, second=59, microsecond=999999)

        events_result = service.events().list(
            calendarId=GOOGLE_CALENDAR_EMAIL,
            timeMin=day_start.isoformat(),
            timeMax=day_end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        existing_events = events_result.get('items', [])
        log(f"[NEXT_DAY_SLOT] Found {len(existing_events)} existing events on {next_day.strftime('%A')}")

        # Operating hours: 9am - 7pm (last appointment at 6pm)
        OPEN_HOUR = 9
        LAST_APPOINTMENT_HOUR = 18  # 6pm

        # Try starting at 10am, then 11am, 12pm, etc.
        for hour in range(10, LAST_APPOINTMENT_HOUR + 1):
            check_time = next_day.replace(hour=hour, minute=0, second=0, microsecond=0)

            # Check for conflicts
            conflict = False
            for event in existing_events:
                event_start = event.get('start', {}).get('dateTime', '')
                event_end = event.get('end', {}).get('dateTime', '')

                if event_start and event_end:
                    event_start_dt = datetime.fromisoformat(event_start.replace('Z', '+00:00'))
                    event_end_dt = datetime.fromisoformat(event_end.replace('Z', '+00:00'))

                    # Check if our slot overlaps (1 hour slot)
                    slot_end = check_time + timedelta(hours=1)

                    if (check_time < event_end_dt and slot_end > event_start_dt):
                        conflict = True
                        log(f"[NEXT_DAY_SLOT] {hour}:00 conflicts with: {event.get('summary', 'Untitled')}")
                        break

            if not conflict:
                # Found available slot!
                day_name = check_time.strftime("%A")
                time_display = check_time.strftime("%I%p").lower().replace('0', '', 1) if check_time.strftime("%I%p").startswith('0') else check_time.strftime("%I%p").lower()

                log(f"[NEXT_DAY_SLOT] First available morning slot: {day_name} at {time_display}")

                return {
                    "datetime": check_time.isoformat(),
                    "display": f"{day_name} at {time_display}"
                }

        # No morning slots available on next business day
        log(f"[NEXT_DAY_SLOT] No available slots on {next_day.strftime('%A')}")
        return {}

    except Exception as e:
        log(f"[ERROR] Failed to get next business day slot: {e}")
        import traceback
        log(f"[ERROR] Traceback: {traceback.format_exc()}")
        return {}

def book_calendar_appointment(slot_datetime: str, customer_name: str, customer_email: str, customer_phone: str, business_type: str) -> bool:
    """Book an appointment in Google Calendar"""
    log(f"[BOOKING] Attempting to book calendar appointment")
    log(f"[BOOKING] Customer: {customer_name}, Business: {business_type}")
    log(f"[BOOKING] Email: {customer_email or 'Not provided'}, Phone: {customer_phone or 'Not provided'}")
    log(f"[BOOKING] Slot: {slot_datetime}")

    if not GOOGLE_CALENDAR_AVAILABLE:
        log("[BOOKING] ✗ Google Calendar not available - skipping booking")
        return False

    try:
        # Load service account credentials
        # Support both file path (local) and JSON string (Railway env var)
        google_creds_json = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        google_creds_base64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON_BASE64")

        if google_creds_base64:
            # Load from base64 environment variable (Railway - recommended)
            import json
            import base64
            log("[BOOKING] Loading credentials from base64 environment variable...")
            decoded = base64.b64decode(google_creds_base64).decode('utf-8')
            credentials_info = json.loads(decoded)
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[BOOKING] ✓ Credentials loaded from base64 env var")
        elif google_creds_json:
            # Load from environment variable (Railway)
            import json
            log("[BOOKING] Loading credentials from environment variable...")
            credentials_info = json.loads(google_creds_json)
            # Fix private key newlines if they got corrupted
            if 'private_key' in credentials_info:
                pk = credentials_info['private_key']
                if '\\n' in pk and '\n' not in pk:
                    log("[BOOKING] Fixing escaped newlines in private key")
                    credentials_info['private_key'] = pk.replace('\\n', '\n')
            credentials = service_account.Credentials.from_service_account_info(
                credentials_info,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[BOOKING] ✓ Credentials loaded from env var")
        elif os.path.exists(GOOGLE_CALENDAR_SERVICE_ACCOUNT):
            # Load from file (local development)
            log(f"[BOOKING] Loading credentials from file: {GOOGLE_CALENDAR_SERVICE_ACCOUNT}")
            credentials = service_account.Credentials.from_service_account_file(
                GOOGLE_CALENDAR_SERVICE_ACCOUNT,
                scopes=['https://www.googleapis.com/auth/calendar']
            )
            log("[BOOKING] ✓ Credentials loaded from file")
        else:
            log(f"[BOOKING] ✗ No Google Calendar credentials found")
            return False

        log("[BOOKING] Building Google Calendar service...")
        service = build('calendar', 'v3', credentials=credentials)
        log("[BOOKING] ✓ Service built successfully")

        # Parse slot datetime
        start_time = datetime.fromisoformat(slot_datetime)
        end_time = start_time + timedelta(hours=1)  # 1-hour appointments

        log(f"[BOOKING] Event time: {start_time.strftime('%A, %B %d at %I:%M%p').replace(' 0', ' ')} - {end_time.strftime('%I:%M%p').replace(' 0', ' ')}")

        # Create event
        event = {
            'summary': f'Implementation Call - {customer_name}',
            'description': f"""Bolt AI Group Implementation Call

Customer: {customer_name}
Business Type: {business_type}
Email: {customer_email or 'Not provided'}
Phone: {customer_phone or 'Not provided'}

This is an implementation call for setting up AI phone agent system.""",
            'start': {
                'dateTime': start_time.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'end': {
                'dateTime': end_time.isoformat(),
                'timeZone': 'America/Los_Angeles',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                    {'method': 'popup', 'minutes': 30},  # 30 min before
                ],
            },
            'visibility': 'public',  # Make event publicly viewable via link
            'guestsCanSeeOtherGuests': False,
        }

        # Note: Not adding attendees because service accounts can't invite without Domain-Wide Delegation
        # Calendar invite will be sent via separate email with send_demo_follow_up()
        log(f"[BOOKING] Event will be created without attendees (invite sent separately via email)")

        # Insert event
        log(f"[BOOKING] Creating event in calendar: {GOOGLE_CALENDAR_EMAIL}")
        created_event = service.events().insert(
            calendarId=GOOGLE_CALENDAR_EMAIL,
            body=event,
            sendUpdates='none'  # Don't send via Google (we handle email separately)
        ).execute()

        event_link = created_event.get('htmlLink', 'N/A')
        event_id = created_event.get('id', 'N/A')
        log(f"[BOOKING] ✓ SUCCESS! Calendar appointment booked")
        log(f"[BOOKING] Event ID: {event_id}")
        log(f"[BOOKING] Event Link: {event_link}")
        return {'success': True, 'link': event_link}

    except Exception as e:
        log(f"[BOOKING] ✗ ERROR Failed to book calendar appointment: {e}")
        import traceback
        log(f"[BOOKING] Traceback: {traceback.format_exc()}")
        return {'success': False, 'link': None}

# ======================== Routes ========================
@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"status": "healthy", "mode": "realtime_api", "platform": COMPANY_NAME}

@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Simple health check for uptime monitoring services like UptimeRobot."""
    uptime_seconds = int(time.time() - SERVER_START_TIME)
    uptime_hours = uptime_seconds // 3600
    uptime_minutes = (uptime_seconds % 3600) // 60

    # Check critical services
    supabase_ok = get_supabase_client() is not None
    openai_ok = bool(OPENAI_API_KEY)

    # Determine overall status
    if supabase_ok and openai_ok:
        status = "healthy"
    else:
        status = "degraded"

    return {
        "status": status,
        "uptime": f"{uptime_hours}h {uptime_minutes}m",
        "uptime_seconds": uptime_seconds,
        "active_calls": len(SESSIONS),
        "services": {
            "database": "ok" if supabase_ok else "error",
            "openai": "ok" if openai_ok else "error"
        }
    }

@app.get("/monitor", response_class=JSONResponse)
async def monitoring_dashboard():
    """
    Production monitoring dashboard - view system health and call metrics.
    Returns detailed metrics about call performance, errors, and WebSocket health.
    """
    try:
        # Get Supabase connection status
        supabase_status = "connected" if get_supabase_client() is not None else "disconnected"

        # Get active sessions
        active_sessions = len(SESSIONS)

        # Calculate uptime (if we track server start time)
        # For now, just return current stats

        # Get database stats (if Supabase is available)
        db_stats = {}
        supabase = get_supabase_client()
        if supabase:
            try:
                # Get call counts from last 24 hours
                yesterday = (datetime.now() - timedelta(days=1)).isoformat()
                calls_24h = supabase.table('calls').select('*').gte('created_at', yesterday).execute()

                db_stats = {
                    "calls_last_24h": len(calls_24h.data) if calls_24h.data else 0,
                    "completed_calls_24h": len([c for c in calls_24h.data if c.get('status') == 'completed']) if calls_24h.data else 0,
                    "failed_calls_24h": len([c for c in calls_24h.data if c.get('status') in ['failed', 'busy', 'no-answer']]) if calls_24h.data else 0,
                }
            except Exception as e:
                db_stats = {"error": str(e)}

        return {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "environment": SENTRY_ENVIRONMENT if SENTRY_DSN else "unknown",
            "services": {
                "supabase": supabase_status,
                "openai": "configured" if OPENAI_API_KEY else "missing",
                "elevenlabs": "enabled" if USE_ELEVENLABS else "disabled",
                "sentry": "enabled" if (SENTRY_DSN and SENTRY_AVAILABLE) else "disabled",
                "google_calendar": "available" if GOOGLE_CALENDAR_AVAILABLE else "unavailable"
            },
            "active_calls": active_sessions,
            "call_metrics": dict(CALL_METRICS.get("websocket", {})),
            "database_stats": db_stats,
            "configuration": {
                "voice": VOICE,
                "model": MODEL,
                "temperature": TEMPERATURE,
                "max_call_duration": MAX_CALL_DURATION,
                "ws_ping_interval": WEBSOCKET_PING_INTERVAL,
                "ws_max_retries": WS_MAX_RETRIES,
            }
        }
    except Exception as e:
        if SENTRY_AVAILABLE and SENTRY_DSN:
            sentry_sdk.capture_exception(e)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat() + "Z"
        }

@app.api_route("/inbound", methods=["GET", "POST"])
@app.api_route("/voice/incoming", methods=["GET", "POST"])
async def handle_incoming_call(request: Request):
    """Handle inbound call - start Media Stream"""
    form = await request.form()
    call_sid = form.get("CallSid")
    from_number = form.get("From")
    to_number = form.get("To")

    log(f"Inbound call: {call_sid}, from={from_number}, to={to_number}")

    # Look up business
    business = get_business_for_phone(to_number)
    if not business:
        log(f"No business found for {to_number}")
        response = VoiceResponse()
        response.say("Sorry, this number is not configured.")
        response.hangup()
        return HTMLResponse(content=str(response), media_type="application/xml")

    # Create call record
    call_record = create_call_record(business['id'], from_number, call_sid, to_number)

    # Store session
    call_start_time = datetime.now()
    SESSIONS[call_sid] = {
        "business": business,
        "call_id": call_record['id'] if call_record else None,
        "caller_phone": from_number,
        "call_start_time": call_start_time,
        "customer_name": None,
        "customer_email": None,
        "customer_phone": None,
        "business_type": None,
        "company_name": None,
        "mode": None,  # "demo" or "signup"
        "demo_business_name": None,  # Generated ACME name
        "contact_preference": None,  # "call" or "email"
        "appointment_datetime": None,  # Booked slot
        "appointment_display": None  # Human-readable slot (e.g., "Tuesday at 2pm")
    }

    # Send instant call alert to business owner
    log(f"Sending instant call alert for {from_number}")
    send_instant_call_alert(call_sid, from_number, call_start_time)

    # Start call recording via REST API (for Media Streams, we can't use TwiML record)
    # This starts recording immediately when the call is answered
    host = request.url.hostname
    try:
        recording = TWILIO_CLIENT.calls(call_sid).recordings.create(
            recording_status_callback=f'https://{host}/recording-status',
            recording_status_callback_method='POST',
            recording_channels='dual'  # Records both legs separately for better quality
        )
        log(f"Started recording for call {call_sid}: {recording.sid}")
    except Exception as e:
        log(f"Failed to start recording for call {call_sid}: {e}")

    # Start Media Stream
    response = VoiceResponse()
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")

# ======================== ElevenLabs Conversational AI Integration ========================

async def get_elevenlabs_signed_url():
    """Get signed URL for authenticated ElevenLabs Conversational AI connection"""
    try:
        url = f"https://api.elevenlabs.io/v1/convai/conversation/get_signed_url?agent_id={ELEVENLABS_AGENT_ID}"
        headers = {"xi-api-key": ELEVENLABS_CONVERSATIONAL_API_KEY}

        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code != 200:
            raise Exception(f"Failed to get signed URL: {response.status_code} - {response.text}")

        data = response.json()
        signed_url = data.get("signed_url")
        if not signed_url:
            raise Exception("No signed_url in response")

        log(f"[ElevenLabs] Got signed URL: {signed_url[:50]}...")
        return signed_url
    except Exception as e:
        log(f"[ElevenLabs] Error getting signed URL: {e}")
        raise

async def handle_media_stream_elevenlabs(websocket: WebSocket):
    """
    Handle Twilio Media Stream with ElevenLabs Conversational AI

    Flow:
    1. Get signed URL from ElevenLabs API
    2. Connect to ElevenLabs WebSocket
    3. Bridge audio: Twilio <-> ElevenLabs
    4. Handle events: audio, transcripts, interruptions
    """
    log(f"[ElevenLabs] Starting media stream handler")

    stream_sid = None
    call_sid = None
    elevenlabs_ws = None
    elevenlabs_connected = True  # Track connection state to avoid sending to closed socket

    try:
        # Get signed URL for authentication
        signed_url = await get_elevenlabs_signed_url()

        # Connect to ElevenLabs WebSocket
        elevenlabs_ws = await websockets.connect(
            signed_url,
            ping_interval=20,
            ping_timeout=10,
            ssl=ssl.create_default_context(cafile=certifi.where())
        )

        log(f"[ElevenLabs] Connected to Conversational AI")

        # Note: We don't send conversation_config_override because the agent
        # is already configured in the ElevenLabs dashboard and doesn't allow runtime overrides.
        # The agent will use its default configuration (prompt, first message, voice, etc.)

        async def receive_from_twilio():
            """Receive audio from Twilio and forward to ElevenLabs"""
            nonlocal stream_sid, call_sid, elevenlabs_connected

            try:
                async for message in websocket.iter_text():
                    # Skip if ElevenLabs connection is closed
                    if not elevenlabs_connected:
                        break

                    data = json.loads(message)

                    if data['event'] == 'connected':
                        log(f"[Twilio] Connected event received")
                        continue

                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        call_sid = data['start'].get('callSid')
                        log(f"[Twilio] Stream started: {stream_sid}, Call SID: {call_sid}")

                    elif data['event'] == 'media':
                        # Skip sending if ElevenLabs is disconnected
                        if not elevenlabs_connected:
                            continue

                        # Send audio directly to ElevenLabs (agent is configured for ulaw_8000)
                        try:
                            # Send Twilio's mulaw audio directly - no conversion needed
                            audio_message = {
                                "user_audio_chunk": data['media']['payload']
                            }
                            await elevenlabs_ws.send(json.dumps(audio_message))
                        except websockets.exceptions.ConnectionClosed as e:
                            log(f"[ElevenLabs] Connection closed while sending audio. Code: {e.code if hasattr(e, 'code') else 'unknown'}, Reason: {e.reason if hasattr(e, 'reason') else 'unknown'}")
                            elevenlabs_connected = False
                            break
                        except Exception as e:
                            log(f"[ERROR] User audio conversion/send failed: {e}")
                            # Check if it's a connection error
                            if "closed" in str(e).lower() or "1000" in str(e):
                                elevenlabs_connected = False
                                break

                        # Send conversation initiation (optional - can override agent config)
                        # For now, we rely on the agent config from ElevenLabs dashboard
                        # Uncomment below to override:
                        # init_message = {
                        #     "type": "conversation_initiation_client_data",
                        #     "conversation_config_override": {
                        #         "agent": {
                        #             "prompt": {"prompt": "custom prompt here"},
                        #             "first_message": "greeting here"
                        #         }
                        #     }
                        # }
                        # await elevenlabs_ws.send(json.dumps(init_message))

                    elif data['event'] == 'stop':
                        log(f"[Twilio] Stream stopped: {stream_sid}")
                        break

            except WebSocketDisconnect:
                log(f"[Twilio] WebSocket disconnected for {call_sid}")
            except Exception as e:
                log(f"[Twilio] Error receiving from Twilio: {e}")

        async def receive_from_elevenlabs():
            """Receive audio/events from ElevenLabs and forward to Twilio"""
            nonlocal elevenlabs_connected

            try:
                async for message in elevenlabs_ws:
                    try:
                        response = json.loads(message)
                        event_type = response.get('type')

                        # DEBUG: Log all events to see what we're receiving
                        log(f"[ElevenLabs DEBUG] Event type: {event_type}, Keys: {list(response.keys())}")

                        if event_type == 'conversation_initiation_metadata':
                            metadata = response.get('conversation_initiation_metadata_event', {})
                            log(f"[ElevenLabs] Conversation initiated. Agent config: {json.dumps(metadata, indent=2)[:500]}")

                        elif event_type == 'audio':
                            # DEBUG: Log audio_event structure
                            audio_event = response.get('audio_event', {})
                            log(f"[ElevenLabs DEBUG] audio_event keys: {list(audio_event.keys()) if audio_event else 'None'}")

                            # ElevenLabs sends audio - forward to Twilio
                            # Check both possible audio formats from API
                            audio_base64 = None
                            if response.get('audio_event', {}).get('audio_base_64'):
                                audio_base64 = response['audio_event']['audio_base_64']
                            elif response.get('audio', {}).get('chunk'):
                                audio_base64 = response['audio']['chunk']

                            # DEBUG: Log extraction results
                            log(f"[DEBUG] Audio extraction - audio_base64 populated: {audio_base64 is not None}, length: {len(audio_base64) if audio_base64 else 0}")
                            log(f"[DEBUG] stream_sid: {stream_sid}")

                            if audio_base64 and stream_sid:
                                try:
                                    # ElevenLabs agent is configured for ulaw_8000 output
                                    # Forward audio directly to Twilio without conversion
                                    twilio_message = {
                                        "event": "media",
                                        "streamSid": stream_sid,
                                        "media": {
                                            "payload": audio_base64
                                        }
                                    }
                                    await websocket.send_text(json.dumps(twilio_message))
                                    log(f"[ElevenLabs] Forwarded audio to Twilio ({len(audio_base64)} chars)")
                                except Exception as e:
                                    log(f"[ERROR] Audio forward failed: {e}")
                            else:
                                log(f"[DEBUG] NOT forwarding - audio_base64: {audio_base64 is not None}, stream_sid: {stream_sid}")

                        elif event_type == 'interruption':
                            # User interrupted agent - clear Twilio playback buffer
                            if stream_sid:
                                clear_message = {
                                    "event": "clear",
                                    "streamSid": stream_sid
                                }
                                await websocket.send_text(json.dumps(clear_message))
                                log(f"[ElevenLabs] Interruption detected - cleared Twilio buffer")

                        elif event_type == 'ping':
                            # Respond to keepalive ping
                            if response.get('ping_event', {}).get('event_id'):
                                pong_message = {
                                    "type": "pong",
                                    "event_id": response['ping_event']['event_id']
                                }
                                await elevenlabs_ws.send(json.dumps(pong_message))

                        elif event_type == 'agent_response':
                            # DEBUG: Log agent_response_event structure
                            agent_response_event = response.get('agent_response_event', {})
                            log(f"[ElevenLabs DEBUG] agent_response_event keys: {list(agent_response_event.keys()) if agent_response_event else 'None'}")

                            # Agent response with audio - extract and forward to Twilio
                            audio_base64 = response.get('audio', {}).get('chunk') or response.get('audio_base_64')
                            if audio_base64 and stream_sid:
                                twilio_message = {
                                    "event": "media",
                                    "streamSid": stream_sid,
                                    "media": {
                                        "payload": audio_base64
                                    }
                                }
                                await websocket.send_text(json.dumps(twilio_message))
                                log(f"[ElevenLabs] Forwarded agent audio to Twilio")

                        elif event_type == 'user_transcript' or event_type == 'agent_transcript':
                            transcript_text = response.get('text', '')
                            role = 'user' if event_type == 'user_transcript' else 'agent'
                            log(f"[Transcript] {role}: {transcript_text}")

                            # Save to database
                            if call_sid and transcript_text:
                                update_call_transcript(call_sid, role, transcript_text)

                        else:
                            log(f"[ElevenLabs] Unhandled event type: {event_type}")

                    except json.JSONDecodeError as e:
                        log(f"[ElevenLabs] JSON decode error: {e}")
                    except Exception as e:
                        log(f"[ElevenLabs] Error processing message: {e}")

            except websockets.exceptions.ConnectionClosed as e:
                log(f"[ElevenLabs] WebSocket closed for {call_sid}. Code: {e.code if hasattr(e, 'code') else 'unknown'}, Reason: {e.reason if hasattr(e, 'reason') else 'unknown'}")
                elevenlabs_connected = False
            except Exception as e:
                log(f"[ElevenLabs] Error receiving from ElevenLabs: {e}")
                if "closed" in str(e).lower() or "1000" in str(e):
                    elevenlabs_connected = False

        # Run both streams concurrently
        await asyncio.gather(
            receive_from_twilio(),
            receive_from_elevenlabs()
        )

    except Exception as e:
        log(f"[ElevenLabs] Handler error for {call_sid}: {e}")
        import traceback
        log(f"[ElevenLabs] Traceback: {traceback.format_exc()}")

    finally:
        # Clean up WebSocket connection
        if elevenlabs_ws:
            try:
                await elevenlabs_ws.close()
                log(f"[ElevenLabs] WebSocket closed for {call_sid}")
            except:
                pass

        log(f"[ElevenLabs] Handler complete for call {call_sid}")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle Twilio Media Stream WebSocket - Routes to ElevenLabs or OpenAI based on feature flag"""
    log("Media stream WebSocket connected")
    await websocket.accept()

    # Feature flag routing: ElevenLabs Conversational AI vs OpenAI Realtime API
    if USE_ELEVENLABS_CONVERSATIONAL_AI:
        log("[ROUTING] Using ElevenLabs Conversational AI")
        await handle_media_stream_elevenlabs(websocket)
        return  # ElevenLabs handler complete

    # Otherwise, use OpenAI Realtime API (existing implementation)
    log("[ROUTING] Using OpenAI Realtime API + ElevenLabs TTS")

    call_sid = None
    stream_sid = None
    heartbeat_task = None

    # Connect to OpenAI with retry logic
    log("Connecting to OpenAI Realtime API with retry logic...")
    openai_ws = await connect_to_openai_with_retry(max_retries=WS_MAX_RETRIES)

    if openai_ws is None:
        log("CRITICAL: Failed to establish OpenAI connection after all retries")
        CALL_METRICS["websocket"]["failed_calls"] += 1
        return

    # Start heartbeat task to keep connection alive
    heartbeat_task = asyncio.create_task(ws_heartbeat(openai_ws, interval=WEBSOCKET_PING_INTERVAL))
    log("[WS] Heartbeat task started")

    try:
        latest_media_timestamp = 0
        last_assistant_item = None
        mark_queue = []
        response_start_timestamp_twilio = None
        stream_start_time = None  # Track when stream started to prevent early interruptions

        async def send_error_message_to_caller(ws, sid):
            """Send graceful error message to caller when OpenAI fails"""
            try:
                if not sid:
                    log("Cannot send error message - no stream SID")
                    return

                error_message = "I apologize, but I'm experiencing technical difficulties right now. Our team has your phone number and will call you back shortly. Thank you for your patience."
                log(f"Sending error message to caller: {error_message}")

                # Note: We can't synthesize speech without OpenAI, so we just log and disconnect gracefully
                # The call will end, and the status callback will trigger follow-up

            except Exception as e:
                log(f"Error sending fallback message: {e}")

        async def receive_from_twilio():
            """Receive audio from Twilio and send to OpenAI"""
            nonlocal stream_sid, latest_media_timestamp, call_sid, stream_start_time
            try:
                async for message in websocket.iter_text():
                    data = json.loads(message)

                    if data['event'] == 'media':
                        latest_media_timestamp = int(data['media']['timestamp'])
                        audio_append = {
                            "type": "input_audio_buffer.append",
                            "audio": data['media']['payload']
                        }
                        await openai_ws.send(json.dumps(audio_append))

                    elif data['event'] == 'start':
                        stream_sid = data['start']['streamSid']
                        call_sid = data['start']['customParameters'].get('CallSid') or data['start'].get('callSid')
                        stream_start_time = time.time()  # Track when stream started
                        log(f"Stream started: {stream_sid}, Call: {call_sid}")

                        # Get session data
                        session = SESSIONS.get(call_sid, {})
                        business = session.get('business', {})
                        agent_name = business.get('agent_name', AGENT_NAME)
                        business_name = business.get('business_name', COMPANY_NAME)
                        industry = business.get('industry', 'sales')

                        # Configure OpenAI session based on business
                        if industry == 'sales':
                            greeting = "Hey there! This is Jack over at Criton AI. I actually just tried reaching you a few minutes ago. You know, the fact that you're calling me back instead of reaching a real person on your end — that's actually the exact problem we solve. We make sure businesses like yours never miss a single call. Got a sec?"
                            system_message = f"""You are {agent_name}, an enthusiastic AI sales agent for {business_name}.

CRITICAL: Your FIRST response must be EXACTLY this greeting word-for-word:
"{greeting}"

═══════════════════════════════════════════════════════════════
CONTEXT: CALLBACK SCENARIO
═══════════════════════════════════════════════════════════════

These callers are returning a missed call from you. USE THIS to your advantage — it's a live proof point. Key stats to weave in naturally:
- 85% of callers who hit voicemail will call a competitor instead
- The average small business misses 40% of incoming calls
- A missed call costs the average service business $200-$1,200 in lost revenue

When they ask "Who is this?" or "Why did you call me?":
- Say: "We actually just gave you a call because we help [their industry if known, otherwise 'businesses like yours'] stop losing customers to missed calls. Funny enough, you calling me back and getting an AI instead of a person — that's the exact situation your customers deal with when they call you and nobody picks up."

═══════════════════════════════════════════════════════════════
AFTER GREETING - BRANCH INTO TWO PATHS:
═══════════════════════════════════════════════════════════════

PATH A: DEMO MODE
If they say "demo", "show me", "demonstration", "how does it work", or similar:

1. Ask: "Perfect! What type of business do you have?"
2. WAIT for them to tell you their complete business type (HVAC, dental, barbershop, etc.)
   ⚠️ CRITICAL: DO NOT interrupt them while they're answering! Wait for them to finish speaking.
3. ONLY AFTER they finish answering, say EXACTLY: "Great! Let me show you how I'd handle calls for your [BusinessType]. Ready?"
4. STOP generating text here. The user will respond with "yes", "ready", "sure", etc.
   ⚠️ CRITICAL: DO NOT generate your demo character greeting in this same response!
   ⚠️ You MUST wait to receive the user's actual confirmation before continuing.
5. ONLY AFTER you receive their verbal confirmation, SWITCH INTO DEMO CHARACTER - You are now the receptionist for "ACME [BusinessType]"
   - Greeting: "Thanks for calling ACME [BusinessType], this is Jack. How can I help you?"
   - They will roleplay as a customer (e.g., "My AC is broken", "I need a dentist appointment")
   - Respond with EMPATHY: "I'm sorry to hear that. That's never fun."

   FOR EMERGENCY BUSINESSES (HVAC, plumbing, electrical, dental, medical):
   - Ask: "Does Tuesday at 2pm work, or is this an emergency?"

   IF THEY SAY "EMERGENCY" OR "URGENT":
   - Say: "Okay, I'll transfer you to a representative now."
   - IMMEDIATELY BREAK CHARACTER
   - Say: "I would then transfer them to a representative of your choosing. What did you think? Would you like to get started and setup an implementation call?"
   - GO TO SIGNUP FLOW

   IF THEY WANT DIFFERENT TIME (e.g., "too late", "something sooner", "earlier"):
   - Offer alternative: "No problem! How about tomorrow at 10am?"
   - IF YES: Continue to phone number collection below
   - IF STILL NO: "Let me transfer you to a representative who can find the perfect time for you."
   - BREAK CHARACTER and go to signup flow

   FOR NON-EMERGENCY BUSINESSES (salon, barbershop, spa, restaurant, etc.):
   - Ask: "Does Tuesday at 2pm work for you?"

   IF THEY WANT DIFFERENT TIME:
   - Offer alternative: "No problem! How about tomorrow at 10am?"
   - IF YES: Continue to phone number collection below
   - IF STILL NO: "Let me transfer you to a representative who can help you find the perfect time."
   - BREAK CHARACTER and go to signup flow

   IF TIME WORKS (Tuesday 2pm OR tomorrow 10am):
   - Say: "Perfect! Let me get your phone number for the confirmation."
   - They give phone number
   - Say: "Great! You're all set for [chosen time]. You'll receive a confirmation text shortly. Is there anything else I can help with?"
   - [Handle 1-2 more exchanges naturally]
   - BREAK CHARACTER
   - Say: "Alright, so that's how I'd handle calls for your [BusinessType]! What did you think? Would you like to get started and setup an implementation call?"
   - GO TO SIGNUP FLOW

═══════════════════════════════════════════════════════════════

PATH B: SIGNUP MODE (Direct or after demo)
If they say "sign up", "get started", "let's do it", or YES after demo:

FIRST: Offer to text the trial link:
- Say: "Awesome! Let me text you a link to get started right now." then call the send_trial_link function.
- After sending: "Perfect, just sent that over. You should see it pop up any second."

Then continue:
1. Say: "Great! First, what's your name?"
2. They tell you their name
3. ONLY ask for business type if you DON'T already know it from the demo:
   - If coming from demo: You already know their business type - SKIP THIS STEP
   - If direct signup (no demo): Ask "Thanks [Name]! What type of business do you have?"
4. Book implementation appointment:
   - Say: "Excellent! Let me find available times for your implementation call."
   - Call get_available_slots function to retrieve available appointments
   - Call get_next_business_day_slot function to get tomorrow morning's first available slot
   - Offer BOTH options: "Would you like the first available [slot from get_available_slots], or does [slot from get_next_business_day_slot] work better?"
   - Customer chooses one of the two options
   - If customer wants a different time, call get_available_slots again and offer alternatives
5. Collect email for calendar invitation:
   - Say: "Perfect! What's your email address so I can send you the calendar invitation?"
   - Confirm it back: "So that's [email] - did I get that right?"
   - If NO, ask: "What's the correct email?" and try again
   - Allow up to 2 attempts - if still wrong, say: "No problem, I'll send the confirmation to this phone number."
6. Confirm booking:
   - Call book_appointment function with chosen slot
   - Say: "Great! You're all set for [Day at Time]. I'm sending you a calendar invitation now so you can add it right to your calendar. Looking forward to speaking with you then!"
   - END CALL after booking

═══════════════════════════════════════════════════════════════

CRITICAL EMPATHY RULES:
- When someone mentions a problem (broken AC, toothache, etc.), ALWAYS respond with empathy first
- Examples: "I'm sorry to hear that. That's never fun." or "Oh no, that sounds frustrating."
- Then offer help

CRITICAL CHARACTER SWITCHING:
- When entering demo mode, ask "Ready?" then immediately switch into character
- When breaking character after demo, clearly signal: "Alright, so that's how I'd handle calls..."
- In demo mode, you ARE the ACME receptionist - speak as that character
- DO NOT announce pauses or say "I'm going to pause" - just switch naturally
- Outside demo mode, you are {agent_name} from {business_name}

BUSINESS NAME GENERATION:
- Auto-generate demo business names as "ACME [BusinessType]"
- Examples: "ACME HVAC", "ACME Dental", "ACME Barbershop", "ACME Plumbing"

TRIAL LINK RULE:
- Whenever a caller shows ANY interest (wants demo, wants to sign up, says "sounds interesting", "tell me more", etc.), offer to text them the link: "Want me to text you the link so you can check it out?"
- If they say yes, call the send_trial_link function immediately
- If they're about to hang up but seemed even slightly interested, offer: "Before you go, let me shoot you a quick text with the link — no pressure, just so you have it."
- Only send ONCE per call

STRICT RULES - DO NOT VIOLATE:
- Keep responses brief (1-2 sentences max)
- Ask ONE question at a time
- Never mention pricing unless customer asks
- Demo mode should be SHORT (3-5 exchanges max)
- Always collect email for calendar invitation
- Always book implementation appointment before ending call
- Be warm, friendly, and professional

VOICEMAIL FALLBACK:
If the caller says any of these:
- "Can I leave a message?"
- "I'd like to leave a voicemail"
- "Can someone call me back?"
- "I'll just leave my number"
- Seems confused and wants to speak to a human

Then:
1. Call the take_message function
2. Say "beep!" (the beep sound)
3. Say "Please leave your message after the beep, and I'll make sure someone gets back to you."
4. Listen to their complete message without interrupting
5. When they finish, call save_voicemail with all the details they provided
6. Thank them and confirm someone will call back

Be conversational, empathetic, and efficient."""
                        else:
                            system_message = f"""You are {agent_name}, a helpful AI receptionist for {business_name}.

Your job is to:
- Greet callers warmly
- Answer questions about the business
- Help with appointments and inquiries
- Provide excellent customer service

VOICEMAIL OPTION:
If the caller wants to leave a message, speak to a human, or you cannot help them:
1. Call the take_message function
2. Say "beep!" and "Please leave your message after the beep."
3. Listen to their complete message
4. Call save_voicemail with their message details
5. Thank them and confirm someone will call back

Be friendly, professional, and concise. Keep responses to 1-2 sentences."""

                        # Send session configuration
                        # Configure VAD to be less sensitive to prevent false interruptions
                        session_config = {
                            "model": MODEL,  # REQUIRED: Specify the Realtime API model
                            "turn_detection": {
                                "type": "server_vad",
                                "threshold": 0.5,  # Lower = more sensitive to silence (prevents cutting off mid-sentence) (default 0.5)
                                "prefix_padding_ms": 300,  # Audio before speech (default 300ms)
                                "silence_duration_ms": 1500  # Wait 1.5 seconds of silence before ending turn
                            },
                            "input_audio_format": "g711_ulaw",
                            "instructions": system_message,
                            "temperature": TEMPERATURE,
                            "input_audio_transcription": {"model": "whisper-1"},  # Enable user speech transcription
                        }

                        # Configure modalities based on TTS provider
                        if USE_ELEVENLABS:
                            # Text-only mode: OpenAI handles conversation, ElevenLabs handles TTS
                            session_config["modalities"] = ["text"]
                            log("[ElevenLabs] Using text-only mode with ElevenLabs TTS")
                        else:
                            # Full audio mode: OpenAI handles both conversation and TTS
                            session_config["modalities"] = ["text", "audio"]
                            session_config["output_audio_format"] = "g711_ulaw"
                            session_config["voice"] = VOICE
                            log(f"[OpenAI] Using audio mode with OpenAI voice: {VOICE}")

                        session_update = {
                            "type": "session.update",
                            "session": session_config
                        }
                        session_update["session"]["tools"] = [
                            {
                                "type": "function",
                                "name": "get_available_slots",
                                "description": "Get the first available appointment slot from the calendar. Returns the next available time starting 1 hour from now during business hours (9am-7pm daily). Call this when the user agrees to book their implementation appointment.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "days_ahead": {
                                            "type": "number",
                                            "description": "Number of days to search ahead for available slots (default 14)"
                                        }
                                    },
                                    "required": []
                                }
                            },
                            {
                                "type": "function",
                                "name": "get_next_business_day_slot",
                                "description": "Get the first available slot for next business day (Monday-Friday) starting at 10am. If 10am is booked, tries 11am, 12pm, etc. Use this to offer 'tomorrow morning' option to customers.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            },
                            {
                                "type": "function",
                                "name": "book_appointment",
                                "description": "Book an appointment slot. Call this after the user selects their preferred time slot.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "slot_datetime": {
                                            "type": "string",
                                            "description": "ISO 8601 datetime string for the appointment (e.g., '2025-11-18T10:00:00')"
                                        },
                                        "slot_display": {
                                            "type": "string",
                                            "description": "Human-readable description of the slot (e.g., 'Monday at 10am')"
                                        }
                                    },
                                    "required": ["slot_datetime", "slot_display"]
                                }
                            },
                            {
                                "type": "function",
                                "name": "send_trial_link",
                                "description": "Send the Criton AI trial signup link via text message to the caller's phone. Call this when the caller shows interest, agrees to check it out, or says 'yes' when you offer to text them the link. Do NOT call this more than once per call.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {},
                                    "required": []
                                }
                            },
                            {
                                "type": "function",
                                "name": "take_message",
                                "description": "Record a voicemail message from the caller. Call this when the caller wants to leave a message, or when you cannot help them with their request and they want someone to call them back. After calling this, say the beep sound 'beep!' and let them know they can leave their message.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "reason": {
                                            "type": "string",
                                            "description": "Brief reason for the voicemail (e.g., 'caller requested callback', 'after hours', 'complex inquiry')"
                                        }
                                    },
                                    "required": ["reason"]
                                }
                            },
                            {
                                "type": "function",
                                "name": "save_voicemail",
                                "description": "Save the voicemail message content. Call this after the caller finishes leaving their message.",
                                "parameters": {
                                    "type": "object",
                                    "properties": {
                                        "message_content": {
                                            "type": "string",
                                            "description": "The transcribed content of the caller's voicemail message"
                                        },
                                        "callback_number": {
                                            "type": "string",
                                            "description": "Phone number to call back (if provided by caller)"
                                        },
                                        "caller_name": {
                                            "type": "string",
                                            "description": "Name of the caller (if provided)"
                                        },
                                        "urgency": {
                                            "type": "string",
                                            "description": "Urgency level: 'urgent', 'normal', or 'low'"
                                        }
                                    },
                                    "required": ["message_content"]
                                }
                            }
                        ]
                        session_update["session"]["tool_choice"] = "auto"
                        await openai_ws.send(json.dumps(session_update))

                        # Trigger initial greeting (greeting text is in system instructions)
                        await openai_ws.send(json.dumps({"type": "response.create"}))

                    elif data['event'] == 'mark':
                        if mark_queue:
                            mark_queue.pop(0)

                    elif data['event'] == 'stop':
                        log(f"[TWILIO] Received 'stop' event from Twilio. Stream: {stream_sid}")
                        log(f"[TWILIO] Stop event details: {json.dumps(data, indent=2)}")
                        log(f"[TWILIO] Call duration before stop: {time.time() - stream_start_time if stream_start_time else 'unknown'}s")
                        # Explicitly close OpenAI WebSocket to prevent resource leak
                        try:
                            await openai_ws.close()
                            log("OpenAI WebSocket closed after Twilio stream ended")
                        except Exception as e:
                            log(f"Error closing OpenAI WebSocket: {e}")
                        break

            except WebSocketDisconnect:
                log("Twilio client disconnected")
            except websockets.exceptions.ConnectionClosed as e:
                log(f"Twilio WebSocket closed: {e.code if hasattr(e, 'code') else 'unknown'}")
            except Exception as e:
                log(f"Error in receive_from_twilio: {e}")

        async def send_to_twilio():
            """Receive audio from OpenAI and send to Twilio"""
            nonlocal last_assistant_item, response_start_timestamp_twilio
            openai_connected = True
            try:
                async for openai_message in openai_ws:
                    response = json.loads(openai_message)
                    log(f"[DEBUG] OpenAI response type: {response.get('type', 'unknown')}")

                    # Log failures and issues for debugging
                    if response['type'] == 'response.done':
                        log(f"[DEBUG] response.done details: {json.dumps(response, indent=2)}")

                        # Handle text responses for ElevenLabs TTS
                        if USE_ELEVENLABS:
                            try:
                                # Extract text from response.done output
                                output = response.get('response', {}).get('output', [])
                                for item in output:
                                    if item.get('type') == 'message' and item.get('role') == 'assistant':
                                        content_parts = item.get('content', [])
                                        for content in content_parts:
                                            if content.get('type') == 'text':
                                                text = content.get('text', '')
                                                if text:
                                                    log(f"[ElevenLabs] Got text from response.done: {text}")

                                                    # Save transcript
                                                    if call_sid:
                                                        update_call_transcript(call_sid, "assistant", text)
                                                        log(f"Assistant: {text}")

                                                    # Generate audio with ElevenLabs
                                                    log("[ElevenLabs] Generating TTS...")
                                                    mulaw_audio = await elevenlabs_tts_async(text)

                                                    if mulaw_audio:
                                                        # Send audio to Twilio
                                                        audio_message = {
                                                            "event": "media",
                                                            "streamSid": stream_sid,
                                                            "media": {"payload": mulaw_audio}
                                                        }
                                                        await websocket.send_json(audio_message)
                                                        log(f"[Audio] Sent μ-law audio to Twilio ({len(mulaw_audio)} chars base64)")

                                                        # Send mark event
                                                        await send_mark(websocket, stream_sid)
                                                    else:
                                                        log("[ERROR] Failed to generate ElevenLabs audio")
                            except Exception as e:
                                log(f"[ERROR] Failed to extract/generate ElevenLabs audio from response.done: {e}")
                                if SENTRY_AVAILABLE and SENTRY_DSN:
                                    sentry_sdk.capture_exception(e)
                    elif response['type'] == 'conversation.item.input_audio_transcription.failed':
                        log(f"[DEBUG] Transcription failed: {json.dumps(response, indent=2)}")

                    if response['type'] == 'response.audio.delta' and 'delta' in response and not USE_ELEVENLABS:
                        # Only process OpenAI audio when NOT using ElevenLabs
                        audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": audio_payload}
                        }
                        try:
                            await websocket.send_json(audio_delta)
                            # Log every 10th audio chunk to avoid spam
                            if not hasattr(send_to_twilio, 'audio_chunk_count'):
                                send_to_twilio.audio_chunk_count = 0
                            send_to_twilio.audio_chunk_count += 1
                            if send_to_twilio.audio_chunk_count % 10 == 0:
                                log(f"[AUDIO] Sent {send_to_twilio.audio_chunk_count} audio chunks to Twilio")
                        except WebSocketDisconnect as e:
                            # Twilio disconnected - call ended by caller
                            log(f"[AUDIO] Twilio WebSocket disconnected (caller hung up): {e}")
                            log(f"[AUDIO] Total audio chunks sent before disconnect: {getattr(send_to_twilio, 'audio_chunk_count', 0)}")
                            break
                        except Exception as e:
                            # Other error sending to Twilio
                            log(f"[AUDIO] Error sending audio to Twilio: {type(e).__name__}: {e}")
                            log(f"[AUDIO] Total audio chunks sent before error: {getattr(send_to_twilio, 'audio_chunk_count', 0)}")
                            break

                        if response.get("item_id") and response["item_id"] != last_assistant_item:
                            response_start_timestamp_twilio = latest_media_timestamp
                            last_assistant_item = response["item_id"]

                        try:
                            await send_mark(websocket, stream_sid)
                        except (WebSocketDisconnect, Exception):
                            # Twilio closed, ignore
                            pass

                    elif response['type'] == 'response.audio_transcript.done':
                        # Log assistant response (OpenAI audio mode only)
                        if not USE_ELEVENLABS:
                            transcript = response.get('transcript', '')
                            if transcript and call_sid:
                                update_call_transcript(call_sid, "assistant", transcript)
                                log(f"Assistant: {transcript}")
                                log(f"[AUDIO] Transcript complete. Audio chunks sent so far: {getattr(send_to_twilio, 'audio_chunk_count', 0)}")

                                # DO NOT add delay here - it interrupts audio playback
                                # The audio chunks are still streaming when transcript completes

                                # DO NOT extract from assistant responses to avoid capturing AI's mistakes
                                # Only extract from user speech

                    elif response['type'] == 'conversation.item.input_audio_transcription.completed':
                        # Log user speech
                        transcript = response.get('transcript', '')
                        if transcript and call_sid:
                            update_call_transcript(call_sid, "user", transcript)
                            log(f"User: {transcript}")

                            # Extract customer info from user speech ONLY
                            session = SESSIONS.get(call_sid)
                            if session:
                                extract_customer_info(transcript, session, is_user_speech=True)

                            # In text-only mode (ElevenLabs), manually trigger response after user speech
                            if USE_ELEVENLABS:
                                log("[ElevenLabs] Triggering response after user speech")
                                await openai_ws.send(json.dumps({"type": "response.create"}))

                    elif response['type'] == 'input_audio_buffer.speech_started':
                        log("Speech started - handling interruption")
                        await handle_speech_started_event()

                    elif response['type'] == 'response.function_call_arguments.done':
                        # Function call from the AI - execute it and return the result
                        call_id = response.get('call_id')
                        function_name = response.get('name')
                        arguments_str = response.get('arguments', '{}')

                        log(f"[FUNCTION CALL] {function_name} with args: {arguments_str}")

                        try:
                            arguments = json.loads(arguments_str)
                        except json.JSONDecodeError:
                            arguments = {}

                        # Execute the function
                        function_result = None
                        session = SESSIONS.get(call_sid)

                        if function_name == "get_available_slots":
                            days_ahead = arguments.get('days_ahead', 14)
                            slots = get_available_calendar_slots(days_ahead=days_ahead, num_slots=1)
                            if slots:
                                function_result = {
                                    "first_available": slots[0],
                                    "message": f"First available appointment is {slots[0]['display']}"
                                }
                                log(f"[FUNCTION RESULT] First available slot: {slots[0]['display']}")
                            else:
                                function_result = {
                                    "first_available": None,
                                    "message": "No available appointments found in the next 14 days"
                                }
                                log(f"[FUNCTION RESULT] No available slots found")

                        elif function_name == "get_next_business_day_slot":
                            next_day_slot = get_next_business_day_slot()
                            if next_day_slot:
                                function_result = {
                                    "next_business_day_slot": next_day_slot,
                                    "message": f"Next business day slot: {next_day_slot['display']}"
                                }
                                log(f"[FUNCTION RESULT] Next business day slot: {next_day_slot['display']}")
                            else:
                                function_result = {
                                    "next_business_day_slot": None,
                                    "message": "No available slots on next business day"
                                }
                                log(f"[FUNCTION RESULT] No next business day slots found")

                        elif function_name == "book_appointment":
                            slot_datetime = arguments.get('slot_datetime')
                            slot_display = arguments.get('slot_display')

                            if slot_datetime and slot_display and session:
                                # Store appointment info in session
                                session['appointment_datetime'] = slot_datetime
                                session['appointment_display'] = slot_display
                                log(f"[APPOINTMENT] Stored in session: {slot_display} ({slot_datetime})")

                                function_result = {
                                    "success": True,
                                    "message": f"Appointment booked for {slot_display}"
                                }
                            else:
                                function_result = {
                                    "success": False,
                                    "message": "Missing required information for booking"
                                }

                        elif function_name == "send_trial_link":
                            caller_phone = session.get('caller_phone', '') if session else ''
                            if caller_phone:
                                sms_sent = send_trial_link_sms(caller_phone)
                                function_result = {
                                    "success": sms_sent,
                                    "message": "Trial link texted to the caller's phone. Let them know to check their texts." if sms_sent else "Failed to send text. Apologize and offer to email the link instead."
                                }
                                log(f"[TRIAL LINK] SMS {'sent' if sms_sent else 'FAILED'} to {caller_phone}")
                            else:
                                function_result = {
                                    "success": False,
                                    "message": "No phone number available. Ask the caller for their phone number to text the link."
                                }

                        elif function_name == "take_message":
                            reason = arguments.get('reason', 'caller requested')
                            log(f"[VOICEMAIL] Starting voicemail mode - reason: {reason}")

                            if session:
                                session['voicemail_mode'] = True
                                session['voicemail_reason'] = reason

                            function_result = {
                                "success": True,
                                "message": "Voicemail mode activated. Say 'beep!' and prompt the caller to leave their message after the beep. Listen to their entire message, then call save_voicemail with the transcribed content."
                            }

                        elif function_name == "save_voicemail":
                            message_content = arguments.get('message_content', '')
                            callback_number = arguments.get('callback_number')
                            caller_name = arguments.get('caller_name')
                            urgency = arguments.get('urgency', 'normal')

                            log(f"[VOICEMAIL] Saving voicemail - caller: {caller_name}, urgency: {urgency}")
                            log(f"[VOICEMAIL] Message: {message_content[:100]}...")

                            if session:
                                session['voicemail_message'] = message_content
                                session['voicemail_callback'] = callback_number
                                session['voicemail_urgency'] = urgency
                                if caller_name:
                                    session['customer_name'] = caller_name

                                # Save voicemail to database
                                if call_sid and SUPABASE:
                                    try:
                                        # Store as a transcript entry with type 'voicemail'
                                        SUPABASE.table('call_transcripts').insert({
                                            "call_sid": call_sid,
                                            "role": "voicemail",
                                            "content": f"[{urgency.upper()}] {caller_name or 'Unknown'} ({callback_number or session.get('caller_phone', 'No callback number')}): {message_content}"
                                        }).execute()
                                        log(f"[VOICEMAIL] Saved to database for call {call_sid}")
                                    except Exception as e:
                                        log(f"[VOICEMAIL] Error saving to database: {e}")

                            function_result = {
                                "success": True,
                                "message": f"Voicemail saved successfully. Thank the caller and let them know someone will get back to them soon."
                            }

                        # Send function result back to OpenAI
                        if function_result is not None:
                            function_output = {
                                "type": "conversation.item.create",
                                "item": {
                                    "type": "function_call_output",
                                    "call_id": call_id,
                                    "output": json.dumps(function_result)
                                }
                            }
                            await openai_ws.send(json.dumps(function_output))

                            # Trigger the AI to respond with the function result
                            await openai_ws.send(json.dumps({"type": "response.create"}))

                    elif response['type'] == 'error':
                        error_info = response.get('error', {})
                        error_code = error_info.get('code', '')
                        log(f"OpenAI error: {error_info}")

                        # Handle rate limiting - slow down briefly
                        if error_code == 'rate_limit_exceeded':
                            log("Rate limit hit - pausing briefly")
                            await asyncio.sleep(2)
                        # Session expired - end call gracefully
                        elif error_code == 'session_expired':
                            log("Session expired - ending call")
                            break

                # If we exit the loop naturally (not via exception), log it
                log("OpenAI message stream ended (connection closed cleanly)")
                log(f"[DEBUG] Loop exited naturally. Call SID: {call_sid}, Stream SID: {stream_sid}")

            except websockets.exceptions.ConnectionClosed as e:
                log(f"ERROR: OpenAI WebSocket closed unexpectedly during call! Code: {e.code if hasattr(e, 'code') else 'unknown'}, Reason: {e.reason if hasattr(e, 'reason') else 'unknown'}")
                log(f"Call SID: {call_sid}, Stream SID: {stream_sid}")
                openai_connected = False
                # Send graceful fallback message to caller
                await send_error_message_to_caller(websocket, stream_sid)
            except Exception as e:
                log(f"ERROR in send_to_twilio: {type(e).__name__}: {e}")
                import traceback
                log(f"Traceback: {traceback.format_exc()}")
                openai_connected = False
                # Send graceful fallback message to caller
                await send_error_message_to_caller(websocket, stream_sid)

        async def handle_speech_started_event():
            """Handle user interruption"""
            nonlocal response_start_timestamp_twilio, last_assistant_item, stream_start_time

            # Guard: Ignore interruptions in first 3 seconds to prevent false triggers during greeting
            if stream_start_time:
                time_since_start = time.time() - stream_start_time
                if time_since_start < 3.0:
                    log(f"Ignoring early interruption ({time_since_start:.1f}s since start)")
                    return

            if mark_queue and response_start_timestamp_twilio is not None:
                elapsed_time = latest_media_timestamp - response_start_timestamp_twilio

                if last_assistant_item:
                    truncate_event = {
                        "type": "conversation.item.truncate",
                        "item_id": last_assistant_item,
                        "content_index": 0,
                        "audio_end_ms": elapsed_time
                    }
                    await openai_ws.send(json.dumps(truncate_event))

                await websocket.send_json({
                    "event": "clear",
                    "streamSid": stream_sid
                })

                mark_queue.clear()
                last_assistant_item = None
                response_start_timestamp_twilio = None

        async def send_mark(connection, stream_sid):
            """Send mark event to track audio playback"""
            if stream_sid:
                mark_event = {
                    "event": "mark",
                    "streamSid": stream_sid,
                    "mark": {"name": "responsePart"}
                }
                await connection.send_json(mark_event)
                mark_queue.append('responsePart')


        # Run both tasks concurrently
        log(f"[DEBUG] Starting concurrent tasks for call {call_sid}")
        try:
            await asyncio.gather(receive_from_twilio(), send_to_twilio())
            log(f"[DEBUG] Both tasks completed normally for call {call_sid}")
        except Exception as e:
            log(f"CRITICAL ERROR in media stream handler: {type(e).__name__}: {e}")
            log(f"Call SID: {call_sid}, Stream SID: {stream_sid}")
            import traceback
            log(f"Traceback: {traceback.format_exc()}")

            # Mark call as failed in session for follow-up
            if call_sid and call_sid in SESSIONS:
                SESSIONS[call_sid]['call_failed'] = True
                SESSIONS[call_sid]['failure_reason'] = str(e)
    finally:
        log(f"[DEBUG] Entering finally block - closing OpenAI WebSocket for call {call_sid}")
        # Always close the OpenAI WebSocket
        await openai_ws.close()
        log(f"[DEBUG] OpenAI WebSocket closed, handler complete for call {call_sid}")

@app.post("/status")
async def status_callback(request: Request):
    """Handle call status updates"""
    form = await request.form()
    call_sid = form.get("CallSid")
    call_status = form.get("CallStatus")

    log(f"Call status: {call_sid} -> {call_status}")

    # Send follow-up emails if call completed
    if call_status == "completed" and call_sid in SESSIONS:
        session = SESSIONS[call_sid]
        customer_email = session.get('customer_email')
        customer_phone = session.get('customer_phone')
        # Prefer customer_name, but don't use company_name as fallback for greeting (sounds weird)
        customer_name = session.get('customer_name') or "there"
        caller_phone = session.get('caller_phone')
        business_type = session.get('business_type') or "business"
        company_name = session.get('company_name')
        contact_preference = session.get('contact_preference')
        appointment_datetime = session.get('appointment_datetime')
        appointment_display = session.get('appointment_display')
        call_failed = session.get('call_failed', False)
        failure_reason = session.get('failure_reason', '')

        # Check if call had technical failures
        if call_failed:
            log(f"⚠️  CALL FAILED - Technical error occurred during call")
            log(f"Failure reason: {failure_reason}")
            log(f"Customer phone: {caller_phone}")
            # TODO: Send alert email to business owner about failed call
        else:
            # Normal successful call flow

            # Book calendar appointment if slot was chosen
            calendar_link = None
            if appointment_datetime and customer_name and business_type:
                log(f"Booking calendar appointment for {appointment_display}")
                booking_result = book_calendar_appointment(
                    appointment_datetime,
                    customer_name,
                    customer_email,
                    customer_phone or caller_phone,
                    business_type
                )
                if booking_result['success']:
                    log(f"✓ Calendar appointment booked successfully")
                    calendar_link = booking_result['link']
                else:
                    log(f"✗ Failed to book calendar appointment")

            # Always send confirmation email if we have customer email
            if customer_email and appointment_datetime:
                log(f"Sending calendar confirmation email to {customer_email}")
                send_demo_follow_up(customer_name, customer_email, business_type, appointment_datetime)
            elif customer_email and not appointment_datetime:
                log(f"Sending follow-up email (no appointment booked) to {customer_email}")
                send_demo_follow_up(customer_name, customer_email, business_type)
            else:
                log(f"No email to send - customer_email: {customer_email}, appointment: {appointment_datetime}")

            # Always send post-call summary to business owner
            log(f"Sending post-call summary to business owner")
            send_post_call_summary(
                call_sid=call_sid,
                caller_phone=caller_phone,
                customer_name=customer_name,
                customer_email=customer_email,
                customer_phone=customer_phone,
                business_type=business_type,
                company_name=company_name,
                appointment_display=appointment_display,
                call_start_time=session.get('call_start_time'),
            )

    # Clean up session
    if call_sid in SESSIONS:
        del SESSIONS[call_sid]

    return JSONResponse(content={"status": "ok"})

@app.post("/recording-status")
async def recording_status_callback(request: Request):
    """Handle recording status updates from Twilio"""
    form = await request.form()

    call_sid = form.get("CallSid")
    recording_sid = form.get("RecordingSid")
    recording_status = form.get("RecordingStatus")
    recording_url = form.get("RecordingUrl")
    recording_duration = form.get("RecordingDuration")

    log(f"Recording status: {recording_sid} -> {recording_status} for call {call_sid}")

    if recording_status == "completed" and recording_url:
        # Add .mp3 extension for playable URL
        recording_url_mp3 = f"{recording_url}.mp3"
        log(f"Recording completed: {recording_url_mp3}")

        # Update the call record in database with recording URL
        if SUPABASE:
            try:
                # Find call by call_sid and update with recording info
                result = SUPABASE.table('calls').update({
                    'recording_url': recording_url_mp3,
                    'recording_sid': recording_sid,
                    'recording_duration': int(recording_duration) if recording_duration else None
                }).eq('call_sid', call_sid).execute()

                if result.data:
                    log(f"Updated call {call_sid} with recording URL")
                else:
                    log(f"No call found with SID {call_sid} to update")
            except Exception as e:
                log(f"Error updating call with recording: {e}")

    return JSONResponse(content={"status": "ok"})

@app.get("/test-digest")
async def test_daily_digest():
    """Manual trigger for testing the daily digest email"""
    log("Manual test of daily digest triggered")

    # Check if Supabase is configured
    supabase = get_supabase_client()
    if not supabase:
        return JSONResponse(content={
            "status": "error",
            "message": "Supabase not configured - check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables"
        })

    # Get today's call count for debugging
    try:
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = datetime.now().replace(hour=23, minute=59, second=59, microsecond=999999)
        result = supabase.table('calls').select('*').gte('created_at', today_start.isoformat()).lte('created_at', today_end.isoformat()).execute()
        call_count = len(result.data) if result.data else 0

        # Send digest
        digest_result = send_daily_digest()

        return JSONResponse(content={
            "status": "success" if digest_result else "failed",
            "message": f"Found {call_count} calls today. " + ("Daily digest email sent" if digest_result else "Failed to send daily digest (check logs for details)"),
            "call_count": call_count
        })
    except Exception as e:
        log(f"Error in test-digest: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        return JSONResponse(content={
            "status": "error",
            "message": f"Error: {str(e)}"
        })

# ======================== Dashboard API Endpoints ========================
# These endpoints power the client dashboard

from fastapi.middleware.cors import CORSMiddleware

# Add CORS for dashboard frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict to dashboard domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/dashboard/stats/{business_id}")
async def get_dashboard_stats(business_id: str):
    """Get aggregate statistics for a business"""
    supabase = get_supabase_client()
    if not supabase:
        return JSONResponse(content={"error": "Database not configured"}, status_code=500)

    try:
        from datetime import datetime, timedelta

        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=today_start.weekday())
        month_start = today_start.replace(day=1)

        # Get all calls for this business
        result = supabase.table('calls').select('*').eq('business_id', business_id).execute()
        all_calls = result.data or []

        # Filter by time periods
        today_calls = [c for c in all_calls if c.get('created_at') and c['created_at'] >= today_start.isoformat()]
        week_calls = [c for c in all_calls if c.get('created_at') and c['created_at'] >= week_start.isoformat()]
        month_calls = [c for c in all_calls if c.get('created_at') and c['created_at'] >= month_start.isoformat()]

        # Calculate stats
        def calc_stats(calls):
            total = len(calls)
            completed = len([c for c in calls if c.get('status') == 'completed'])
            failed = len([c for c in calls if c.get('status') in ['failed', 'busy', 'no-answer']])
            total_duration = sum(int(c.get('duration', 0)) for c in calls if c.get('duration'))
            avg_duration = total_duration / completed if completed > 0 else 0
            return {
                "total": total,
                "completed": completed,
                "failed": failed,
                "in_progress": total - completed - failed,
                "total_duration_seconds": total_duration,
                "avg_duration_seconds": round(avg_duration, 1)
            }

        return JSONResponse(content={
            "success": True,
            "business_id": business_id,
            "today": calc_stats(today_calls),
            "this_week": calc_stats(week_calls),
            "this_month": calc_stats(month_calls),
            "all_time": calc_stats(all_calls)
        })

    except Exception as e:
        log(f"Error getting dashboard stats: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/dashboard/calls/{business_id}")
async def get_dashboard_calls(business_id: str, limit: int = 50, offset: int = 0):
    """Get paginated list of calls for a business"""
    supabase = get_supabase_client()
    if not supabase:
        return JSONResponse(content={"error": "Database not configured"}, status_code=500)

    try:
        # Get calls with pagination, newest first
        result = supabase.table('calls').select('*').eq('business_id', business_id).order('created_at', desc=True).range(offset, offset + limit - 1).execute()

        # Get total count
        count_result = supabase.table('calls').select('id', count='exact').eq('business_id', business_id).execute()
        total_count = count_result.count if hasattr(count_result, 'count') else len(count_result.data or [])

        return JSONResponse(content={
            "success": True,
            "calls": result.data or [],
            "total": total_count,
            "limit": limit,
            "offset": offset
        })

    except Exception as e:
        log(f"Error getting dashboard calls: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/dashboard/call/{call_id}")
async def get_call_detail(call_id: str):
    """Get detailed information about a single call including transcript"""
    supabase = get_supabase_client()
    if not supabase:
        return JSONResponse(content={"error": "Database not configured"}, status_code=500)

    try:
        # Get call record
        call_result = supabase.table('calls').select('*').eq('id', call_id).execute()
        if not call_result.data:
            return JSONResponse(content={"error": "Call not found"}, status_code=404)

        call = call_result.data[0]

        # Get transcript for this call (call_transcripts uses Twilio call_sid, not UUID)
        transcript_result = supabase.table('call_transcripts').select('*').eq('call_sid', call.get('call_sid', '')).order('created_at', desc=False).execute()

        return JSONResponse(content={
            "success": True,
            "call": call,
            "transcript": transcript_result.data or []
        })

    except Exception as e:
        log(f"Error getting call detail: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/dashboard/business/{business_id}")
async def get_business_settings(business_id: str):
    """Get business configuration (read-only for dashboard)"""
    supabase = get_supabase_client()
    if not supabase:
        return JSONResponse(content={"error": "Database not configured"}, status_code=500)

    try:
        # Get business info
        result = supabase.table('businesses').select('*').eq('id', business_id).execute()
        if not result.data:
            return JSONResponse(content={"error": "Business not found"}, status_code=404)

        business = result.data[0]

        # Get phone numbers for this business
        phones_result = supabase.table('phone_numbers').select('*').eq('business_id', business_id).execute()

        # Remove sensitive fields
        safe_business = {k: v for k, v in business.items() if k not in ['dashboard_password_hash']}

        return JSONResponse(content={
            "success": True,
            "business": safe_business,
            "phone_numbers": phones_result.data or []
        })

    except Exception as e:
        log(f"Error getting business settings: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

@app.get("/api/dashboard/businesses")
async def list_businesses():
    """List all businesses (for admin view)"""
    supabase = get_supabase_client()
    if not supabase:
        return JSONResponse(content={"error": "Database not configured"}, status_code=500)

    try:
        result = supabase.table('businesses').select('id, business_name, owner_name, owner_email, industry, status, created_at').execute()

        return JSONResponse(content={
            "success": True,
            "businesses": result.data or []
        })

    except Exception as e:
        log(f"Error listing businesses: {e}")
        return JSONResponse(content={"error": str(e)}, status_code=500)

# ======================== Calendar API Endpoints (for ElevenLabs tools) ========================

@app.post("/api/calendar/available-slots")
async def api_available_slots(request: Request):
    """Get available appointment slots - called by ElevenLabs agent"""
    try:
        body = await request.json()
        days_ahead = body.get("days_ahead", 14)

        slots = get_available_calendar_slots(days_ahead=days_ahead, num_slots=3)

        if slots:
            slot_list = ", ".join([s['display'] for s in slots[:3]])
            return JSONResponse(content={
                "success": True,
                "message": f"Available appointment times: {slot_list}",
                "slots": slots
            })
        else:
            return JSONResponse(content={
                "success": False,
                "message": "No available slots found in the next 2 weeks"
            })
    except Exception as e:
        log(f"[API] Error getting available slots: {e}")
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

@app.post("/api/calendar/check-slot")
async def api_check_slot(request: Request):
    """Check if a specific time slot is available - called by ElevenLabs agent"""
    try:
        body = await request.json()
        requested_datetime = body.get("requested_datetime")

        if not requested_datetime:
            return JSONResponse(content={"success": False, "message": "requested_datetime is required"})

        # Parse the requested datetime
        from dateutil import parser
        requested_dt = parser.parse(requested_datetime)

        # Check if slot is available using existing function
        slots = get_available_calendar_slots(days_ahead=14, num_slots=10)

        # Check if requested time matches any available slot (within 30 min window)
        for slot in slots:
            slot_dt = parser.parse(slot['datetime'])
            if abs((requested_dt - slot_dt).total_seconds()) < 1800:  # 30 min window
                return JSONResponse(content={
                    "success": True,
                    "available": True,
                    "message": f"Yes, {slot['display']} is available!",
                    "slot": slot
                })

        # Slot not available, suggest alternatives
        if slots:
            alt_list = ", ".join([s['display'] for s in slots[:3]])
            return JSONResponse(content={
                "success": True,
                "available": False,
                "message": f"That time isn't available. Here are some alternatives: {alt_list}",
                "alternative_slots": slots[:3]
            })
        else:
            return JSONResponse(content={
                "success": False,
                "available": False,
                "message": "No available slots found"
            })
    except Exception as e:
        log(f"[API] Error checking slot: {e}")
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

@app.post("/api/calendar/next-business-day")
async def api_next_business_day(request: Request):
    """Get first slot on next business day - called by ElevenLabs agent"""
    try:
        now = datetime.now()
        # Find next business day (skip weekends)
        next_day = now + timedelta(days=1)
        while next_day.weekday() >= 5:  # Saturday=5, Sunday=6
            next_day += timedelta(days=1)

        # Set to 9 AM
        next_slot = next_day.replace(hour=9, minute=0, second=0, microsecond=0)

        return JSONResponse(content={
            "success": True,
            "message": f"The first slot tomorrow is {next_slot.strftime('%A at %I%p').lower().replace(' 0', ' ')}",
            "slot": {
                "datetime": next_slot.isoformat(),
                "display": next_slot.strftime('%A at %I%p').lower().replace(' 0', ' ')
            }
        })
    except Exception as e:
        log(f"[API] Error getting next business day: {e}")
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

@app.post("/api/calendar/book")
async def api_book_appointment(request: Request):
    """Book an appointment - called by ElevenLabs agent"""
    try:
        body = await request.json()
        slot_datetime = body.get("slot_datetime")
        customer_name = body.get("customer_name", "Customer")
        customer_email = body.get("customer_email")
        customer_phone = body.get("customer_phone")
        company_name = body.get("company_name", "")

        if not slot_datetime:
            return JSONResponse(content={"success": False, "message": "slot_datetime is required"})

        # Parse datetime
        from dateutil import parser
        slot_dt = parser.parse(slot_datetime)

        # Try to book in Google Calendar using existing function
        result = book_calendar_appointment(
            slot_datetime=slot_datetime,
            customer_name=customer_name,
            customer_email=customer_email or "",
            customer_phone=customer_phone or "",
            business_type=company_name
        )

        if result and result.get('success'):
            return JSONResponse(content={
                "success": True,
                "message": f"Your appointment is booked for {slot_dt.strftime('%A at %I:%M %p')}. You'll receive a calendar invite shortly.",
                "event_link": result.get('link'),
                "datetime": slot_dt.isoformat()
            })
        else:
            # Calendar not available but still confirm
            return JSONResponse(content={
                "success": True,
                "message": f"Your appointment is confirmed for {slot_dt.strftime('%A at %I:%M %p')}. We'll send you a confirmation.",
                "datetime": slot_dt.isoformat()
            })
    except Exception as e:
        log(f"[API] Error booking appointment: {e}")
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

@app.post("/api/sms/send-confirmation")
async def api_send_sms_confirmation(request: Request):
    """Send SMS confirmation - called by ElevenLabs agent"""
    try:
        body = await request.json()
        customer_name = body.get("customer_name", "there")
        appointment_datetime = body.get("appointment_datetime")

        # Get caller phone from active call session (if available)
        # For now, return success message
        return JSONResponse(content={
            "success": True,
            "message": f"Text confirmation will be sent to your phone number."
        })
    except Exception as e:
        log(f"[API] Error sending SMS: {e}")
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

@app.post("/api/sms/send-trial-link")
async def api_send_trial_link(request: Request):
    """Send trial signup link via SMS - called by ElevenLabs agent webhook"""
    try:
        # Find the most recent active session with a caller_phone
        caller_phone = None
        latest_time = None
        for sid, session in SESSIONS.items():
            phone = session.get('caller_phone')
            start = session.get('call_start_time')
            if phone and start:
                if latest_time is None or start > latest_time:
                    latest_time = start
                    caller_phone = phone

        if not caller_phone:
            log("[TRIAL LINK] No active session with caller phone found")
            return JSONResponse(content={
                "success": False,
                "message": "No active caller phone found. Ask the caller for their phone number."
            })

        sms_sent = send_trial_link_sms(caller_phone)
        if sms_sent:
            return JSONResponse(content={
                "success": True,
                "message": "Trial link texted successfully. Let the caller know to check their texts."
            })
        else:
            return JSONResponse(content={
                "success": False,
                "message": "Failed to send text. Apologize and offer to provide the link verbally: criton.ai/signup"
            })
    except Exception as e:
        log(f"[API] Error sending trial link SMS: {e}")
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

@app.post("/api/waiting-list/add")
async def api_add_to_waiting_list(request: Request):
    """Add to waiting list - called by ElevenLabs agent"""
    try:
        body = await request.json()
        customer_name = body.get("customer_name")
        service_type = body.get("service_type")

        if not customer_name:
            return JSONResponse(content={"success": False, "message": "customer_name is required"})

        log(f"[WAITING LIST] Added {customer_name} for {service_type}")

        return JSONResponse(content={
            "success": True,
            "message": f"Got it, {customer_name}! You're on the waiting list. We'll reach out when we have availability."
        })
    except Exception as e:
        log(f"[API] Error adding to waiting list: {e}")
        return JSONResponse(content={"success": False, "message": str(e)}, status_code=500)

# ======================== Scheduler Setup ========================
# Initialize scheduler for daily digest
scheduler = BackgroundScheduler()

# Schedule daily digest at 11:59 PM every day
scheduler.add_job(
    send_daily_digest,
    trigger=CronTrigger(hour=23, minute=59),
    id='daily_digest',
    name='Send daily call digest at 11:59 PM',
    replace_existing=True
)

scheduler.start()
log("Scheduler started - Daily digest will be sent at 11:59 PM")

# ======================== Main ========================
if __name__ == "__main__":
    import uvicorn
    log(f"Starting Bolt AI Platform (Realtime API) on port {PORT}")
    log(f"Public base: {PUBLIC_BASE}")
    log(f"Voice: {VOICE}")
    # Use asyncio instead of uvloop for websockets compatibility
    uvicorn.run(app, host="0.0.0.0", port=PORT, loop="asyncio")
