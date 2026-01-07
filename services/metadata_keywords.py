"""Keyword generation utilities for listings.

This module produces deterministic keyword metadata that can later be used by the
search stack for token-based matching. The implementation mirrors the
"metadata_keywords" document from the v2 architecture notes so that both the
backend tools and LLM prompts can rely on the same behaviour.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
import json
import re

from loguru import logger

from .openai_client import get_openai_client


def _normalize_keyword(token: str) -> Optional[str]:
    token = (token or "").strip().lower()
    if not token:
        return None

    # Basic cleanup
    token = re.sub(r"\s+", " ", token)
    token = token.strip("-•,.;:()[]{}\"'“”‘’")

    # Avoid useless tokens
    if token in {"ürün", "esya", "eşya", "satılık", "satilik", "ikinci el", "2. el"}:
        return None
    if len(token) < 2:
        return None
    return token


def _dedupe_preserve_order(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        k = it.lower().strip()
        if not k or k in seen:
            continue
        out.append(it)
        seen.add(k)
    return out


async def generate_listing_keywords(
    *,
    title: str,
    category: str,
    description: str = "",
    condition: str = "",
    vision_product: Optional[Dict[str, Any]] = None,
    max_keywords: int = 12,
) -> Dict[str, Any]:
    """Generate Turkish keywords for a listing.

    Returns a dictionary with "keywords" (list[str]) and "keywords_text"
    (space-separated string). The call is best-effort—callers should handle
    empty lists gracefully if the LLM request fails.
    """

    title = (title or "").strip()
    category = (category or "").strip()
    description = (description or "").strip()
    condition = (condition or "").strip()

    if not title:
        return {"keywords": [], "keywords_text": ""}

    vision = vision_product if isinstance(vision_product, dict) else {}

    system = (
        "Sen bir ilan etiket/anahtar kelime üretim asistanısın. "
        "Çıktın SADECE JSON olmalı ve şu şemaya uymalı: "
        "{\"keywords\": [string, ...]}. "
        "Kurallar: Türkçe yaz; 6-12 arası anahtar kelime üret; hepsi küçük harf olsun; "
        "noktalama/emoji yok; tekrar yok. "
        "İstisna: emlak ilanlarında oda formatı gibi ifadeler (1+1, 2+1, 3+1 vb.) kullanılabilir. "
        "Sadece çok genel olmayan ama aramayı kolaylaştıran terimler üret: "
        "ürün türü, kategori, marka, model, varyant, eş anlamlı/üst sınıf terimler (ör: araba/otomobil/araç), "
        "ve ilgili kullanım alanı. "
        "Yasak: kişi bilgisi/telefon/konum, fiyat, seri numarası."
    )

    payload = {
        "title": title,
        "category": category,
        "description": description,
        "condition": condition,
        "vision": {
            "product": vision.get("product"),
            "category": vision.get("category"),
            "features": vision.get("features"),
        },
        "max_keywords": int(max_keywords),
    }

    user = (
        "Aşağıdaki ilan bilgisinden arama için anahtar kelimeler üret. "
        "Örnek: 'citroen c3' için 'araba', 'otomobil', 'araç' gibi üst terimler ekle.\n\n"
        "Eğer kategori emlak ise uygun oldukça şu tür terimleri ekle: villa, dubleks, triplex, havuzlu, 1+1/2+1 gibi oda formatları.\n\n"
        f"ILAN_JSON: {json.dumps(payload, ensure_ascii=False)}"
    )

    try:
        client = get_openai_client()
        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            temperature=0.2,
            max_tokens=250,
        )
        text = (resp.choices[0].message.content or "").strip()
        data = json.loads(text) if text else {}
        raw = data.get("keywords") if isinstance(data, dict) else None
        if not isinstance(raw, list):
            raw = []

        normed: List[str] = []
        for t in raw:
            kw = _normalize_keyword(str(t))
            if kw:
                normed.append(kw)
        normed = _dedupe_preserve_order(normed)
        normed = normed[: max(1, int(max_keywords))]

        return {
            "keywords": normed,
            "keywords_text": " ".join(normed),
        }
    except Exception as exc:  # pragma: no cover - network call fallback
        logger.warning(f"Keyword generation failed: {exc}")
        return {"keywords": [], "keywords_text": ""}
