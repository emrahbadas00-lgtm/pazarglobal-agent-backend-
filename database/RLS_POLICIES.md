# Row Level Security (RLS) Policies - Pazarglobal

## Overview
Bu dokümant Supabase'deki tüm RLS policy'lerini detaylı açıklar.

**ÖNEMLI**: Şu an development modunda tüm policy'ler `true` kullanıyor.  
Production'da `auth.uid()` ile gerçek user authentication yapılacak.

---

## 🔐 Security Model

### Current State (Development)
```sql
-- ⚠️ DEVELOPMENT ONLY - Herkes her şeye erişebilir
USING (true)
WITH CHECK (true)
```

### Future State (Production with WhatsApp Auth)
```sql
-- ✅ PRODUCTION - Sadece kendi verisine erişebilir
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid())
```

---

## 📋 Table: users

### Policy 1: Users can view own profile
```sql
CREATE POLICY "Users can view own profile"
ON users FOR SELECT
USING (true);  -- TODO: auth.uid() = id
```

**Development Behavior**:
- ✅ Herkes tüm kullanıcıları görebilir

**Production Behavior**:
```sql
USING (auth.uid() = id)
```
- ✅ Sadece kendi profilini görebilir
- ❌ Başkalarının profilini göremez

**Use Cases**:
- User kendi bilgilerini çeker
- Profile update sayfası
- Settings ekranı

---

### Policy 2: Users can update own profile
```sql
CREATE POLICY "Users can update own profile"
ON users FOR UPDATE
USING (true)  -- TODO: auth.uid() = id
WITH CHECK (true);
```

**Development Behavior**:
- ✅ Herkes her kullanıcıyı güncelleyebilir

**Production Behavior**:
```sql
USING (auth.uid() = id)
WITH CHECK (auth.uid() = id)
```
- ✅ Sadece kendi profilini güncelleyebilir
- ❌ Başkasının profilini değiştiremez

**Use Cases**:
- İsim değiştirme: "adımı Ahmet yap"
- Lokasyon güncelleme: "şehir bilgimi İstanbul yap"
- Email ekleme

---

## 📦 Table: listings

### Policy 1: Anyone can view active listings
```sql
CREATE POLICY "Anyone can view active listings"
ON listings FOR SELECT
USING (status = 'active' OR true);  -- TODO: OR user_id = auth.uid()
```

**Development Behavior**:
- ✅ Herkes tüm ilanları görebilir (draft dahil)

**Production Behavior**:
```sql
USING (status = 'active' OR user_id = auth.uid())
```
- ✅ Herkes aktif ilanları görebilir
- ✅ User kendi draft ilanlarını görebilir
- ❌ Başkalarının draft ilanlarını göremez

**Use Cases**:
- Search: "laptop bul"
- Browse: "elektronik kategorisindeki ilanları göster"
- Own drafts: "taslak ilanlarımı göster"

---

### Policy 2: Users can insert own listings
```sql
CREATE POLICY "Users can insert own listings"
ON listings FOR INSERT
WITH CHECK (true);  -- TODO: user_id = auth.uid()
```

**Development Behavior**:
- ✅ Herkes herhangi bir user_id ile ilan oluşturabilir

**Production Behavior**:
```sql
WITH CHECK (user_id = auth.uid())
```
- ✅ Sadece kendi user_id'si ile ilan oluşturabilir
- ❌ Başkası adına ilan oluşturamaz

**Use Cases**:
- CreateListingAgent: "macbook satmak istiyorum"
- Bulk import: WhatsApp'tan toplu ilan

**CRITICAL**: Şu an tools'da user_id parametresi eksik! WhatsApp phase'de eklenecek.

---

### Policy 3: Users can update own listings
```sql
CREATE POLICY "Users can update own listings"
ON listings FOR UPDATE
USING (true)  -- TODO: user_id = auth.uid()
WITH CHECK (true);
```

**Development Behavior**:
- ✅ Herkes her ilanı güncelleyebilir

**Production Behavior**:
```sql
USING (user_id = auth.uid())
WITH CHECK (user_id = auth.uid())
```
- ✅ Sadece kendi ilanlarını güncelleyebilir
- ❌ Başkasının ilanını değiştiremez

**Use Cases**:
- UpdateListingAgent: "fiyatı 5000 tl yap"
- Status change: "ilanı aktif yap"
- Edit content: "açıklamayı değiştir"

---

### Policy 4: Users can delete own listings
```sql
CREATE POLICY "Users can delete own listings"
ON listings FOR DELETE
USING (true);  -- TODO: user_id = auth.uid()
```

**Development Behavior**:
- ✅ Herkes her ilanı silebilir

**Production Behavior**:
```sql
USING (user_id = auth.uid())
```
- ✅ Sadece kendi ilanlarını silebilir
- ❌ Başkasının ilanını silemez

