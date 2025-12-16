# 🚀 Edge Function Deployment Guide

## 📋 Adım Adım Kurulum

### 1️⃣ **Supabase SQL Editor'de Database Scriptlerini Çalıştır**

#### a) Session Management Migration

```sql
-- Dosya: database/session_management_migration.sql
-- Supabase Dashboard → SQL Editor → New Query → Paste & Run
```

Bu script:

- ✅ `user_sessions` tablosunu oluşturur veya günceller
- ✅ `session_type`, `last_activity`, `end_reason` kolonlarını ekler
- ✅ İndeksler oluşturur (performans için)
- ✅ `cleanup_expired_sessions()` fonksiyonunu ekler

#### b) RPC Functions

```sql
-- Dosya: database/supabase_rpc_functions.sql
-- Supabase Dashboard → SQL Editor → New Query → Paste & Run
```

Bu script:

- ✅ `verify_pin(p_phone, p_pin)` - PIN doğrulama
- ✅ `register_user_pin(p_user_id, p_phone, p_pin_hash)` - PIN kayıt
- ✅ `check_session(p_phone, p_session_token)` - Session kontrol
- ✅ `user_security` ve `pin_verification_attempts` tablolarını oluşturur
- ✅ RLS (Row Level Security) policies ekler

---

### 2️⃣ **Supabase CLI ile Edge Function Deploy Et**

#### Prerequisites

```bash
# Supabase CLI yükle (henüz yoksa)
npm install -g supabase

# Login yap
supabase login
```

#### Edge Function Deploy

```bash
# Proje klasörüne git
cd "c:\Users\emrah badas\OneDrive\Desktop\pazarglobal mcpp\PazarGlobal_Fronted\pazarglobal-frontend"

# Edge Function deploy et
supabase functions deploy whatsapp-traffic-controller --project-ref YOUR_PROJECT_REF

# Project ref bulmak için:
# Supabase Dashboard → Settings → General → Reference ID
```

**Environment Variables Ayarla (Supabase Dashboard):**

```
Settings → Edge Functions → whatsapp-traffic-controller → Environment Variables

BACKEND_URL=https://pazarglobal-agent-backend-production-4ec8.up.railway.app
```

---

### 3️⃣ **WhatsApp Bridge Environment Variables Güncelle**

Railway Dashboard → pazarglobal-whatsapp-bridge → Variables

**YENİ Variable Ekle:**

```
EDGE_FUNCTION_URL=https://YOUR_PROJECT_REF.supabase.co/functions/v1/whatsapp-traffic-controller
```

**Örnek:**

```
EDGE_FUNCTION_URL=https://abcdefgh.supabase.co/functions/v1/whatsapp-traffic-controller
```

**Mevcut Variables (değişmez):**

- ✅ AGENT_BACKEND_URL
- ✅ TWILIO_ACCOUNT_SID
- ✅ TWILIO_AUTH_TOKEN
- ✅ TWILIO_WHATSAPP_NUMBER
- ✅ SUPABASE_URL
- ✅ SUPABASE_SERVICE_KEY
- ✅ SUPABASE_STORAGE_BUCKET

---

### 4️⃣ **Railway'e Push Et (WhatsApp Bridge)**

```bash
cd "c:\Users\emrah badas\OneDrive\Desktop\pazarglobal mcpp\pazarglobal-whatsapp-bridge"

git add -A
git commit -m "Integrate Edge Function for PIN authentication and session management"
git push
```

Railway otomatik deploy eder.

---

### 5️⃣ **Test Et**

#### Test 1: WhatsApp'tan PIN İste

```
Kullanıcı (WhatsApp): "Araba satmak istiyorum"

Sistem → "🔒 Güvenlik için 4 haneli PIN kodunuzu girin"
```

#### Test 2: PIN Doğrula

```
Kullanıcı: "1234"

Sistem → "✅ Giriş başarılı! 🕐 10 dakika boyunca işlem yapabilirsiniz."
```

#### Test 3: Normal İşlem (Session Aktif)

```
Kullanıcı: "Marka: Toyota, Model: Corolla, Fiyat: 500.000 TL"

Sistem → "✅ İlanınız oluşturuldu..."
```

#### Test 4: Session Timeout (10 dakika sonra)

```
Kullanıcı: "Başka bir ilan eklemek istiyorum"

Sistem → "⏰ Oturumunuz sona erdi (10 dakika). PIN kodunuzu tekrar girin"
```

#### Test 5: İptal

```
Kullanıcı: "iptal"

Sistem → "✅ İşlem iptal edildi. Oturumunuz kapatıldı."
```

---

### 6️⃣ **Monitoring & Logs**

#### Edge Function Logs

```
Supabase Dashboard → Edge Functions → whatsapp-traffic-controller → Logs

Real-time logs görebilirsin:
- 🔒 PIN request
- ✅ Session created
- ⏰ Session expired
- ❌ Invalid PIN
```

#### Railway Logs

```
Railway Dashboard → pazarglobal-whatsapp-bridge → Deployments → Logs

WhatsApp mesajlarını görebilirsin:
- 📱 Incoming WhatsApp message
- 🚦 Calling Edge Function
- ✅ Response received
```

#### Database Logs

```sql
-- Active sessions
SELECT * FROM user_sessions WHERE is_active = true;

-- Failed PIN attempts
SELECT * FROM pin_verification_attempts 
WHERE phone = '+905551234567' 
ORDER BY attempt_time DESC 
LIMIT 10;

-- Session statistics (son 7 gün)
SELECT * FROM session_stats 
WHERE day > now() - INTERVAL '7 days'
ORDER BY day DESC;
```

---

## 🔧 **Troubleshooting**

### Problem 1: "EDGE_FUNCTION_URL not configured"

**Çözüm:** Railway'de `EDGE_FUNCTION_URL` environment variable ekle

### Problem 2: "verify_pin function does not exist"

**Çözüm:** `database/supabase_rpc_functions.sql` script'ini Supabase SQL Editor'de çalıştır

### Problem 3: "user_sessions table does not exist"

**Çözüm:** `database/session_management_migration.sql` script'ini çalıştır

### Problem 4: Edge Function 403 Forbidden

**Çözüm:** Supabase Dashboard → Settings → API → Disable RLS for Edge Functions (veya SUPABASE_SERVICE_KEY doğru mu kontrol et)

### Problem 5: PIN doğrulaması çalışmıyor

**Debug:**

```sql
-- user_security tablosunda kayıt var mı?
SELECT * FROM user_security WHERE phone = '+905551234567';

-- PIN hash doğru mu? (Frontend ile aynı algoritma: SHA-256)
SELECT encode(digest('1234', 'sha256'), 'hex');
```

---

## 📊 **Deployment Checklist**

- [ ] ✅ `session_management_migration.sql` çalıştırıldı
- [ ] ✅ `supabase_rpc_functions.sql` çalıştırıldı
- [ ] ✅ Edge Function deploy edildi (`supabase functions deploy`)
- [ ] ✅ Edge Function URL Railway'e eklendi
- [ ] ✅ WhatsApp Bridge Railway'e push edildi
- [ ] ✅ Test 1-5 başarılı
- [ ] ✅ Logs izleniyor (hata yok)

---

## 🎉 **Sistem Hazır!**

Artık WhatsApp kullanıcıları:

- 🔒 PIN ile güvenli giriş yapabilir
- ⏰ 10 dakikalık oturum alabilir
- ❌ İptal edebilir
- ⏰ Otomatik timeout olabilir

**WebChat kullanıcıları etkilenmez** - Direkt backend'e gider (email/password auth).
