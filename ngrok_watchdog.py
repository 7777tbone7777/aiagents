#!/usr/bin/env python3
"""
Ngrok Watchdog - Auto-restarts ngrok when it dies or becomes unhealthy
Also auto-updates Twilio webhooks when ngrok URL changes
"""
import subprocess
import time
import requests
import os
import signal
import sys
from datetime import datetime
from twilio.rest import Client
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path="/Users/anthony/aiagent/.env")

NGROK_PORT = 5000
NGROK_API = "http://localhost:4040/api/tunnels"
CHECK_INTERVAL = 30  # Check every 30 seconds
RESTART_DELAY = 5    # Wait 5 seconds before restarting
ENV_FILE = "/Users/anthony/aiagent/.env"
NGROK_BIN = "/usr/local/bin/ngrok"

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.getenv("TWILIO_NUMBER")

ngrok_process = None
current_ngrok_url = None
twilio_client = None
twilio_phone_sid = None

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def init_twilio():
    """Initialize Twilio client and find phone number SID"""
    global twilio_client, twilio_phone_sid

    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_NUMBER]):
        log("WARNING: Twilio credentials not found in .env - auto-update disabled")
        return False

    try:
        twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        # Find the phone number SID by matching the number
        incoming_numbers = twilio_client.incoming_phone_numbers.list()
        for number in incoming_numbers:
            if number.phone_number == TWILIO_NUMBER:
                twilio_phone_sid = number.sid
                log(f"Found Twilio number: {TWILIO_NUMBER} (SID: {twilio_phone_sid})")
                return True

        log(f"WARNING: Could not find Twilio number {TWILIO_NUMBER} - auto-update disabled")
        return False
    except Exception as e:
        log(f"WARNING: Failed to initialize Twilio: {e} - auto-update disabled")
        return False

def update_twilio_webhooks(new_url):
    """Update Twilio phone number webhooks"""
    if not twilio_client or not twilio_phone_sid:
        log("Twilio not initialized - skipping webhook update")
        return False

    try:
        log("Updating Twilio webhooks...")

        # Update the phone number's webhooks
        phone_number = twilio_client.incoming_phone_numbers(twilio_phone_sid).update(
            voice_url=f"{new_url}/inbound",
            voice_method="POST",
            status_callback=f"{new_url}/status",
            status_callback_method="POST"
        )

        log("✓ Twilio webhooks updated successfully!")
        log(f"  Voice URL: {new_url}/inbound")
        log(f"  Status Callback: {new_url}/status")
        return True
    except Exception as e:
        log(f"ERROR updating Twilio webhooks: {e}")
        return False

def get_ngrok_url():
    """Get the current ngrok public URL"""
    try:
        response = requests.get(NGROK_API, timeout=5)
        if response.status_code == 200:
            data = response.json()
            tunnels = data.get('tunnels', [])
            for tunnel in tunnels:
                url = tunnel.get('public_url', '')
                if url.startswith('https://'):
                    return url
        return None
    except Exception as e:
        return None

def is_ngrok_healthy():
    """Check if ngrok tunnel is active and healthy"""
    url = get_ngrok_url()
    if url:
        log(f"Tunnel healthy: {url}")
        return True
    else:
        log(f"Health check failed: No tunnel found")
        return False

def restart_bolt():
    """Restart bolt_realtime.py to pick up new URL"""
    try:
        log("Restarting bolt_realtime.py...")
        # Kill bolt processes
        subprocess.run(['pkill', '-9', '-f', 'bolt_realtime'], check=False)
        subprocess.run(['pkill', '-9', '-f', 'bolt_watchdog'], check=False)
        time.sleep(2)

        # Start bolt watchdog (which starts bolt_realtime)
        # Log to file so we can monitor it
        log_file = open('/tmp/watchdog.log', 'a')
        subprocess.Popen(
            ['./venv/bin/python', '/Users/anthony/aiagent/bolt_watchdog.py'],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd='/Users/anthony/aiagent'
        )
        log("✓ Bolt services restarting with updated URL...")
        return True
    except Exception as e:
        log(f"ERROR restarting bolt: {e}")
        return False

