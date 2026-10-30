"""The single owner of area names: Booli tokens, cleaned names, model keys, display names.

Three forms of one area, from raw to served:

- ``extract_area_token``: the area token in a Booli ``Type · Area · Municipality`` string.
- ``clean_area_name``: the Swedish-cased, consolidated name ingestion stores in ``area``.
- ``normalize_area_for_model``: the ASCII slug the model trains and serves on.
- ``get_display_name``: the Swedish display name for a model slug.

``tests/test_areas.py`` pins every form against a golden file.
"""

from __future__ import annotations

import re

from estate_value_index.utils.narrowing import is_missing

_NBSP_VARIANTS = tuple(chr(c) for c in (0xA0, 0x202F, 0x2009, 0xFEFF))
_ESCAPED_NBSP_VARIANTS = ("\\xa0", "\\u202f", "\\u00a0", "&nbsp;")

_GENERIC_TOKENS = frozenset(
    {
        "stockholm",
        "stockholms län",
        "stockholms kommun",
        "stockholms stad",
        "län",
        "kommun",
        "stad",
        "lägenhet",
        "villa",
        "radhus",
        "bostadsrätt",
    }
)


def normalize_text(value: object) -> str:
    """Collapse whitespace, NBSP variants, and HTML entities to a single space."""

    if not value:
        return ""
    text = str(value)
    for literal in _ESCAPED_NBSP_VARIANTS:
        text = text.replace(literal, " ")
    for char in _NBSP_VARIANTS:
        text = text.replace(char, " ")
    return re.sub(r"\s+", " ", text).strip()


def is_generic_token(token: object) -> bool:
    """Return True for tokens that are property types or broad regions, not areas."""

    if not token:
        return True
    return str(token).strip().lower() in _GENERIC_TOKENS


def extract_area_token(area_field: object) -> str:
    """Extract the area name from a Booli ``Type · Area · Municipality`` string.

    Single source of truth for tokenisation: shared by ingestion-time cleaning
    (which keeps the Swedish-cased token) and ML-time normalisation (which
    transliterates to an ASCII slug).
    """

    if not area_field:
        return ""

    text = normalize_text(area_field)
    parts = re.split(r"\s*·\s*", text)

    if len(parts) >= 2:
        tokens = [t for t in parts if t]
        filtered = [t for t in tokens if not is_generic_token(t)]
        if filtered:
            return filtered[-1]
        if len(tokens) >= 3 and tokens[-1].lower() == "stockholm":
            return tokens[-2]
        return tokens[0]

    return text


def clean_area_name(area_field: object) -> str:
    """Ingestion-time area name: Swedish-cased, consolidated, spelling-fixed. ``""`` if none."""
    area = extract_area_token(area_field)

    if not area:
        return ""

    # Remove quotes
    area = area.strip('"').strip()

    # Area consolidation mappings (apply first)
    area_consolidations = {
        "Solna kommun": "Solna",
        "Frösunda": "Solna",
        "Sundbyberg/Duvbo": "Sundbyberg",
        "Sundbybergs kommun": "Sundbyberg",
        "Rissne/Ursvik": "Sundbyberg",
        "Kristineberg": "Kungsholmen",
    }

    for original, consolidated in area_consolidations.items():
        if area == original:
            area = consolidated
            break

    # Fix common spelling errors
    spelling_fixes = {
        "Vasasatan": "Vasastan",
        "Kungholmen": "Kungsholmen",
        "Östemalm": "Östermalm",
        "Strockholm": "Stockholm",
        "Hagastan": "Hagastaden",
    }

    for wrong, correct in spelling_fixes.items():
        if wrong in area:
            area = area.replace(wrong, correct)

    # Handle "Söder" abbreviation
    if area == "Söder" or area.startswith("Söder "):
        area = area.replace("Söder", "Södermalm", 1)

    # Standardize compound areas
    if "/" in area:
        parts = area.split("/")
        major_districts = [
            "Vasastan",
            "Kungsholmen",
            "Södermalm",
            "Östermalm",
            "Norrmalm",
        ]
        for district in reversed(major_districts):
            if any(district in p for p in parts):
                return district

    return area


