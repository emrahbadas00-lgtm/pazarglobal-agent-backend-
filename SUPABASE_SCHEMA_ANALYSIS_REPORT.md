# 🔍 PAZARGLOBAL SUPABASE SCHEMA ANALYSIS REPORT
**Tarih:** 16 Aralık 2025  
**Durum:** ✅ Tüm tablo ilişkileri tutarlı

---

## 📊 TABLO YAPISI ve İLİŞKİLER

### 1. **PROFILES TABLE** (Ana kullanıcı tablosu)
```sql
profiles (
  id UUID PRIMARY KEY,          -- ← USER KIMLIĞI (Ana referans)
  phone TEXT UNIQUE,            -- ← WhatsApp authentication
  full_name TEXT,               -- ← Display name
  email TEXT,
  location TEXT,
  role TEXT,                    -- ← "admin", "user"
  ...
)
```

**Kullanım:**
- `id`: Tüm agent'lar için kullanıcı kimliği
- `phone`: WhatsApp PIN authentication
- `full_name`: Agent'ların gösterdiği isim

---

### 2. **LISTINGS TABLE** (İlan tablosu)
```sql
listings (
  id UUID PRIMARY KEY,          -- ← İLAN NUMARASI (listing_id)
  user_id UUID FK → profiles(id), -- ← İlan sahibi
  title TEXT,
  description TEXT,
  price NUMERIC,
  category TEXT,
  location TEXT,
  condition TEXT,
  metadata JSONB,               -- ← Ürün özellikleri (brand, model, type)
  images TEXT[],
  user_name TEXT,               -- ← KOPYA: profiles.full_name
  user_phone TEXT,              -- ← KOPYA: profiles.phone
  is_premium BOOLEAN,
  premium_badge TEXT,
  expires_at TIMESTAMPTZ,
  ...
)
```

**⚠️ ÖNEMLİ BULGU:**
- `listings` tablosunda **user_name** ve **user_phone** kolonları var!
- Bu kolonlar `profiles` tablosundan **denormalize** edilmiş (kopyalanmış)
- **Avantaj:** Listing sorgusunda JOIN yapılmadan owner bilgisi alınabilir
- **Risk:** profiles.full_name veya profiles.phone değişirse listings.user_name/user_phone güncel olmayabilir!

---

### 3. **USER_SECURITY TABLE** (PIN Authentication)
```sql
user_security (
  id UUID PRIMARY KEY,
  user_id UUID FK → profiles(id),
  phone TEXT UNIQUE,            -- ← profiles.phone ile eşleşmeli
  pin_hash TEXT,
  failed_attempts INT,
  is_locked BOOLEAN,
  blocked_until TIMESTAMPTZ,
  ...
)
```

**İlişki:**
- `user_id` → `profiles.id` (FK)
- `phone` → `profiles.phone` (duplicate for fast lookup)

---

### 4. **USER_SESSIONS TABLE** (10-minute sessions)
```sql
user_sessions (
  id UUID PRIMARY KEY,
  user_id UUID FK → profiles(id),
  phone TEXT,                   -- ← profiles.phone copy
  session_token UUID,
  is_active BOOLEAN,
  expires_at TIMESTAMPTZ,
  ...
)
```

---

### 5. **WALLETS TABLE** (Credit system)
```sql
wallets (
  user_id UUID PRIMARY KEY FK → profiles(id),
  balance_bigint BIGINT,        -- ← Credits (100x multiplier)
  currency TEXT,
  ...
)
```

---

### 6. **WALLET_TRANSACTIONS TABLE** (Credit history)
```sql
wallet_transactions (
  id UUID PRIMARY KEY,          -- ← TRANSACTION ID
  user_id UUID FK → profiles(id),
  amount_bigint BIGINT,
  kind TEXT,                    -- ← "topup", "purchase", "refund", "admin_adjust"
  reference TEXT,               -- ← Optional: listing_id veya başka referans
  metadata JSONB,
  ...
)
```

**⚠️ ÖNEMLİ:**
- `reference` kolonu **TEXT** - listing_id saklanıyor ama FK yok!
- `reference` = `listings.id` (UUID as TEXT) veya başka metin

---

### 7. **PRODUCT_IMAGES TABLE** (Ürün görselleri)
```sql
product_images (
  id UUID PRIMARY KEY,
  listing_id UUID FK → listings(id),
  storage_path TEXT,
  display_order INT,
  is_primary BOOLEAN,
  ...
)
```

