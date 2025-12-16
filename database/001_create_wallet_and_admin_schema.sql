-- Migration: Create wallet, payments, transactions, admin actions, illegal reports
-- Run in Supabase SQL editor

/*
 * CREDIT SYSTEM & PRICING (1 credit = ₺0.20)
 * 
 * CREDIT PACKAGES:
 * - Başlangıç: 100kr = ₺20 (₺0.20/kr, no bonus)
 * - Standart: 300kr = ₺50 (₺0.17/kr, 15% bonus)
 * - Pro: 600kr = ₺90 (₺0.15/kr, 25% bonus)
 * - Premium: 1500kr = ₺200 (₺0.13/kr, 35% bonus)
 * 
 * SERVICE COSTS:
 * - Base listing (mandatory): 25kr (₺5) - 30 days active
 * - AI assistant: +10kr (₺2)
 * - AI photo analysis: +5kr per photo (₺1)
 * - AI price suggestion: +3kr (₺0.60)
 * - AI description expansion: +2kr (₺0.40)
 * - Manual listing edit: +2kr (₺0.40)
 * - AI listing edit: +5kr (₺1)
 * - Listing renewal (30 days): +5kr (₺1)
 * 
 * PREMIUM BADGES (can be added AFTER listing creation):
 * - 🥇 Gold Premium: +50kr (₺10) - 7 days featured
 * - 💎 Platinum Premium: +90kr (₺18) - 14 days featured + search boost
 * - 💠 Diamond Premium: +150kr (₺30) - 30 days featured + guaranteed top 5 in search
 * 
 * STORAGE FORMAT:
 * - All credits stored as bigint (multiply by 100 for precision)
 * - Example: 25 credits = 2500 bigint units
 * - Example: 50kr package (₺10) = 5000 bigint units
 */

-- 1) Wallets
CREATE TABLE IF NOT EXISTS wallets (
  user_id uuid PRIMARY KEY REFERENCES profiles(id) ON DELETE CASCADE,
  balance_bigint bigint NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'TRY',
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- 2) Wallet transactions (credit/debit ledger)
CREATE TABLE IF NOT EXISTS wallet_transactions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  amount_bigint bigint NOT NULL,
  kind text NOT NULL CHECK (kind IN ('topup','purchase','refund','admin_adjust')),
  reference text,
  metadata jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_wallet_transactions_user ON wallet_transactions(user_id);

-- 3) Payments (external gateway records + webhook ids)
CREATE TABLE IF NOT EXISTS payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES profiles(id),
  gateway text NOT NULL,
  gateway_payment_id text,
  amount_bigint bigint NOT NULL,
  currency text NOT NULL DEFAULT 'TRY',
  status text NOT NULL DEFAULT 'pending',
  metadata jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_payments_gateway_id ON payments(gateway_payment_id);

-- 4) Admin actions log (audit trail)
CREATE TABLE IF NOT EXISTS admin_actions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  admin_id uuid NOT NULL REFERENCES profiles(id),
  action text NOT NULL,
  target_user uuid,
  target_listing uuid,
  details jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_admin_actions_admin ON admin_actions(admin_id);

-- 5) Illegal reports table
CREATE TABLE IF NOT EXISTS illegal_reports (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reporter_user uuid REFERENCES profiles(id),
  listing_id uuid REFERENCES listings(id) ON DELETE SET NULL,
  reason text,
  evidence jsonb,
  reviewed boolean NOT NULL DEFAULT false,
  reviewed_by uuid REFERENCES profiles(id),
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_illegal_reports_listing ON illegal_reports(listing_id);

-- 6) Add premium and expiration columns to listings if table exists
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'listings') THEN
    ALTER TABLE listings
      ADD COLUMN IF NOT EXISTS is_premium boolean DEFAULT false,
      ADD COLUMN IF NOT EXISTS premium_until timestamptz,
      ADD COLUMN IF NOT EXISTS premium_badge text CHECK (premium_badge IN ('gold', 'platinum', 'diamond')),
      ADD COLUMN IF NOT EXISTS expires_at timestamptz DEFAULT (now() + interval '30 days');
    
    -- Index for querying premium listings
    CREATE INDEX IF NOT EXISTS idx_listings_premium ON listings(is_premium, premium_until) WHERE is_premium = true;
    -- Index for querying active listings
    CREATE INDEX IF NOT EXISTS idx_listings_expires_at ON listings(expires_at);
  END IF;
END$$;

-- 7) Utility: helper to credit wallet (example function)
-- Note: you may want to implement this as a Edge Function or RPC
CREATE OR REPLACE FUNCTION credit_wallet(p_user uuid, p_amount_bigint bigint, p_kind text, p_reference text DEFAULT NULL, p_metadata jsonb DEFAULT '{}'::jsonb)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
  INSERT INTO wallets(user_id, balance_bigint, currency)
    VALUES (p_user, 0, 'TRY')
    ON CONFLICT (user_id) DO NOTHING;

  UPDATE wallets SET balance_bigint = wallets.balance_bigint + p_amount_bigint, updated_at = now() WHERE user_id = p_user;

  INSERT INTO wallet_transactions(user_id, amount_bigint, kind, reference, metadata, created_at)
    VALUES (p_user, p_amount_bigint, p_kind, p_reference, p_metadata, now());
END; $$;

-- 8) Small view for easy balance checks
CREATE OR REPLACE VIEW user_wallets AS
SELECT p.id as user_id, COALESCE(w.balance_bigint, 0) as balance_bigint, COALESCE(w.currency, 'TRY') as currency, w.updated_at
FROM profiles p
LEFT JOIN wallets w ON p.id = w.user_id;

-- End of migration
