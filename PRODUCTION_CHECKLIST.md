# 🚀 Production Checklist - PazarGlobal

## ✅ GÜVENLİK (Security)

### Temel Güvenlik
- [x] Rate limiting eklendi (100 req/60s)
- [x] SQL injection koruması eklendi
- [x] XSS koruması eklendi
- [x] Security headers eklendi (X-Frame-Options, CSP, etc.)
- [ ] HTTPS zorunlu (Railway/Vercel otomatik sağlar)
- [x] Hassas veri maskeleme (telefon, email, API keys loglanmıyor)

### Authentication & Authorization
- [ ] **YAPILACAK:** Frontend login sistemi tamamlanmalı
- [x] Backend user_id bazlı yetkilendirme mevcut
- [x] İlan sahipliği kontrolü yapılıyor
- [ ] **ÖNERİLİR:** JWT token sistemi eklenebilir (şu an user_id based)
- [ ] **ÖNERİLİR:** WhatsApp PIN sistemi aktif edilebilir

### Supabase Row Level Security
- [ ] **KRİTİK:** Supabase RLS policies kontrol edilmeli:
  ```sql
  -- listings tablosu için
  CREATE POLICY "Users can insert own listings"
  ON listings FOR INSERT
  WITH CHECK (auth.uid() = user_id);
  
  CREATE POLICY "Users can update own listings"
  ON listings FOR UPDATE
  USING (auth.uid() = user_id);
  
  CREATE POLICY "Users can delete own listings"
  ON listings FOR DELETE
  USING (auth.uid() = user_id);
  
  CREATE POLICY "Everyone can view published listings"
  ON listings FOR SELECT
  USING (status = 'active');
  ```

### API Keys
- [x] API keys .env dosyasında
- [ ] **KRİTİK:** Production .env Railway'de environment variables olarak set edilmeli
- [ ] API key rotation stratejisi belirlenm eli

---

## ⚡ PERFORMANS (Performance)

### Database
- [ ] **YAPILACAK:** Database indexler oluşturulmalı:
  ```sql
  CREATE INDEX idx_listings_user_id ON listings(user_id);
  CREATE INDEX idx_listings_category ON listings(category);
  CREATE INDEX idx_listings_location ON listings(location);
  CREATE INDEX idx_listings_created_at ON listings(created_at DESC);
  CREATE INDEX idx_listings_price ON listings(price);
  CREATE INDEX idx_listings_status ON listings(status);
  
  -- Full text search için
  CREATE INDEX idx_listings_title_search ON listings USING GIN(to_tsvector('turkish', title));
  CREATE INDEX idx_listings_desc_search ON listings USING GIN(to_tsvector('turkish', description));
  ```

### Caching
- [ ] **ÖNERİLİR:** Redis cache eklenebilir (popüler aramalar, ilan detayları)
- [ ] **ÖNERİLİR:** CDN kullanımı (resimler için Supabase Storage zaten CDN kullanıyor)

### Image Optimization
- [x] Supabase Storage kullanılıyor (otomatik CDN)
- [ ] **ÖNERİLİR:** Resim yüklemede max boyut kontrolü eklenebilir
- [ ] **ÖNERİLİR:** Otomatik image compression (Sharp.js veya benzeri)

### Response Time
- [x] SSE streaming ile agent yanıtları
- [ ] **ÖNERİLİR:** Slow query monitoring
- [x] Health check endpoints (/health, /health/ready, /health/live)

---

## 📊 MONİTORİNG & LOGGING

### Logging
- [x] Structured logging sistem eklendi
- [x] Hassas veri maskeleme aktif
- [x] Performance logging (`PerformanceLogger`)
- [ ] **ÖNERİLİR:** Log aggregation servisi (Datadog, Papertrail, etc.)

### Monitoring
- [x] Health check endpoints
- [x] System resource monitoring (CPU, RAM, Disk)
- [x] Dependency checks (Supabase, OpenAI)
- [ ] **ÖNERİLİR:** Uptime monitoring (UptimeRobot, Pingdom)
- [ ] **ÖNERİLİR:** Error tracking (Sentry)
- [ ] **ÖNERİLİR:** APM tool (Application Performance Monitoring)

