"""Search composer that unifies deterministic listing queries."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Sequence

from tools.search_listings import search_listings
from services.category_library import classify_category, extract_search_tokens


@dataclass
class ComposerListing:
    id: str
    title: str
    price: Optional[int]
    location: Optional[str]
    condition: Optional[str]
    category: Optional[str]
    description: Optional[str]
    signed_images: List[str]
    owner_name: Optional[str]
    owner_phone: Optional[str]
    raw: Dict[str, Any]


class SearchComposerAgent:
    """High-level orchestrator that runs multiple search strategies in parallel."""

    def __init__(self, *, preview_limit: int = 5, fetch_limit: int = 30):
        self.preview_limit = preview_limit
        self.fetch_limit = fetch_limit

    async def orchestrate_search(
        self,
        *,
        user_message: str,
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        message = (user_message or "").strip()
        if not message:
            return {
                "success": False,
                "message": "Ne aramak istediğinizi yazar mısınız?",
                "listings": [],
                "listings_full": [],
                "total": 0,
                "category": None,
                "search_terms": [],
            }

        limit = limit or self.fetch_limit
        inferred_category = classify_category(message)
        search_terms = extract_search_tokens(message, max_tokens=6)
        search_text = self._build_search_text(search_terms)
        price_range = self._extract_price_range(message)

        tasks = []
        if inferred_category:
            tasks.append(
                self._run_search(
                    category=inferred_category,
                    search_text=search_text,
                    limit=limit,
                    source="category",
                )
            )
        if price_range:
            tasks.append(
                self._run_search(
                    category=inferred_category,
                    search_text=search_text,
                    min_price=price_range[0],
                    max_price=price_range[1],
                    limit=limit,
                    source="price",
                )
            )
        # Content search is always included as a fallback
        tasks.append(
            self._run_search(
                category=None if inferred_category else None,
                query=self._build_query_from_terms(search_terms),
                search_text=search_text,
                limit=limit,
                source="content",
            )
        )

        responses = await asyncio.gather(*tasks, return_exceptions=True)

        aggregated: List[ComposerListing] = []
        total_candidates: List[int] = []
        for resp in responses:
            if isinstance(resp, Exception):
                continue
            total_candidates.append(resp.get("total", 0))
            aggregated.extend(resp.get("listings", []))

        deduped = self._dedupe_listings(aggregated)
        preview = deduped[: self.preview_limit]
        total_estimate = max(total_candidates) if total_candidates else len(deduped)
        has_more = total_estimate > len(preview)

        cache_payload = self.build_cache_payload(deduped[: min(len(deduped), self.fetch_limit)])
        message_text = self._format_preview_message(
            preview,
            total_estimate,
            start_index=1,
            original_query=message,
            category_label=inferred_category,
            suggest_more=has_more,
            cache_payload=cache_payload,
        )

        return {
            "success": bool(preview),
            "message": message_text,
            "listings": preview,
            "listings_full": deduped[: limit],
            "total": total_estimate,
            "category": inferred_category,
            "search_terms": search_terms,
            "has_more": has_more,
            "cache_payload": cache_payload,
        }

    def format_preview_chunk(
        self,
        listings: Sequence[ComposerListing],
        *,
        total: int,
        start_index: int,
        original_query: str,
        category_label: Optional[str],
        suggest_more: bool,
        cache_payload: List[Dict[str, Any]],
    ) -> str:
        return self._format_preview_message(
            listings,
            total,
            start_index=start_index,
            original_query=original_query,
            category_label=category_label,
            suggest_more=suggest_more,
            cache_payload=cache_payload,
        )

    async def _run_search(
        self,
        *,
        category: Optional[str],
        query: Optional[str] = None,
        search_text: Optional[str] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        limit: int,
        source: str,
    ) -> Dict[str, Any]:
        resp = await search_listings(
            query=query,
            category=category,
            min_price=min_price,
            max_price=max_price,
            limit=limit,
            search_text=search_text,
        )
        if not isinstance(resp, dict) or not resp.get("success"):
            return {"total": 0, "listings": [], "source": source}

        listings_raw = resp.get("results") or []
        listings = [self._normalize_listing(item) for item in listings_raw if isinstance(item, dict)]
        listings = [lst for lst in listings if lst]
        return {
            "total": resp.get("total", len(listings)),
            "listings": listings,
            "source": source,
        }

    @staticmethod
    def _build_search_text(terms: Sequence[str], *, max_terms: int = 4) -> Optional[str]:
        if not terms:
            return None
        selected = terms[:max_terms]
        return " ".join(selected)

    @staticmethod
    def _build_query_from_terms(terms: Sequence[str]) -> Optional[str]:
        if not terms:
            return None
        primary_terms = [tok for tok in terms if len(tok) >= 3]
        if not primary_terms:
            primary_terms = list(terms)
        phrase = " ".join(primary_terms[:3]).strip()
        return phrase or None

    @staticmethod
    def _normalize_listing(item: Dict[str, Any]) -> Optional[ComposerListing]:
        listing_id = item.get("id")
        title = (item.get("title") or "").strip()
        if not listing_id or not title:
            return None
        signed_images: List[str] = []
        if isinstance(item.get("signed_images"), list):
            signed_images = [str(url) for url in item["signed_images"][:3]]
        return ComposerListing(
            id=str(listing_id),
            title=title,
            price=item.get("price"),
            location=item.get("location"),
            condition=item.get("condition"),
            category=item.get("category"),
            description=item.get("description"),
            signed_images=signed_images,
            owner_name=item.get("user_name") or item.get("owner_name"),
            owner_phone=item.get("user_phone") or item.get("owner_phone"),
            raw=item,
        )

    @staticmethod
    def _dedupe_listings(listings: Iterable[ComposerListing]) -> List[ComposerListing]:
        seen = set()
        ordered: List[ComposerListing] = []
        for listing in listings:
            if listing.id in seen:
                continue
            seen.add(listing.id)
            ordered.append(listing)
        return ordered

    @staticmethod
    def _format_price(value: Optional[int]) -> str:
        if value is None:
            return "Belirtilmemiş"
        return f"{value:,}".replace(",", ".") + " TL"

    def _format_preview_message(
        self,
        listings: Sequence[ComposerListing],
        total: int,
        *,
        start_index: int,
        original_query: str,
        category_label: Optional[str],
        suggest_more: bool,
        cache_payload: List[Dict[str, Any]],
    ) -> str:
        if not listings:
            return (
                f"🔍 '{original_query}' için sonuç bulamadım. "
                "Filtreleri genişletmek istersen haber ver."
            )

        header_parts: List[str] = []
        if category_label:
            header_parts.append(f"{category_label} kategorisinde")
        if total:
            header_parts.append(f"toplam {total} ilan bulundu")
        header = " ".join(header_parts) or "İlanları buldum"

        lines: List[str] = [f"🔍 {header}.", ""]
        for offset, listing in enumerate(listings, start=start_index):
            user_ref = listing.owner_name or listing.owner_phone or "İletişim yok"
            price_text = self._format_price(listing.price)
            location = listing.location or "Konum yok"
            lines.append(f"{offset}️⃣ {listing.title}")
            lines.append(f"   💰 {price_text} | 📍 {location} | 👤 {user_ref}")
        if suggest_more:
            lines.append("")
            lines.append("💡 Daha fazla ilan için 'daha fazla göster' diyebilirsin.")
        lines.append("")
        lines.append("💡 Detay için 'X nolu ilanı göster' yazman yeterli.")
        lines.append(f"[SEARCH_CACHE]{json.dumps(cache_payload, ensure_ascii=False)}")
        return "\n".join(lines)

    @staticmethod
    def build_cache_payload(listings: Sequence[ComposerListing]) -> List[Dict[str, Any]]:
        payload: List[Dict[str, Any]] = []
        for listing in listings:
            payload.append(
                {
                    "id": listing.id,
                    "title": listing.title,
                    "price": listing.price,
                    "location": listing.location,
                    "condition": listing.condition,
                    "category": listing.category,
                    "description": (listing.description or "")[:160],
                    # "signed_images": listing.signed_images,  # Removed: Twilio can't access signed URLs
                    "user_name": listing.owner_name,
                    "user_phone": listing.owner_phone,
                }
            )
        return payload

    @staticmethod
    def _extract_price_range(text: str) -> Optional[tuple[Optional[int], Optional[int]]]:
        lowered = text.lower()
        matches: List[tuple[int, int]] = []
        for match in re.finditer(r"(\d{1,3}(?:[\.\s]\d{3})+|\d+)(?:\s*(bin|k|milyon))?", lowered):
            value = SearchComposerAgent._parse_numeric_token(match.group(1), match.group(2))
            if value is None:
                continue
            matches.append((value, match.start()))
        if len(matches) >= 2:
            values = sorted(val for val, _ in matches[:2])
            return values[0], values[1]
        if len(matches) == 1:
            value, pos = matches[0]
            window = lowered[max(0, pos - 12): pos + 12]
            if any(word in window for word in ("alt", "alti", "max")):
                return (None, value)
            if any(word in window for word in ("üst", "usti", "ustu", "min")):
                return (value, None)
        return None

    @staticmethod
    def _parse_numeric_token(raw: Optional[str], suffix: Optional[str]) -> Optional[int]:
        if not raw:
            return None
        digits = re.sub(r"[\.\s]", "", raw)
        if not digits.isdigit():
            return None
        value = int(digits)
        if not suffix:
            return value
        suffix = suffix.strip()
        if suffix == "k" or suffix == "bin":
            return value * 1000
        if suffix == "milyon":
            return value * 1_000_000
        return value
