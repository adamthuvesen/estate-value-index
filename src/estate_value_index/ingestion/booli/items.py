import scrapy


class BooliListingItem(scrapy.Item):
    """Item for individual property listings"""

    # Basic information
    listing_id = scrapy.Field()
    url = scrapy.Field()
    scraped_at = scrapy.Field()
    page_title = scrapy.Field()
    source_page = scrapy.Field()

    # Price information
    listing_price = scrapy.Field()  # Original listing price
    sold_price = scrapy.Field()  # Final sold price
    price_currency = scrapy.Field()
    price_per_sqm = scrapy.Field()
    monthly_fee = scrapy.Field()

    # Sale information
    sold_date = scrapy.Field()
    days_on_market = scrapy.Field()
    price_change = scrapy.Field()
    price_change_percentage = scrapy.Field()

    # Address and location
    address = scrapy.Field()
    area = scrapy.Field()
    municipality = scrapy.Field()

    # Property details
    living_area = scrapy.Field()
    rooms = scrapy.Field()
    property_type = scrapy.Field()
    construction_year = scrapy.Field()
    floor = scrapy.Field()

    # Features
    balcony = scrapy.Field()
    elevator = scrapy.Field()

    # Description and images
    description = scrapy.Field()
    images = scrapy.Field()

    # Broker information
    broker_name = scrapy.Field()
    broker_company = scrapy.Field()
    broker_phone = scrapy.Field()