### Alerts
- [ ] **YAPILACAK:** Critical alerts setup:
  - API down
  - High error rate
  - Database connection issues
  - Rate limit breaches
  - Disk space low

---

## 🎯 KULLANICI DENEYİMİ (UX)

### Hata Mesajları
- [x] Kullanıcı dostu Türkçe hata mesajları
- [x] Teknik hata detayları loglanıyor, kullanıcıya gösterilmiyor
- [x] Standard error response formatı

### Agent Davranışı
- [x] Samimi ve doğal dil kullanımı
- [x] Kişiselleştirme (isim ile hitap)
- [x] TTS için optimize edilmiş noktalama
- [x] Akıllı başlık/açıklama önerileri
- [x] Vision analysis ile ürün tanıma

### Hız & Pratiklik
- [x] Minimum soru sorma (sadece eksik bilgi)
- [x] Otomatik kategori tespiti
- [x] Fiyat temizleme ("900 bin" → 900000)
- [x] Resimden ürün çıkarma
- [x] SSE streaming (anlık yanıt)

---

## 🔄 BACKUP & RECOVERY

### Database Backup
- [ ] **KRİTİK:** Supabase otomatik backup açık mı kontrol et
- [ ] **ÖNERİLİR:** Point-in-time recovery enable
- [ ] Backup restore testi yapılmalı

### Disaster Recovery
- [ ] **YAPILACAK:** Recovery plan dokümante edilmeli:
  - Database restore süreci
  - API key rotation süreci
  - Service restart süreci
  - Emergency contact list

---

## 📱 FRONTEND (React/Vite)

### Production Build
- [ ] **YAPILACAK:** Frontend production build optimize edilmeli:
  ```bash
  npm run build
  ```
- [ ] Bundle size analizi yapılmalı
- [ ] Code splitting uygulanmalı (lazy loading)
- [ ] Service worker eklenebilir (PWA)

### Security
- [ ] **KRİTİK:** Supabase anon key frontend'de (güvenli)
- [ ] Service role key asla frontend'e konmamalı
- [ ] CSP headers set edilmeli

### Performance
- [ ] Image lazy loading
- [ ] Route-based code splitting
- [ ] Compression (gzip/brotli)
- [ ] Asset minification

---

## 🧪 TESTING

### Backend Tests
- [ ] **ÖNERİLİR:** Unit testler yazılabilir (pytest)
- [ ] **ÖNERİLİR:** Integration testler
- [ ] **ÖNERİLİR:** Load testing (k6, Locust)

### Frontend Tests
- [ ] **ÖNERİLİR:** Component testleri (Vitest)
- [ ] **ÖNERİLİR:** E2E testler (Playwright)

### Agent Quality
- [x] Vision safety agent aktif
- [x] Guardrails (PII protection)
- [ ] **ÖNERİLİR:** Agent response quality testing

---

## 📋 DEPLOYMENT

### Railway (Backend)
- [x] GitHub auto-deploy aktif
- [ ] **YAPILACAK:** Environment variables set edilmeli:
  ```
  ENVIRONMENT=production
  OPENAI_API_KEY=***
  SUPABASE_URL=***
  SUPABASE_SERVICE_KEY=***
  LOG_LEVEL=INFO
  LOG_FORMAT=json
  MASK_SENSITIVE_DATA=true
  ```
- [ ] Health check URL Railway'e tanıtılmalı
- [ ] Resource limits belirlenmeli (CPU, RAM)

### Vercel (Frontend)
- [ ] Environment variables set edilmeli
- [ ] Build optimizasyonu yapılmalı
- [ ] Analytics eklenebilir

### Domain & SSL
- [ ] Domain DNS ayarları
- [ ] SSL sertifikaları (otomatik - Railway/Vercel)
- [ ] HTTPS redirect

---

## 🎛️ CONFIGURATION

### Environment Variables (Production)
```bash
# Backend (Railway)
ENVIRONMENT=production
OPENAI_API_KEY=sk-***
SUPABASE_URL=https://***.supabase.co
SUPABASE_SERVICE_KEY=eyJ***
SUPABASE_ANON_KEY=eyJ***
MCP_SERVER_URL=https://pazarglobal-production.up.railway.app
LOG_LEVEL=INFO
LOG_FORMAT=json
MASK_SENSITIVE_DATA=true
RATE_LIMIT_MAX_REQUESTS=100
RATE_LIMIT_WINDOW_SECONDS=60
ALLOWED_ORIGINS=https://pazarglobal.com,https://www.pazarglobal.com

# Frontend (Vercel)
VITE_SUPABASE_URL=https://***.supabase.co
VITE_SUPABASE_ANON_KEY=eyJ***
VITE_API_BASE_URL=https://backend.railway.app
```

