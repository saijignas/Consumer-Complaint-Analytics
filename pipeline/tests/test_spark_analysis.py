"""Unit test for the Spark analysis's actual business logic, using
synthetic in-memory data -- doesn't depend on the real lake existing,
so it verifies the groupBy/join/window logic in isolation rather than
just "did the job run without crashing."
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from spark.spark_lake_analysis import build_spark, worst_in_class_companies  # noqa: E402


@pytest.fixture(scope="module")
def spark():
    s = build_spark(app_name="pytest-spark-analysis")
    yield s
    s.stop()


def test_flags_only_the_below_average_company(spark):
    # BankA: 5/5 timely (100%). BankB: 1/5 timely (20%). Category avg: 60%.
    # Only BankB should be flagged.
    rows = (
        [("Mortgage", "BankA", True)] * 5
        + [("Mortgage", "BankB", True)] * 1
        + [("Mortgage", "BankB", False)] * 4
    )
    df = spark.createDataFrame(rows, ["product", "company", "was_timely"])

    result = worst_in_class_companies(df).toPandas()

    assert set(result["company"]) == {"BankB"}
    assert result.iloc[0]["pct_timely_response"] == 20.0
    assert result.iloc[0]["category_avg_pct_timely"] == 60.0


def test_below_min_volume_companies_are_excluded(spark):
    # BankC has a terrible rate but only 2 complaints -- below the
    # MIN_COMPLAINTS_PER_COMPANY_PER_CATEGORY threshold, must be excluded
    # even though it "deserves" to be flagged on rate alone.
    rows = (
        [("Mortgage", "BankA", True)] * 5
        + [("Mortgage", "BankC", False)] * 2
    )
    df = spark.createDataFrame(rows, ["product", "company", "was_timely"])

    result = worst_in_class_companies(df).toPandas()

    assert "BankC" not in set(result["company"])


def test_no_flags_when_everyone_matches_the_average(spark):
    rows = [("Mortgage", "BankA", True)] * 5 + [("Mortgage", "BankB", True)] * 5
    df = spark.createDataFrame(rows, ["product", "company", "was_timely"])

    result = worst_in_class_companies(df).toPandas()

    assert len(result) == 0
