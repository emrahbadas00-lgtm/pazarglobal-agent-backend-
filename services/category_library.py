"""Deterministic category inference helpers.

This module adapts the category system documented in the "CATEGORY_AND_KEYWORDS"
architecture notes. It provides:

* Canonical category definitions (`CATEGORY_OPTIONS`).
* Keyword specs for deterministic classification (`CATEGORY_SPECS`).
* Helper functions like `classify_category` and `normalize_category_id` for
  both listing creation workflows and the search composer.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List, Optional, Tuple
import re


@dataclass(frozen=True)
class CategoryOption:
    id: str
    label: str


@dataclass(frozen=True)
class CategorySpec:
    label: str
    strong: Tuple[str, ...]
    weak: Tuple[str, ...] = ()


CATEGORY_OPTIONS: Tuple[CategoryOption, ...] = (
    CategoryOption(id="Emlak", label="Emlak"),
    CategoryOption(id="Otomotiv", label="Otomotiv"),
    CategoryOption(id="Elektronik", label="Elektronik"),
    CategoryOption(id="Ev & Yaşam", label="Ev & Yaşam"),
    CategoryOption(id="Moda & Aksesuar", label="Moda & Aksesuar"),
    CategoryOption(id="Anne, Bebek & Oyuncak", label="Anne, Bebek & Oyuncak"),
    CategoryOption(id="Spor & Outdoor", label="Spor & Outdoor"),
    CategoryOption(id="Hobi, Koleksiyon & Sanat", label="Hobi, Koleksiyon & Sanat"),
    CategoryOption(id="İş Makineleri & Sanayi", label="İş Makineleri & Sanayi"),
    CategoryOption(id="Yedek Parça & Aksesuar", label="Yedek Parça & Aksesuar"),
    CategoryOption(id="Hizmetler", label="Ustalar & Hizmetler"),
    CategoryOption(id="Eğitim & Kurs", label="Özel Ders & Eğitim"),
    CategoryOption(id="İş İlanları", label="İş İlanları"),
    CategoryOption(id="Dijital Ürün & Hizmetler", label="Dijital Ürün & Hizmetler"),
    CategoryOption(id="Diğer", label="Genel / Diğer"),
)

_CATEGORY_LABELS = {opt.label: opt.id for opt in CATEGORY_OPTIONS}
_CATEGORY_IDS = {opt.id: opt.id for opt in CATEGORY_OPTIONS}
_CATEGORY_LABEL_AND_ID = {**_CATEGORY_LABELS, **_CATEGORY_IDS}


_CATEGORY_SPECS: Tuple[CategorySpec, ...] = (
    CategorySpec(
        label="Otomotiv",
        strong=(
            "otomotiv",
            "otomobil",
            "araba",
            "araç",
            "arac",
            "vasita",
            "vasıta",
            "kamyonet",
            "kamyon",
            "motorsiklet",
            "motosiklet",
            "scooter",
            "atv",
            "pickup",
            "suv",
            "tekne",
            "jetski",
            "jet ski",
            "van",
        ),
        weak=(
            "bmw",
            "mercedes",
            "audi",
            "volkswagen",
            "renault",
            "fiat",
            "ford",
            "toyota",
            "honda",
            "hyundai",
            "kia",
            "peugeot",
            "citroen",
            "opel",
            "nissan",
            "volvo",
            "tofas",
            "togg",
            "tesla",
            "porsche",
            "jeep",
        ),
    ),
    CategorySpec(
        label="Elektronik",
        strong=(
            "elektronik",
            "telefon",
            "akilli",
            "smartphone",
            "iphone",
            "ipad",
            "macbook",
            "laptop",
            "notebook",
            "bilgisayar",
            "pc",
            "monitor",
            "ekran",
            "ps5",
            "playstation",
            "xbox",
            "kulaklik",
            "airpods",
            "kamera",
            "drone",
        ),
        weak=(
            "apple",
            "samsung",
            "xiaomi",
            "redmi",
            "huawei",
            "honor",
            "oppo",
            "realme",
            "lenovo",
            "hp",
            "dell",
            "asus",
            "msi",
            "lg",
            "sony",
            "canon",
        ),
    ),
    CategorySpec(
        label="Emlak",
        strong=(
            "emlak",
            "daire",
            "ev",
            "konut",
            "rezidans",
            "villa",
            "yazlik",
            "yazlık",
            "müstakil",
            "mustakil",
            "dubleks",
            "triplex",
            "arsa",
            "tarla",
            "dükkan",
            "dukkan",
            "ofis",
        ),
        weak=("metrekare", "m2", "tapu", "site", "siteli", "havuzlu", "kat"),
    ),
    CategorySpec(
        label="Moda & Aksesuar",
        strong=(
            "giyim",
            "aksesuar",
            "ayakkabi",
            "ayakkabı",
            "elbise",
            "mont",
            "ceket",
            "pantolon",
            "kazak",
            "çanta",
            "canta",
            "saat",
            "takı",
            "takim",
            "takım",
        ),
        weak=("nike", "adidas", "puma", "zara", "hm", "mango"),
    ),
    CategorySpec(
        label="Ev & Yaşam",
        strong=(
            "buzdolabi",
            "buzdolabı",
            "camasir",
            "çamaşır",
            "bulasik",
            "bulaşık",
            "kurutma",
            "klima",
            "firin",
            "fırın",
            "ocak",
            "mikrodalga",
            "mobilya",
            "koltuk",
            "kanepe",
            "masa",
            "sandalye",
            "yatak",
            "gardrop",
            "hali",
            "halı",
            "perde",
        ),
        weak=("arcelik", "beko", "bosch", "siemens", "vestel", "profilo", "regal", "altus"),
    ),
)

_TR_MAP = str.maketrans({
    "ç": "c",
    "ğ": "g",
    "ı": "i",
    "ö": "o",
    "ş": "s",
    "ü": "u",
    "Ç": "c",
    "Ğ": "g",
    "İ": "i",
    "Ö": "o",
    "Ş": "s",
    "Ü": "u",
})

_STOPWORDS = {
    "var",
    "mı",
    "mi",
    "musunuz",
    "musun",
    "bana",
    "bir",
    "acaba",
    "uygun",
    "satılık",
    "kiralık",
    "ilan",
    "ilanı",
    "ilanlar",
    "fiyat",
    "ne",
    "kaç",
    "kac",
}


def _norm(text: str) -> str:
    text = (text or "").strip().lower().translate(_TR_MAP)
    text = re.sub(r"[^0-9a-z&+]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _tokenize(text: str) -> List[str]:
    return [tok for tok in _norm(text).split(" ") if tok]


def _has_room_format(tokens: Iterable[str]) -> bool:
    return any(re.fullmatch(r"\d\+\d", tok) for tok in tokens)


def classify_category(text: str) -> Optional[str]:
    """Return canonical category ID inferred from free text."""

    tokens = _tokenize(text)
    if not tokens:
        return None

    token_set = set(tokens)

    # Emlak heuristic for room formats (2+1 vb)
    if _has_room_format(tokens):
        emlak_tokens = {
            "emlak",
            "daire",
            "ev",
            "konut",
            "villa",
            "rezidans",
            "apart",
            "bahce",
            "bahçe",
        }
        if token_set & emlak_tokens:
            return "Emlak"

    # Strong keywords
    for spec in _CATEGORY_SPECS:
        for strong in spec.strong:
            if strong in token_set:
                return spec.label

    # Weak keyword scoring
    best_label: Optional[str] = None
    best_score = 0
    for spec in _CATEGORY_SPECS:
        score = sum(1 for weak in spec.weak if weak in token_set)
        if spec.label == "Otomotiv" and score >= 1:
            has_year = any(re.fullmatch(r"(19|20)\d{2}", tok) for tok in tokens)
            has_km = any("km" in tok for tok in tokens)
            has_model_word = "model" in token_set
            if has_year or has_km or has_model_word:
                return spec.label
        if score > best_score >= 0:
            best_label = spec.label
            best_score = score
    if best_score >= 2:
        return best_label

    return None


def normalize_category_id(text: Optional[str]) -> Optional[str]:
    """Return canonical category id from arbitrary label text."""

    if not text:
        return None
    text_norm = _norm(text)
    for opt in CATEGORY_OPTIONS:
        if _norm(opt.id) == text_norm:
            return opt.id
        if _norm(opt.label) == text_norm:
            return opt.id
    return classify_category(text)


def extract_search_tokens(text: str, *, max_tokens: int = 5) -> List[str]:
    """Best-effort keyword extraction for search queries."""

    tokens = [tok for tok in _tokenize(text) if tok not in _STOPWORDS]
    seen = []
    for tok in tokens:
        if tok not in seen:
            seen.append(tok)
        if len(seen) >= max_tokens:
            break
    return seen
