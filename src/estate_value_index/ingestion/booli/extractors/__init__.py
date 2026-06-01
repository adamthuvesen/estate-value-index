"""Booli listing field extractors (mixins for BooliSpider)."""

from estate_value_index.ingestion.booli.extractors.amenities import BooliAmenitiesMixin
from estate_value_index.ingestion.booli.extractors.area import BooliAreaMixin
from estate_value_index.ingestion.booli.extractors.helpers import BooliExtractionHelpersMixin
from estate_value_index.ingestion.booli.extractors.metadata import BooliMetadataMixin
from estate_value_index.ingestion.booli.extractors.next_data import BooliNextDataMixin
from estate_value_index.ingestion.booli.extractors.next_fetch import BooliNextFetchMixin
from estate_value_index.ingestion.booli.extractors.price import BooliPriceMixin
from estate_value_index.ingestion.booli.extractors.price_patterns import (
    extract_sold_price_from_text,
)
from estate_value_index.ingestion.booli.extractors.property import BooliPropertyMixin

__all__ = ["BooliExtractionMixins", "extract_sold_price_from_text"]


class BooliExtractionMixins(
    BooliNextDataMixin,
    BooliExtractionHelpersMixin,
    BooliPriceMixin,
    BooliMetadataMixin,
    BooliAreaMixin,
    BooliPropertyMixin,
    BooliAmenitiesMixin,
    BooliNextFetchMixin,
):
    """Combined extraction API mixed into BooliSpider."""
