# 🤖 PazarGlobal Agent Backend

**AI-Powered Multi-Agent Listing Platform - Core Backend**

Modern AI destekli ilan platformu PazarGlobal'in ana backend servisi. OpenAI Agents SDK kullanarak çok-ajanlı (multi-agent) mimari ile kullanıcı isteklerini işler, ilanları yönetir ve akıllı sohbet deneyimi sağlar.

> 🚧 Deneme: Bu sürümde WhatsApp ilan akışı için guardrails-first + deterministik FSM (draft → preview → publish) kurgusu aktif. Geri dönüş için son stabil commit: `deb267473299ab11cd33ac32c3b1bf6ec031cba8`.
>
> 📎 **Operasyon Notu (22 Dec 2025):** Router/List/Publish ajanları tam `gpt-4o` ile bırakıldı, diğer ajanlar `gpt-4o-mini`'ye küçültüldü. Herhangi bir performans/hata durumunda _bir önceki repo durumuna_ geri dönerek bu değişikliği geri alın.

## 📌 Son Değişiklik Özeti (18 Dec 2025)
- Aktif taslaklar Supabase `active_drafts` tablosuna kalıcı yazılıyor; draft state, images, vision snapshot saklanıyor.
- FSM yayın hataları artık detaylı döndürülüyor; condition normalizasyonu (new/used/refurbished) eklendi.
- Lokasyon varsayılan Türkiye, stok varsayılan 1, metadata daima `type` içeriyor; vision attribute’ları metadata’ya birleşiyor.
- Fotoğraflı akış test edildi (Citroën SUV örneği): vision brand/color/type eklendi, kategori düzeltmesi yapıldı, kredi kesimi çalıştı.
- SmallTalkAgent sandboxlandı: intent/tool/state karar vermiyor, sadece örnek komut gösteriyor ("iphone 14 arıyorum", "ilan ver", "onayla", "daha fazla ilan göster", "1 nolu ilanı göster" vb.).

---

## 📋 İçindekiler

