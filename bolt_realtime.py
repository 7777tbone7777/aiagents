#!/usr/bin/env python3
"""
Bolt AI Platform with OpenAI Realtime API
Real-time voice conversations with instant responses - no more long pauses!
"""
import os, json, base64, asyncio, websockets, ssl, re, time, requests
import certifi
from datetime import datetime
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# ======================== Config ========================
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PORT = int(os.getenv("PORT", 5000))

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

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
AGENT_NAME = os.getenv("AGENT_NAME", "Bolt")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Bolt AI Group")
PRODUCT_PITCH = os.getenv("PRODUCT_PITCH", "We build custom AI agents for small businesses that answer every call 24/7, book appointments automatically, handle customer questions, and ensure you never lose business to a missed call")
MONTHLY_PRICE = os.getenv("MONTHLY_PRICE", "$199")
CALENDAR_BOOKING_URL = os.getenv("CALENDAR_BOOKING_URL", "")

# ======================== Globals ========================
app = FastAPI()
SUPABASE = None  # Lazy-initialized on first use
SESSIONS = {}  # call_sid -> session data

def get_supabase_client():
    """Get or create Supabase client (lazy initialization)"""
    global SUPABASE
    if SUPABASE is None and SUPABASE_URL and SUPABASE_KEY:
        try:
            log(f"[DEBUG] Creating Supabase client for {SUPABASE_URL[:30]}...")
            SUPABASE = create_client(SUPABASE_URL, SUPABASE_KEY)
            log(f"[DEBUG] Supabase client created successfully")
        except Exception as e:
            log(f"[ERROR] Failed to create Supabase client: {e}")
            return None
    return SUPABASE

# ======================== Logging ========================
def log(msg, **kwargs):
    timestamp = datetime.utcnow().isoformat() + "Z"
    print(f"{timestamp} {msg}", flush=True)

