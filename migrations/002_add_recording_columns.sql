-- Migration: Add recording columns to calls table
-- Run this in Supabase SQL editor: https://supabase.com/dashboard/project/owffvdmmvcnbnjaprqis/sql

-- Add recording_url column for storing Twilio recording URLs
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_url TEXT;

-- Add recording_sid column for Twilio recording ID
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_sid TEXT;

-- Add recording_duration column (in seconds)
ALTER TABLE calls ADD COLUMN IF NOT EXISTS recording_duration INTEGER;

-- Add call_transcripts table if it doesn't exist
CREATE TABLE IF NOT EXISTS call_transcripts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    call_id UUID REFERENCES calls(id) ON DELETE CASCADE,
    role TEXT NOT NULL, -- 'user' or 'assistant'
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create index for faster transcript lookups
CREATE INDEX IF NOT EXISTS idx_call_transcripts_call_id ON call_transcripts(call_id);

-- Verify columns were added
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'calls'
AND column_name IN ('recording_url', 'recording_sid', 'recording_duration');
