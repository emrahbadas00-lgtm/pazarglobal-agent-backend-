-- ═══════════════════════════════════════════════════════════════════
-- WhatsApp Traffic Controller - Database Migration
-- Adds columns for 10-minute timed sessions
-- ═══════════════════════════════════════════════════════════════════

-- 1. user_sessions tablosunu güncelle (varsa)
-- Yoksa oluştur

CREATE TABLE IF NOT EXISTS user_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  phone TEXT NOT NULL,
  session_token UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
  is_active BOOLEAN NOT NULL DEFAULT true,
  expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
  created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now(),
  ended_at TIMESTAMP WITH TIME ZONE,
  
  -- Yeni kolonlar (Edge Function için)
  session_type TEXT DEFAULT 'timed' CHECK (session_type IN ('timed', 'event-based')),
  last_activity TIMESTAMP WITH TIME ZONE DEFAULT now(),
  end_reason TEXT CHECK (end_reason IN ('timeout', 'user_cancelled', 'operation_completed', 'manual')),
  ip_address TEXT,
  user_agent TEXT
);

-- 2. Mevcut tabloda kolonlar yoksa ekle
DO $$ 
BEGIN
  -- session_type kolonu yoksa ekle
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name = 'user_sessions' AND column_name = 'session_type'
  ) THEN
    ALTER TABLE user_sessions 
    ADD COLUMN session_type TEXT DEFAULT 'timed' 
    CHECK (session_type IN ('timed', 'event-based'));
  END IF;

  -- last_activity kolonu yoksa ekle
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name = 'user_sessions' AND column_name = 'last_activity'
  ) THEN
    ALTER TABLE user_sessions 
    ADD COLUMN last_activity TIMESTAMP WITH TIME ZONE DEFAULT now();
  END IF;

  -- end_reason kolonu yoksa ekle
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name = 'user_sessions' AND column_name = 'end_reason'
  ) THEN
    ALTER TABLE user_sessions 
    ADD COLUMN end_reason TEXT 
    CHECK (end_reason IN ('timeout', 'user_cancelled', 'operation_completed', 'manual'));
  END IF;

  -- ip_address kolonu yoksa ekle
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name = 'user_sessions' AND column_name = 'ip_address'
  ) THEN
    ALTER TABLE user_sessions 
    ADD COLUMN ip_address TEXT;
  END IF;

  -- user_agent kolonu yoksa ekle
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name = 'user_sessions' AND column_name = 'user_agent'
  ) THEN
    ALTER TABLE user_sessions 
    ADD COLUMN user_agent TEXT;
  END IF;
END $$;

-- 3. İndeksler (performans için)
CREATE INDEX IF NOT EXISTS idx_user_sessions_phone_active 
  ON user_sessions(phone, is_active) 
  WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_user_sessions_expires_at 
  ON user_sessions(expires_at) 
  WHERE is_active = true;

CREATE INDEX IF NOT EXISTS idx_user_sessions_last_activity 
  ON user_sessions(last_activity);

-- 4. Otomatik cleanup function (opsiyonel - expired sessions'ları temizler)
CREATE OR REPLACE FUNCTION cleanup_expired_sessions()
RETURNS void
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  UPDATE user_sessions
  SET 
    is_active = false,
    ended_at = now(),
    end_reason = 'timeout'
  WHERE 
    is_active = true 
    AND expires_at < now();
END;
$$;

-- 5. Cleanup için scheduled job (Supabase cron extension gerekli)
-- Supabase Dashboard'dan manuel olarak çalıştırılabilir:
-- SELECT cron.schedule('cleanup-expired-sessions', '*/5 * * * *', 'SELECT cleanup_expired_sessions()');

COMMENT ON TABLE user_sessions IS 'WhatsApp ve WebChat kullanıcı session yönetimi';
COMMENT ON COLUMN user_sessions.session_type IS 'timed: 10 dakikalık timer, event-based: işlem bazlı';
COMMENT ON COLUMN user_sessions.last_activity IS 'Son aktivite zamanı (mesaj gönderme)';
COMMENT ON COLUMN user_sessions.end_reason IS 'Session neden kapandı: timeout, user_cancelled, operation_completed';
COMMENT ON COLUMN user_sessions.ip_address IS 'Session oluşturan IP (güvenlik için)';

-- 6. İstatistik için view (opsiyonel)
CREATE OR REPLACE VIEW session_stats AS
SELECT 
  date_trunc('day', created_at) as day,
  session_type,
  end_reason,
  COUNT(*) as session_count,
  AVG(EXTRACT(EPOCH FROM (COALESCE(ended_at, now()) - created_at)) / 60) as avg_duration_minutes
FROM user_sessions
WHERE created_at > now() - INTERVAL '30 days'
GROUP BY date_trunc('day', created_at), session_type, end_reason
ORDER BY day DESC;

COMMENT ON VIEW session_stats IS 'Son 30 günün session istatistikleri';
