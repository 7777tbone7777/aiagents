#!/usr/bin/env python3
"""
Bolt AI Platform with OpenAI Realtime API
Real-time voice conversations with instant responses - no more long pauses!
"""
import os, json, base64, asyncio, websockets, ssl, re, time, requests
import certifi
from datetime import datetime, timedelta
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.websockets import WebSocketDisconnect
from twilio.twiml.voice_response import VoiceResponse, Connect
from dotenv import load_dotenv
from supabase import create_client
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

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
MODEL = "gpt-4o-realtime-preview-2024-10-01"  # OpenAI Realtime API model

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
COMPANY_NAME = os.getenv("COMPANY_NAME", "Bolt AI Group")
PRODUCT_PITCH = os.getenv("PRODUCT_PITCH", "We build custom AI agents for small businesses that answer every call 24/7, book appointments automatically, handle customer questions, and ensure you never lose business to a missed call")
MONTHLY_PRICE = os.getenv("MONTHLY_PRICE", "$199")
CALENDAR_BOOKING_URL = os.getenv("CALENDAR_BOOKING_URL", "")

# Google Calendar configuration
GOOGLE_CALENDAR_EMAIL = os.getenv("GOOGLE_CALENDAR_EMAIL", "boltaigroup@gmail.com")
GOOGLE_CALENDAR_SERVICE_ACCOUNT = os.getenv("GOOGLE_CALENDAR_SERVICE_ACCOUNT", "/Users/anthony/aiagent/keys/calendar-sa.json")

# ======================== Globals ========================
app = FastAPI()
SUPABASE = None  # Lazy-initialized on first use
SESSIONS = {}  # call_sid -> session data

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

def send_instant_call_alert(call_sid, caller_phone, call_start_time):
    """Send instant email alert when a call comes in"""
    subject = f"🔔 Incoming Call Alert - {caller_phone}"

    call_time_formatted = call_start_time.strftime("%I:%M %p") if isinstance(call_start_time, datetime) else str(call_start_time)

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
                This is an automated alert from your Bolt AI phone agent system.
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