- [Mimari Genel Bakış](#-mimari-genel-bakış)
- [Agent Yapısı](#-agent-yapısı)
- [Tools (Araçlar)](#-tools-araçlar)
- [API Endpoints](#-api-endpoints)
- [Kurulum](#-kurulum)
- [Railway Deployment](#-railway-deployment)
- [Environment Variables](#-environment-variables)
- [Workflow Detayları](#-workflow-detayları)
- [Güvenlik](#-güvenlik)
- [Gelecek Özellikler](#-gelecek-özellikler)
- [Sorun Giderme](#-sorun-giderme)

---

## 🏗️ Mimari Genel Bakış

```
┌─────────────────────────────────────────────────────────────┐
│                  PazarGlobal Agent Backend                  │
│                     (Ana Çekirdek)                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  WhatsApp Bridge ──┐                                        │
│                    ├──► POST /agent/run ──► Workflow       │
│  Web Frontend ─────┘                        Runner         │
│                                                ↓            │
│                              [STEP 0: Vision Safety Check]  │
│                              VisionSafetyProductAgent       │
│                                   ↓                         │
│                           Safe? ──┬── No → Block + Log     │
│                                   │                         │
│                                  Yes                        │
│                                   ↓                         │
│                            RouterAgent                      │
│                         (Intent Classifier)                 │
│                                   ↓                         │
│              ┌──────────────┬──────────────┬──────────┐     │
│              ↓              ↓              ↓          ↓     │
│         CreateListing  SearchAgent  UpdateListing  Delete  │
│              ↓              ↓              ↓          ↓     │
│              └──────────────┴──────────────┴──────────┘     │
│                              ↓                              │
│                      Native Function Tools                  │
│                              ↓                              │
│                      Supabase Database                      │
│                   (+ image_safety_flags table)             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Teknoloji Stack:**
- **Framework:** FastAPI 0.109+
- **AI Engine:** OpenAI Agents SDK (Agent Builder)
- **Model:** GPT-4 (configurable via ModelSettings)
- **Vision Model:** GPT-4o-mini (vision-capable, lightweight)
- **Database:** Supabase (PostgreSQL)
- **Storage:** Supabase Storage (product-images bucket)
- **Deployment:** Railway
- **Language:** Python 3.11+

---

## 🎯 Agent Yapısı

### 0. **VisionSafetyProductAgent** (Görsel Güvenlik + Ürün Tanıma) 🛡️
**Görev:** Kullanıcının yüklediği görselleri analiz eder, illegal/güvensiz içerikleri tespit eder ve güvenli görsellerde ürün özetini çıkarır.

**Özellikler:**
- ✅ **Safety-First Yaklaşım:** İllegal içerik tespiti öncelikli
- 🖼️ **Ürün Tanıma:** Kategori, marka, model, durum, fiyat tahmini
- 🚫 **Auto-Block:** Güvensiz içerik tespit edilirse işlem durdurulur
- 📝 **Supabase Logging:** Her flag `image_safety_flags` tablosuna kaydedilir
- 👨‍💼 **Admin Review:** Manuel inceleme için pending statusü (otomatik ban yok)
- ⚠️ **False Positive Önlemi:** Mayo, bikini, iç çamaşırı tek başına illegal değil

**Workflow (Step 0 - Router'dan ÖNCE):**
```
1. media_paths kontrolü (görsel var mı?)
2. İlk görseli VisionSafetyProductAgent'a gönder
3. JSON response parse et:
   ├─ safe=false veya allow_listing=false
   │  ├─ log_image_safety_flag() ile Supabase'e kaydet
   │  ├─ Kullanıcıya "❌ Güvenlik nedeniyle reddedildi" mesajı
   │  └─ Return (Router'a GİTMEDEN işlem sonlanır)
   │
   └─ safe=true ve allow_listing=true
      ├─ product_info'yu conversation_history'ye ekle
      └─ RouterAgent'a devam et (normal akış)
```

**Output Schema:**
```python
class VisionSafetyProductSchema(BaseModel):
    safe: bool  # Genel güvenlik
    flag_type: str  # weapon, drugs, violence, sexual, hate, stolen, document, abuse, terrorism, unknown, none
    confidence: str  # high, medium, low
    message: str  # Detaylı açıklama
    allow_listing: bool  # İlan yayına alınabilir mi?
    product: Optional[Dict[str, Any]]  # Güvenli ise ürün bilgileri
```

**Illegal Content Kategorileri:**
- Silah, kesici alet, patlayıcı
- Uyuşturucu, tütün ürünleri
- Şiddet içeriği, kan, yaralama
- Cinsel içerik (çocuk istismarı, pornografi)
- Nefret söylemi, ayrımcılık
- Çalıntı ürün (imei, plaka belirsiz)
- Sahte evrak, kimlik
- Terör, suç örgütü içeriği

**Örnek:**
```
Kullanıcı: [Bıçak görseli yükler]
VisionSafetyProductAgent → safe=false, flag_type="weapon", confidence="high"
→ Supabase'e kaydedilir (user_id, image_url, flag_type, message)
→ "❌ Güvenlik nedeniyle reddedildi: Silah veya kesici alet tespit edildi"
→ RouterAgent'a GİTMEZ, işlem burada biter

Kullanıcı: [iPhone 13 fotoğrafı yükler]
VisionSafetyProductAgent → safe=true, allow_listing=true
→ product: {"category": "Elektronik", "brand": "Apple", "model": "iPhone 13"...}
→ Conversation history'ye ürün özeti eklenir
→ RouterAgent → CreateListingAgent (ürün bilgileri pre-filled)
```

**Model:** `gpt-4o-mini` (vision-capable, cost-effective)

**Supabase Logging Table: `image_safety_flags`**
```sql
- id, user_id, image_url, flag_type, confidence, message
- status (pending/confirmed/dismissed/banned)
- created_at, reviewed_at, reviewer, notes
```

---

### 1. **RouterAgent** (Intent Classifier)
**Görev:** Kullanıcı mesajını analiz ederek hangi specialized agent'a yönlendireceğine karar verir.

**Intent Types:**
- `create_listing` - Yeni ilan oluşturma
- `search_listing` - İlan arama
- `update_listing` - Mevcut ilan güncelleme
- `delete_listing` - İlan silme
- `view_my_listings` - Kullanıcının ilanlarını listeleme
- `small_talk` - Selamlaşma, genel sohbet
- `cancel` - İşlem iptali

**Örnek:**
```
Kullanıcı: "iPhone 13 satıyorum 25 bin TL"
RouterAgent → Intent: create_listing → CreateListingAgent
```

---

### 2. **CreateListingAgent** (İlan Hazırlama)
**Görev:** Kullanıcıdan ilan bilgilerini toplar ve taslak hazırlar.

**Akış:**
1. Kullanıcıdan bilgi topla (başlık, fiyat, kategori, durum, açıklama)
2. `clean_price_tool` ile fiyat temizle
3. `suggest_category_tool` ile kategori öner
4. Taslağı conversation context'e kaydet
5. Kullanıcıya önizleme göster
6. Onay alınca → **PublishAgent**'a yönlendir

**Önemli:** CreateListingAgent asla `insert_listing_tool` çağırmaz - bu PublishAgent'ın işidir!

**Metadata Özellikleri:**
- **Elektronik:** `brand`, `model`, `screen_size`, `storage`, `ram`
- **Otomotiv:** `make`, `model`, `year`, `km`, `fuel_type`, `transmission`
- **Emlak:** `property_type`, `rooms`, `m2`, `floor`, `heating`
- **Moda:** `brand`, `size`, `color`, `material`, `gender`

---

### 3. **PublishAgent** (Veritabanına Kayıt)
**Görev:** CreateListingAgent'ın hazırladığı taslağı Supabase'e kaydeder.

**Akış:**
1. Conversation context'ten taslak bilgilerini al
2. `insert_listing_tool` çağır (images, metadata dahil)
3. Başarılı ise kullanıcıya ilan ID ver
4. Hata varsa detaylı mesaj döndür

**Örnek Response:**
```
✅ İlanınız başarıyla yayınlandı!
📋 İlan ID: 550e8400-e29b-41d4-a716-446655440000
📱 Başlık: iPhone 13 128GB
💰 Fiyat: 25,000 TL
```

---

### 4. **SearchAgent** (İlan Arama)
**Görev:** Kullanıcının arama kriterlerine göre ilanları bulur ve sunar.

**Özellikler:**
- Akıllı arama (query-based)
- Kategori filtreleme
- Fiyat aralığı (min/max)
- Durum filtreleme (yeni/kullanılmış)
- Lokasyon bazlı arama
- Metadata tip filtreleme (automotive, electronics, etc.)

**Pagination Stratejisi:**
- Varsayılan: 5 ilan göster
- Kullanıcıya "daha fazla" seçeneği sun
- Her batch'te clear formatting

**Örnek:**
```
Kullanıcı: "20-30 bin arası iPhone bul"
SearchAgent: 
  → search_listings_tool(query="iPhone", min_price=20000, max_price=30000, limit=5)
  → "12 ilan bulundu. İlk 5'i göstereyim mi?"
```

**Display Format:**
```
📱 iPhone 13 128GB
💰 Fiyat: 25,000 TL
📍 Lokasyon: İstanbul
👤 İlan sahibi: Ahmet Yılmaz
📞 Telefon: +90541****705
🆔 ID: 550e8400-...
```

---

### 5. **UpdateListingAgent** (İlan Güncelleme)
**Görev:** Kullanıcının mevcut ilanlarını günceller.

**Güvenlik Kontrolü:** ⚠️
- Sadece kullanıcının kendi ilanlarını güncelleyebilir
- `user_id` zorunlu filtre
- Güncelleme öncesi ilan sahipliği doğrulaması

**Akış:**
1. `list_user_listings_tool` ile kullanıcının ilanlarını listele
2. Kullanıcıya hangi ilanı güncellemek istediğini sor
3. Güncellenecek alanları al (fiyat, başlık, açıklama, etc.)
4. `update_listing_tool` çağır (user_id kontrolü ile)
5. Başarı/hata mesajı döndür

**Güvenlik Notu:**
```python
# ✅ DOĞRU: user_id kontrolü ile
update_listing_tool(listing_id="...", user_id=current_user_id, price=30000)

# ❌ YANLIŞ: user_id olmadan (güvenlik açığı!)
update_listing_tool(listing_id="...", price=30000)
```

---

### 6. **DeleteListingAgent** (İlan Silme)
**Görev:** Kullanıcının ilanlarını siler.

**Güvenlik Kontrolü:** ⚠️
- `user_id` zorunlu filtre
- Silme öncesi onay alma
- Sadece kullanıcının kendi ilanları silinebilir

**Akış:**
1. `list_user_listings_tool` ile ilanları listele
2. Kullanıcıya hangi ilanı silmek istediğini sor
3. "Bu ilanı silmek istediğinize emin misiniz?" onayı al
4. `delete_listing_tool` çağır (user_id kontrolü ile)
5. Başarı mesajı döndür

---

### 7. **SmallTalkAgent** (Genel Sohbet)
**Görev:** Selamlaşma, teşekkür, genel sorulara cevap verir.

**Özellikler:**
- Kullanıcı adı ile kişiselleştirilmiş selamlama
- PazarGlobal hakkında bilgi
- Yardım menüsü
- Friendly & professional tone

**Örnek:**
```
Kullanıcı: "Merhaba"
SmallTalkAgent: "Merhaba Ahmet Bey! 👋 PazarGlobal'e hoş geldiniz. 
                 Size nasıl yardımcı olabilirim?"
```

---

### 8. **CancelAgent** (İptal İşlemleri)
**Görev:** Devam eden işlemleri iptal eder, conversation context'i temizler.

**Kullanım:**
```
Kullanıcı: "vazgeçtim", "iptal", "durdur"
CancelAgent → Context temizleme → "İşlem iptal edildi" mesajı
```

---

## 🛠️ Tools (Araçlar)

### 1. **clean_price_tool**
```python
clean_price_tool(price_text: Optional[str]) -> Dict[str, Optional[int]]
```
**Görev:** Fiyat metnini sayısal değere çevirir.

**Örnekler:**
- "25 bin TL" → 25000
- "45000" → 45000
- "2.5M" → 2500000
- "otuz beş bin" → 35000

---

### 2. **insert_listing_tool**
```python
insert_listing_tool(
    title: str,
    user_id: str,
    price: Optional[int] = None,
    condition: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    stock: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    images: Optional[list[str]] = None,
    listing_id: Optional[str] = None
) -> Dict[str, Any]
```

**Görev:** Supabase `listings` tablosuna yeni ilan ekler.

**Return:**
```json
{
  "success": true,
  "listing_id": "550e8400-e29b-41d4-a716-446655440000",
  "message": "Listing created successfully"
}
```

---

### 3. **search_listings_tool**
```python
search_listings_tool(
    query: Optional[str] = None,
    category: Optional[str] = None,
    condition: Optional[str] = None,
    location: Optional[str] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    limit: int = 10,
    metadata_type: Optional[str] = None
) -> Dict[str, Any]
```

**Görev:** Supabase'den ilan arar.

**Return:**
```json
{
  "success": true,
  "count": 12,
  "listings": [...]
}
```

---

### 4. **update_listing_tool**
```python
update_listing_tool(
    listing_id: str,
    title: Optional[str] = None,
    price: Optional[int] = None,
    condition: Optional[str] = None,
    category: Optional[str] = None,
    description: Optional[str] = None,
    location: Optional[str] = None,
    stock: Optional[int] = None,
    metadata: Optional[Dict[str, Any]] = None,
    images: Optional[list[str]] = None
) -> Dict[str, Any]
```

**Güvenlik:** `user_id` kontrolü `CURRENT_REQUEST_USER_ID` global variable ile yapılır.

---

### 5. **delete_listing_tool**
```python
delete_listing_tool(listing_id: str) -> Dict[str, Any]
```

**Güvenlik:** `user_id` kontrolü ile sadece kullanıcının kendi ilanları silinir.

---

### 6. **list_user_listings_tool**
```python
list_user_listings_tool() -> Dict[str, Any]
```

**Görev:** Mevcut kullanıcının tüm ilanlarını listeler.

---

### 7. **suggest_category_tool**
```python
suggest_category_tool(title: str, description: Optional[str] = None) -> Dict[str, Any]
```

**Görev:** Başlık ve açıklamadan otomatik kategori önerir.

**Kategoriler:**
- Elektronik
- Otomotiv
- Emlak
- Moda & Aksesuar
- Ev & Yaşam
- Spor & Outdoor
- Hobi & Eğlence
- Diğer

---

## 🌐 API Endpoints

### **GET /**
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "Pazarglobal Agent Backend",
  "version": "2.0.0",
  "api_type": "Agents SDK + MCP",
  "openai_configured": true,
  "mcp_server": "https://pazarglobal-production.up.railway.app"
}
```

---

### **POST /agent/run**
Ana workflow endpoint. Tüm agent işlemlerini bu endpoint üzerinden yapın.

**Request Body:**
```json
{
  "user_id": "string",
  "phone": "optional-string",
  "message": "string",
  "conversation_history": [],
  "media_paths": ["optional-list"],
  "media_type": "optional-string",
  "draft_listing_id": "optional-uuid",
  "auth_context": {
    "user_id": "uuid-string",
    "phone": "optional-string",
    "authenticated": true,
    "session_expires_at": "2025-01-15T12:00:00Z"
  },
  "conversation_state": {
    "mode": "web|whatsapp",
    "active_listing_id": "optional-uuid",
    "last_intent": "create_listing|search_listing|update_listing|delete_listing|view_my_listings"
  },
  "session_token": "optional-string",
  "user_context": {
    "name": "optional-string"
  }
}
```

**Response:**
```json
{
  "response": "Agent'tan gelen cevap metni",
  "intent": "create_listing",
  "success": true
}
```

**Example:**
```bash
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user_123",
    "message": "iPhone 13 satıyorum 25 bin TL",
    "conversation_history": []
  }'
```

**Auth & Session Model:**
- `auth_context` zorunlu alanlar: `user_id` (Supabase auth.uid), `authenticated` (bool). `phone` opsiyonel ama WhatsApp için önerilir. `session_expires_at` ISO8601 (Supabase session expiry).
- `conversation_state` global state taşıyıcısıdır: `mode` (`web` veya `whatsapp`), `active_listing_id` (opsiyonel UUID), `last_intent` (router çıktısı). Köprü katmanı (Web Chat / WhatsApp Bridge) her istekte gönderir.
- Router intent + `conversation_state.last_intent` backend'de güncellenir; agent'lar sadece iş yapar, yetki kontrolü backend seviyesinde.
- ⚠️ Aktif session varken sistem asla “Hoş geldin / Giriş yap” mesajı üretmez.
- Korunan intentler (`update_listing`, `delete_listing`) `authenticated=true` ve `auth_context.user_id` olmadan çalışmaz; backend owner_id doğrular.
- Supabase RLS için owner-only politikalar [pazarglobal-agent-backend/RLS_POLICY_LISTINGS.sql](pazarglobal-agent-backend/RLS_POLICY_LISTINGS.sql) dosyasında. Uygulamak için: Supabase SQL editor → dosyayı çalıştır → ilgili tabloda RLS enable.
- Web Chat: Supabase session'dan `auth_context` üret, `conversation_state.mode="web"` gönder.
- WhatsApp Bridge: Telefon → user_id eşlemesini yaptıktan sonra `auth_context.authenticated=true` + `phone` gönder, `conversation_state.mode="whatsapp"` ilet.
- VisionSafetyProductAgent yalnızca `media_paths` varsa çalışır; metin-only mesajlarda devre dışı kalır.

---

### **POST /web-chat** (Frontend için)
Web frontend'den gelen chat istekleri için özel endpoint.

**Features:**
- CORS enabled
- Session management
- User context hydration

---

## 🚀 Kurulum

### 1. Gereksinimler
- Python 3.11+
- pip
- Supabase account
- OpenAI API key

### 2. Dependencies Kurulumu
```bash
cd pazarglobal-agent-backend
pip install -r requirements.txt
```

**requirements.txt:**
```
fastapi>=0.109.0
uvicorn[standard]>=0.27.0
pydantic>=2.12.3
python-multipart>=0.0.6
httpx>=0.26.0
openai-agents>=0.1.0
openai>=1.54.0
openai-guardrails>=0.1.0
supabase>=2.0.0
python-dotenv>=1.0.0
```

### 3. Environment Variables
`.env` dosyası oluşturun:

```env
# OpenAI
OPENAI_API_KEY=sk-proj-...

# Supabase
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGc...
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_STORAGE_BUCKET=product-images

# Server
PORT=8000

# Optional: MCP Server (eski sistem, artık kullanılmıyor)
MCP_SERVER_URL=https://pazarglobal-production.up.railway.app
```

### 4. Lokal Çalıştırma
```bash
uvicorn main:app --reload --port 8000
```

Server: `http://localhost:8000`

### 5. Test
```bash
# Health check
curl http://localhost:8000

# Test agent
curl -X POST http://localhost:8000/agent/run \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "test_user",
    "message": "merhaba",
    "conversation_history": []
  }'
```

---

## 🚂 Railway Deployment

### 1. GitHub Repository
```bash
git init
git add .
git commit -m "Initial commit: Agent backend"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/pazarglobal-agent-backend.git
git push -u origin main
```

### 2. Railway Setup
1. **Railway'e git:** https://railway.app/new
2. **"Deploy from GitHub repo"** seç
3. **Repository:** `pazarglobal-agent-backend`
4. Railway otomatik Python detect edecek

### 3. Environment Variables (Railway Dashboard)
```env
OPENAI_API_KEY=sk-proj-...
SUPABASE_URL=https://...
SUPABASE_SERVICE_KEY=eyJhbGc...
SUPABASE_ANON_KEY=eyJhbGc...
SUPABASE_STORAGE_BUCKET=product-images
PORT=8000
```

### 4. Deploy
- Railway otomatik deploy başlatır
- Build time: ~3-5 dakika
- Railway size public URL verir: `https://pazarglobal-agent-backend-production.up.railway.app`

### 5. Doğrulama
```bash
curl https://your-railway-url.up.railway.app
```

Expected:
```json
{
  "status": "healthy",
  "service": "Pazarglobal Agent Backend"
}
```

---

## 🔧 Environment Variables

| Variable | Gerekli | Açıklama | Örnek |
|----------|---------|----------|-------|
| `OPENAI_API_KEY` | ✅ | OpenAI API anahtarı | `sk-proj-...` |
| `SUPABASE_URL` | ✅ | Supabase project URL | `https://xyz.supabase.co` |
| `SUPABASE_SERVICE_KEY` | ✅ | Supabase service role key (RLS bypass) | `eyJhbGc...` |
| `SUPABASE_ANON_KEY` | ❌ | Supabase anon key (public operations) | `eyJhbGc...` |
| `SUPABASE_STORAGE_BUCKET` | ✅ | Storage bucket name | `product-images` |
| `PORT` | ❌ | Server port (Railway otomatik set eder) | `8000` |

---

## 📊 Workflow Detayları

### Conversation Flow
```
1. User Message → main.py (/agent/run endpoint)
                    ↓
2. WorkflowInput oluştur (message, history, media, user_id)
                    ↓
3. run_workflow(workflow_input) → workflow.py
                    ↓
4. RouterAgent → Intent classification
                    ↓
5. Specialized Agent (Create/Search/Update/Delete/SmallTalk)
                    ↓
6. Tool calls (insert_listing, search_listings, etc.)
                    ↓
7. Supabase operations
                    ↓
8. Response → User
```

### Media Handling Flow
```
WhatsApp Bridge → Media download & compress
                    ↓
                Supabase Storage upload
                    ↓
                Storage path → Agent Backend
                    ↓
                CreateListingAgent → images field
                    ↓
                insert_listing_tool → Database
```

### Global State Management
**⚠️ İyileştirme Gerekiyor:**
```python
# workflow.py
CURRENT_REQUEST_USER_ID = None  # Concurrent requests'te risk!

# TODO: WorkflowContext class ile değiştirilmeli
```

---

## 🔒 Güvenlik

### Mevcut Güvenlik Önlemleri
✅ **Supabase Service Key kullanımı** (RLS bypass)  
✅ **User ID validation** (update/delete işlemlerinde)  
✅ **Phone number → user profile mapping**  
✅ **Media type validation** (WhatsApp Bridge'de)

### Güvenlik İyileştirmeleri (TODO)
⚠️ **Global State Riski:**
```python
# ❌ Şu anki: Concurrent request'lerde sorun çıkarabilir
CURRENT_REQUEST_USER_ID = None

# ✅ Olması gereken
class WorkflowContext:
    def __init__(self, user_id: str):
        self.user_id = user_id
```

⚠️ **Yayınlanmış İlan Güncelleme Güvenlik Açığı:**
- UpdateListingAgent yayınlanmış ilanları sadece conversation context'e bakarak güncelliyor
- PIN/OTP doğrulama yok
- **Çözüm:** Phase 4 (Güvenlik Sertleştirmesi) ile implement edilecek

⚠️ **Rate Limiting Eksik:**
```python
# TODO: Eklenecek
from slowapi import Limiter
@limiter.limit("10/minute")
```

⚠️ **Session Persistence:**
- In-memory conversation store → Redis'e taşınmalı
- Session timeout & device fingerprinting

---

## 🎯 Gelecek Özellikler

### Phase 3.5: Premium Listing (MONETIZATION) 💰
**Timeline:** 2-3 hafta

**Database Changes:**
```sql
ALTER TABLE listings ADD COLUMN is_premium BOOLEAN DEFAULT FALSE;
ALTER TABLE listings ADD COLUMN premium_expires_at TIMESTAMP;
CREATE INDEX idx_listings_premium ON listings(is_premium, created_at);
```

**SearchAgent Enhancement:**
- Premium ilanlar her zaman ilk sırada
- "⭐ PREMIUM" badge
- Monetization trigger messages

**UX Example:**
```
SearchAgent: "50 ilan bulundu (2 premium). İlk 5'i göstereyim mi?"
[2 premium + 3 normal göster]
"💡 ⭐ Premium ilanlar listenin başında görünür! 
    İlanınızı öne çıkarmak için Premium üyelik edinin."
```

---

### Phase 4: VisionSafetyProductAgent ✅ **COMPLETED**
**Status:** ✅ Deployed and Active (December 2025)

**Features:**
- ✅ OpenAI Vision API (GPT-4o-mini) ile ürün tanıma
- ✅ İllegal/güvensiz içerik tespiti (Safety-First)
- ✅ Otomatik kategori, marka, model çıkarımı
- ✅ Fiyat tahmin algoritması
- ✅ Ürün durumu analizi (yeni/kullanılmış)
- ✅ Supabase logging (image_safety_flags table)
- ✅ Router pre-check (Step 0 entegrasyonu)
- ✅ Admin review workflow (manuel ban)
- ✅ False positive önlemleri (mayo/bikini NOT illegal)

**Implementation:**
```python
# VisionSafetyProductAgent definition in workflow.py
vision_safety_product_agent = Agent(
    name="VisionSafetyProductAgent",
    instructions="""Safety first. Illegal content detection priority.
    Output STRICT JSON: {safe, flag_type, confidence, message, product, allow_listing}""",
    model="gpt-4o-mini",
    output_type=VisionSafetyProductSchema
)

# Step 0 integration (pre-router check)
if media_paths:
    vision_result = await Runner.run(vision_safety_product_agent, input=vision_input)
    if not vision_result.safe or not vision_result.allow_listing:
        log_image_safety_flag(...)  # Supabase'e kaydet
        return {"response": "❌ Güvenlik nedeniyle reddedildi", "success": False}
    # Safe: product summary'yi conversation_history'ye ekle
```

**Supabase Schema:**
```sql
-- image_safety_flags table (created via supabase/image_safety_flags.sql)
CREATE TABLE image_safety_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL,
    image_url TEXT,
    flag_type TEXT CHECK (flag_type IN ('weapon','drugs','violence','sexual','hate','stolen','document','abuse','terrorism','unknown','none')),
    confidence TEXT CHECK (confidence IN ('high','medium','low')),
    message TEXT NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending','confirmed','dismissed','banned')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewer TEXT,
    notes TEXT
);
-- Indexes: user_id, status, created_at, (flag_type, status)
```

**Testing Status:**
- ✅ Safe image → Product summary injected, listing created
- ✅ Unsafe image → Blocked + logged, no router call
- ✅ Mayo/bikini → NOT flagged (false positive prevention)
- ⏳ Live testing in production environment

---

### Phase 5: VoiceAgent (Speech) 🎤
**Timeline:** 2 hafta

**Features:**
- OpenAI Whisper (STT)
- OpenAI TTS (Text-to-Speech)
- Sesli komutlar: "iPhone sat", "telefon ara"
- Türkçe optimizasyon

---

### Phase 6: MarketingAgent (Market Intelligence) 📊
**Timeline:** 3 hafta

**Features:**
- Sahibinden/Letgo web scraping
- Piyasa fiyat karşılaştırma
- Trend analizi
- Optimal fiyat önerisi

**Tools:**
```python
@function_tool
async def search_market_prices_tool(product: str) -> Dict:
    """Piyasa fiyat araştırması"""
    # Playwright/BeautifulSoup scraping
    # Return: min, max, avg, median prices
```

---

### Phase 7: SecurityAgent (Advanced Security) 🔐
**Timeline:** 1 hafta

**Features:**
- PIN/OTP doğrulama
- Device fingerprinting
- Session management
- Audit logging
- Fraud detection

---

### Phase 8: Payment Integration 💳
**Timeline:** 3-4 hafta

**Gateways:**
- Stripe (global)
- İyzico (Turkey)

**Features:**
- Escrow system
- Premium membership payments
- Transaction history

---

## 🐛 Sorun Giderme

### 1. Agent Çalışmıyor
**Semptom:** "error" in response

**Kontroller:**
```bash
# OpenAI API key doğru mu?
echo $OPENAI_API_KEY

# Supabase erişimi var mı?
curl -H "apikey: $SUPABASE_ANON_KEY" $SUPABASE_URL/rest/v1/listings?limit=1

# Logs kontrol
# Railway: Dashboard → Logs
```

---

### 2. User ID Mapping Hatası
**Semptom:** "Kullanıcı bulunamadı"

**Çözüm:**
```python
# main.py'de user profile fetch kontrolü
# Phone number formatting: +905551234567 (country code ile)
```

---

### 3. Conversation History Kayboluyor
**Semptom:** Agent önceki mesajları hatırlamıyor

**Çözüm:**
- WhatsApp Bridge'den `conversation_history` gönderildiğinden emin olun
- Bridge'deki `conversation_store` timeout'u artırın (default: 30 dakika)

---

### 4. Media Upload Başarısız
**Semptom:** Fotoğraf yüklenmiyor

**Kontroller:**
```bash
# Supabase Storage bucket var mı?
# product-images bucket public mi? (private olmalı)
# SUPABASE_SERVICE_KEY doğru mu?
```

---

### 5. Slow Response Time
**Optimizasyon:**
- Model değiştir: GPT-4 → GPT-3.5-turbo (hızlı işlemler için)
- `max_tokens` limitini azalt
- Conversation history'yi kısalt (son 10 mesaj)

```python
# workflow.py
model_settings=ModelSettings(
    model="gpt-3.5-turbo",  # Hızlı işlemler için
    max_tokens=500
)
```

---

## 📚 Kaynaklar

- **OpenAI Agents SDK Docs:** https://platform.openai.com/docs/agents
- **Supabase Docs:** https://supabase.com/docs
- **FastAPI Docs:** https://fastapi.tiangolo.com
- **Railway Docs:** https://docs.railway.app

---

## 📝 Changelog

### v2.0.0 (Aralık 2025)
- ✅ OpenAI Agents SDK migration (MCP'den native functions'a)
- ✅ Multi-agent architecture (8 specialized agents)
- ✅ Media handling (images support)
- ✅ User profile mapping (phone → Supabase users)
- ✅ Conversation history management
- ✅ Category suggestion tool
- ✅ Metadata support (electronics, automotive, real estate)

### v1.0.0 (Kasım 2025)
- Initial release
- MCP server integration
- Basic listing operations

---

## 👨‍💻 Geliştirici Notları

### Code Structure
```
pazarglobal-agent-backend/
├── main.py                 # FastAPI app + endpoints
├── workflow.py             # Agents + tools + workflow logic
├── requirements.txt        # Python dependencies
├── runtime.txt            # Python version (Railway için)
├── tools/                 # Native function tools for agents
│   ├── clean_price.py
│   ├── insert_listing.py
│   ├── search_listings.py
│   ├── update_listing.py
│   ├── delete_listing.py
│   ├── list_user_listings.py
│   └── suggest_category.py
├── middleware/            # Production middleware
│   └── security.py        # Rate limiting, SQL/XSS protection
├── utils/                 # Utility functions
│   ├── logging_config.py  # Structured logging
│   └── error_handling.py  # Turkish error messages
├── routes/                # API routes
│   └── health.py          # Health check endpoints
├── supabase/
│   └── config.toml        # Supabase local config
└── scripts/
    ├── test_insert_simple.py
    └── test_3_photos.py
```

### Development Tips
```bash
# Hot reload development
uvicorn main:app --reload --port 8000

# Test specific agent
# workflow.py'de agent'ı manuel çağır

# Database schema değişikliği
# Supabase Dashboard → SQL Editor

# Logs
# Railway: Dashboard → Deployments → View Logs
# Local: Terminal output
```

---

## 🤝 Katkıda Bulunma

Bu proje aktif geliştirme aşamasında. Öneri ve katkılarınız için:
- GitHub Issues
- Pull Requests

---

## 📄 Lisans

Private project - PazarGlobal

---

**Son Güncelleme:** 10 Aralık 2025  
**Versiyon:** 2.0.0  
**Durum:** Production Ready (with improvements needed)
