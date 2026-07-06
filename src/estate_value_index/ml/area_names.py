"""Area name mapping between normalized keys and Swedish display names.

The canonical area-key normaliser is
:func:`estate_value_index.ml.preprocessing.normalize_area_for_model` and is
re-exported here as ``normalize_area_key`` for a stable entry point alongside
the display-name mapping.
"""

from estate_value_index.ml.preprocessing import normalize_area_for_model as _normalize

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
    """Convert a normalized area key to its Swedish display name."""
    if not area_key:
        return "Unknown"
    return AREA_DISPLAY_NAMES.get(area_key) or area_key.replace("_", " ").title()


def normalize_area_key(area_name: str) -> str:
    """Normalize an area string to a stable ASCII slug.

    Thin re-export of :func:`normalize_area_for_model`.
    """
    return _normalize(area_name)