**Use Cases**:
- DeleteListingAgent: "bu ilanı sil"
- Bulk delete: "tüm taslak ilanlarımı sil"

---

## 💬 Table: conversations

### Policy 1: Users can view own conversations
```sql
CREATE POLICY "Users can view own conversations"
ON conversations FOR SELECT
USING (true);  -- TODO: user_id = auth.uid()
```

**Production Behavior**:
```sql
USING (user_id = auth.uid())
```
- ✅ Sadece kendi konuşmalarını görebilir

**Use Cases**:
- WhatsApp geçmişi
- Conversation context için agent

---

### Policy 2: System can insert conversations
```sql
CREATE POLICY "System can insert conversations"
ON conversations FOR INSERT
WITH CHECK (true);  -- Service role only
```

**Behavior**:
- ✅ Service role key ile sistem oluşturabilir
- ❌ Normal user oluşturamaz (JWT ile)

**Use Cases**:
- WhatsApp webhook yeni konuşma başlatır
- Background job cleanup

---

## 🛒 Table: orders

### Policy 1: Users can view own orders
```sql
CREATE POLICY "Users can view own orders"
ON orders FOR SELECT
USING (true);  -- TODO: buyer_id = auth.uid() OR seller_id = auth.uid()
```

**Production Behavior**:
```sql
USING (buyer_id = auth.uid() OR seller_id = auth.uid())
```
- ✅ Alıcı kendi siparişlerini görebilir
- ✅ Satıcı kendi satışlarını görebilir
- ❌ İlgisiz siparişleri göremez

**Use Cases**:
- "siparişlerimi göster"
- "satışlarımı listele"
- Order history

---

### Policy 2: System can create orders
```sql
CREATE POLICY "System can create orders"
ON orders FOR INSERT
WITH CHECK (true);  -- Service role only
```

**Behavior**:
- ✅ Service role ile sistem oluşturur
- ❌ Normal user direkt oluşturamaz

**Use Cases**:
- Payment confirmation sonrası order oluşturma
- Checkout flow

---

### Policy 3: Users can update own orders
```sql
CREATE POLICY "Users can update own orders"
ON orders FOR UPDATE
USING (true);  -- TODO: buyer_id = auth.uid() OR seller_id = auth.uid()
```

**Production Behavior**:
```sql
USING (buyer_id = auth.uid() OR seller_id = auth.uid())
```
- ✅ İlgili taraflar durumu güncelleyebilir
- Örn: Satıcı "completed" yapabilir

**Use Cases**:
- "siparişi tamamla"
- "iptali onayla"

---

## 🧠 Table: product_embeddings

### Policy 1: Anyone can view embeddings
```sql
CREATE POLICY "Anyone can view embeddings"
ON product_embeddings FOR SELECT
USING (true);
```

**Behavior**:
- ✅ Herkes okuyabilir (semantic search için)

---

### Policy 2: System can manage embeddings
```sql
CREATE POLICY "System can manage embeddings"
ON product_embeddings FOR ALL
USING (true)  -- Service role only
WITH CHECK (true);
```

**Behavior**:
- ✅ Service role key ile CRUD
- ❌ Normal user'lar yönetemez

**Use Cases**:
- Background job: Yeni ilan → embedding oluştur
- Update: İlan değişti → embedding yenile
- Delete: İlan silindi → embedding temizle

---

## 🖼️ Table: product_images

### Policy 1: Anyone can view product images
```sql
CREATE POLICY "Anyone can view product images"
ON product_images FOR SELECT
USING (true);
```

**Behavior**:
- ✅ Herkes image metadata'yı okuyabilir
- ✅ Public bucket ise görsel de erişilebilir

---

### Policy 2: Users can manage own product images
```sql
CREATE POLICY "Users can manage own product images"
ON product_images FOR ALL
USING (
    EXISTS (
        SELECT 1 FROM listings
        WHERE listings.id = product_images.listing_id
        -- AND listings.user_id = auth.uid()  -- TODO: Enable with auth
    )
);
```

**Production Behavior**:
```sql
USING (
    EXISTS (
        SELECT 1 FROM listings
        WHERE listings.id = product_images.listing_id
        AND listings.user_id = auth.uid()
    )
)
```
- ✅ İlan sahibi kendi ilanının görsellerini yönetebilir
- ❌ Başkasının görsellerine dokunamaz

**Use Cases**:
- "ilan fotoğrafı ekle"
- "3. resmi sil"
- "ana görseli değiştir"

---

## 🔔 Table: notifications

### Policy 1: Users can view own notifications
```sql
CREATE POLICY "Users can view own notifications"
ON notifications FOR SELECT
USING (true);  -- TODO: user_id = auth.uid()
```

**Production Behavior**:
```sql
USING (user_id = auth.uid())
```
- ✅ Sadece kendi bildirimlerini görebilir

---

### Policy 2: System can create notifications
```sql
CREATE POLICY "System can create notifications"
ON notifications FOR INSERT
WITH CHECK (true);  -- Service role only
```

