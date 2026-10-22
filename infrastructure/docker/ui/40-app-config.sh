#!/bin/sh
# Writes runtime settings for the Web UI from environment variables.
# Empty values make the UI use the same host with the default ports (Airflow 8080, Flink 8081),
# which also works behind GitHub Codespaces port forwarding.
set -eu

cat > /usr/share/nginx/html/config.js <<EOF
window.__APP_CONFIG__ = {
  airflowUrl: "${AIRFLOW_URL:-}",
  flinkUrl: "${FLINK_URL:-}"
}
EOF
