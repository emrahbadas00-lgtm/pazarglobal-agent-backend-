# 🔐 WhatsApp PIN Authentication & Session Management

## 📊 Sistem Mimarisi

```
┌──────────────┐                 ┌─────────────────────┐
│   WhatsApp   │────────────────>│  WhatsApp Bridge    │
│  (Kullanıcı) │                 │    (Railway)        │
└──────────────┘                 └──────────┬──────────┘
                                            │
                                            │ Forward
                                            ↓
                              ┌─────────────────────────┐
                              │   Edge Function         │
                              │  Traffic Controller     │
                              │   (Supabase Edge)       │
                              └────────┬────────────────┘
                                       │
                     ┌─────────────────┼─────────────────┐
                     │                 │                 │
                     ↓                 ↓                 ↓
            ┌────────────┐    ┌──────────────┐  ┌──────────┐
            │ PIN Check  │    │Session Check │  │ 10 Min   │
            │ verify_pin │    │user_sessions │  │ Timer    │
            └────────────┘    └──────────────┘  └──────────┘
                     │                 │                 │
                     └─────────────────┼─────────────────┘
                                       │
                                  ✅ Valid?
                                       │
                                       ↓
                              ┌─────────────────┐
                              │  Agent Backend  │
                              │    (Railway)    │
                              └─────────────────┘
```

---

## 🎯 İş Akışı

### 1️⃣ **İlk Giriş (PIN İsteme)**

```
Kullanıcı → WhatsApp: "Araba satmak istiyorum"
  ↓
WhatsApp Bridge → Edge Function
  ↓
Edge Function: Session var mı kontrol eder
  ✅ Yok → PIN iste
  ↓
Response: "🔒 Güvenlik için 4 haneli PIN kodunuzu girin"
  ↓
WhatsApp Bridge → Kullanıcıya mesaj gönder
```

### 2️⃣ **PIN Doğrulama**

```
Kullanıcı → WhatsApp: "1234"
  ↓
WhatsApp Bridge → Edge Function
  ↓
Edge Function: Mesaj PIN mi? (regex: ^\d{4,6}$)
  ✅ Evet → verify_pin() çağır
  ↓
Supabase RPC: verify_pin(p_phone, p_pin)
  - user_security tablosundan pin_hash çek
  - SHA-256 hash karşılaştır
  - failed_attempts kontrol et (3 hatalı = 15 dk block)
  ↓
  ✅ Doğru → 10 dakikalık session oluştur
  ↓
user_sessions tablosuna kaydet:
  - session_token: UUID
  - expires_at: now() + 10 minutes
  - session_type: 'timed'
  - is_active: true
  ↓
Response: "✅ Giriş başarılı! 10 dakika işlem yapabilirsiniz"
```

### 3️⃣ **Normal İşlem (Session Aktif)**

```
Kullanıcı → WhatsApp: "Toyota Corolla, 500.000 TL"
  ↓
WhatsApp Bridge → Edge Function
  ↓
Edge Function: Session kontrol
  - user_sessions tablosu query
  - is_active = true?
  - expires_at > now()?
  - created_at < 10 minutes ago?
  ↓
  ✅ Geçerli → last_activity güncelle
  ↓
Backend'e forward et:
  POST /chat
  {
    "user_id": "...",
    "phone": "+905551234567",
    "message": "Toyota Corolla, 500.000 TL",
    "session_token": "abc123..."
  }
  ↓
Agent Backend → İşlemi yap
  ↓
Response: "✅ İlanınız oluşturuldu"
  ↓
Edge Function: İşlem tamamlandı mı?
  - intent.includes('complet') → Session kapat
  ↓
WhatsApp Bridge → Kullanıcıya gönder
```

### 4️⃣ **Session Timeout (10 Dakika Sonra)**

```
Kullanıcı → WhatsApp: "Başka bir ilan ekleyeceğim"
  ↓
WhatsApp Bridge → Edge Function
  ↓
Edge Function: Session kontrol
  - created_at = 11 minutes ago
  ❌ 10 dakika geçmiş → TIMEOUT
  ↓
user_sessions güncelle:
  - is_active = false
  - ended_at = now()
  - end_reason = 'timeout'
  ↓
Response: "⏰ Oturumunuz sona erdi (10 dakika). PIN kodunuzu tekrar girin"
```

### 5️⃣ **Kullanıcı İptal Etti**

```
Kullanıcı → WhatsApp: "iptal"
  ↓
WhatsApp Bridge → Edge Function
  ↓
Edge Function: Cancel keywords kontrol
  - ['iptal', 'vazgeç', 'kapat', 'çık', 'cancel', 'stop']
  ✅ Bulundu → Session kapat
  ↓
user_sessions güncelle:
  - is_active = false
  - ended_at = now()
  - end_reason = 'user_cancelled'
  ↓
Response: "✅ İşlem iptal edildi. Oturumunuz kapatıldı"
```

---

## 📁 Dosya Yapısı

```
pazarglobal-agent-backend/
├── database/
│   ├── session_management_migration.sql      # user_sessions tablosu + kolonlar
│   ├── supabase_rpc_functions.sql           # verify_pin, register_user_pin
│   └── optimize_indexes.sql                 # Mevcut (değişmez)
├── tools/
│   └── security_tools.py                    # PIN tools (şimdilik kullanılmıyor, RPC var)
└── EDGE_FUNCTION_DEPLOYMENT.md              # Deployment guide

PazarGlobal_Fronted/pazarglobal-frontend/
└── supabase/
    └── functions/
        ├── whatsapp-traffic-controller/
        │   └── index.ts                     # 🚦 Traffic Police (10 dk timer)
        └── _shared/
            └── cors.ts                      # CORS headers

pazarglobal-whatsapp-bridge/
└── main.py                                  # Edge Function'a forward eder
```

