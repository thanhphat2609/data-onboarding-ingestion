# data-onboarding-ingestion
Self-service ingestion platform: declare a source in YAML (SQL Server, PostgreSQL, BigQuery), and it compiles to a bounded Flink batch job that lands Parquet in ADLS Gen2, with row-count reconciliation and run tracking.
