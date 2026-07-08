from __future__ import annotations

import re
import unicodedata

import pandas as pd

"""Description-derived listing quality features."""


_WORD_RE = re.compile(r"[a-z0-9]+")

_RENOVATED_PHRASES = (
    "nyrenoverad",
    "nyrenoverat",
    "renoverad",
    "renoverat",
    "totalrenoverad",
    "totalrenoverat",
    "newly renovated",
    "renovated",
    "updated",
)
_MODERN_KITCHEN_PHRASES = (
    "nytt kok",
    "nyrenoverat kok",
    "renoverat kok",
    "modernt kok",
    "modern kitchen",
    "new kitchen",
    "renovated kitchen",
)
_MODERN_BATHROOM_PHRASES = (
    "nytt badrum",
    "nyrenoverat badrum",
    "renoverat badrum",
    "modernt badrum",
    "modern bathroom",
    "new bathroom",
    "renovated bathroom",
)
_VIEW_PHRASES = (
    "utsikt",
    "sjoutsikt",
    "havsglimt",
    "vattenutsikt",
    "panoramavy",
    "view",
    "water view",
)
_QUIET_PHRASES = (
    "lugnt lage",
    "lugnt omrade",
    "tyst lage",
    "stillsamt",
    "rofullt",
    "quiet",
    "calm area",
)
_NEEDS_RENOVATION_PHRASES = (
    "renoveringsbehov",
    "moderniseringsbehov",
    "renoveras",
    "originalskick",
    "fixer upper",
    "needs renovation",
    "in need of renovation",
)
_LUXURY_PHRASES = (
    "exklusiv",
    "exklusivt",
    "pakostad",
    "premium",
    "luxe",
    "lyx",
    "sekelskifte",
    "takhojd",
    "kakelugn",
    "terrass",
    "balkong",
    "sjoutsikt",
    "water view",
)


def _normalize_description(value: object) -> str:
    if pd.isna(value):
        return ""
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _contains_any(text: str, phrases: tuple[str, ...]) -> int:
    return int(any(phrase in text for phrase in phrases))


def _count_phrases(text: str, phrases: tuple[str, ...]) -> int:
    return sum(1 for phrase in phrases if phrase in text)


def _word_count(text: str) -> int:
    return len(_WORD_RE.findall(text))


def create_description_features(df: pd.DataFrame) -> pd.DataFrame:
    """Create deterministic features from listing descriptions."""
    df = df.copy()
    descriptions = df.get("description", pd.Series([""] * len(df), index=df.index))
    normalized = descriptions.apply(_normalize_description)

    df["description_length"] = normalized.str.len().astype(float)
    df["description_word_count"] = normalized.apply(_word_count).astype(float)
    df["is_renovated"] = normalized.apply(lambda text: _contains_any(text, _RENOVATED_PHRASES))
    df["has_modern_kitchen"] = normalized.apply(
        lambda text: _contains_any(text, _MODERN_KITCHEN_PHRASES)
    )
    df["has_modern_bathroom"] = normalized.apply(
        lambda text: _contains_any(text, _MODERN_BATHROOM_PHRASES)
    )
    df["has_view"] = normalized.apply(lambda text: _contains_any(text, _VIEW_PHRASES))
    df["is_quiet_location"] = normalized.apply(lambda text: _contains_any(text, _QUIET_PHRASES))
    df["needs_renovation"] = normalized.apply(
        lambda text: _contains_any(text, _NEEDS_RENOVATION_PHRASES)
    )
    df["luxury_keyword_count"] = normalized.apply(
        lambda text: _count_phrases(text, _LUXURY_PHRASES)
    ).astype(float)

    positive_condition = (
        df["is_renovated"]
        + df["has_modern_kitchen"]
        + df["has_modern_bathroom"]
        + df["is_quiet_location"] * 0.5
    )
    df["condition_score"] = (positive_condition - df["needs_renovation"] * 2).clip(0, 5)
    df["premium_score"] = (
        df["luxury_keyword_count"]
        + df["has_view"]
        + df["has_modern_kitchen"] * 0.5
        + df["has_modern_bathroom"] * 0.5
        + df["is_quiet_location"] * 0.5
    ).clip(0, 8)

    return df
