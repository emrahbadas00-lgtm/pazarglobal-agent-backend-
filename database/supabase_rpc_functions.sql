-- ═══════════════════════════════════════════════════════════════════
-- Supabase RPC Functions for PIN Authentication & Session Management
-- Bu fonksiyonlar Edge Function tarafından çağrılır
-- ═══════════════════════════════════════════════════════════════════

-- SHA-256 için gerekli
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ───────────────────────────────────────────────────────────────────
-- 0. Eski fonksiyonları sil (eğer varsa)
-- ───────────────────────────────────────────────────────────────────

DROP FUNCTION IF EXISTS verify_pin(TEXT, TEXT);
DROP FUNCTION IF EXISTS register_user_pin(UUID, TEXT, TEXT);
DROP FUNCTION IF EXISTS check_session(TEXT, UUID);
DROP FUNCTION IF EXISTS reset_user_pin(UUID);

-- ───────────────────────────────────────────────────────────────────
-- 1. verify_pin - PIN doğrulama ve brute force koruması
-- ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION verify_pin(
  p_phone TEXT,
  p_pin TEXT
)
RETURNS TABLE (
  success BOOLEAN,
  user_id UUID,
  message TEXT,
  blocked_until TIMESTAMP WITH TIME ZONE
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_security RECORD;
  v_pin_hash TEXT;
  v_failed_attempts INT;
  v_is_locked BOOLEAN;
  v_blocked_until TIMESTAMP WITH TIME ZONE;
BEGIN
  -- user_security tablosundan kullanıcı bilgilerini al
  SELECT * INTO v_user_security
  FROM user_security
  WHERE phone = p_phone;

  -- Kullanıcı bulunamadı
  IF NOT FOUND THEN
    RETURN QUERY SELECT 
      false, 
      NULL::UUID, 
      '❌ Bu telefon numarası kayıtlı değil. Lütfen önce profil ayarlarından PIN oluşturun.'::TEXT,
      NULL::TIMESTAMP WITH TIME ZONE;
    RETURN;
  END IF;

  v_failed_attempts := COALESCE(v_user_security.failed_attempts, 0);
  v_is_locked := COALESCE(v_user_security.is_locked, false);
  v_blocked_until := v_user_security.blocked_until;

  -- Hesap kilitli mi kontrol et
  IF v_is_locked AND v_blocked_until IS NOT NULL AND v_blocked_until > now() THEN
    RETURN QUERY SELECT 
      false, 
      NULL::UUID,
      '🔒 Çok fazla hatalı deneme. ' || 
      EXTRACT(EPOCH FROM (v_blocked_until - now()))::INT / 60 || 
      ' dakika sonra tekrar deneyin.'::TEXT,
      v_blocked_until;
    RETURN;
  END IF;

  -- Kilit süresi dolmuşsa kilidi aç
  IF v_is_locked AND (v_blocked_until IS NULL OR v_blocked_until <= now()) THEN
    UPDATE user_security 
    SET is_locked = false, 
        failed_attempts = 0, 
        blocked_until = NULL
    WHERE phone = p_phone;
    v_failed_attempts := 0;
    v_is_locked := false;
  END IF;

  -- PIN'i hash'le (SHA-256 browser'dan geliyor, burada da aynı algoritma)
  v_pin_hash := encode(digest(p_pin, 'sha256'), 'hex');

  -- PIN doğrula
  IF v_pin_hash = v_user_security.pin_hash THEN
    -- Başarılı giriş
    UPDATE user_security
    SET failed_attempts = 0,
        is_locked = false,
        blocked_until = NULL,
        last_login_at = now(),
        last_login_ip = 'edge-function'
    WHERE phone = p_phone;

    -- Attempt log kaydet
    INSERT INTO pin_verification_attempts (phone, success, ip_address)
    VALUES (p_phone, true, 'edge-function');

    RETURN QUERY SELECT 
      true, 
      v_user_security.user_id,
      '✅ Giriş başarılı'::TEXT,
      NULL::TIMESTAMP WITH TIME ZONE;
    RETURN;
  ELSE
    -- Hatalı PIN
    v_failed_attempts := v_failed_attempts + 1;

    -- 3 veya daha fazla hatalı deneme → 15 dakika kilitle
    IF v_failed_attempts >= 3 THEN
      v_blocked_until := now() + INTERVAL '15 minutes';
      v_is_locked := true;

      UPDATE user_security
      SET failed_attempts = v_failed_attempts,
          is_locked = true,
          blocked_until = v_blocked_until
      WHERE phone = p_phone;

      -- Attempt log kaydet
      INSERT INTO pin_verification_attempts (phone, success, ip_address)
      VALUES (p_phone, false, 'edge-function');

      RETURN QUERY SELECT 
        false, 
        NULL::UUID,
        '🔒 Çok fazla hatalı deneme. 15 dakika bekleyin.'::TEXT,
        v_blocked_until;
      RETURN;
    ELSE
      -- Henüz kilitlenme yok, sadece sayacı artır
      UPDATE user_security
      SET failed_attempts = v_failed_attempts
      WHERE phone = p_phone;

      -- Attempt log kaydet
      INSERT INTO pin_verification_attempts (phone, success, ip_address)
      VALUES (p_phone, false, 'edge-function');

      RETURN QUERY SELECT 
        false, 
        NULL::UUID,
        ('❌ Hatalı PIN. ' || (3 - v_failed_attempts)::TEXT || ' deneme hakkınız kaldı.')::TEXT,
        NULL::TIMESTAMP WITH TIME ZONE;
      RETURN;
    END IF;
  END IF;
END;
$$;

COMMENT ON FUNCTION verify_pin IS 'PIN doğrulama ve brute force koruması (3 hatalı = 15 dk kilit)';

-- ───────────────────────────────────────────────────────────────────
-- 2. register_user_pin - Yeni PIN kaydı (frontend'den çağrılır)
-- ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION register_user_pin(
  p_user_id UUID,
  p_phone TEXT,
  p_pin_hash TEXT
)
RETURNS TABLE (
  success BOOLEAN,
  message TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_id ALIAS FOR p_user_id;
  v_phone   ALIAS FOR p_phone;
  v_pin     ALIAS FOR p_pin_hash;
BEGIN
  -- Güvenlik: sadece giriş yapmış kullanıcı kendi kaydını güncelleyebilir
  IF auth.uid() IS NULL OR auth.uid() <> v_user_id THEN
    RETURN QUERY SELECT false, '❌ Yetkisiz işlem'::TEXT;
    RETURN;
  END IF;

  -- Aynı telefon başka bir kullanıcıda kayıtlıysa temizle (unique constraint hatasını önler)
  DELETE FROM user_security
  WHERE phone = v_phone
    AND user_id <> v_user_id;

  -- profiles.phone unique olduğu için: aynı telefon başka profilde varsa temizle
  UPDATE profiles
  SET phone = NULL
  WHERE phone = v_phone
    AND id <> v_user_id;

  -- user_security tablosuna upsert
  INSERT INTO user_security (user_id, phone, pin_hash, failed_attempts, is_locked)
  VALUES (v_user_id, v_phone, v_pin, 0, false)
  ON CONFLICT (user_id) 
  DO UPDATE SET 
    phone = EXCLUDED.phone,
    pin_hash = EXCLUDED.pin_hash,
    failed_attempts = 0,
    is_locked = false,
    blocked_until = NULL,
    updated_at = now();

  -- profiles tablosunda da phone güncelle
  UPDATE profiles
  SET phone = v_phone
  WHERE id = v_user_id;

  RETURN QUERY SELECT true, '✅ PIN başarıyla kaydedildi'::TEXT;
EXCEPTION WHEN OTHERS THEN
  RETURN QUERY SELECT false, ('❌ Hata: ' || SQLERRM)::TEXT;
END;
$$;

COMMENT ON FUNCTION register_user_pin IS 'Yeni PIN kaydı veya güncelleme (frontend profil ayarlarından)';

-- ───────────────────────────────────────────────────────────────────
-- 2b. reset_user_pin - PIN sıfırlama (frontend'den çağrılır)
-- ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION reset_user_pin(
  p_user_id UUID
)
RETURNS TABLE (
  success BOOLEAN,
  message TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_user_id ALIAS FOR p_user_id;
BEGIN
  -- Güvenlik: sadece giriş yapmış kullanıcı kendi PIN'ini sıfırlayabilir
  IF auth.uid() IS NULL OR auth.uid() <> v_user_id THEN
    RETURN QUERY SELECT false, '❌ Yetkisiz işlem'::TEXT;
    RETURN;
  END IF;

  DELETE FROM user_security
  WHERE user_id = v_user_id;

  -- Profildeki telefon bilgisini temizle (opsiyonel ama tutarlı)
  UPDATE profiles
  SET phone = NULL
  WHERE id = v_user_id;

  RETURN QUERY SELECT true, '✅ PIN sıfırlandı. Yeni PIN oluşturabilirsiniz.'::TEXT;
EXCEPTION WHEN OTHERS THEN
  RETURN QUERY SELECT false, ('❌ Hata: ' || SQLERRM)::TEXT;
END;
$$;

COMMENT ON FUNCTION reset_user_pin IS 'Frontend profil ayarlarından çağrılır - WhatsApp PIN sıfırlama';

-- ───────────────────────────────────────────────────────────────────
-- 3. check_session - Session geçerliliği kontrolü (opsiyonel, edge function'da da yapılıyor)
-- ───────────────────────────────────────────────────────────────────

CREATE OR REPLACE FUNCTION check_session(
  p_phone TEXT,
  p_session_token UUID
)
RETURNS TABLE (
  valid BOOLEAN,
  user_id UUID,
  message TEXT
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
  v_session RECORD;
BEGIN
  SELECT * INTO v_session
  FROM user_sessions
  WHERE phone = p_phone
    AND session_token = p_session_token
    AND is_active = true
    AND expires_at > now();

  IF FOUND THEN
    RETURN QUERY SELECT true, v_session.user_id, '✅ Session geçerli'::TEXT;
  ELSE
    RETURN QUERY SELECT false, NULL::UUID, '❌ Session geçersiz veya süresi dolmuş'::TEXT;
  END IF;
END;
$$;

COMMENT ON FUNCTION check_session IS 'Session token geçerliliği kontrolü';

-- ───────────────────────────────────────────────────────────────────
-- 4. Tablolar oluştur (yoksa)
-- ───────────────────────────────────────────────────────────────────

-- user_security tablosu
CREATE TABLE IF NOT EXISTS user_security (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES profiles(id) ON DELETE CASCADE,
  phone TEXT NOT NULL UNIQUE,
  pin_hash TEXT NOT NULL,
  session_token TEXT,
  session_expires_at TIMESTAMP WITH TIME ZONE,
  failed_attempts INT DEFAULT 0,
  blocked_until TIMESTAMP WITH TIME ZONE,
  last_login_at TIMESTAMP WITH TIME ZONE,
  last_login_ip TEXT,
  device_fingerprint TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
  is_locked BOOLEAN DEFAULT false
);

CREATE INDEX IF NOT EXISTS idx_user_security_phone ON user_security(phone);
CREATE INDEX IF NOT EXISTS idx_user_security_user_id ON user_security(user_id);
CREATE INDEX IF NOT EXISTS idx_user_security_session_token ON user_security(session_token);
CREATE INDEX IF NOT EXISTS idx_user_security_session_expires_at ON user_security(session_expires_at);

-- update_updated_at_column() fonksiyonu varsa trigger kur (rerunnable)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_proc WHERE proname = 'update_updated_at_column') THEN
    EXECUTE 'DROP TRIGGER IF EXISTS update_user_security_updated_at ON public.user_security';
    EXECUTE 'CREATE TRIGGER update_user_security_updated_at BEFORE UPDATE ON public.user_security FOR EACH ROW EXECUTE FUNCTION update_updated_at_column()';
  END IF;
END
$$;

COMMENT ON TABLE user_security IS 'WhatsApp PIN güvenlik ayarları';
COMMENT ON COLUMN user_security.pin_hash IS 'SHA-256 hash (frontend tarafından oluşturuluyor)';

-- pin_verification_attempts tablosu
CREATE TABLE IF NOT EXISTS pin_verification_attempts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT NOT NULL,
  attempt_time TIMESTAMP WITH TIME ZONE DEFAULT now(),
  success BOOLEAN NOT NULL,
  ip_address TEXT,
  user_agent TEXT
);

CREATE INDEX IF NOT EXISTS idx_pin_attempts_phone ON pin_verification_attempts(phone, attempt_time DESC);

COMMENT ON TABLE pin_verification_attempts IS 'PIN doğrulama denemelerinin audit logu';

-- ───────────────────────────────────────────────────────────────────
-- 5. RLS Policies (Row Level Security)
-- ───────────────────────────────────────────────────────────────────

-- user_security için RLS
ALTER TABLE user_security ENABLE ROW LEVEL SECURITY;

-- Script tekrar çalıştırılabilir olsun diye mevcut policy'leri temizle
DROP POLICY IF EXISTS "Users can read own security settings" ON user_security;
DROP POLICY IF EXISTS "Users can update own security settings" ON user_security;

CREATE POLICY "Users can read own security settings"
  ON user_security FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can update own security settings"
  ON user_security FOR UPDATE
  USING (auth.uid() = user_id);

-- user_sessions için RLS
ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;

-- Script tekrar çalıştırılabilir olsun diye mevcut policy'yi temizle
DROP POLICY IF EXISTS "Users can read own sessions" ON user_sessions;

CREATE POLICY "Users can read own sessions"
  ON user_sessions FOR SELECT
  USING (auth.uid() = user_id);

-- pin_verification_attempts için RLS (kimse okuyamaz, sadece sistem yazabilir)
ALTER TABLE pin_verification_attempts ENABLE ROW LEVEL SECURITY;

-- No read policy - audit logs are write-only for security
-- To view logs, use Supabase Dashboard with service_role access

-- ───────────────────────────────────────────────────────────────────
-- 6. Test Queries (Manuel test için)
-- ───────────────────────────────────────────────────────────────────

-- Test PIN verification
-- SELECT * FROM verify_pin('+905551234567', '1234');

-- Test session check
-- SELECT * FROM check_session('+905551234567', 'your-session-token-uuid');

-- Test PIN registration
-- SELECT * FROM register_user_pin('user-uuid', '+905551234567', 'sha256-hash');

-- Failed attempts kontrol
-- SELECT * FROM pin_verification_attempts WHERE phone = '+905551234567' ORDER BY attempt_time DESC LIMIT 10;

-- Active sessions kontrol
-- SELECT * FROM user_sessions WHERE is_active = true;

COMMENT ON FUNCTION verify_pin IS 'Edge Function tarafından çağrılır - WhatsApp PIN doğrulama';
COMMENT ON FUNCTION check_session IS 'Opsiyonel session kontrolü - Edge Function zaten yapıyor';
COMMENT ON FUNCTION register_user_pin IS 'Frontend profil ayarlarından çağrılır';
