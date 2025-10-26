#!/usr/bin/env python3
"""
Add a demo business to test the multi-tenant platform
"""
import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

print("=" * 60)
print("ADD DEMO BUSINESS TO BOLT AI GROUP")
print("=" * 60)

# Create Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Test connection
print("\n✅ Testing database connection...")
try:
    result = supabase.table('businesses').select("*").limit(1).execute()
    print(f"✓ Connected! Found {len(result.data)} existing businesses.")
except Exception as e:
    print(f"✗ Connection failed: {e}")
    exit(1)

# Add demo business
print("\n📝 Adding demo business: Joe's Barber Shop...")

demo_business = {
    "business_name": "Joe's Barber Shop",
    "owner_name": "Joe Smith",
    "owner_email": "joe@joesbarber.com",
    "owner_phone": "+15551234567",
    "industry": "barber",
    "agent_name": "Alex",
    "custom_greeting": "Thanks for calling Joe's Barber Shop! How can I help you today?",
    "capabilities": ["appointments", "services", "hours"],
    "business_hours": {
        "monday": "9am-6pm",
        "tuesday": "9am-6pm",
        "wednesday": "9am-6pm",
        "thursday": "9am-6pm",
        "friday": "9am-7pm",
        "saturday": "8am-4pm",
        "sunday": "Closed"
    },
    "services": ["haircut", "beard_trim", "hot_towel_shave", "kids_cut"],
    "google_calendar_id": "scarfaceforward@gmail.com",  # Use your calendar for demo
    "plan": "starter",
    "status": "active",
    "monthly_rate": 99.00
}

try:
    result = supabase.table('businesses').insert(demo_business).execute()
    business_id = result.data[0]['id']
    print(f"✓ Business created! ID: {business_id}")

    # Add phone number for this business
    print(f"\n📞 Adding phone number for Joe's Barber Shop...")

    phone_data = {
        "business_id": business_id,
        "phone_number": "+18555287028",  # Your current Twilio number
        "is_primary": True,
        "purpose": "main"
    }

    phone_result = supabase.table('phone_numbers').insert(phone_data).execute()
    print(f"✓ Phone number added: {phone_data['phone_number']}")

except Exception as e:
    print(f"✗ Error: {e}")
    exit(1)

print("\n" + "=" * 60)
print("✅ DEMO BUSINESS SETUP COMPLETE!")
print("=" * 60)
print(f"\nBusiness: {demo_business['business_name']}")
print(f"Industry: {demo_business['industry']}")
print(f"Phone: {phone_data['phone_number']}")
print(f"Plan: ${demo_business['monthly_rate']}/month")
print("\nNext: Build the multi-tenant platform code!")
print("=" * 60)