---

## 🔐 AGENT KİMLİK DOĞRULAMA FLOW

### WhatsApp → Edge Function → Backend → Agent

1. **WhatsApp Bridge** (Twilio)
   ```
   User: "ilanlarımı göster"
   → Phone: +905412879705
   → Edge Function'a gönder
   ```

2. **Edge Function** (PIN Authentication)
   ```python
   verify_pin(phone="+905412879705", pin="1234")
   → user_security tablosunda PIN check
   → user_sessions'a yeni session yarat
   → Return: {user_id: UUID, session_token: UUID}
   ```

3. **Backend** (/agent/run)
   ```python
   CURRENT_REQUEST_USER_ID = "3ec55e9d-93e8-40c5-8e0e-7dc933da997f"
   CURRENT_REQUEST_USER_PHONE = "+905412879705"
   CURRENT_REQUEST_USER_NAME = "emrah badas"
   ```

4. **Agent Tools** (Database queries)
   ```python
   # UpdateListingAgent → list_user_listings
   list_user_listings(user_id="3ec55e9d-93e8-40c5-8e0e-7dc933da997f")
   
   # Query:
   SELECT * FROM listings WHERE user_id = '3ec55e9d-...' LIMIT 20
   ```

---

## 💡 METADATA vs SPECIFIC COLUMNS

### ❌ Agent user check: METADATA KULLANMIYOR!
```python
# YANLIŞ (Agent böyle yapmıyor):
SELECT * FROM listings WHERE metadata->>'user_name' = 'emrah badas'
```

### ✅ Agent user check: USER_ID ile PROFILES tablosuna bakar
```python
# DOĞRU (Agent bunu yapıyor):
SELECT * FROM listings WHERE user_id = '3ec55e9d-93e8-40c5-8e0e-7dc933da997f'
```

### 📦 listings.metadata: SADECE ÜRÜN ÖZELLİKLERİ
```json
{
  "type": "electronics",
  "brand": "Apple",
  "model": "iPhone 13 Pro",
  "color": "siyah",
  "storage": "256GB"
}
```

**VEYA** (Otomotiv)
```json
{
  "type": "vehicle",
  "brand": "BMW",
  "model": "320i",
  "year": 2018,
  "fuel_type": "benzin",
  "transmission": "otomatik",
  "color": "siyah"
}
```

**VEYA** (Emlak)
```json
{
  "type": "property",
  "property_type": "daire",
  "ad_type": "rent",
  "room_count": "3+1",
  "floor": "4",
  "heating": "doğalgaz"
}
```

---

## 🔍 SEARCH_LISTINGS TOOL KULLANIMI

### Mevcut Durum:
```python
# tools/search_listings.py (Line 210-236)
# ✅ profiles tablosundan user bilgileri çekiliyor:
user_ids = [item["user_id"] for item in data]
profiles_url = f"{SUPABASE_URL}/rest/v1/profiles"
profiles_params = {"id": f"in.({','.join(user_ids)})", "select": "id,full_name,phone"}

# Profile bilgilerini listings'e ekle:
for item in data:
    owner_name = user_obj.get("full_name")
    owner_phone = user_obj.get("phone")
    item["user_name"] = owner_name
    item["user_phone"] = owner_phone
```

### ⚠️ PROBLEM: GEREKSIZ QUERY!
- `listings` tablosunda zaten `user_name` ve `user_phone` kolonları var
- `search_listings` tool profiles'a JOIN yapıyor ama listings'ten direkt alabilir!

### ✅ OPTİMİZASYON ÖNERİSİ:
```python
# Listings'ten direkt al (JOIN'e gerek yok):
SELECT id, title, price, user_name, user_phone FROM listings WHERE ...

# NOT: Eğer profiles.full_name değişirse, listings.user_name güncellenmeli!
```

---

## ⚡ UUID İLİŞKİLERİ - TUTARLILIK KONTROLÜ

### ✅ Doğru Foreign Key İlişkileri:

| Tablo | Kolon | İlişki | Açıklama |
|-------|-------|--------|----------|
| **profiles** | id | PRIMARY KEY | User kimliği |
| **listings** | id | PRIMARY KEY | İlan kimliği |
| **listings** | user_id | FK → profiles(id) | İlan sahibi |
| **user_security** | user_id | FK → profiles(id) | PIN sahibi |
| **user_sessions** | user_id | FK → profiles(id) | Session sahibi |
| **wallets** | user_id | PK & FK → profiles(id) | Cüzdan sahibi |
| **wallet_transactions** | user_id | FK → profiles(id) | Transaction sahibi |
| **product_images** | listing_id | FK → listings(id) | İlana ait görsel |

