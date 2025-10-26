#!/usr/bin/env python3
"""Test the full calendar flow with actual call data"""
import os, json, sys
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

# Import the functions from ag.py
sys.path.insert(0, '/Users/anthony/aiagent')

print("=" * 60)
print("TESTING FULL CALENDAR FLOW")
print("=" * 60)

# Test 1: parse_appointment_time
print("\n1. Testing parse_appointment_time:")
from ag import parse_appointment_time

test_text = "I just told you that I'd like to speak with Anthony tomorrow at 3 p.m."
result = parse_appointment_time(test_text)
print(f"   Input: {test_text}")
print(f"   Result: {result}")

if not result:
    print("   ✗ FAILED: parse_appointment_time returned None!")
    sys.exit(1)
else:
    print(f"   ✓ Parsed appointment time: {result['datetime']}")

# Test 2: Check calendar service initialization
print("\n2. Checking calendar service:")
from ag import calendar_service

if calendar_service is None:
    print("   ✗ FAILED: calendar_service is None!")
    print("   This means the calendar service failed to initialize in ag.py")
    sys.exit(1)
else:
    print(f"   ✓ calendar_service initialized: {calendar_service}")

# Test 3: create_calendar_event
print("\n3. Testing create_calendar_event:")
from ag import create_calendar_event

lead = {
    'name': 'Anthony',
    'company': 'Test',
    'email': 'scarfaceforward@gmail.com',
    'phone': '18185316200'
}

conversation_summary = "Lead expressed interest in speaking tomorrow at 3 PM."

result = create_calendar_event(lead, result['datetime'], conversation_summary)
print(f"   Result: {result}")

if result['success']:
    print(f"   ✓ Calendar event created successfully!")
    print(f"   Event ID: {result['event_id']}")
    print(f"   Event Link: {result['link']}")
else:
    print(f"   ✗ FAILED: {result['error']}")

print("\n" + "=" * 60)
print("TEST COMPLETE")
print("=" * 60)
