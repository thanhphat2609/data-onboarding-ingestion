# Flink image (ADR-0007): JDBC connector and drivers, Kafka connector, Parquet, and the ADLS Gen2 filesystem plugin.
# Target `taskmanager` is the base; target `jobmanager` adds Python 3.11 and PyFlink for the runner (ADR-0010),
# because only the JobManager runs Python. Versions are the Phase 2 candidates; the spikes confirm or replace them.

FROM flink:1.20.5-scala_2.12-java17 AS taskmanager

ARG MAVEN=https://repo1.maven.org/maven2

# JDBC connector with every dialect (SQL Server, PostgreSQL, MySQL...) and the drivers.
ADD --chmod=644 ${MAVEN}/org/apache/flink/flink-connector-jdbc/3.4.0-1.20/flink-connector-jdbc-3.4.0-1.20.jar /opt/flink/lib/
ADD --chmod=644 ${MAVEN}/com/microsoft/sqlserver/mssql-jdbc/13.6.1.jre11/mssql-jdbc-13.6.1.jre11.jar /opt/flink/lib/
ADD --chmod=644 ${MAVEN}/org/postgresql/postgresql/42.7.14/postgresql-42.7.14.jar /opt/flink/lib/
ADD --chmod=644 ${MAVEN}/com/mysql/mysql-connector-j/9.7.0/mysql-connector-j-9.7.0.jar /opt/flink/lib/

# Kafka SQL connector (shaded, with its client): reads the landing topics of API sources on Redpanda (ADR-0015).
ADD --chmod=644 ${MAVEN}/org/apache/flink/flink-sql-connector-kafka/3.3.0-1.20/flink-sql-connector-kafka-3.3.0-1.20.jar /opt/flink/lib/

# Parquet format for the filesystem connector; it needs Hadoop classes, from the shaded Hadoop client.
ADD --chmod=644 ${MAVEN}/org/apache/flink/flink-sql-parquet/1.20.5/flink-sql-parquet-1.20.5.jar /opt/flink/lib/
ADD --chmod=644 ${MAVEN}/org/apache/hadoop/hadoop-client-api/3.3.6/hadoop-client-api-3.3.6.jar /opt/flink/lib/
ADD --chmod=644 ${MAVEN}/org/apache/hadoop/hadoop-client-runtime/3.3.6/hadoop-client-runtime-3.3.6.jar /opt/flink/lib/

# abfss:// through the bundled plugin (loaded in its own class loader), and flink-python for PythonDriver.
RUN set -eux; \
    mkdir -p /opt/flink/plugins/azure-fs-hadoop; \
    cp /opt/flink/opt/flink-azure-fs-hadoop-*.jar /opt/flink/plugins/azure-fs-hadoop/; \
    cp /opt/flink/opt/flink-python-*.jar /opt/flink/lib/

FROM taskmanager AS jobmanager

# Python from python-build-standalone through uv: runs on the image's glibc, no apt packages needed.
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_NO_CACHE=1
RUN set -eux; \
    uv venv --python 3.11 /opt/pyflink; \
    uv pip install --python /opt/pyflink/bin/python apache-flink==1.20.5; \
    rm /usr/local/bin/uv
ENV PATH=/opt/pyflink/bin:$PATH
