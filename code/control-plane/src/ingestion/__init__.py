"""Control plane of the ingestion platform: templates, validation, config store, source access, Airflow client.

The Ingestion API (``ingestion.api``) is a thin HTTP layer over this library; ``ingestctl`` and the Airflow tasks
use the same modules from Phase 3 on (architecture §3.2).
"""