def send_demo_follow_up(customer_name, customer_email, business_type):
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

    # Implementation call reminder
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

        log(f"[CALENDAR] Mock slot: {next_slot.strftime('%A at %I%p').replace(' 0', ' ')}")
        return [{
            "datetime": next_slot.isoformat(),
            "display": f"{next_slot.strftime('%A at %I%p').lower().replace(' 0', ' ')}"
        }]

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
                log(f"[CALENDAR] Has backslash-n: {'\\n' in pk}")

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

        while current_check < max_search_date:
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
                    # Found first available slot!
                    day_name = current_check.strftime("%A")
                    time_display = current_check.strftime("%I%p").lower().replace('0', '', 1) if current_check.strftime("%I%p").startswith('0') else current_check.strftime("%I%p").lower()

                    log(f"[CALENDAR] ✓ FOUND available slot after checking {slots_checked} slots: {day_name} at {time_display}")

                    return [{
                        "datetime": slot_iso,
                        "display": f"{day_name} at {time_display}"
                    }]

            # Move to next hour
            current_check += timedelta(hours=1)

            # If we've gone past last appointment hour, jump to next day at 9am
            if current_check.hour > LAST_APPOINTMENT_HOUR or current_check.hour < OPEN_HOUR:
                current_check = (current_check + timedelta(days=1)).replace(hour=OPEN_HOUR, minute=0, second=0, microsecond=0)

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
            'attendees': [],
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                    {'method': 'popup', 'minutes': 30},  # 30 min before
                ],
            },
        }

        # Add customer email as attendee if provided
        if customer_email and validate_email(customer_email):
            event['attendees'].append({'email': customer_email})
            log(f"[BOOKING] Adding attendee: {customer_email}")
        else:
            log(f"[BOOKING] No valid email - calendar invite will not be sent to customer")

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
        return True

    except Exception as e:
        log(f"[BOOKING] ✗ ERROR Failed to book calendar appointment: {e}")
        import traceback
        log(f"[BOOKING] Traceback: {traceback.format_exc()}")
        return False

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
                            greeting = "Hi! I'm Jack with Bolt AI Group. We build AI agents that answer calls 24/7 for small businesses. Are you interested in a quick demo, or ready to get set up?"
                            system_message = f"""You are {agent_name}, an enthusiastic AI sales agent for {business_name}.

CRITICAL: Your FIRST response must be EXACTLY this greeting word-for-word:
"{greeting}"

═══════════════════════════════════════════════════════════════
AFTER GREETING - BRANCH INTO TWO PATHS:
═══════════════════════════════════════════════════════════════

PATH A: DEMO MODE
If they say "demo", "show me", "demonstration", "how does it work", or similar:

1. Ask: "Perfect! What type of business do you have?"
2. They tell you business type (HVAC, dental, barbershop, etc.)
3. Say EXACTLY: "Great! Let me show you how I'd handle calls for your [BusinessType]. Ready?"
4. Wait for their response, then IMMEDIATELY switch into character WITHOUT announcing the pause
5. SWITCH INTO DEMO CHARACTER - You are now the receptionist for "ACME [BusinessType]"
   - Greeting: "Thanks for calling ACME [BusinessType], this is Jack. How can I help you?"
   - They will roleplay as a customer (e.g., "My AC is broken", "I need a dentist appointment")
   - Respond with EMPATHY: "I'm sorry to hear that. That's never fun."
   - Ask: "Does Tuesday at 2pm work, or is this an emergency?"

   IF EMERGENCY:
   - Say: "Okay, I'll transfer you to a representative now."
   - IMMEDIATELY BREAK CHARACTER
   - Say: "I would then transfer them to a representative of your choosing. What did you think? Would you like to get started and setup an implementation call?"
   - GO TO SIGNUP FLOW

   IF TUESDAY WORKS:
   - Say: "Perfect! Let me get your phone number for the confirmation."
   - They give phone number
   - Say: "Great! You're all set for Tuesday at 2pm. You'll receive a confirmation text shortly. Is there anything else I can help with?"
   - [Handle 1-2 more exchanges naturally]
   - BREAK CHARACTER
   - Say: "Alright, so that's how I'd handle calls for your [BusinessType]! What did you think? Would you like to get started and setup an implementation call?"
   - GO TO SIGNUP FLOW

═══════════════════════════════════════════════════════════════

PATH B: SIGNUP MODE (Direct or after demo)
If they say "sign up", "get started", "let's do it", or YES after demo:

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
   - If NO, try once more. If still NO, say: "No problem, I'll send the confirmation to this phone number."
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
- Outside demo mode, you are Jack from Bolt AI Group

BUSINESS NAME GENERATION:
- Auto-generate demo business names as "ACME [BusinessType]"
- Examples: "ACME HVAC", "ACME Dental", "ACME Barbershop", "ACME Plumbing"

STRICT RULES - DO NOT VIOLATE:
- Keep responses brief (1-2 sentences max)
- Ask ONE question at a time
- Never mention pricing unless customer asks
- Demo mode should be SHORT (3-5 exchanges max)
- Always collect email for calendar invitation
- Always book implementation appointment before ending call
- Be warm, friendly, and professional

Be conversational, empathetic, and efficient."""
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
                                "model": MODEL,  # REQUIRED: Specify the Realtime API model
                                "turn_detection": {
                                    "type": "server_vad",
                                    "threshold": 0.7,  # Balanced: not too sensitive (0.8 missed speech), not too low (0.6 false interrupts) (default 0.5)
                                    "prefix_padding_ms": 300,  # Audio before speech (default 300ms)
                                    "silence_duration_ms": 1200  # Longer silence before turn ends
                                },
                                "input_audio_format": "g711_ulaw",
                                "output_audio_format": "g711_ulaw",
                                "voice": VOICE,
                                "instructions": system_message,
                                "modalities": ["text", "audio"],
                                "temperature": TEMPERATURE,
                                "input_audio_transcription": {"model": "whisper-1"},  # Enable user speech transcription
                                "tools": [
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
                                    }
                                ],
                                "tool_choice": "auto"
                            }
                        }
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
                    elif response['type'] == 'conversation.item.input_audio_transcription.failed':
                        log(f"[DEBUG] Transcription failed: {json.dumps(response, indent=2)}")

                    if response['type'] == 'response.audio.delta' and 'delta' in response:
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
                        # Log assistant response
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
        customer_name = session.get('customer_name') or session.get('company_name') or "there"
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
            if appointment_datetime and customer_name and business_type:
                log(f"Booking calendar appointment for {appointment_display}")
                book_success = book_calendar_appointment(
                    appointment_datetime,
                    customer_name,
                    customer_email,
                    customer_phone or caller_phone,
                    business_type
                )
                if book_success:
                    log(f"✓ Calendar appointment booked successfully")
                else:
                    log(f"✗ Failed to book calendar appointment")

            # Always send confirmation email if we have customer email
            if customer_email and appointment_datetime:
                log(f"Sending calendar confirmation email to {customer_email}")
                send_demo_follow_up(customer_name, customer_email, business_type)
            elif customer_email and not appointment_datetime:
                log(f"Sending follow-up email (no appointment booked) to {customer_email}")
                send_demo_follow_up(customer_name, customer_email, business_type)
            else:
                log(f"No email to send - customer_email: {customer_email}, appointment: {appointment_datetime}")

            # Only send notification to business owner if we collected meaningful data
            if customer_email or customer_phone or (business_type and business_type != "business") or company_name:
                log(f"Sending notification to business owner")
                send_business_owner_notification(
                    customer_name,
                    customer_email,
                    customer_phone or caller_phone,
                    business_type,
                    company_name,
                    None,  # contact_preference no longer used
                    appointment_display
                )
            else:
                log(f"Skipping business owner notification - no customer data collected")

    # Clean up session
    if call_sid in SESSIONS:
        del SESSIONS[call_sid]

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
