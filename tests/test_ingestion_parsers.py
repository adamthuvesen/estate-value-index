from scrapy.http import HtmlResponse

from src.estate_value_index.ingestion.booli.parsers import (
    apollo_state_from_next,
    extract_next_data_html,
    listing_ids_from_links,
    listing_links_from_next_payload,
    resolve_listing_links,
    resolve_property_record,
)


def make_response(url: str, body: str) -> HtmlResponse:
    return HtmlResponse(url=url, body=body.encode("utf-8"), encoding="utf-8")


def test_resolve_listing_links_returns_unique_absolute_urls():
    html = """
    <html><body>
      <a href="/annons/123">Listing 1</a>
      <a href="/bostad/area/456">Listing 2</a>
      <a href="https://www.booli.se/annons/123">Duplicate</a>
    </body></html>
    """
    response = make_response("https://www.booli.se/sok/slutpriser?page=1", html)
    links = resolve_listing_links(response)
    assert links == [
        "https://www.booli.se/annons/123",
        "https://www.booli.se/bostad/area/456",
    ]


def test_listing_ids_from_links():
    links = [
        "https://www.booli.se/annons/123",
        "https://www.booli.se/bostad/area/456",
        "https://www.booli.se/listing?booliId=789",
    ]
    assert listing_ids_from_links(links) == ["123", "456", "789"]


def test_extract_next_data_html_parses_script():
    payload = {"props": {"pageProps": {"__APOLLO_STATE__": {}}}}
    html = f"""
    <html><body>
      <script id='__NEXT_DATA__' type='application/json'>{payload}</script>
    </body></html>
    """
    response = make_response("https://www.booli.se/sok", html.replace("'", '"'))
    next_data = extract_next_data_html(response)
    assert isinstance(next_data, dict)


def test_apollo_state_from_next_returns_dict():
    next_payload = {
        "props": {"pageProps": {"__APOLLO_STATE__": {"Listing:123": {"url": "/annons/123"}}}}
    }
    apollo_state = apollo_state_from_next(next_payload)
    assert apollo_state == {"Listing:123": {"url": "/annons/123"}}


def test_listing_links_from_next_payload_extracts_links():
    payload = {
        "pageProps": {
            "__APOLLO_STATE__": {
                "Listing:123": {"url": "/annons/123"},
                "Listing:456": {"listingUrl": "https://www.booli.se/bostad/area/456"},
            }
        }
    }
    links = listing_links_from_next_payload(payload)
    assert links == [
        "https://www.booli.se/annons/123",
        "https://www.booli.se/bostad/area/456",
    ]


def test_resolve_property_record_matches_identifiers():
    apollo_state = {
        "Listing:123": {},
        "SoldProperty:123": {"id": "123", "booliId": "123"},
        "Property:456": {"listingId": "456"},
    }
    record = resolve_property_record(apollo_state, "123")
    assert record == {"id": "123", "booliId": "123"}
    fallback = resolve_property_record(apollo_state, "456")
    assert fallback == {"listingId": "456"}
    missing = resolve_property_record(apollo_state, "999")
    assert missing is None
