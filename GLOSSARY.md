# Estate Value Index

Predicts sale prices for Swedish residential listings. This file fixes the names the code, the BigQuery schema, and the web app share.

## Language

**Listing**:
One property advertised on Booli, keyed by `listing_id`. A row in `booli_raw.listings` (`schemas/bq_raw_listings.json`). A sold listing is both a listing and a sale.
_Avoid_: Ad, property record

**Sale**:
A listing that has a `sold_price` and a `sold_date`. Training uses sales only. `sold_date` orders all evaluation.
_Avoid_: Transaction, deal

**Valuation**:
The model's predicted sale price for a listing, in SEK. The API returns it with an estimate range (`estimate_range_factors`). In the value analysis it is `predicted_price`.
_Avoid_: Prediction price, appraisal

**Value analysis**:
The derived web file (`value_analysis.json`) that scores every sale: valuation against `sold_price`, with a delta and an `is_undervalued` flag. Built in `analytics/value_analysis.py`.
_Avoid_: Value finder

## Places

**Area**:
The neighborhood-level place of a listing, the `area` column. The code never uses the word "neighborhood" for it, except in two descriptions (`api_server.py`, `ingestion/geocoding.py`). `areas.py` is the only owner of its forms: Booli token, cleaned name, model slug (`normalize_area_for_model`), display name.
_Avoid_: Neighborhood, district

**Municipality**:
The kommun that contains an area, the `municipality` column. Larger than an area.

## Prices

**Ask price**:
The price a listing is advertised at. The canonical name is `listing_price`: it is the BigQuery column, the API field, and a model feature. `ask_price` appears only in the module `ml/ask_price.py`, which masks ask-price signals for the no-list-price model. `list_price` is not used in Python. The web app has `listPrice` and `listingPrice` in one place each, as spelling drift.
_Avoid_: `list_price`, `asking_price`

**Price per sqm**:
Price divided by `living_area`. The canonical name is `price_per_sqm` (BigQuery column, feature, Python). `ppsqm` is the shorthand in feature statistics and context fields (`area_ppsqm_stats`, `micro_area_ppsqm_median`). `pricePerSqm` is the camelCase form in the web app. All three mean the same thing. The code does not rename them.
_Avoid_: `ppsqm` in new column names, price per m2

## Modeling

**Feature context**:
The training-time statistics (area medians, H3 cell stats, fill values) saved with a model so inference rebuilds the same features. Class `FeatureEngineeringContext` in `ml/features/context.py`.
_Avoid_: Feature cache

**Feature set**:
A named, fixed list of model inputs in `ml/features/registry.py`. Two exist: `no_list_price_v1` hides ask-price signals, and `with_list_price_v1` uses them. Each production model uses one.
_Avoid_: Feature subset, feature config

**Production model**:
One of two tiered LightGBM ensembles served by the API: `no_list_price` and `with_list_price`. `/predict` picks `with_list_price` only when a positive `listing_price` is given.

**Package version stamp**:
The installed `estate-value-index` version, written to each model's metrics file as `package_version`. The API refuses a model without a matching stamp.

**Data fingerprint**:
The row count, newest `sold_date`, and content hash of the training frame, written to the metrics file as `data_fingerprint`. It identifies the data a model trained on. `ml/data_fingerprint.py`.

## Source

**Booli**:
The Swedish listing site and source of listing data. Access is through a signed API or authorized export. Raw Booli strings (`Type · Area · Municipality`) are parsed in `areas.py` and `ingestion/`.
