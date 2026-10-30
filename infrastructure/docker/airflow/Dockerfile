# Airflow with the Kafka client for the fetch task of API jobs (ADR-0015). Everything else is the stock image; the
# control plane library is mounted and put on PYTHONPATH by the Compose files, so DAG code changes need no rebuild.

FROM apache/airflow:3.3.2

RUN pip install --no-cache-dir confluent-kafka==2.16.0
