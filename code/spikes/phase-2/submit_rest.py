"""Phase 2 spike (ADR-0010): submits a PyFlink script through the Flink REST API with PythonDriver, the way the
Airflow `submit` task will in Phase 4, and waits for the job to end.

  python /opt/spikes/phase-2/submit_rest.py /opt/spikes/phase-2/jdbc_to_parquet.py --source mysql --table customers

The script path must exist on the JobManager, which runs it to build the job graph.
"""

from __future__ import annotations

import glob
import os
import sys
import time

import requests

FLINK = os.environ.get("FLINK_REST_URL", "http://localhost:8081")
TERMINAL = {"FINISHED", "FAILED", "CANCELED"}


def upload_flink_python() -> str:
    """Uploads the flink-python JAR once and reuses it by name."""
    jar = glob.glob("/opt/flink/lib/flink-python-*.jar")[0]
    name = os.path.basename(jar)
    for uploaded in requests.get(f"{FLINK}/jars", timeout=30).json().get("files", []):
        if uploaded["name"] == name:
            return str(uploaded["id"])
    with open(jar, "rb") as content:
        response = requests.post(f"{FLINK}/jars/upload", files={"jarfile": (name, content)}, timeout=120)
    response.raise_for_status()
    return str(response.json()["filename"].rsplit("/", 1)[-1])


def main(script: str, script_args: list[str]) -> None:
    """Uploads the flink-python JAR, submits ``script`` through the REST API with PythonDriver and waits."""
    jar_id = upload_flink_python()
    started = time.monotonic()
    response = requests.post(
        f"{FLINK}/jars/{jar_id}/run",
        json={
            "entryClass": "org.apache.flink.client.python.PythonDriver",
            "programArgsList": ["-py", script, *script_args],
        },
        timeout=600,
    )
    if response.status_code >= 400:
        sys.exit(f"Submit failed ({response.status_code}): {response.text[:2000]}")
    job_id = response.json()["jobid"]
    print(f"Submitted {job_id} in {time.monotonic() - started:.1f} s")
    while (state := requests.get(f"{FLINK}/jobs/{job_id}", timeout=30).json()["state"]) not in TERMINAL:
        time.sleep(3)
    print(f"Job {job_id}: {state} after {time.monotonic() - started:.1f} s")
    sys.exit(0 if state == "FINISHED" else 1)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
