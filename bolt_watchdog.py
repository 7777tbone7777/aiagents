#!/usr/bin/env python3
"""
Bolt Watchdog - Auto-restarts bolt_realtime.py when it dies or becomes unhealthy
"""
import subprocess
import time
import requests
import os
import signal
import sys
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv(dotenv_path="/Users/anthony/aiagent/.env")

BOLT_PORT = 5000
HEALTH_CHECK_URL = f"http://localhost:{BOLT_PORT}/"
CHECK_INTERVAL = 30  # Check every 30 seconds
RESTART_DELAY = 5    # Wait 5 seconds before restarting
ENV_FILE = "/Users/anthony/aiagent/.env"
VENV_PYTHON = "/Users/anthony/aiagent/venv/bin/python"
BOLT_SCRIPT = "/Users/anthony/aiagent/bolt_realtime.py"

# Get PUBLIC_BASE_URL from env
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

bolt_process = None

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}", flush=True)

def kill_port_process(port):
    """Force kill any process holding the specified port"""
    try:
        # Find process using the port
        result = subprocess.run(
            ['lsof', '-ti', f':{port}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.stdout.strip():
            pids = result.stdout.strip().split('\n')
            for pid in pids:
                try:
                    log(f"Found process {pid} holding port {port}, force killing...")
                    os.kill(int(pid), signal.SIGKILL)
                    time.sleep(1)
                    log(f"Killed PID {pid}")
                except Exception as e:
                    log(f"Error killing PID {pid}: {e}")
            return True
        return False
    except Exception as e:
        log(f"Error checking port {port}: {e}")
        return False

def ensure_port_free(port, max_attempts=3):
    """Ensure port is free, force killing if necessary"""
    for attempt in range(max_attempts):
        try:
            result = subprocess.run(
                ['lsof', '-ti', f':{port}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if not result.stdout.strip():
                log(f"Port {port} is free")
                return True

            log(f"Port {port} is in use (attempt {attempt + 1}/{max_attempts})")
            kill_port_process(port)
            time.sleep(2)
        except Exception as e:
            log(f"Error ensuring port free: {e}")

    # Final check
    result = subprocess.run(['lsof', '-ti', f':{port}'], capture_output=True, text=True)
    is_free = not result.stdout.strip()
    if not is_free:
        log(f"WARNING: Could not free port {port} after {max_attempts} attempts")
    return is_free

def is_bolt_healthy():
    """Check if bolt_realtime.py is healthy via HTTP health check"""
    try:
        response = requests.get(HEALTH_CHECK_URL, timeout=5)
        if response.status_code == 200:
            log(f"Health check passed: {HEALTH_CHECK_URL}")
            return True
        else:
            log(f"Health check failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        log(f"Health check failed: {e}")
        return False

def start_bolt():
    """Start bolt_realtime.py process"""
    global bolt_process

    log("Starting bolt_realtime.py...")

    # CRITICAL: Ensure port is free before starting
    log(f"Checking if port {BOLT_PORT} is free...")
    if not ensure_port_free(BOLT_PORT):
        log(f"ERROR: Could not free port {BOLT_PORT}. Cannot start bolt.")
        return False

    try:
        env = os.environ.copy()
        if PUBLIC_BASE_URL:
            env["PUBLIC_BASE_URL"] = PUBLIC_BASE_URL
            log(f"Using PUBLIC_BASE_URL: {PUBLIC_BASE_URL}")

        # Log to file for troubleshooting
        log_file = open('/tmp/bolt_realtime.log', 'a')
        bolt_process = subprocess.Popen(
            [VENV_PYTHON, BOLT_SCRIPT],
            stdout=log_file,
            stderr=subprocess.STDOUT,
            env=env,
            preexec_fn=os.setsid  # Create new process group
        )
        log(f"Bolt started with PID: {bolt_process.pid}")

        # Wait a bit for bolt to start up
        time.sleep(10)

        # Verify it started successfully
        if is_bolt_healthy():
            log("Bolt started successfully and is healthy")
            return True
        else:
            log("WARNING: Bolt started but health check failed")
            return True  # Give it a chance
    except Exception as e:
        log(f"ERROR starting bolt: {e}")
        return False

def stop_bolt():
    """Stop bolt_realtime.py process gracefully"""
    global bolt_process

    if bolt_process:
        log(f"Stopping bolt_realtime.py (PID: {bolt_process.pid})...")
        try:
            # Kill the entire process group
            os.killpg(os.getpgid(bolt_process.pid), signal.SIGTERM)
            bolt_process.wait(timeout=10)
            log("Bolt stopped")
        except Exception as e:
            log(f"Error stopping bolt: {e}")
            try:
                # Force kill if graceful shutdown failed
                os.killpg(os.getpgid(bolt_process.pid), signal.SIGKILL)
            except:
                pass
        bolt_process = None

    # Additional safety: ensure port is actually freed after stopping
    time.sleep(1)
    kill_port_process(BOLT_PORT)

def restart_bolt():
    """Restart bolt_realtime.py"""
    log("=" * 60)
    log("RESTARTING BOLT_REALTIME.PY")
    log("=" * 60)
    stop_bolt()
    time.sleep(RESTART_DELAY)
    return start_bolt()

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    log("\nShutdown signal received. Cleaning up...")
    stop_bolt()
    sys.exit(0)

def main():
    """Main watchdog loop"""
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log("=" * 60)
    log("BOLT WATCHDOG STARTED")
    log(f"Monitoring bolt_realtime.py on port {BOLT_PORT}")
    log(f"Check interval: {CHECK_INTERVAL}s")
    log("=" * 60)

    # Start bolt initially
    if not start_bolt():
        log("ERROR: Failed to start bolt initially. Exiting.")
        sys.exit(1)

    consecutive_failures = 0
    max_consecutive_failures = 3

    # Monitor loop
    while True:
        time.sleep(CHECK_INTERVAL)

        # Check if process is still running
        if bolt_process and bolt_process.poll() is not None:
            log("ERROR: Bolt process died!")
            consecutive_failures += 1
            if restart_bolt():
                consecutive_failures = 0
        # Check if service is healthy
        elif not is_bolt_healthy():
            log("ERROR: Bolt health check failed!")
            consecutive_failures += 1
            if restart_bolt():
                consecutive_failures = 0
        else:
            # All good
            consecutive_failures = 0

        # Check for too many failures
        if consecutive_failures >= max_consecutive_failures:
            log(f"ERROR: {consecutive_failures} consecutive failures. Giving up.")
            stop_bolt()
            sys.exit(1)

if __name__ == '__main__':
    main()
