#!/usr/bin/env python3
"""
Failsafe Monitor - Detects when bolt_watchdog fails to restart bolt_realtime.py
If bolt is down for >2 minutes, this restarts the watchdog itself
"""
import subprocess
import time
import requests
import signal
import sys
from datetime import datetime

BOLT_PORT = 5000
HEALTH_CHECK_URL = f"http://localhost:{BOLT_PORT}/"
CHECK_INTERVAL = 30  # Check every 30 seconds
MAX_DOWNTIME = 60    # If down for 60+ seconds, intervene
LAUNCHD_LABEL = "com.boltai.realtime"

downtime_start = None

def log(message):
    """Log with timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[FAILSAFE] [{timestamp}] {message}", flush=True)

def is_bolt_healthy():
    """Check if bolt_realtime.py is responding"""
    try:
        response = requests.get(HEALTH_CHECK_URL, timeout=5)
        return response.status_code == 200
    except Exception:
        return False

def restart_bolt():
    """Restart bolt_realtime via launchctl"""
    log("CRITICAL: Bolt has been down too long. Restarting via launchd...")
    try:
        # Unload and reload to force restart
        subprocess.run(
            ['launchctl', 'kickstart', '-k', f'gui/{subprocess.getoutput("id -u")}/{LAUNCHD_LABEL}'],
            timeout=30,
            check=True,
            capture_output=True
        )
        log("Bolt restarted successfully via launchd")
        return True
    except Exception as e:
        log(f"ERROR restarting bolt: {e}")
        return False

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    log("Shutdown signal received. Exiting...")
    sys.exit(0)

def main():
    """Main failsafe monitoring loop"""
    global downtime_start

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    log("=" * 60)
    log("FAILSAFE MONITOR STARTED")
    log(f"Will intervene if bolt is down for >{MAX_DOWNTIME}s")
    log(f"Check interval: {CHECK_INTERVAL}s")
    log("=" * 60)

    while True:
        time.sleep(CHECK_INTERVAL)

        if is_bolt_healthy():
            # Bolt is healthy, reset downtime tracker
            if downtime_start:
                log("Bolt recovered. Resetting downtime tracker.")
                downtime_start = None
            else:
                log("Bolt is healthy.")
        else:
            # Bolt is down
            if not downtime_start:
                # First detection of downtime
                downtime_start = time.time()
                log(f"WARNING: Bolt is down. Downtime started.")
            else:
                # Calculate how long it's been down
                downtime_duration = time.time() - downtime_start
                log(f"WARNING: Bolt still down. Downtime: {int(downtime_duration)}s")

                # If down too long, intervene
                if downtime_duration >= MAX_DOWNTIME:
                    log(f"CRITICAL: Bolt down for {int(downtime_duration)}s (max: {MAX_DOWNTIME}s)")
                    log("Restarting bolt via launchd...")

                    if restart_bolt():
                        # Wait for bolt to restart
                        log("Waiting 30s for bolt to restart...")
                        time.sleep(30)

                        if is_bolt_healthy():
                            log("SUCCESS: Bolt is back online")
                            downtime_start = None
                        else:
                            log("FAILURE: Bolt still down after watchdog restart")
                            # Reset timer to try again
                            downtime_start = time.time()
                    else:
                        log("FAILURE: Could not restart watchdog")
                        downtime_start = time.time()

if __name__ == '__main__':
    main()
