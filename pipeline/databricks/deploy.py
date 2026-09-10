"""Deploys the Spark lake analysis to Databricks for real: uploads the
row-level Parquet fact table to a Unity Catalog volume, imports the
notebook, submits a one-time job run on serverless compute, polls it to
completion, and prints the actual output.

This is a one-shot deployment/verification tool, not something meant to
run on every CI push -- Databricks trial/free-tier workspaces aren't a
sensible thing to hit on every commit. Re-run manually if the analysis
logic or the underlying data changes.

Requires two environment variables:
    DATABRICKS_HOST   e.g. https://dbc-xxxxxxxx-xxxx.cloud.databricks.com
    DATABRICKS_TOKEN  a personal access token
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

HOST = os.environ["DATABRICKS_HOST"].rstrip("/")
TOKEN = os.environ["DATABRICKS_TOKEN"]
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

ROOT = Path(__file__).resolve().parent.parent
PARQUET_LOCAL = ROOT / "data_lake" / "stg_complaints" / "run_date=2026-09-09" / "data_0.parquet"

CATALOG, SCHEMA, VOLUME = "workspace", "complaint_analytics", "data_lake"
VOLUME_ROOT = f"/Volumes/{CATALOG}/{SCHEMA}/{VOLUME}"
UC_PARQUET_PATH = f"{VOLUME_ROOT}/stg_complaints/run_date=2026-09-09/data_0.parquet"
UC_RESULTS_PATH = f"{VOLUME_ROOT}/results/spark_worst_in_class_companies"
NOTEBOOK_WORKSPACE_PATH = "/Shared/complaint_lake_spark_analysis"


def ensure_catalog_objects():
    """Creates the schema and volume if they don't already exist. Safe to
    call repeatedly -- a 400 on an already-exists case is swallowed."""
    for kind, url, payload in [
        ("schema", f"{HOST}/api/2.1/unity-catalog/schemas",
         {"name": SCHEMA, "catalog_name": CATALOG}),
        ("volume", f"{HOST}/api/2.1/unity-catalog/volumes",
         {"catalog_name": CATALOG, "schema_name": SCHEMA, "name": VOLUME, "volume_type": "MANAGED"}),
    ]:
        r = requests.post(url, headers=HEADERS, json=payload)
        if r.status_code not in (200, 400):
            r.raise_for_status()
        print(f"  {kind}: {'created' if r.status_code == 200 else 'already exists'}")


def upload_parquet_to_volume():
    data = PARQUET_LOCAL.read_bytes()
    r = requests.put(
        f"{HOST}/api/2.0/fs/files{UC_PARQUET_PATH}?overwrite=true",
        headers={**HEADERS, "Content-Type": "application/octet-stream"},
        data=data,
    )
    r.raise_for_status()
    print(f"Uploaded {PARQUET_LOCAL.name} ({len(data)} bytes) -> {UC_PARQUET_PATH}")


NOTEBOOK_SOURCE = f'''# Databricks notebook source
# COMMAND ----------
# MAGIC %md
# MAGIC ## Complaint Lake Analysis (Spark)
# MAGIC Reads the real row-level complaint fact table (exported from the
# MAGIC Consumer-Complaint-Analytics dbt+DuckDB pipeline as partitioned
# MAGIC Parquet) and answers a question none of the pre-aggregated dbt
# MAGIC marts can answer alone: which companies are worst-in-class
# MAGIC *within their own product category*, not just worst overall.

# COMMAND ----------
from pyspark.sql import Window
from pyspark.sql import functions as F

LAKE_PATH = "{VOLUME_ROOT}/stg_complaints"
MIN_COMPLAINTS_PER_COMPANY_PER_CATEGORY = 5

df = spark.read.parquet(LAKE_PATH)
row_count = df.count()
print(f"Read {{row_count}} rows from {{LAKE_PATH}}")
assert row_count > 0, "No rows read -- check the Unity Catalog volume path"

# COMMAND ----------
per_company = (
    df.groupBy("product", "company")
    .agg(
        F.count("*").alias("complaint_count"),
        F.round(100.0 * F.sum(F.col("was_timely").cast("int")) / F.count("*"), 1)
            .alias("pct_timely_response"),
    )
    .filter(F.col("complaint_count") >= MIN_COMPLAINTS_PER_COMPANY_PER_CATEGORY)
)

category_avg = df.groupBy("product").agg(
    F.round(100.0 * F.avg(F.col("was_timely").cast("int")), 1).alias("category_avg_pct_timely")
)

ranked = per_company.join(category_avg, on="product")
ranked = ranked.withColumn(
    "rank_within_category",
    F.rank().over(Window.partitionBy("product").orderBy(F.col("pct_timely_response").asc())),
)

result = (
    ranked.filter(F.col("pct_timely_response") < F.col("category_avg_pct_timely"))
    .orderBy("product", "rank_within_category")
)

print(f"Found {{result.count()}} companies underperforming their own category average:")
result.show(30, truncate=False)

# COMMAND ----------
# Write the result back out so it's inspectable after the run completes.
result.write.mode("overwrite").option("header", "true").csv("{UC_RESULTS_PATH}")
print("Wrote results to {UC_RESULTS_PATH}")
'''


def import_notebook():
    encoded = base64.b64encode(NOTEBOOK_SOURCE.encode()).decode()
    r = requests.post(
        f"{HOST}/api/2.0/workspace/import",
        headers=HEADERS,
        json={
            "path": NOTEBOOK_WORKSPACE_PATH,
            "format": "SOURCE",
            "language": "PYTHON",
            "content": encoded,
            "overwrite": True,
        },
    )
    r.raise_for_status()
    print(f"Imported notebook -> {NOTEBOOK_WORKSPACE_PATH}")


def submit_run():
    r = requests.post(
        f"{HOST}/api/2.1/jobs/runs/submit",
        headers=HEADERS,
        json={
            "run_name": "complaint-lake-spark-analysis-verify",
            "tasks": [
                {
                    "task_key": "run_analysis",
                    "notebook_task": {"notebook_path": NOTEBOOK_WORKSPACE_PATH},
                    # This workspace only supports serverless compute (no classic
                    # clusters available on the trial) -- omitting new_cluster/
                    # existing_cluster_id routes the task to serverless by default.
                }
            ],
        },
    )
    r.raise_for_status()
    run_id = r.json()["run_id"]
    print(f"Submitted run_id={run_id}")
    return run_id


def poll_run(run_id):
    while True:
        r = requests.get(f"{HOST}/api/2.1/jobs/runs/get", headers=HEADERS, params={"run_id": run_id})
        r.raise_for_status()
        payload = r.json()
        state = payload["state"]
        life_cycle = state.get("life_cycle_state")
        print(f"  state: {life_cycle} {state.get('state_message', '')}")
        if life_cycle in ("TERMINATED", "SKIPPED", "INTERNAL_ERROR"):
            return payload
        time.sleep(20)


def print_task_output(run_payload):
    task_run_id = run_payload["tasks"][0]["run_id"]
    r = requests.get(f"{HOST}/api/2.1/jobs/runs/get-output", headers=HEADERS, params={"run_id": task_run_id})
    r.raise_for_status()
    print(json.dumps(r.json().get("notebook_output", {}), indent=2))

    # notebook_output only captures dbutils.notebook.exit() values, not
    # print()/display() output -- the real proof is the CSV the job wrote.
    r = requests.get(
        f"{HOST}/api/2.0/fs/directories{UC_RESULTS_PATH}", headers=HEADERS
    )
    r.raise_for_status()
    part_files = [f for f in r.json().get("contents", []) if f["name"].startswith("part-")]
    for f in part_files:
        content = requests.get(f"{HOST}/api/2.0/fs/files{f['path']}", headers=HEADERS)
        content.raise_for_status()
        print(f"\n--- {f['path']} ---")
        print(content.text)


if __name__ == "__main__":
    print("=== Ensuring Unity Catalog schema/volume exist ===")
    ensure_catalog_objects()

    print("\n=== Uploading Parquet data to the volume ===")
    upload_parquet_to_volume()

    print("\n=== Importing notebook ===")
    import_notebook()

    print("\n=== Submitting job run ===")
    run_id = submit_run()

    print("\n=== Polling for completion ===")
    final_payload = poll_run(run_id)

    result_state = final_payload["state"].get("result_state")
    print(f"\nResult: {result_state}")
    if result_state != "SUCCESS":
        sys.exit(1)

    print("\n=== Output ===")
    print_task_output(final_payload)
