# Market Price Agent - Roadmap

## 🎯 Mevcut Durum (v1.0)
**Sistem:** Supabase Cache (market_price_snapshots tablosu)
- Jaccard similarity ile ürün eşleştirme
- Haftalık Perplexity API snapshot (frontend tarafında)
- Backend: Sadece DB query (hızlı, stabil)

###장점:
✅ Hızlı (DB okuma)
✅ Maliyet düşük (1 haftalık cache)
✅ Perplexity API down olsa sistem çalışır
✅ Offline çalışabilir

### Eksikler:
❌ Real-time piyasa değişimlerini takip etmez
❌ Yeni/niş ürünler için veri yok ise başarısız
❌ 1 haftalık gecikme (snapshot güncellenmezse)

---

## 🚀 Phase 2: Hybrid Sistem (Cache + Fallback API)

### Mimari:
```
1. İlk önce cache'e bak (market_price_snapshots)
   ↓ Bulunamadı mı?
2. Perplexity API real-time çağır (backend'den)
   ↓
3. Sonucu cache'e ekle (future queries için)
```

### Implementasyon:
```python
async def get_market_price_estimate_v2(
    title: str,
    category: str,
    condition: str = "used",
    use_realtime: bool = False  # Yeni parametre
):
    # 1. Cache'ten dene
    cached = query_cache(title, category, similarity_threshold=0.5)
    
    if cached and cached['confidence'] > 0.7:
        return cached  # Yeterince iyi eşleşme
    
    # 2. Real-time fallback (eğer enabled ise)
    if use_realtime:
        realtime = await perplexity_realtime_search(title, category)
        if realtime['success']:
            # Cache'e kaydet
            save_to_cache(realtime)
            return realtime
    
    # 3. Cache'te zayıf eşleşme varsa onu döndür
    if cached:
        return cached
    
    # 4. Hiç veri yok
    return {"success": False, "error": "No data found"}
```

### Maliyet Kontrolü:
```python
# Agent instructions'a ekle:
"""
market_price_tool:
- Her zaman önce cache'ten dene
- Sadece confidence < 0.5 ise realtime API çağır
- Realtime çağrı sayısını limit (günlük 100 çağrı)
"""
```

---

## 🔮 Phase 3: ML-Powered Price Prediction

### Vision:
Cache + Perplexity yerine **kendi ML modelimiz**

### Data Pipeline:
```
1. Sitedeki ilanlar (listings table)
   ↓
2. Haftalık batch job: Fiyat trendlerini analiz et
   ↓
3. ML model: Kategori/marka/durum → Tahmini fiyat
   ↓
4. Model sonuçlarını cache'e yaz
```

### Model Architecture:
```python
Input Features:
- category (one-hot encoded)
- brand (embedding)
- condition (ordinal: 0-1-2)
- location (city, optional)
- year (for vehicles/electronics)
- metadata (brand, model, storage, etc.)

Output:
- predicted_price (regression)
- confidence_score (0-1)
```

###장점:
- ✅ API dependency yok (tamamen internal)
- ✅ Sitedeki GERÇEK fiyatlara dayalı (Perplexity'den daha doğru)
- ✅ Trend analizi (fiyat artıyor mu, düşüyor mu?)

---

## 📋 Implementation Priority

### 🟢 Phase 1 (DONE):
✅ Supabase cache sistemi
✅ Jaccard similarity matching
✅ Condition multipliers

### 🟡 Phase 2 (Next 3 months):
🔲 Perplexity API backend entegrasyonu (fallback)
🔲 Realtime search rate limiting
🔲 Cache miss tracking (hangi ürünler için veri yok?)
🔲 Agent'a "use_realtime" parametresi ekle

### 🔴 Phase 3 (6+ months):
🔲 Internal listings fiyat dataseti oluştur
🔲 ML model training pipeline
🔲 Batch prediction job (weekly)
🔲 A/B test: Cache vs ML vs Perplexity

---

## 🔧 Quick Wins (Şu an için)

### Backend'e Perplexity API entegrasyonu:
```python
# tools/market_price_tool.py'ye ekle

async def perplexity_realtime_search(title: str, category: str):
    """Real-time Perplexity API search (fallback için)"""
    # Edge Function'dan kopyala
    # Rate limit: 100/day
    # Cache sonucu
    pass
```

### Frontend → Backend handoff:
```javascript
// Frontend: Snapshot oluştururken backend'e de kaydet
await fetch('/api/market-price-snapshot', {
  method: 'POST',
  body: JSON.stringify(snapshot_data)
})
```

---

## 📝 Notes

**Şu anki sistemin gücü:**
- Supabase cache sistemi zaten çok iyi
- Perplexity API haftalık snapshot yeterli
- Backend hızlı ve stabil

**Ne zaman Phase 2'ye geçmeli?**
- Cache miss oranı %20'yi geçerse
- Kullanıcılar "fiyat öner" çok kullanıyorsa
- Niş ürünler için veri eksikliği belirginse

**Ne zaman Phase 3'e geçmeli?**
- Sitede 10K+ ilan olduğunda
- ML expertise takımda olduğunda
- Perplexity API maliyeti yüksek geliyorsa