_SWEDISH_CHAR_MAP = {"ö": "o", "ä": "a", "å": "a", "Ö": "o", "Ä": "a", "Å": "a"}


def transliterate_swedish(text: object) -> str | None:
    """Convert Swedish characters to ASCII equivalents and clean for LightGBM compatibility.

    Returns None for missing values to preserve NA semantics in tests/pipelines.
    """
    if is_missing(text):
        return None

    text = str(text).lower()
    for swedish_char, ascii_char in _SWEDISH_CHAR_MAP.items():
        text = text.replace(swedish_char, ascii_char)

    text = re.sub(r"[^a-zA-Z0-9_]", "_", text)
    text = re.sub(r"_+", "_", text)
    return text.strip("_")


def extract_area_name(area_string: object) -> str | None:
    """Extract the ASCII area key from a Booli ``Type · Area · Municipality`` string.

    Tokenisation uses :func:`extract_area_token`, then transliterates the token to
    the slug the model expects. Returns None for missing inputs.
    """
    if is_missing(area_string):
        return None

    token = extract_area_token(area_string)
    if not token:
        return None
    return transliterate_swedish(token)


def normalize_area_for_model(area: object) -> str:
    """Return the area key used in training and inference (ASCII slug, Booli-safe).

    Handles Booli-style ``Lägenhet · Södermalm · Stockholm`` via ``extract_area_name``.
    Missing or empty areas map to ``"unknown"``.
    """
    extracted = extract_area_name(area)
    if extracted is None or extracted == "":
        return "unknown"
    return extracted


AREA_DISPLAY_NAMES = {
    # Areas requiring Swedish character corrections
    "sodermalm": "Södermalm",
    "ostermalm": "Östermalm",
    "gardet": "Gärdet",
    "hammarby_sjostad": "Hammarby Sjöstad",
    "sodermalm_katarina": "Södermalm Katarina",
    "sodermalm_hogalid": "Södermalm Högalid",
    "sodermalm_sofia": "Södermalm Sofia",
    "arsta": "Årsta",
    "grondal": "Gröndal",
    "sodermalm_maria": "Södermalm Maria",
    "norra_djurgardsstaden": "Norra Djurgårdsstaden",
    "fredhall": "Fredhäll",
    # Areas with correct spellings (no special characters needed)
    "vasastan": "Vasastan",
    "kungsholmen": "Kungsholmen",
    "liljeholmen": "Liljeholmen",
    "bromma": "Bromma",
    "norrmalm": "Norrmalm",
    "liljeholmskajen": "Liljeholmskajen",
    "nacka": "Nacka",
    "birkastan": "Birkastan",
    "hornstull": "Hornstull",
    "kungsholmen_fridhemsplan": "Kungsholmen Fridhemsplan",
    "gamla_stan": "Gamla Stan",
    "johanneshov": "Johanneshov",
    "hornsbergs_strand": "Hornsbergs Strand",
    "vasastan_odenplan": "Vasastan Odenplan",
    "ekhagen": "Ekhagen",
    "hagastaden": "Hagastaden",
    "reimersholme": "Reimersholme",
    "solna": "Solna",
    "sundbyberg": "Sundbyberg",
    "rasunda": "Råsunda",
    "enskede_arsta_vantor": "Enskede-Årsta-Vantör",
    # Note: Kristineberg consolidated into Kungsholmen
    # Note: Frösunda consolidated into Solna
}


def get_display_name(area_key: str) -> str:
    """Convert a model area key to its Swedish display name."""
    if not area_key:
        return "Unknown"
    return AREA_DISPLAY_NAMES.get(area_key) or area_key.replace("_", " ").title()
