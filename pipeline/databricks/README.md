# Databricks Deployment

Runs `spark/spark_lake_analysis.py`'s analysis for real on Databricks,
against a Unity Catalog volume instead of local disk -- not just code
that *would* work on Databricks, an actual verified job run.

## What `deploy.py` does

1. Creates a Unity Catalog schema + managed volume (`workspace.complaint_analytics.data_lake`)
   if they don't already exist.
2. Uploads the real `stg_complaints` Parquet partition to the volume.
3. Imports a notebook version of the analysis to `/Shared/complaint_lake_spark_analysis`.
4. Submits a one-time job run (serverless compute -- this workspace's
   trial tier doesn't support classic clusters) and polls it to completion.
5. Prints the actual output CSV the job wrote.

## What was actually verified

Run twice for real, both times with identical, correct results:

```
Result: SUCCESS

product,company,complaint_count,pct_timely_response,category_avg_pct_timely,rank_within_category
Checking or savings account,"BANK OF AMERICA, NATIONAL ASSOCIATION",55,96.4,99.2,1
Mortgage,"LD Holdings Group, LLC",5,80.0,98.8,1
Student loan,EdFinancial Services,40,42.5,95.2,1
Vehicle loan or lease,"American Credit Acceptance, LLC",7,85.7,98.2,1
```

That result is internally consistent with a finding already documented in
the main pipeline README: Student loan complaints have a notably worse
timely-response rate than every other category (95.2% avg vs. 98-99% for
the others). This run shows *why* -- EdFinancial Services, with 40
complaints, is running at 42.5%, dragging the whole category's average
down. That's a real, useful finding this Spark job surfaces that none of
the three pre-aggregated dbt marts could show on their own (they're
aggregated at grains that don't share a join key with each other).

Verified via the Databricks REST API directly (`runs/get`, `runs/get-output`,
and reading the actual output file back from the volume), not just "the
job didn't crash."

## Running it yourself

```bash
export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
export DATABRICKS_TOKEN="dapi..."
python deploy.py
```

## Limitations

- This is a one-shot deployment/verification script, not something wired
  into CI -- a free-tier Databricks workspace isn't a sensible thing to
  hit on every push. Re-run manually if the analysis logic or the
  underlying data changes.
- The workspace this was verified against only supports serverless
  compute (no classic clusters on the trial tier) -- `deploy.py`
  deliberately omits a `new_cluster`/`existing_cluster_id` spec so the
  task routes to serverless by default. A workspace with classic
  clusters available would work identically either way.
- `notebook_output` in the Jobs API only captures an explicit
  `dbutils.notebook.exit(...)` value, not `print()`/`.show()` output --
  `deploy.py` reads the actual CSV the job wrote back from the volume
  instead, which is the real proof the analysis ran correctly.