---

## ✅ PRE-LAUNCH SON KONTROLLER

### 1 Hafta Önce
- [ ] Load testing yapılmalı
- [ ] Security audit
- [ ] Backup testi
- [ ] Monitoring alerts test
- [ ] Emergency contacts hazır

### 1 Gün Önce
- [ ] Database indexler oluşturuldu mu?
- [ ] RLS policies aktif mi?
- [ ] Production environment variables set edildi mi?
- [ ] Health checks çalışıyor mu?
- [ ] Logging düzgün çalışıyor mu?
- [ ] Error tracking aktif mi?

### Launch Günü
- [ ] Monitoring dashboards açık
- [ ] Oncall team hazır
- [ ] Rollback planı hazır
- [ ] Status page hazır (opsiyonel)

### Launch Sonrası
- [ ] İlk 24 saat yakından izle
- [ ] Error rates monitor et
- [ ] Response times kontrol et
- [ ] User feedback topla

---

## 💡 ÖNERİLEN EK ÖZELLIKLER

### Kısa Vadeli (1-2 Hafta)
1. **Email notifications** - İlan yayınlandı, mesaj geldi, etc.
2. **Push notifications** - PWA için
3. **Analytics** - Kullanıcı davranışı, popüler kategoriler
4. **Search filters** - Fiyat aralığı, konum, kategori
5. **Saved searches** - Kullanıcı arama kaydetme

### Orta Vadeli (1 Ay)
1. **User reviews & ratings** - Satıcı değerlendirme
2. **Chat history** - Konuşma geçmişi kaydetme
3. **Favorites** - İlan favorileme
4. **Price suggestions** - AI ile fiyat önerisi
5. **Similar listings** - Benzer ilanlar önerisi

### Uzun Vadeli (2-3 Ay)
1. **Mobile app** - React Native
2. **Social sharing** - İlan paylaşma
3. **Premium listings** - Öne çıkan ilanlar
4. **Messaging system** - Alıcı-satıcı mesajlaşma
5. **Payment integration** - Güvenli ödeme

---

## 📞 DESTEK & DOKÜMANTASYON

### Dokümantasyon
- [ ] API documentation (Swagger/OpenAPI)
- [ ] User guide (Kullanıcı kılavuzu)
- [ ] Admin guide
- [ ] Troubleshooting guide

### Destek
- [ ] Support email
- [ ] FAQ sayfası
- [ ] Community/Forum (opsiyonel)

---

## 🎉 SONUÇ

### ✅ MEVCUT GÜÇLÜ YANLAR:
1. ✅ Multi-agent sistem (Router, Listing, Search, Update, Delete, SmallTalk)
2. ✅ Vision AI ile ürün tanıma
3. ✅ WhatsApp + Web chat entegrasyonu
4. ✅ Güvenlik middleware ve rate limiting
5. ✅ User-friendly error messages
6. ✅ Structured logging
7. ✅ Health check endpoints
8. ✅ SSE streaming responses
9. ✅ Akıllı başlık/açıklama önerileri

### ⚠️ KRİTİK EKSİKLER (Launch öncesi zorunlu):
1. ❗ Database indexler oluşturulmalı
2. ❗ Supabase RLS policies aktif edilmeli
3. ❗ Production environment variables set edilmeli
4. ❗ Monitoring alerts kurulmalı
5. ❗ Load testing yapılmalı

### 💡 ÖNERİLEN İYİLEŞTİRMELER (Launch sonrası):
1. Redis cache
2. Error tracking (Sentry)
3. Log aggregation
4. Image optimization
5. Analytics

**Genel Değerlendirme:** Sistem %80 production-ready. Kritik güvenlik ve performans iyileştirmeleri eklendi. Database optimizasyonu ve monitoring alerts eklendikten sonra launch yapılabilir! 🚀
