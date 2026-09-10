"""Reads the row-level complaint fact table from the Parquet data lake
with PySpark and answers a genuinely fresh cross-cutting question that
none of the pre-aggregated dbt marts can answer alone: which companies
are worst-in-class *within their own product category*, not just worst
in absolute terms.

The three dbt marts are aggregated at different, non-joinable grains
(by product, by company, by response type) -- there's no shared key to
join them on. This job instead reads the row-level `stg_complaints`
fact export from the lake, which is the realistic thing a downstream
engine would consume once volume outgrows a single-node DuckDB
warehouse; DuckDB could technically answer this same query today at
this data's actual size (a few thousand rows) -- the point here is
demonstrating the Spark DataFrame API itself (groupBy, join, window
functions over a partitioned Parquet source), not claiming a
performance win that doesn't exist at this scale.
"""
import os
import sys
from pathlib import Path

# Without this, PySpark's worker subprocesses launch via a bare "python3"
# resolved from PATH -- on Windows (and some CI images) that can hit the
# Microsoft Store's python.exe alias stub instead of a real interpreter,
# failing every task with a cryptic SocketTimeoutException. Pointing both
# at the interpreter actually running this script fixes it everywhere,
# not just locally, and is a no-op on setups where PATH was already fine.
os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)

from pyspark.sql import SparkSession, Window  # noqa: E402
from pyspark.sql import functions as F  # noqa: E402

ROOT = Path(__file__).parent.parent
LAKE_PATH = ROOT / "data_lake" / "stg_complaints"
RESULTS_PATH = ROOT / "results" / "tables" / "spark_worst_in_class_companies.csv"
MIN_COMPLAINTS_PER_COMPANY_PER_CATEGORY = 5


def build_spark(app_name: str = "complaint-lake-analysis") -> SparkSession:
    return (
        SparkSession.builder
        .appName(app_name)
        .master("local[*]")
        .config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )


def worst_in_class_companies(df):
    """For each (product, company) pair with enough volume, compute the
    company's timely-response rate and its rank against peers within the
    *same* product category, then return only the companies performing
    below their own category's average -- flags relative underperformers,
    not just companies with a low rate in absolute terms."""
    per_company = (
        df.groupBy("product", "company")
        .agg(
            F.count("*").alias("complaint_count"),
            F.round(
                100.0 * F.sum(F.col("was_timely").cast("int")) / F.count("*"), 1
            ).alias("pct_timely_response"),
        )
        .filter(F.col("complaint_count") >= MIN_COMPLAINTS_PER_COMPANY_PER_CATEGORY)
    )

    category_avg = df.groupBy("product").agg(
        F.round(100.0 * F.avg(F.col("was_timely").cast("int")), 1).alias(
            "category_avg_pct_timely"
        )
    )

    ranked = per_company.join(category_avg, on="product")
    ranked = ranked.withColumn(
        "rank_within_category",
        F.rank().over(
            Window.partitionBy("product").orderBy(F.col("pct_timely_response").asc())
        ),
    )

    return (
        ranked.filter(F.col("pct_timely_response") < F.col("category_avg_pct_timely"))
        .orderBy("product", "rank_within_category")
    )


def main():
    spark = build_spark()
    try:
        df = spark.read.parquet(str(LAKE_PATH))
        row_count = df.count()
        print(f"Read {row_count} rows from the partitioned lake at {LAKE_PATH}")
        if row_count == 0:
            raise RuntimeError(
                f"No rows read from {LAKE_PATH} -- has export_parquet.py been run yet?"
            )

        result = worst_in_class_companies(df)
        print("\nCompanies underperforming their own product category's average timely-response rate:")
        result.show(30, truncate=False)

        RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
        result.toPandas().to_csv(RESULTS_PATH, index=False)
        print(f"\nWrote {RESULTS_PATH}")
    finally:
        spark.stop()


if __name__ == "__main__":
    main()