# ======================== Database ========================
def get_business_for_phone(phone):
    """Look up business by phone number"""
    # TEMPORARY WORKAROUND: If Supabase fails, use fallback config for known numbers
    FALLBACK_CONFIGS = {
        "+18555287028": {
            "id": "78e2ea0f-f34b-4459-9d5b-6e32d946db13",
            "business_name": "Bolt AI Group",
            "owner_name": "Anthony Vazquez",
            "owner_email": "scarfaceforward@gmail.com",
            "industry": "sales",
            "agent_name": "Bolt",
            "capabilities": ["appointments"],
            "google_calendar_id": "scarfaceforward@gmail.com",
            "plan": "internal",
            "status": "active"
        }
    }

    supabase = get_supabase_client()
    if not supabase:
        log(f"[WARN] SUPABASE client is None - using fallback config")
        return FALLBACK_CONFIGS.get(phone)

    try:
        log(f"[DEBUG] Querying phone_numbers table for: {phone}")
        result = supabase.table('phone_numbers').select('business_id').eq('phone_number', phone).execute()
        log(f"[DEBUG] Phone lookup result: {result.data}")
        if not result.data:
            log(f"[WARN] No database record - trying fallback config")
            return FALLBACK_CONFIGS.get(phone)
        business_id = result.data[0]['business_id']
        log(f"[DEBUG] Found business_id: {business_id}, fetching business details...")
        biz_result = supabase.table('businesses').select('*').eq('id', business_id).execute()
        log(f"[DEBUG] Business lookup successful: {biz_result.data[0]['business_name'] if biz_result.data else 'None'}")
        return biz_result.data[0] if biz_result.data else None
    except Exception as e:
        import traceback
        log(f"[ERROR] Database error in get_business_for_phone: {e}")
        log(f"[WARN] Using fallback config due to database error")
        # Fall back to hardcoded config
        return FALLBACK_CONFIGS.get(phone)

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
    """Update call transcript"""
    session = SESSIONS.get(call_sid)
    if not session or not SUPABASE:
        return

    call_id = session.get('call_id')
    if not call_id:
        return

    try:
        SUPABASE.table('call_transcripts').insert({
            "call_id": call_id,
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
                    "from": f"{COMPANY_NAME} <{FROM_EMAIL}>",
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
            msg['From'] = f"{COMPANY_NAME} <{SMTP_USER}>"  # Use SMTP user email for FROM
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

def send_business_owner_notification(customer_name, customer_email, customer_phone, business_type, company_name=None):
    """Notify business owner of new lead"""
    owner_email = BUSINESS_OWNER_EMAIL
    company_display = f" ({company_name})" if company_name else ""
    subject = f"New Lead: {business_type}{company_display}"

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
        </ul>

        <p>A follow-up email with demo information has been sent to the customer.</p>

        <p><strong>Next Steps:</strong> Reach out to schedule their demo!</p>

        <hr>
        <p style="font-size: 0.9em; color: #666;">
            This notification was automatically generated by your Bolt AI sales agent.
        </p>
    </body>
    </html>
    """

    return send_email(owner_email, subject, body_html)

def send_demo_follow_up(customer_name, customer_email, business_type):
    """Send follow-up email after sales call"""
    subject = f"Your AI Phone Solution for {business_type} - {COMPANY_NAME}"

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

    # Calendar booking button
    calendar_button = ""
    if CALENDAR_BOOKING_URL:
        calendar_button = f"""
        <div style="text-align: center; margin: 30px 0;">
            <a href="{CALENDAR_BOOKING_URL}"
               style="background-color: #0066cc; color: white; padding: 15px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                📅 Schedule Your Demo Now
            </a>
        </div>
        <p style="text-align: center; color: #666; font-size: 0.9em;">
            Or I'll reach out within 24 hours to find a time that works for you.
        </p>
        """
    else:
        calendar_button = f"""
        <p><strong>I'll be reaching out within 24 hours to schedule your personalized demo.</strong></p>
        """

    body_html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto;">
        <h2 style="color: #0066cc;">Hi {customer_name}!</h2>

        <p>Thanks for taking the time to learn about {COMPANY_NAME}. I'm excited to show you how our AI phone solution can help your {business_type}.</p>

        <h3 style="color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 5px;">
            How We'll Help Your {business_type.title()}:
        </h3>
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

        <h3 style="color: #0066cc; border-bottom: 2px solid #0066cc; padding-bottom: 5px;">
            Pricing:
        </h3>
        <p style="font-size: 1.1em;">
            <strong>{MONTHLY_PRICE}/month</strong> - All-inclusive, no hidden fees
        </p>

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
                log(f"Updated email: {old_email} -> {normalized_email}")
            elif raw_email != normalized_email:
                log(f"Captured email: {raw_email} -> normalized to: {normalized_email}")
            else:
                log(f"Captured email: {normalized_email}")
        else:
            log(f"Invalid email format rejected: {normalized_email}")

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
            'office', 'firm', 'agency', 'center'
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
                excluded = ['Sure', 'Yes', 'Yeah', 'Okay', 'Great', 'Perfect', 'Hello', 'Hi', 'Hey', 'Thanks', 'Thank']
                if customer_name not in excluded and len(customer_name) >= 2:
                    session['customer_name'] = customer_name
                    log(f"Captured customer name: {customer_name}")
                    break

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

# ======================== Routes ========================
@app.get("/", response_class=JSONResponse)
async def index_page():
    return {"status": "healthy", "mode": "realtime_api", "platform": "Bolt AI Group"}

@app.get("/health", response_class=JSONResponse)
async def health_check():
    return {"status": "ok"}

@app.api_route("/inbound", methods=["GET", "POST"])
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
    SESSIONS[call_sid] = {
        "business": business,
        "call_id": call_record['id'] if call_record else None,
        "caller_phone": from_number,
        "customer_name": None,
        "customer_email": None,
        "business_type": None,
        "company_name": None
    }

    # Start Media Stream
    response = VoiceResponse()
    host = request.url.hostname
    connect = Connect()
    connect.stream(url=f'wss://{host}/media-stream')
    response.append(connect)

    return HTMLResponse(content=str(response), media_type="application/xml")

@app.websocket("/media-stream")
async def handle_media_stream(websocket: WebSocket):
    """Handle Twilio Media Stream WebSocket"""
    log("Media stream WebSocket connected")
    await websocket.accept()

    call_sid = None
    stream_sid = None

    # Create SSL context with certifi's CA bundle
    ssl_context = ssl.create_default_context(cafile=certifi.where())

    log("Connecting to OpenAI Realtime API...")
    try:
        openai_ws = await asyncio.wait_for(
            websockets.connect(
                "wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01",
                extra_headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "OpenAI-Beta": "realtime=v1"
                },
                ssl=ssl_context,
                ping_interval=WEBSOCKET_PING_INTERVAL,
                ping_timeout=WEBSOCKET_PING_TIMEOUT,
                open_timeout=30  # 30 second timeout for connection
            ),
            timeout=30.0
        )
        log("✓ OpenAI WebSocket connected successfully")
    except asyncio.TimeoutError:
        log("ERROR: OpenAI WebSocket connection timed out after 30 seconds - call will disconnect")
        log("This usually indicates network issues or OpenAI API problems")
        return
    except Exception as e:
        log(f"ERROR: Failed to connect to OpenAI: {type(e).__name__}: {e}")
        import traceback
        log(f"Traceback: {traceback.format_exc()}")
        return

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
                            greeting = "Hi I'm Bolt, an AI Agent with the Bolt AI Group. We build AI agents for small businesses that handle phone, SMS, and web chat—booking appointments, answering FAQs, taking orders, and syncing calendars—starting at $199/month. Who am I speaking with?"
                            system_message = f"""You are {agent_name}, an enthusiastic AI sales agent for {business_name}.

CRITICAL: Your FIRST response must be EXACTLY this greeting word-for-word:
"{greeting}"

After the greeting, your goals IN THIS EXACT ORDER:
1. They tell you their name (first name or full name - accept whatever they provide)
2. Thank them and ask: "Thanks [Name]! What type of business do you have?"
3. They tell you their business type (gym, restaurant, salon, etc.)
4. Give ONE brief sentence about how Bolt AI Group can help that specific business type
   Examples:
   - Gym: "We can help your gym handle class bookings and membership inquiries 24/7."
   - Restaurant: "We can help your restaurant take reservations and answer menu questions around the clock."
   - Salon: "We can help your salon book appointments and send reminders automatically."
   Keep it to ONE sentence, then immediately move to next step
5. Ask: "What's your email address?"
6. They provide email - repeat it back NORMALLY: "So that's [email] - did I get that right?"
7. After confirming email is correct, say EXACTLY: "Perfect! We'll be calling you within 24 hours to speak about your specific implementation. Thank you for your time!"
8. END THE CALL - do NOT ask additional questions after this

CRITICAL NAME COLLECTION:
- When you ask "Who am I speaking with?" they may give first name only (Tony) or full name (Tony Vazquez)
- Accept whatever they provide - don't ask for clarification
- Use their name when asking about business type: "Thanks [Name]! What type of business do you have?"

CRITICAL EMAIL COLLECTION INSTRUCTIONS:
- After they tell you their email, repeat it back NORMALLY (NOT letter by letter, NOT phonetically)
- Example: If you hear "tbone7777@hotmail.com", say "So that's tbone7777@hotmail.com - did I get that right?"
- DO NOT say "t as in tango" or spell it phonetically - just say the email normally
- If they say NO or correct you ONCE, try ONE more time: "Let me try again - [email]?"
- If they say NO a SECOND time, say: "I'm having trouble catching the email clearly. We'll give you a call back at this number to confirm everything. Thank you!"
- After confirming the correct email, IMMEDIATELY wrap up the call as instructed above
- NEVER attempt more than 2 times for email

STRICT RULES - DO NOT VIOLATE:
- ONLY give ONE brief sentence about how you help their business - nothing more
- DO NOT ask "Can you spend 10 minutes discussing..." - skip this entirely
- Never mention payment, money, or pricing unless the customer asks first
- Never make assumptions about what the customer is thinking or feeling
- Stay focused on collecting: name → business type → brief benefit → email → end call
- Keep responses brief (1-2 sentences max)
- Ask one question at a time
- NEVER move forward without confirming the email is 100% correct

Be conversational, friendly, and efficient. Get the information quickly and end the call."""
                        else:
                            system_message = f"""You are {agent_name}, a helpful AI receptionist for {business_name}.

Your job is to:
- Greet callers warmly
- Answer questions about the business
- Help with appointments and inquiries
- Provide excellent customer service

Be friendly, professional, and concise. Keep responses to 1-2 sentences."""

                        # Send session configuration
                        # Configure VAD to be less sensitive to prevent false interruptions
                        session_update = {
                            "type": "session.update",
                            "session": {
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.9,  # Much higher to prevent echo/feedback (default 0.5)
                                    "prefix_padding_ms": 300,  # Audio before speech (default 300ms)
                                    "silence_duration_ms": 1000  # Longer silence before turn ends
                                },
                                "input_audio_format": "g711_ulaw",
                                "output_audio_format": "g711_ulaw",
                                "voice": VOICE,
                                "instructions": system_message,
                                "modalities": ["text", "audio"],
                                "temperature": TEMPERATURE,
                                "input_audio_transcription": {"model": "whisper-1"}  # Enable user speech transcription
                            }
                        }
                        await openai_ws.send(json.dumps(session_update))

                        # Trigger initial greeting (greeting text is in system instructions)
                        await openai_ws.send(json.dumps({"type": "response.create"}))

                    elif data['event'] == 'mark':
                        if mark_queue:
                            mark_queue.pop(0)

                    elif data['event'] == 'stop':
                        log(f"Stream stopped: {stream_sid}")
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

                    if response['type'] == 'response.audio.delta' and 'delta' in response:
                        audio_payload = base64.b64encode(base64.b64decode(response['delta'])).decode('utf-8')
                        audio_delta = {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {"payload": audio_payload}
                        }
                        try:
                            await websocket.send_json(audio_delta)
                        except (WebSocketDisconnect, Exception) as e:
                            # Twilio already closed - call ended, stop sending
                            log(f"Twilio WebSocket closed while sending audio, call ended")
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
                        # Log assistant response
                        transcript = response.get('transcript', '')
                        if transcript and call_sid:
                            update_call_transcript(call_sid, "assistant", transcript)
                            log(f"Assistant: {transcript}")

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

                    elif response['type'] == 'input_audio_buffer.speech_started':
                        log("Speech started - handling interruption")
                        await handle_speech_started_event()

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
        try:
            await asyncio.gather(receive_from_twilio(), send_to_twilio())
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
        # Always close the OpenAI WebSocket
        await openai_ws.close()

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
        customer_name = session.get('customer_name') or session.get('company_name') or "there"
        customer_phone = session.get('caller_phone')
        business_type = session.get('business_type') or "business"
        company_name = session.get('company_name')
        call_failed = session.get('call_failed', False)
        failure_reason = session.get('failure_reason', '')

        # Check if call had technical failures
        if call_failed:
            log(f"⚠️  CALL FAILED - Technical error occurred during call")
            log(f"Failure reason: {failure_reason}")
            log(f"Customer phone: {customer_phone}")
            # TODO: Send alert email to business owner about failed call
        else:
            # Normal successful call flow
            if customer_email:
                log(f"Sending follow-up email to {customer_email}")
                send_demo_follow_up(customer_name, customer_email, business_type)

            # Only send notification to business owner if we collected meaningful data
            if customer_email or (business_type and business_type != "business") or company_name:
                log(f"Sending notification to business owner")
                send_business_owner_notification(customer_name, customer_email, customer_phone, business_type, company_name)
            else:
                log(f"Skipping business owner notification - no customer data collected")

    # Clean up session
    if call_sid in SESSIONS:
        del SESSIONS[call_sid]

    return JSONResponse(content={"status": "ok"})

# ======================== Main ========================
if __name__ == "__main__":
    import uvicorn
    log(f"Starting Bolt AI Platform (Realtime API) on port {PORT}")
    log(f"Public base: {PUBLIC_BASE}")
    log(f"Voice: {VOICE}")
    # Use asyncio instead of uvloop for websockets compatibility
    uvicorn.run(app, host="0.0.0.0", port=PORT, loop="asyncio")
