"""Loads a fresh sample of real CFPB consumer-complaint data directly
into the DuckDB warehouse as a raw table -- the "extract and load" step
that would normally be a scheduled ingestion job upstream of dbt.

Pulled live from the CFPB public API, not a cleaned CSV -- same source
as the classical-vs-LLM Consumer-Complaint-Triage project, but this
pipeline is self-contained (it does its own pull) so it can run without
depending on that other repo.
"""
from pathlib import Path

import duckdb
import pandas as pd
import requests

API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "warehouse.duckdb"

PRODUCTS = [
    "Credit card",
    "Mortgage",
    "Checking or savings account",
    "Student loan",
    "Vehicle loan or lease",
    "Money transfer, virtual currency, or money service",
]
PER_CATEGORY = 500
DATE_MIN = "2023-01-01"

FIELDS = [
    "complaint_id", "product", "sub_product", "issue", "sub_issue",
    "company", "state", "date_received", "date_sent_to_company",
    "company_response", "timely", "complaint_what_happened", "submitted_via",
]


def fetch_category(product, target):
    resp = requests.get(API, params={
        "product": product,
        "has_narrative": "true",
        "date_received_min": DATE_MIN,
        "size": target,
    }, timeout=45)
    resp.raise_for_status()
    hits = resp.json()["hits"]["hits"]
    return [
        {f: h["_source"].get(f) for f in FIELDS}
        for h in hits if h["_source"].get("complaint_what_happened")
    ]


def main():
    all_rows = []
    for product in PRODUCTS:
        print(f"Fetching {product!r}...")
        rows = fetch_category(product, PER_CATEGORY)
        print(f"  got {len(rows)}")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows).drop_duplicates(subset="complaint_id")
    print(f"\nTotal rows: {len(df)}")

    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE SCHEMA IF NOT EXISTS raw")
    con.execute("CREATE OR REPLACE TABLE raw.complaints AS SELECT * FROM df")
    n = con.execute("SELECT COUNT(*) FROM raw.complaints").fetchone()[0]
    print(f"Loaded {n} rows into raw.complaints ({DB_PATH})")
    con.close()


if __name__ == "__main__":
    main()
