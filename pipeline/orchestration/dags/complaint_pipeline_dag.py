"""Orchestrates the complaint-analytics pipeline end-to-end: wait for the
source API, extract+load, transform+test with dbt, then export the marts
to a partitioned Parquet data lake.

This is the piece the pipeline README explicitly flagged as missing:
"a real pipeline would run on a schedule; this project demonstrates the
model layer and testing discipline, not orchestration/scheduling."

Design notes
------------
- Tasks shell out to a dedicated virtualenv (`pipeline/.venv`) rather than
  installing dbt/duckdb into the Airflow environment itself, to avoid
  dependency conflicts between Airflow's pinned constraints and dbt-core's.
  This mirrors how a real team would isolate a dbt project's environment
  from the orchestrator's.
- `wait_for_cfpb_api` and `extract_load` hit the live CFPB API, so they are
  NOT exercised by CI (same reasoning the existing dbt CI job already
  documents: deterministic, no network dependency). CI instead runs
  `dbt_run`, `dbt_test`, and `export_parquet` directly via
  `airflow tasks test` against the already-committed warehouse.duckdb.
  A full live run (all 5 tasks) is verified locally, not in CI -- see
  orchestration/README.md.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests
from airflow import DAG
from airflow.operators.bash import BashOperator
from airflow.sensors.python import PythonSensor

PIPELINE_DIR = Path(__file__).resolve().parents[2]
VENV_DIR = PIPELINE_DIR / ".venv"
VENV_BIN = VENV_DIR / ("Scripts" if os.name == "nt" else "bin")
VENV_PYTHON = VENV_BIN / ("python.exe" if os.name == "nt" else "python")
VENV_DBT = VENV_BIN / ("dbt.exe" if os.name == "nt" else "dbt")

CFPB_API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"

default_args = {
    "owner": "saijignas",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def _cfpb_api_reachable() -> bool:
    """Sensor poke function: is the source API up before we bother extracting?"""
    try:
        resp = requests.get(CFPB_API, params={"size": 1}, timeout=10)
        return resp.status_code < 500
    except requests.RequestException:
        return False


with DAG(
    dag_id="complaint_pipeline",
    description="Extract CFPB complaints -> dbt transform/test -> export to a Parquet data lake",
    default_args=default_args,
    schedule="@daily",
    start_date=datetime(2026, 9, 1),
    catchup=False,
    tags=["data-engineering", "dbt", "duckdb"],
) as dag:

    wait_for_cfpb_api = PythonSensor(
        task_id="wait_for_cfpb_api",
        python_callable=_cfpb_api_reachable,
        mode="reschedule",
        poke_interval=30,
        timeout=60 * 10,
    )

    extract_load = BashOperator(
        task_id="extract_load",
        bash_command=f'"{VENV_PYTHON}" scripts/load_raw.py',
        cwd=str(PIPELINE_DIR),
    )

    dbt_run = BashOperator(
        task_id="dbt_run",
        bash_command=f'"{VENV_DBT}" run',
        cwd=str(PIPELINE_DIR),
        env={**os.environ, "DBT_PROFILES_DIR": str(PIPELINE_DIR)},
    )

    dbt_test = BashOperator(
        task_id="dbt_test",
        bash_command=f'"{VENV_DBT}" test',
        cwd=str(PIPELINE_DIR),
        env={**os.environ, "DBT_PROFILES_DIR": str(PIPELINE_DIR)},
    )

    export_parquet = BashOperator(
        task_id="export_parquet",
        bash_command=f'"{VENV_PYTHON}" scripts/export_parquet.py {{{{ ds }}}}',
        cwd=str(PIPELINE_DIR),
    )

    wait_for_cfpb_api >> extract_load >> dbt_run >> dbt_test >> export_parquet
