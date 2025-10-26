#!/usr/bin/env python3
"""
Bulk calling script - reads from CSV and places calls
Usage: python bulk_call.py leads.csv
CSV format: name,company,email,phone
"""
import sys, csv, requests, time, os
from dotenv import load_dotenv
load_dotenv()

BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000")

if len(sys.argv) < 2:
    print("Usage: python bulk_call.py leads.csv")
    print("CSV format: name,company,email,phone")
    sys.exit(1)

csv_file = sys.argv[1]
delay = int(sys.argv[2]) if len(sys.argv) > 2 else 5  # seconds between calls

print(f"Reading leads from {csv_file}...")
with open(csv_file, 'r') as f:
    reader = csv.DictReader(f)
    leads = list(reader)

print(f"Found {len(leads)} leads. Starting bulk calling...")

for i, lead in enumerate(leads, 1):
    name = lead.get('name', 'there')
    company = lead.get('company', '')
    email = lead.get('email', '')
    phone = lead.get('phone', '')

    if not phone:
        print(f"[{i}/{len(leads)}] Skipping {name} - no phone number")
        continue

    print(f"[{i}/{len(leads)}] Calling {name} ({company}) at {phone}...")

    try:
        resp = requests.post(f"{BASE_URL}/outbound", params={
            'to': phone,
            'lead_name': name,
            'company': company,
            'email': email
        }, timeout=10)

        if resp.ok:
            data = resp.json()
            print(f"  ✓ Call placed! SID: {data.get('sid')}")
        else:
            print(f"  ✗ Failed: {resp.status_code}")
    except Exception as e:
        print(f"  ✗ Error: {e}")

    if i < len(leads):
        print(f"  Waiting {delay}s before next call...")
        time.sleep(delay)

print(f"\n✓ Bulk calling complete! Placed {len(leads)} calls.")