### ⚠️ Text Reference (FK yok):
| Tablo | Kolon | İlişki | Risk |
|-------|-------|--------|------|
| **wallet_transactions** | reference | TEXT (listing_id as string) | Listing silinirse orphan reference kalır |

---

## 🚨 POTANSİYEL SORUNLAR

### 1. **Denormalize Data Sync Issue**
```sql
-- listings tablosundaki user_name ve user_phone kolonları:
-- ❌ Eğer kullanıcı ismini değiştirirse:
UPDATE profiles SET full_name = 'Yeni İsim' WHERE id = '3ec55e9d-...'

-- ⚠️ listings.user_name hala eski ismi gösterir!
-- ✅ Çözüm: Trigger veya periyodik sync gerekli
```

**Trigger Örneği:**
```sql
CREATE OR REPLACE FUNCTION sync_user_name_to_listings()
RETURNS TRIGGER AS $$
BEGIN
  UPDATE listings 
  SET user_name = NEW.full_name, 
      user_phone = NEW.phone
  WHERE user_id = NEW.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER profiles_update_sync
  AFTER UPDATE OF full_name, phone ON profiles
  FOR EACH ROW
  EXECUTE FUNCTION sync_user_name_to_listings();
```

### 2. **wallet_transactions.reference - Orphan Risk**
```sql
-- Listing silinirse transaction referansı boşta kalır:
DELETE FROM listings WHERE id = 'ec5c21a4-...'

-- ⚠️ wallet_transactions.reference hala 'ec5c21a4-...' içerir
-- ✅ Çözüm 1: reference'ı FK yapma (CASCADE veya SET NULL)
-- ✅ Çözüm 2: reference'ı JSON yapma: {"type": "listing", "id": "..."}
```

### 3. **search_listings - Gereksiz Profiles JOIN**
```python
# ❌ Mevcut: profiles'tan user_name/user_phone çekiyor
# ✅ Optimizasyon: listings.user_name/user_phone direkt kullan
```

---

## ✅ SONUÇ ve ÖNERİLER

### Tablo İlişkileri:
- ✅ Tüm FK ilişkileri doğru ve tutarlı
- ✅ profiles.id → Tüm user referanslarının merkezi
- ✅ listings.id → Tüm ilan referanslarının merkezi
- ⚠️ listings.user_name/user_phone → Denormalize edilmiş, sync gerekli

### Agent Kullanımı:
- ✅ Agent'lar user_id (UUID) ile profiles'a bakıyor
- ✅ Metadata sadece ürün özellikleri için kullanılıyor
- ✅ Kimlik doğrulama: phone → user_id → UUID lookup

### Optimizasyon Fırsatları:
1. **search_listings.py**: profiles JOIN yerine listings.user_name/user_phone kullan
2. **Trigger ekle**: profiles.full_name değişirse listings.user_name güncelle
3. **wallet_transactions.reference**: TEXT yerine FK veya JSONB yap

### Güvenlik:
- ✅ PIN authentication: user_security tablosu ayrı ve güvenli
- ✅ Session management: 10-minute timeout ile kontrollü
- ✅ User isolation: user_id FK ile her data kullanıcıya bağlı

---

## 📋 SON NOT

**Kullanıcı sorularına cevaplar:**
1. **"Tüm tablolar birbiri ile uyumlu mu?"** → ✅ Evet, FK ilişkileri tutarlı
2. **"user_id FK id ilişkisi farklı olabilir mi?"** → ❌ Hayır, her zaman profiles.id'ye işaret eder
3. **"Listing id ile başka tablodaki id UUID ilişkisi?"** → listings.id = PRIMARY KEY (listing numarası), user_id = FK profiles.id (ilan sahibi)
4. **"Agent'lar kullanıcıları neye göre check ediyor?"** → user_id (UUID) ile profiles tablosuna bakıyor, metadata KULLANMIYOR!
5. **"Metadata mı spesifik kolonlar mı?"** → Spesifik kolonlar (user_id FK), metadata sadece ürün özellikleri için!

**Şema tamamen tutarlı ve doğru çalışıyor! 🎉**
