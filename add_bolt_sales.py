#!/usr/bin/env python3
"""Add Bolt AI Group sales business"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_ROLE_KEY"))

# Add Bolt AI Group as sales business
bolt_business = {
    "business_name": "Bolt AI Group",
    "owner_name": "Anthony Vazquez",
    "owner_email": "scarfaceforward@gmail.com",
    "owner_phone": "+18185316200",
    "industry": "sales",  # Special industry for sales
    "agent_name": "Bolt",
    "plan": "internal",
    "status": "active"
}

result = supabase.table('businesses').insert(bolt_business).execute()
business_id = result.data[0]['id']

# Add phone number
phone_data = {
    "business_id": business_id,
    "phone_number": "+18555287028",
    "is_primary": True,
    "purpose": "sales"
}

# Delete old Joe's Barber Shop mapping first
supabase.table('phone_numbers').delete().eq('phone_number', '+18555287028').execute()

# Add new mapping
supabase.table('phone_numbers').insert(phone_data).execute()

print(f"✓ Bolt AI Group added! Business ID: {business_id}")
print(f"✓ Phone +18555287028 now routes to Bolt AI Group sales")
