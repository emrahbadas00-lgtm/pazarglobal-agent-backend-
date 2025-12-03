# tools/clean_price.py

import re
from typing import Optional, Dict


def clean_price(price_text: Optional[str]) -> Dict[str, Optional[int]]:
    """
    Türkçe fiyat formatlarını temizler:
    - "22 bin" → 22000
    - "1,5 milyon" → 1500000
    - "54,999 TL" → 54999
    - "45.000" → 45000
    
    Args:
        price_text: Temizlenecek fiyat metni
        
    Returns:
        Dict içinde clean_price anahtarı ile temizlenmiş fiyat (int veya None)
    """
    if not price_text:
        return {"clean_price": None}
    
    # Lowercase normalize
    text = price_text.lower().strip()
    
    # "bin" ve "milyon" desteği
    multiplier = 1
    if "milyon" in text:
        multiplier = 1_000_000
        text = text.replace("milyon", "")
    elif "bin" in text:
        multiplier = 1_000
        text = text.replace("bin", "")
    
    # Sadece rakam, virgül ve nokta bırak
    cleaned = re.sub(r"[^\d,.]", "", text)
    
    # Virgül ve noktayı kaldır (Türkçe: 54.999 veya 54,999 → 54999)
    cleaned = cleaned.replace(",", "").replace(".", "")
    
    if not cleaned:
        return {"clean_price": None}
    
    try:
        number = int(cleaned) * multiplier
    except ValueError:
        return {"clean_price": None}
    
    return {"clean_price": number}
