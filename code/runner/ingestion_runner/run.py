"""Command line of the runner: builds the plan, asks the source for the columns, runs one bounded Flink job."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import time
import uuid
from pathlib import Path

from ingestion_runner import flink_sql, jdbc_meta
from ingestion_runner.plan import build_plan


def parse(argv: list[str] | None) -> argparse.Namespace:
    """Command line arguments of the runner."""
    parser = argparse.ArgumentParser(description="Copies the result of an ingestion job's query to Parquet.")
    parser.add_argument("--job", type=Path, required=True, help="IngestionJob file, for example pipelines/jobs/x.yaml")
    parser.add_argument("--connections-dir", type=Path, help="default: the connections folder next to the job's folder")
    parser.add_argument(
        "--templates-dir",
        type=Path,
        default=Path(os.environ.get("INGESTION_TEMPLATES_DIR", "/opt/ingestion/templates")),
    )
    parser.add_argument("--run-id", default=f"manual-{uuid.uuid4().hex[:12]}")
    parser.add_argument("--ingest-date", default=dt.datetime.now(dt.UTC).date().isoformat())
    parser.add_argument("--output-root", help="replaces the sink's storage root, e.g. file:///opt/ingestion/spike-out")
    parser.add_argument("--no-wait", action="store_true", help="return once the job is submitted")
    return parser.parse_args(argv)


def run(argv: list[str] | None = None) -> None:
    """Builds the plan, reads the query's columns from the source and runs the bounded job; prints ``RUNNER_RESULT``."""
    from pyflink.table import EnvironmentSettings, TableEnvironment

    args = parse(argv)
    plan = build_plan(
        args.job,
        args.connections_dir or args.job.parent.parent / "connections",
        args.templates_dir,
        args.run_id,
        args.ingest_date,
        args.output_root,
    )
    columns = jdbc_meta.describe(plan)
    bounds = jdbc_meta.bounds(plan, columns)

    env = TableEnvironment.create(EnvironmentSettings.in_batch_mode())
    if plan.parallelism:
        env.get_config().set("parallelism.default", str(plan.parallelism))
    env.execute_sql(flink_sql.source_ddl(plan, columns, bounds))
    env.execute_sql(flink_sql.sink_ddl(plan, columns))

    started = time.monotonic()
    result = env.execute_sql(flink_sql.insert_sql(plan, columns))
    client = result.get_job_client()
    summary = {
        "job": plan.job_name,
        "run_id": plan.run_id,
        "ingest_date": plan.ingest_date,
        "flink_job_id": client.get_job_id() if client else None,
        "columns": len(columns),
        "partitioned": bounds is not None,
        "staging": plan.staging_uri,
    }
    if not args.no_wait:
        result.wait()
        summary["seconds"] = round(time.monotonic() - started, 1)
    print("RUNNER_RESULT " + json.dumps(summary))