**Behavior**:
- ✅ Service role ile sistem gönderir

**Use Cases**:
- "Yeni mesaj var" bildirimi
- "İlanınız satıldı" notification
- "Fiyat düştü" alert

---

### Policy 3: Users can update own notifications
```sql
CREATE POLICY "Users can update own notifications"
ON notifications FOR UPDATE
USING (true);  -- TODO: user_id = auth.uid()
```

**Production Behavior**:
```sql
USING (user_id = auth.uid())
```
- ✅ Kendi bildirimini "read" yapabilir

**Use Cases**:
- Mark as read
- Archive notification

---

## 🗄️ Storage Buckets

### product-images (Public Bucket)

#### Policy 1: Anyone can view
```sql
CREATE POLICY "Anyone can view product images"
ON storage.objects FOR SELECT
USING (bucket_id = 'product-images');
```

**Behavior**:
- ✅ Public URL herkes tarafından erişilebilir
- ✅ CDN friendly

---

#### Policy 2: Authenticated upload/delete
```sql
CREATE POLICY "Users can upload/delete own images"
ON storage.objects FOR INSERT
WITH CHECK (
    bucket_id = 'product-images' AND
    auth.role() = 'authenticated'
);

CREATE POLICY "Users can delete own images"
ON storage.objects FOR DELETE
USING (
    bucket_id = 'product-images' AND
    auth.uid()::text = (storage.foldername(name))[1]
);
```

**Behavior**:
- ✅ Path convention: `{user_id}/{listing_id}/image.jpg`
- ✅ User sadece kendi folder'ındaki dosyaları silebilir

---

### user-documents (Private Bucket)

#### Policies: View/Upload/Update/Delete Own Documents
```sql
-- Folder-based access control
USING (
    bucket_id = 'user-documents' AND
    auth.uid()::text = (storage.foldername(name))[1]
)
```

**Behavior**:
- ✅ Path: `{user_id}/invoice.pdf`
- ✅ Sadece kendi folder'ına erişebilir
- ❌ Public access YOK
- ✅ Signed URL ile temporary sharing

---

## 🔧 Implementation Checklist

### Phase 1: Current (Development)
- [x] Tüm tablolar RLS enabled
- [x] Development policy'ler (`true`) aktif
- [x] Service role key ile bypass
- [ ] **CRITICAL**: Tools'a `user_id` parametresi ekle

### Phase 2: WhatsApp Auth Integration
- [ ] Supabase Auth setup
- [ ] WhatsApp → JWT mapping
- [ ] Session management
- [ ] Replace all `true` with `auth.uid()`

### Phase 3: Testing
- [ ] Test user oluştur
- [ ] JWT token ile test
- [ ] Negative test: Başkasının verisine erişim dene
- [ ] Policy violation error handling

### Phase 4: Production
- [ ] Enable all `auth.uid()` policies
- [ ] Remove development policies
- [ ] Audit logging
- [ ] Rate limiting

---

## 🐛 Common Issues

### Issue: "new row violates row-level security policy"
```
ERROR: new row violates row-level security policy for table "listings"
```

**Cause**: `WITH CHECK` condition failed

**Development Fix**: Policy'de `true` var mı kontrol et

**Production Fix**: 
```sql
-- user_id eşleşiyor mu?
WITH CHECK (user_id = auth.uid())
```

---

### Issue: "permission denied for table"
```
ERROR: permission denied for table listings
```

**Cause**: RLS enabled ama policy yok

**Fix**: Policy ekle veya:
```sql
ALTER TABLE listings DISABLE ROW LEVEL SECURITY;  -- ⚠️ Only dev!
```

---

### Issue: "null value in column user_id violates not-null constraint"
```
ERROR: null value in column "user_id" violates not-null constraint
```

**Cause**: Tool'da user_id gönderilmemiş

**Current State**: `insert_listing`, `update_listing` tools'da eksik

**Fix**: 
```python
# tools/insert_listing.py
def insert_listing(
    user_id: str,  # ← EKLE
    title: str,
    price: float,
    ...
):
    payload = {
        "user_id": user_id,  # ← EKLE
        "title": title,
        ...
    }
```

---

## 📚 Related Documentation

- [complete_schema.sql](./complete_schema.sql) - Full database schema
- [STORAGE_BUCKETS.md](./STORAGE_BUCKETS.md) - Storage configuration
- [Supabase RLS Docs](https://supabase.com/docs/guides/auth/row-level-security)

---

## 🎯 Next Steps

1. **URGENT**: Add `user_id` parameter to tools
   - `insert_listing.py`
   - `update_listing.py`
   - Test with UUID: `a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11`

2. **WhatsApp Phase**: 
   - Implement auth
   - Map phone → user_id
   - Update all policies

3. **Production**:
   - Enable real RLS
   - Security audit
   - Penetration testing
