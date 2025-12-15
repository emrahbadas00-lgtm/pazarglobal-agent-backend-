"""
Market Price Snapshot Tool
Cache'lenmiş piyasa verilerinden benzer ürünleri bulup fiyat tahmini yapar.
"""

from typing import Dict, Any, cast  # type: ignore
import os
from supabase import create_client, Client


def normalize_product_key(title: str, category: str) -> str:
    """Product key normalizasyonu (frontend ile aynı)"""
    # Türkçe karakter dönüşümü
    tr_map = {
        'ç': 'c', 'Ç': 'C', 'ğ': 'g', 'Ğ': 'G',
        'ı': 'i', 'I': 'I', 'İ': 'I', 'i': 'i',
        'ö': 'o', 'Ö': 'O', 'ş': 's', 'Ş': 'S',
        'ü': 'u', 'Ü': 'U'
    }
    
    normalized = title
    for tr_char, en_char in tr_map.items():
        normalized = normalized.replace(tr_char, en_char)
    
    normalized = normalized.lower()
    
    # Stop words
    stop_words = [
        'satilik', 'temiz', 'bakimli', 'orjinal', 'orijinal',
        'az', 'kullanilmis', 'sifir', 'ayarinda', 'gibi',
        'hatasiz', 'boyasiz', 'degisensiz', 'garantili',
        'acil', 'ucuz', 'uygun', 'firsat', 'son', 'model',
        'yeni', 'ikinci', 'el', '2.el', 'ikinciel'
    ]
    
    for word in stop_words:
        normalized = normalized.replace(word, '')
    
    # Özel karakterleri temizle
    import re
    normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
    normalized = re.sub(r'\s+', ' ', normalized).strip()
    
    # Category key
    category_key = re.sub(r'[^a-z0-9]', '_', category.lower())
    category_key = re.sub(r'_+', '_', category_key)
    
    words = [w for w in normalized.split() if w]
    product_key = '_'.join(words)
    
    return f"{category_key}_{product_key}"


def calculate_similarity(key1: str, key2: str) -> float:
    """Jaccard similarity ile ürün benzerliği hesapla"""
    set1 = set(key1.split('_'))
    set2 = set(key2.split('_'))
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


