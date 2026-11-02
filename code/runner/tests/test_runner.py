"""Offline tests: the plan, the type mapping and the SQL. The Flink job itself runs in the non-prod cluster."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest
import yaml

from ingestion_runner import types
from ingestion_runner.flink_sql import Column, check_columns, insert_sql, sink_ddl, source_ddl
from ingestion_runner.plan import SpecError, build_plan, render

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
NOW = dt.datetime(2026, 11, 2, 2, 0, 5, 123456, tzinfo=dt.UTC)


def write(path: Path, document: dict[str, object]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(document), encoding="utf-8")
    return path


@pytest.fixture
def pipelines(tmp_path: Path) -> Path:
    write(
        tmp_path / "connections" / "shop-mysql-connection.yaml",
        {
            "kind": "Connection",
            "name": "shop-mysql-connection",
            "template": "mysql@1",
            "owner": "de-team",
            "params": {
                "host": "mysql-source",
                "database": "shop",
                "username": "svc_ingest_ro",
                "password": "env://SHOP_MYSQL_RO_PASSWORD",
            },
        },
    )
    write(
        tmp_path / "jobs" / "shop-orders-daily.yaml",
        {
            "kind": "IngestionJob",
            "name": "shop-orders-daily",
            "owner": "de-team",
            "connection": "shop-mysql-connection",
            "source": {
                "query": "SELECT order_id, customer_id FROM orders;\n",
                "read": {"partition_column": "order_id"},
            },
            "sink": {"template": "adls_parquet@1", "params": {"storage_account": "acct", "path": "shop/shop/orders"}},
            "runtime": {"parallelism": 2},
        },
    )
    return tmp_path


def plan_for(pipelines: Path, **kwargs: object):  # type: ignore[no-untyped-def]
    values = {"run_id": "run-1", "ingest_date": "2026-11-02", "now": NOW, **kwargs}
    return build_plan(
        pipelines / "jobs" / "shop-orders-daily.yaml",
        pipelines / "connections",
        TEMPLATES,
        **values,  # type: ignore[arg-type]
    )


def test_plan_reads_job_connection_and_templates(pipelines: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOP_MYSQL_RO_PASSWORD", "s3cret")
    plan = plan_for(pipelines)
    assert plan.dialect == "mysql"
    assert plan.jdbc_url.startswith("jdbc:mysql://mysql-source:3306/shop?sslMode=PREFERRED&useCursorFetch=true")
    assert (plan.username, plan.password) == ("svc_ingest_ro", "s3cret")
    assert plan.query == "SELECT order_id, customer_id FROM orders"
    assert (plan.fetch_size, plan.partition_column, plan.partition_num, plan.parallelism) == (10000, "order_id", 4, 2)
    assert plan.compression == "SNAPPY"
    assert plan.staging_uri == "abfss://raw@acct.dfs.core.windows.net/_staging/run-1"
    assert plan.ingested_at == "2026-11-02 02:00:05.123"
    assert "s3cret" not in repr(plan)


def test_output_root_replaces_the_storage_root(pipelines: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOP_MYSQL_RO_PASSWORD", "x")
    plan = plan_for(pipelines, output_root="file:///opt/ingestion/spike-out/")
    assert plan.staging_uri == "file:///opt/ingestion/spike-out/_staging/run-1"


def test_missing_password_variable_names_the_variable(pipelines: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SHOP_MYSQL_RO_PASSWORD", raising=False)
    with pytest.raises(SpecError, match="SHOP_MYSQL_RO_PASSWORD"):
        plan_for(pipelines)


def test_bad_run_id_and_date_are_rejected(pipelines: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOP_MYSQL_RO_PASSWORD", "x")
    with pytest.raises(SpecError, match="run id"):
        plan_for(pipelines, run_id="a'; DROP TABLE x")
    with pytest.raises(SpecError, match="ingest date"):
        plan_for(pipelines, ingest_date="02/11/2026")


def test_render_fills_placeholders_and_lowercases_booleans() -> None:
    assert render("a={{ x }}&b={{ y }}", {"x": 1, "y": True}) == "a=1&b=true"
    with pytest.raises(SpecError, match="no value"):
        render("{{ missing }}", {})


def test_type_mapping() -> None:
    assert types.flink_type("c", types.INTEGER, "INT", 10, 0) == "INT"
    assert types.flink_type("c", types.BIGINT, "BIGINT", 19, 0) == "BIGINT"
    assert types.flink_type("c", types.DECIMAL, "DECIMAL", 12, 2) == "DECIMAL(12, 2)"
    assert types.flink_type("c", types.BIT, "BIT", 1, 0) == "BOOLEAN"
    assert types.flink_type("c", types.TINYINT, "TINYINT", 3, 0) == "SMALLINT"
    assert types.flink_type("c", types.TIMESTAMP, "DATETIME", 19, 0) == "TIMESTAMP(3)"
    assert types.flink_type("c", types.TIMESTAMP, "timestamptz", 35, 6) == "TIMESTAMP_LTZ(3)"
    assert types.flink_type("c", types.OTHER, "uuid", 36, 0) == "STRING"
    assert types.flink_type("c", types.NVARCHAR, "nvarchar", 100, 0) == "STRING"


def test_unsupported_types_say_what_to_do() -> None:
    with pytest.raises(types.UnsupportedType, match="CAST"):
        types.flink_type("amount", types.NUMERIC, "numeric", 0, 0)
    with pytest.raises(types.UnsupportedType, match="cast it"):
        types.flink_type("flags", types.BIT, "BIT", 8, 0)
    with pytest.raises(types.UnsupportedType, match="geom"):
        types.flink_type("geom", 1111, "geometry", 0, 0)


def test_columns_must_be_unique_and_not_audit_names() -> None:
    with pytest.raises(ValueError, match="twice"):
        check_columns([Column("a", "INT"), Column("A", "INT")])
    with pytest.raises(ValueError, match="adds"):
        check_columns([Column("ingest_date", "STRING")])


def test_sql_statements(pipelines: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SHOP_MYSQL_RO_PASSWORD", "it's")
    plan = plan_for(pipelines)
    columns = [Column("order_id", "BIGINT"), Column("customer_id", "INT")]

    source = source_ddl(plan, columns, ("1", "5000"))
    assert "`order_id` BIGINT, `customer_id` INT" in source
    assert "'table-name' = '(SELECT order_id, customer_id FROM orders) AS q'" in source
    assert "'password' = 'it''s'" in source
    assert "'scan.partition.column' = 'order_id'" in source
    assert "'scan.partition.lower-bound' = '1'" in source and "'scan.partition.upper-bound' = '5000'" in source
    assert "scan.auto-commit" not in source  # PostgreSQL only
    assert "scan.partition" not in source_ddl(plan, columns, None)

    sink = sink_ddl(plan, columns)
    assert "ingest_date STRING, _ingest_run_id STRING, _ingested_at TIMESTAMP(3)) PARTITIONED BY (ingest_date)" in sink
    assert "'path' = 'abfss://raw@acct.dfs.core.windows.net/_staging/run-1'" in sink
    assert "'parquet.compression' = 'SNAPPY'" in sink

    assert insert_sql(plan, columns) == (
        "INSERT INTO dst SELECT `order_id`, `customer_id`, '2026-11-02', 'run-1', "
        "CAST('2026-11-02 02:00:05.123' AS TIMESTAMP(3)) FROM src"
    )
