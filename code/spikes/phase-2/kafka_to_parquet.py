"""Phase 2 spike (ADR-0015): an API job's landing topic -> Parquet, as a bounded PyFlink SQL job.

The fetch task (ingestion.rest_api) lands one message per API record on Redpanda and returns the run's offsets. This
job reads exactly [start, end) of partition 0 as the table `landing`, runs the job's query over it, and must reach
FINISHED by itself (scan.bounded.mode), like the JDBC jobs (ADR-0002).

Run on the JobManager (see README.md), with the offsets from the fetch task's log ("offsets [start, end)") after
"Run now" on ingest__shop-api-orders-daily (create it first: infrastructure/non-prod/example-sources/README.md):
  flink run -py /opt/spikes/phase-2/kafka_to_parquet.py --topic ingest.shop-api-orders-daily --start 0 --end 100
Output: <out>/api/<topic>/ingest_date=<date>/part-*.parquet; check it with check_parquet.py.
"""

from __future__ import annotations

import argparse
import time

from pyflink.table import EnvironmentSettings, TableEnvironment

# The job's query from pipelines/jobs/shop-api-orders-daily.yaml: typed columns plus the raw JSON.
QUERY = """SELECT
  CAST(JSON_VALUE(payload, '$.order_id') AS BIGINT) AS order_id,
  JSON_VALUE(payload, '$.status') AS status,
  payload,
  _fetched_at
FROM landing"""
COLUMNS = "order_id BIGINT, status STRING, payload STRING, _fetched_at TIMESTAMP_LTZ(3)"


def options(values: dict[str, object]) -> str:
    """The body of a ``WITH (...)`` clause: one ``'key' = 'value'`` per option, quotes escaped."""
    return ",\n  ".join(f"'{k}' = '{str(v).replace(chr(39), chr(39) * 2)}'" for k, v in values.items())


def main() -> None:
    """Reads the offset range of one run from a landing topic and writes it to Parquet."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--topic", required=True)
    parser.add_argument("--start", type=int, required=True, help="first offset of the run (inclusive)")
    parser.add_argument("--end", type=int, required=True, help="end offset of the run (exclusive)")
    parser.add_argument("--bootstrap-servers", default="redpanda:9092")
    parser.add_argument("--out", default="file:///opt/ingestion/spike-out", help="file:///... or abfss://...")
    parser.add_argument("--ingest-date", default="2026-10-25")
    args = parser.parse_args()

    env = TableEnvironment.create(EnvironmentSettings.in_batch_mode())
    # Same DDL as landing.table in code/templates/sources/rest_api.yaml.
    kafka = {
        "connector": "kafka",
        "topic": args.topic,
        "properties.bootstrap.servers": args.bootstrap_servers,
        "format": "raw",
        "scan.startup.mode": "specific-offsets",
        "scan.startup.specific-offsets": f"partition:0,offset:{args.start}",
        "scan.bounded.mode": "specific-offsets",
        "scan.bounded.specific-offsets": f"partition:0,offset:{args.end}",
    }
    env.execute_sql(
        "CREATE TABLE landing (\n  payload STRING,\n  _offset BIGINT METADATA FROM 'offset' VIRTUAL,\n"
        f"  _fetched_at TIMESTAMP_LTZ(3) METADATA FROM 'timestamp' VIRTUAL\n) WITH (\n  {options(kafka)}\n)"
    )
    out = f"{args.out.rstrip('/')}/api/{args.topic}"
    env.execute_sql(
        f"CREATE TABLE dst ({COLUMNS}, ingest_date STRING) PARTITIONED BY (ingest_date) WITH (\n  "
        + options({"connector": "filesystem", "path": out, "format": "parquet", "parquet.compression": "SNAPPY"})
        + "\n)"
    )

    started = time.monotonic()
    result = env.execute_sql(f"INSERT INTO dst SELECT *, '{args.ingest_date}' FROM ({QUERY}) AS q")
    job_id = result.get_job_client().get_job_id() if result.get_job_client() else "?"
    result.wait()
    seconds = time.monotonic() - started
    print(
        f"SPIKE source=api topic={args.topic} offsets=[{args.start},{args.end}) job={job_id} "
        f"seconds={seconds:.1f} out={out}"
    )


if __name__ == "__main__":
    main()