---

## 🗄️ Database Tabloları

### **user_security** (PIN Storage)
```sql
id              | UUID PRIMARY KEY
user_id         | UUID UNIQUE REFERENCES profiles(id)
phone           | TEXT UNIQUE
pin_hash        | TEXT (SHA-256)
failed_attempts | INT DEFAULT 0
is_locked       | BOOLEAN DEFAULT false
blocked_until   | TIMESTAMP (3 hatalı = 15 dk block)
last_login      | TIMESTAMP
created_at      | TIMESTAMP
updated_at      | TIMESTAMP
```

### **user_sessions** (Session Management)
```sql
id              | UUID PRIMARY KEY
user_id         | UUID REFERENCES profiles(id)
phone           | TEXT
session_token   | UUID UNIQUE
is_active       | BOOLEAN DEFAULT true
expires_at      | TIMESTAMP (10 dakika sonra)
created_at      | TIMESTAMP
ended_at        | TIMESTAMP
session_type    | TEXT ('timed' | 'event-based')
last_activity   | TIMESTAMP
end_reason      | TEXT ('timeout' | 'user_cancelled' | 'operation_completed')
ip_address      | TEXT
user_agent      | TEXT
```

### **pin_verification_attempts** (Audit Log)
```sql
id              | UUID PRIMARY KEY
phone           | TEXT
attempt_time    | TIMESTAMP DEFAULT now()
success         | BOOLEAN
ip_address      | TEXT
user_agent      | TEXT
```

---

## 🔑 Environment Variables

### **Supabase Edge Function**
```bash
BACKEND_URL=https://pazarglobal-agent-backend-production-4ec8.up.railway.app
```

### **WhatsApp Bridge (Railway)**
```bash
EDGE_FUNCTION_URL=https://YOUR_PROJECT.supabase.co/functions/v1/whatsapp-traffic-controller
AGENT_BACKEND_URL=https://pazarglobal-agent-backend-production-4ec8.up.railway.app
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_SERVICE_KEY=eyJ...
TWILIO_ACCOUNT_SID=AC...
TWILIO_AUTH_TOKEN=...
TWILIO_WHATSAPP_NUMBER=+14155238886
```

### **Agent Backend (Railway)**
```bash
# Session kontrolü YOK - Edge Function hallediyor
OPENAI_API_KEY=sk-...
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
```

---

## 🔐 Güvenlik Özellikleri

### 1. **Brute Force Protection**
```
3 hatalı PIN denemesi → 15 dakika block
pin_verification_attempts tablosunda log tutuluyor
```

### 2. **Session Timeout**
```
10 dakikalık timer (user-friendly, öngörülebilir)
Otomatik expire: expires_at > now()
```

### 3. **Rate Limiting** (Middleware - değişmez)
```
100 request / 60 saniye
SQL Injection & XSS koruması
Security headers
```

### 4. **IP Binding** (Opsiyonel - ileride)
```
Session oluştururken IP kaydedilir
Farklı IP'den gelen request reddedilebilir
```

### 5. **RLS Policies**
```
Kullanıcılar sadece kendi security settings'lerini görebilir
Sadece admin pin_verification_attempts görebilir
```

---

## 📊 Monitoring Queries

### Active Sessions
```sql
SELECT 
  phone,
  session_token,
  created_at,
  expires_at,
  EXTRACT(EPOCH FROM (expires_at - now())) / 60 as minutes_remaining
FROM user_sessions
WHERE is_active = true
ORDER BY created_at DESC;
```

### Failed PIN Attempts (Son 24 saat)
```sql
SELECT 
  phone,
  COUNT(*) as attempt_count,
  MAX(attempt_time) as last_attempt,
  SUM(CASE WHEN success THEN 1 ELSE 0 END) as successful,
  SUM(CASE WHEN NOT success THEN 1 ELSE 0 END) as failed
FROM pin_verification_attempts
WHERE attempt_time > now() - INTERVAL '24 hours'
GROUP BY phone
ORDER BY failed DESC;
```

### Session Statistics
```sql
SELECT * FROM session_stats 
WHERE day > now() - INTERVAL '7 days'
ORDER BY day DESC;
```

### Locked Accounts
```sql
SELECT 
  phone,
  failed_attempts,
  blocked_until,
  EXTRACT(EPOCH FROM (blocked_until - now())) / 60 as minutes_remaining
FROM user_security
WHERE is_locked = true
ORDER BY blocked_until DESC;
```

---

## ✅ Test Checklist

- [ ] PIN oluşturma (Frontend Profil Ayarları)
- [ ] PIN ile ilk giriş (WhatsApp)
- [ ] Hatalı PIN (3 deneme → block)
- [ ] Normal işlem (session aktif)
- [ ] Session timeout (10 dakika sonra)
- [ ] İptal komutu ("iptal")
- [ ] İşlem tamamlandığında session kapanması
- [ ] WebChat etkilenmemesi (bypass)
- [ ] Edge Function logs görüntüleme
- [ ] Database queries çalışması

---

## 🎉 Avantajlar

✅ **Güvenlik:** PIN + 10 dk timer + brute force protection  
✅ **Hız:** Edge Function DB'ye yakın (düşük latency)  
✅ **Maliyet:** Supabase Pro'da dahil (ekstra ücret yok)  
✅ **Kullanıcı Dostu:** 10 dk öngörülebilir  
✅ **Bakım:** Tek kontrol noktası (Edge Function)  
✅ **Scalable:** Serverless auto-scale  
✅ **WebChat Uyumlu:** Bypass ile etkilenmez  

🚀 **Production Ready!**
