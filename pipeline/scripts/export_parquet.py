"""Exports the mart tables from the DuckDB warehouse to a partitioned
Parquet data lake -- the "distributed warehouse" pattern the pipeline
README flags as a limitation of DuckDB alone.

Partitions by `run_date` (the date this export was executed), the
standard Hive-style pattern for date-partitioned incremental snapshots
in a real data lake, so downstream engines (Spark, Athena, BigQuery
external tables) can prune partitions instead of scanning everything.

Uses DuckDB's native COPY ... TO ... (FORMAT PARQUET, PARTITION_BY ...)
rather than a pandas round-trip, since DuckDB can write partitioned
Parquet directly.
"""
import sys
from datetime import date, datetime
from pathlib import Path

import duckdb

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "warehouse.duckdb"
LAKE_ROOT = ROOT / "data_lake"

MARTS = [
    "mart_complaints_by_category",
    "mart_company_response_analysis",
    "mart_top_companies",
]


def export_mart(con, mart: str, run_date: str, lake_root: Path) -> int:
    out_dir = lake_root / mart
    out_dir.mkdir(parents=True, exist_ok=True)

    row_count = con.execute(f"SELECT COUNT(*) FROM main.{mart}").fetchone()[0]
    if row_count == 0:
        raise RuntimeError(
            f"{mart} has 0 rows -- refusing to export an empty partition "
            "(likely means dbt run/test hasn't populated it yet)"
        )

    con.execute(f"""
        COPY (
            SELECT *, DATE '{run_date}' AS run_date
            FROM main.{mart}
        )
        TO '{out_dir.as_posix()}'
        (FORMAT PARQUET, PARTITION_BY (run_date), OVERWRITE_OR_IGNORE TRUE)
    """)
    return row_count


def main(run_date: str | None = None):
    run_date = run_date or date.today().isoformat()
    con = duckdb.connect(str(DB_PATH), read_only=True)

    print(f"Exporting marts to Parquet data lake (run_date={run_date})")
    total = 0
    for mart in MARTS:
        n = export_mart(con, mart, run_date, LAKE_ROOT)
        print(f"  {mart}: {n} rows -> data_lake/{mart}/run_date={run_date}/")
        total += n

    con.close()
    print(f"Done. {total} total rows exported across {len(MARTS)} marts.")


if __name__ == "__main__":
    run_date_arg = sys.argv[1] if len(sys.argv) > 1 else None
    main(run_date_arg)
