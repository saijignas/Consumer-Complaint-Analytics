"""Pull a real, messy sample from the CFPB Consumer Complaint Database
public API -- not a cleaned Kaggle CSV. Complaints only have a free-text
narrative when the consumer opted in to publish one (~roughly a third of
all complaints), and CFPB pre-redacts PII as XXXX tokens before
publishing; no PII handling needed on our end beyond that.

Six product categories are pulled directly (not by random-sampling the
whole corpus) because the raw corpus is heavily dominated by one category
(credit reporting is >90% of complaints in a typical recent window) --
random sampling would produce a near-useless single-class dataset for a
classification demo. This under/over-sampling-by-category choice is
disclosed here and in the README.
"""
from pathlib import Path

import requests

API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
ROOT = Path(__file__).parent.parent
OUT = ROOT / "data" / "complaints_raw.csv"

PRODUCTS = [
    "Credit card",
    "Mortgage",
    "Checking or savings account",
    "Student loan",
    "Vehicle loan or lease",
    "Money transfer, virtual currency, or money service",
]
PER_CATEGORY = 800
DATE_MIN = "2023-01-01"

FIELDS = [
    "complaint_id", "product", "sub_product", "issue", "sub_issue",
    "company", "state", "date_received", "company_response",
    "timely", "complaint_what_happened",
]


def fetch_category(product, target):
    # Note: this API's offset params (frm/from/page/offset) are silently
    # ignored -- they don't error, they just return the same top results
    # every time. Verified by direct comparison before relying on this.
    # size, however, is honored directly up to at least 800, so a single
    # request per category is used instead of paginating.
    resp = requests.get(API, params={
        "product": product,
        "has_narrative": "true",
        "date_received_min": DATE_MIN,
        "size": target,
    }, timeout=45)
    resp.raise_for_status()
    hits = resp.json()["hits"]["hits"]
    rows = [
        {f: h["_source"].get(f) for f in FIELDS}
        for h in hits if h["_source"].get("complaint_what_happened")
    ]
    return rows


def main():
    import pandas as pd
    all_rows = []
    for product in PRODUCTS:
        print(f"Fetching {product!r}...")
        rows = fetch_category(product, PER_CATEGORY)
        print(f"  got {len(rows)}")
        all_rows.extend(rows)

    df = pd.DataFrame(all_rows).drop_duplicates(subset="complaint_id")
    df.to_csv(OUT, index=False)
    print(f"\nSaved {len(df)} rows to {OUT}")
    print(df["product"].value_counts())


if __name__ == "__main__":
    main()
