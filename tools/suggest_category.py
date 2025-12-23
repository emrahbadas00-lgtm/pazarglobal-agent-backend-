# tools/suggest_category.py

"""
Category Suggestion Tool - AI-powered category inference
Use this tool to validate or suggest categories for listings
"""

from typing import Any, Dict, Optional


CATEGORY_KEYWORDS = {
    "Otomotiv": ["araba", "araç", "otomobil", "motor", "kamyon", "motorsiklet", "BMW", "Mercedes", "Volkswagen", "Renault", "Toyota", "Honda", "lastik", "aksesuar"],
    "Elektronik": ["telefon", "bilgisayar", "laptop", "tablet", "TV", "televizyon", "iPhone", "Samsung", "MacBook", "oyun konsolu", "PlayStation", "Xbox", "kulaklık", "şarj"],
    "Emlak": ["ev", "daire", "dubleks", "villa", "arsa", "işyeri", "ofis", "kiralık", "satılık", "bahçe", "site", "kat", "oda", "salon", "balkon"],
    "Mobilya": ["koltuk", "masa", "sandalye", "dolap", "yatak", "kanepe", "gardırop", "kitaplık", "konsol", "berjer", "köşe takımı"],
    "Giyim": ["ayakkabı", "bot", "spor ayakkabı", "mont", "kaban", "pantolon", "gömlek", "elbise", "takım elbise", "ceket", "tişört"],
    "Kozmetik & Bakım": ["kolonya", "kolonyağı", "parfüm", "koku", "deodorant", "şampuan", "sabun", "krem", "makyaj", "cilt bakımı", "saç bakımı", "tıraş"],
    "Spor & Outdoor": ["bisiklet", "scooter", "kamp", "çadır", "spor ekipmanı", "fitness", "dağ bisikleti", "kayak", "dalış"],
    "Hobi & Eğlence": ["müzik", "gitar", "piyano", "kitap", "roman", "koleksiyon", "pul", "bozuk para", "oyun"],
    "Anne & Bebek": ["bebek arabası", "mama sandalyesi", "oyuncak", "bebek odası", "emzirme", "bebek giysileri", "biberon"],
    "Hayvanlar": ["köpek", "kedi", "kuş", "akvaryum", "mama", "kafes", "evcil hayvan", "pet"],
    "Ev & Yaşam": ["mutfak", "tencere", "tabak", "çanak", "dekorasyon", "vazo", "lamba", "halı", "perde", "ev tekstili"],
}


async def suggest_category(
    title: str,
    description: Optional[str] = None,
    user_category: Optional[str] = None
) -> Dict[str, Any]:
    """
    Suggest appropriate category based on title and description.
    
    Args:
        title: Listing title
        description: Optional listing description
        user_category: Optional user-selected category (for validation)
        
    Returns:
        {
            "success": True,
            "suggested_category": "Otomotiv",
            "confidence": 0.95,
            "matches": ["araba", "BMW"],
            "is_correct": True  # If user_category matches suggestion
        }
    """
    
    text = (title + " " + (description or "")).lower()
    
    # Score each category based on keyword matches
    scores = {}
    matched_keywords = {}
    
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        matches = []
        for keyword in keywords:
            if keyword.lower() in text:
                score += 1
                matches.append(keyword)
        
        if score > 0:
            scores[category] = score
            matched_keywords[category] = matches
    
    # No matches found
    if not scores:
        return {
            "success": True,
            "suggested_category": None,
            "confidence": 0.0,
            "matches": [],
            "message": "No clear category match found. Using generic category recommended."
        }
    
    # Find best match
    best_category = max(scores, key=scores.get)
    best_score = scores[best_category]
    total_keywords = len(CATEGORY_KEYWORDS[best_category])
    confidence = min(best_score / 3.0, 1.0)  # Cap at 1.0
    
    result = {
        "success": True,
        "suggested_category": best_category,
        "confidence": round(confidence, 2),
        "matches": matched_keywords[best_category],
    }
    
    # Validate user's category if provided
    if user_category:
        is_correct = user_category.lower() in best_category.lower() or best_category.lower() in user_category.lower()
        result["is_correct"] = is_correct
        result["user_category"] = user_category
        
        if not is_correct:
            result["warning"] = f"User selected '{user_category}' but AI suggests '{best_category}'"
    
    return result