def update_env_file(new_url):
    """Update PUBLIC_BASE_URL in .env file"""
    global current_ngrok_url

    if new_url == current_ngrok_url:
        return  # No change

    try:
        # Read current .env file
        with open(ENV_FILE, 'r') as f:
            lines = f.readlines()

        # Update PUBLIC_BASE_URL line
        updated = False
        for i, line in enumerate(lines):
            if line.startswith('PUBLIC_BASE_URL='):
                old_url = line.split('=')[1].strip()
                lines[i] = f'PUBLIC_BASE_URL={new_url}\n'
                updated = True
                log(f"Updated .env: {old_url} -> {new_url}")
                break

        # Write back to file
        if updated:
            with open(ENV_FILE, 'w') as f:
                f.writelines(lines)
            current_ngrok_url = new_url
            log("=" * 60)
            log(f"New ngrok URL: {new_url}")
            log("=" * 60)

            # Auto-update Twilio webhooks
            if update_twilio_webhooks(new_url):
                log("✓ Twilio webhooks updated!")
            else:
                log("WARNING: Twilio auto-update failed")
                log("ACTION REQUIRED: Manually update Twilio webhooks:")
                log(f"  - Voice URL: {new_url}/inbound")
                log(f"  - Status Callback URL: {new_url}/status")

            # Restart bolt to pick up new URL
            if restart_bolt():
                log("✓ Fully automated update complete - system ready!")
            else:
                log("WARNING: Bolt restart failed - may need manual restart")

            log("=" * 60)
        else:
            log("WARNING: PUBLIC_BASE_URL not found in .env file")

    except Exception as e:
        log(f"ERROR updating .env file: {e}")

def start_ngrok():
    """Start ngrok process"""
    global ngrok_process

    log("Starting ngrok...")
    try:
        ngrok_process = subprocess.Popen(
            [NGROK_BIN, 'http', str(NGROK_PORT), '--log=stdout'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid  # Create new process group
        )
        log(f"Ngrok started with PID: {ngrok_process.pid}")

        # Wait a bit for ngrok to establish tunnel
        time.sleep(5)

        # Verify it started successfully
        if is_ngrok_healthy():
            log("Ngrok tunnel established successfully")
            # Update .env with new URL
            new_url = get_ngrok_url()
            if new_url:
                update_env_file(new_url)
            return True
        else:
            log("WARNING: Ngrok started but tunnel not healthy yet")
            return True  # Give it a chance
    except Exception as e:
        log(f"ERROR starting ngrok: {e}")
        return False

def stop_ngrok():
    """Stop ngrok process gracefully"""
    global ngrok_process

    if ngrok_process:
        log(f"Stopping ngrok (PID: {ngrok_process.pid})...")
        try:
            # Kill the entire process group
            os.killpg(os.getpgid(ngrok_process.pid), signal.SIGTERM)
            ngrok_process.wait(timeout=10)
            log("Ngrok stopped")
        except Exception as e:
            log(f"Error stopping ngrok: {e}")
            try:
                # Force kill if graceful shutdown failed
                os.killpg(os.getpgid(ngrok_process.pid), signal.SIGKILL)
            except:
                pass
        ngrok_process = None

def restart_ngrok():
    """Restart ngrok"""
    log("=" * 60)
    log("RESTARTING NGROK")
    log("=" * 60)
    stop_ngrok()
    time.sleep(RESTART_DELAY)
    return start_ngrok()

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    log("\nShutdown signal received. Cleaning up...")
    stop_ngrok()
    sys.exit(0)

def main():
    """Main watchdog loop"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log("=" * 60)
    log("NGROK WATCHDOG STARTED (with Twilio Auto-Update)")
    log(f"Monitoring ngrok on port {NGROK_PORT}")
    log(f"Check interval: {CHECK_INTERVAL}s")
    log("=" * 60)

    # Initialize Twilio
    if init_twilio():
        log("✓ Twilio auto-update enabled")
    else:
        log("⚠ Twilio auto-update disabled - will require manual updates")
    log("=" * 60)

    # Start ngrok initially
    if not start_ngrok():
        log("ERROR: Failed to start ngrok initially. Exiting.")
        sys.exit(1)

    consecutive_failures = 0
    max_consecutive_failures = 3

    # Monitor loop
    while True:
        time.sleep(CHECK_INTERVAL)

        # Check if process is still running
        if ngrok_process and ngrok_process.poll() is not None:
            log("ERROR: Ngrok process died!")
            consecutive_failures += 1
            if restart_ngrok():
                consecutive_failures = 0
        # Check if tunnel is healthy
        elif not is_ngrok_healthy():
            log("ERROR: Ngrok tunnel unhealthy!")
            consecutive_failures += 1
            if restart_ngrok():
                consecutive_failures = 0
        else:
            # All good
            consecutive_failures = 0

        # Check for too many failures
        if consecutive_failures >= max_consecutive_failures:
            log(f"ERROR: {consecutive_failures} consecutive failures. Giving up.")
            stop_ngrok()
            sys.exit(1)

if __name__ == '__main__':
    main()
