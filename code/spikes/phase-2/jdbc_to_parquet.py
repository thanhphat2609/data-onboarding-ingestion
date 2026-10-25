"""Phase 2 spike: JDBC source -> Parquet, partitioned by ingest_date, as a bounded PyFlink SQL job.

Covers the JDBC spikes of docs/roadmap.md Phase 2 for SQL Server, PostgreSQL and MySQL:
  --mode table  the JDBC table connector over a table, optionally with a partitioned scan
  --mode query  the user's query as a derived table `(<query>) AS q` (JOIN + CTE): does the connector accept it?

Run on the JobManager (see README.md):
  flink run -py /opt/spikes/phase-2/jdbc_to_parquet.py --source postgres --table orders --partitions 4
Output: <out>/<source>/<table or query>/ingest_date=<date>/part-*.parquet; check it with check_parquet.py.
Note: the password ends up in the table options, so it is visible in the job plan. The runner (Phase 4) must not do
this; recording how to avoid it is part of the spike.
"""

from __future__ import annotations

import argparse
import os
import time

from pyflink.table import EnvironmentSettings, TableEnvironment

SOURCES = {
    "sqlserver": {
        "url": "jdbc:sqlserver://sqlserver:1433;databaseName=crm;encrypt=true;trustServerCertificate=true;"
        "applicationIntent=ReadOnly",
        "password_env": "CRM_SQLSERVER_RO_PASSWORD",
        "schema": "dbo.",
        "extra": {},
    },
    "postgres": {
        "url": "jdbc:postgresql://postgres-source:5432/sales",
        "password_env": "SALES_POSTGRES_RO_PASSWORD",
        "schema": "public.",
        # The PostgreSQL driver only streams with a fetch size when auto-commit is off.
        "extra": {"scan.auto-commit": "false"},
    },
    "mysql": {
        # Without useCursorFetch the MySQL driver loads the whole result set into memory.
        "url": "jdbc:mysql://mysql-source:3306/shop?useCursorFetch=true",
        "password_env": "SHOP_MYSQL_RO_PASSWORD",
        "schema": "",
        "extra": {},
    },
}

TABLES = {
    "customers": {
        "columns": "customer_id INT, full_name STRING, email STRING, segment_id INT, is_deleted BOOLEAN, "
        "created_at TIMESTAMP(3), updated_at TIMESTAMP(3)",
        "partition_column": "customer_id",
        "bounds": (1, 10_000),
    },
    "orders": {
        "columns": "order_id BIGINT, customer_id INT, amount DECIMAL(12, 2), status STRING, created_at TIMESTAMP(3)",
        "partition_column": "order_id",
        "bounds": (1, 10_000_000),
    },
}

# Query mode: a JOIN and a CTE, as a user would write it. {s} is the schema prefix.
QUERY = """WITH active AS (SELECT customer_id, full_name, segment_id FROM {s}customers WHERE is_deleted = {false})
SELECT a.customer_id, a.full_name, s.segment_name FROM active a JOIN {s}segments s ON s.segment_id = a.segment_id"""
QUERY_COLUMNS = "customer_id INT, full_name STRING, segment_name STRING"


def options(values: dict[str, object]) -> str:
    return ",\n  ".join(f"'{k}' = '{str(v).replace(chr(39), chr(39) * 2)}'" for k, v in values.items())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=SOURCES, required=True)
    parser.add_argument("--mode", choices=["table", "query"], default="table")
    parser.add_argument("--table", choices=TABLES, default="customers")
    parser.add_argument("--partitions", type=int, default=0, help="0 = no partitioned scan")
    parser.add_argument("--fetch-size", type=int, default=10_000)
    parser.add_argument("--out", default="file:///opt/ingestion/spike-out", help="file:///... or abfss://...")
    parser.add_argument("--ingest-date", default="2026-10-25")
    args = parser.parse_args()

    source = SOURCES[args.source]
    jdbc = {
        "connector": "jdbc",
        "url": source["url"],
        "username": "svc_ingest_ro",
        "password": os.environ[source["password_env"]],
        "scan.fetch-size": args.fetch_size,
        **source["extra"],
    }
    if args.mode == "table":
        table = TABLES[args.table]
        columns, name = table["columns"], args.table
        jdbc["table-name"] = f"{source['schema']}{args.table}"
        if args.partitions:
            low, high = table["bounds"]
            jdbc |= {
                "scan.partition.column": table["partition_column"],
                "scan.partition.num": args.partitions,
                "scan.partition.lower-bound": low,
                "scan.partition.upper-bound": high,
            }
    else:
        columns, name = QUERY_COLUMNS, "customers_by_segment"
        false = "0" if args.source == "sqlserver" else "FALSE"
        jdbc["table-name"] = f"({QUERY.format(s=source['schema'], false=false)}) AS q"

    env = TableEnvironment.create(EnvironmentSettings.in_batch_mode())
    env.execute_sql(f"CREATE TABLE src ({columns}) WITH (\n  {options(jdbc)}\n)")
    out = f"{args.out.rstrip('/')}/{args.source}/{name}"
    env.execute_sql(
        f"CREATE TABLE dst ({columns}, ingest_date STRING) PARTITIONED BY (ingest_date) WITH (\n  "
        + options({"connector": "filesystem", "path": out, "format": "parquet", "parquet.compression": "SNAPPY"})
        + "\n)"
    )

    started = time.monotonic()
    result = env.execute_sql(f"INSERT INTO dst SELECT *, '{args.ingest_date}' FROM src")
    job_id = result.get_job_client().get_job_id() if result.get_job_client() else "?"
    result.wait()
    seconds = time.monotonic() - started
    print(
        f"SPIKE source={args.source} mode={args.mode} table={name} partitions={args.partitions} "
        f"fetch_size={args.fetch_size} job={job_id} seconds={seconds:.1f} out={out}"
    )


if __name__ == "__main__":
    main()