def get_market_price_estimate(
    title: str,
    category: str,
    condition: str = "Az Kullanılmış",
    description: str = "",
    similarity_threshold: float = 0.5
) -> Dict[str, Any]:
    """
    Cache'lenmiş piyasa verilerinden benzer ürünleri bulup fiyat tahmini yapar.
    
    Args:
        title: Ürün başlığı
        category: Kategori
        condition: Ürün durumu
        description: Ürün açıklaması (opsiyonel)
        similarity_threshold: Benzerlik eşiği (0-1)
    
    Returns:
        Dict with 'success', 'global_market_price', 'similar_products', 'confidence'
    """
    try:
        # Supabase client
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        
        if not supabase_url or not supabase_key:
            return {
                "success": False,
                "error": "Supabase credentials not found"
            }
        
        supabase: Client = create_client(supabase_url, supabase_key)
        
        # Product key oluştur
        search_key = normalize_product_key(title, category)
        print(f"🔍 Searching for similar products: {search_key}")
        
        # Cache'ten kategori bazlı veriyi çek
        response = supabase.table("market_price_snapshots")\
            .select("*")\
            .eq("category", category)\
            .execute()
        
        if not response.data:
            return {
                "success": False,
                "error": f"No cached market data found for category: {category}"
            }
        
        # Benzer ürünleri bul
        similar_products: list[Dict[str, Any]] = []
        for item in response.data:
            if not isinstance(item, dict):
                continue
            
            # Type-safe dictionary access
            product_key = item.get('product_key', '')
            if not product_key:
                continue
                
            similarity = calculate_similarity(search_key, str(product_key))
            
            if similarity >= similarity_threshold:
                # Safe type conversion for numeric fields
                min_price_val = item.get('min_price', 0)
                max_price_val = item.get('max_price', 0)
                avg_price_val = item.get('avg_price', 0)
                confidence_val = item.get('confidence', 0)
                query_count_val = item.get('query_count', 0)
                
                similar_products.append({
                    'product_key': str(item.get('product_key', '')),
                    'title': str(item.get('title', '')),
                    'min_price': float(min_price_val) if isinstance(min_price_val, (int, float, str)) else 0.0,
                    'max_price': float(max_price_val) if isinstance(max_price_val, (int, float, str)) else 0.0,
                    'avg_price': float(avg_price_val) if isinstance(avg_price_val, (int, float, str)) else 0.0,
                    'confidence': float(confidence_val) if isinstance(confidence_val, (int, float, str)) else 0.0,
                    'similarity': similarity,
                    'last_updated': str(item.get('last_updated_at', '')),
                    'query_count': int(query_count_val) if isinstance(query_count_val, (int, str)) else 0
                })
        
        if not similar_products:
            return {
                "success": False,
                "error": f"No similar products found (threshold: {similarity_threshold})"
            }
        
        # En benzer ürünleri önce sırala (similarity + confidence)
        def sort_key(x: Dict[str, Any]) -> float:
            sim = x.get('similarity', 0)
            conf = x.get('confidence', 0)
            return float(sim) * 0.6 + float(conf) * 0.4
        
        similar_products.sort(key=sort_key, reverse=True)
        
        # Top 3 benzer ürünü al
        top_matches: list[Dict[str, Any]] = similar_products[:3]
        
        # Weighted average fiyat hesapla
        total_weight = sum(float(m.get('similarity', 0)) for m in top_matches)
        if total_weight == 0:
            total_weight = 1.0
        
        weighted_min = sum(float(m.get('min_price', 0)) * float(m.get('similarity', 0)) for m in top_matches) / total_weight
        weighted_avg = sum(float(m.get('avg_price', 0)) * float(m.get('similarity', 0)) for m in top_matches) / total_weight
        weighted_max = sum(float(m.get('max_price', 0)) * float(m.get('similarity', 0)) for m in top_matches) / total_weight
        
        # Durum katsayısı uygula
        condition_multipliers = {
            'Sıfır': 1.0,
            'Az Kullanılmış': 0.85,
            'İyi Durumda': 0.70,
            'Orta Durumda': 0.55
        }
        multiplier = condition_multipliers.get(condition, 0.70)
        
        final_price = int(weighted_avg * multiplier)
        min_price = int(weighted_min * multiplier)
        max_price = int(weighted_max * multiplier)
        
        # Average confidence
        avg_confidence = sum(float(m.get('confidence', 0)) for m in top_matches) / max(len(top_matches), 1)
        
        return {
            "success": True,
            "global_market_price": {
                "min": min_price,
                "max": max_price,
                "average": final_price,
                "confidence": round(avg_confidence, 2),
                "condition_multiplier": multiplier
            },
            "similar_products": [
                {
                    "title": str(m.get('title', 'Unknown')),
                    "price_range": f"{int(float(m.get('min_price', 0)))}-{int(float(m.get('max_price', 0)))} ₺",
                    "similarity": f"{float(m.get('similarity', 0))*100:.0f}%",
                    "last_updated": str(m.get('last_updated', ''))
                }
                for m in top_matches
            ],
            "total_matches": len(similar_products),
            "search_key": search_key
        }
        
    except Exception as e:
        print(f"❌ Error in get_market_price_estimate: {str(e)}")
        return {
            "success": False,
            "error": str(e)
        }


# Tool definition for agent
TOOL_DEFINITION = {
    "type": "function",
    "function": {
        "name": "get_market_price_estimate",
        "description": "Cache'lenmiş global piyasa verilerinden benzer ürünleri bulup fiyat tahmini yapar. Kullanıcı fiyat önerisi istediğinde bu tool'u kullan.",
        "parameters": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Ürün başlığı (örn: 'iPhone 14 Pro Max 256GB')"
                },
                "category": {
                    "type": "string",
                    "description": "Ürün kategorisi (örn: 'Elektronik', 'Otomotiv')"
                },
                "condition": {
                    "type": "string",
                    "description": "Ürün durumu",
                    "enum": ["Sıfır", "Az Kullanılmış", "İyi Durumda", "Orta Durumda"]
                },
                "description": {
                    "type": "string",
                    "description": "Ürün açıklaması (opsiyonel, daha iyi eşleşme için)"
                },
                "similarity_threshold": {
                    "type": "number",
                    "description": "Benzerlik eşiği (0-1), varsayılan 0.5",
                    "default": 0.5
                }
            },
            "required": ["title", "category"]
        }
    }
}
