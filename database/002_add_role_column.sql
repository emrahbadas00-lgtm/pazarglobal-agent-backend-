-- Add role column to profiles table for admin system
-- Run in Supabase SQL Editor

ALTER TABLE profiles 
  ADD COLUMN IF NOT EXISTS role text DEFAULT 'user' CHECK (role IN ('user', 'admin', 'moderator'));

-- Create index for fast admin lookups
CREATE INDEX IF NOT EXISTS idx_profiles_role ON profiles(role) WHERE role != 'user';

-- Add comment
COMMENT ON COLUMN profiles.role IS 'User role: user (default), admin (full access), moderator (content moderation)';
