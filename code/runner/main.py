"""Entry point for ``flink run -py`` and for PythonDriver (ADR-0010); the logic is in ingestion_runner/."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingestion_runner.run import run  # noqa: E402

if __name__ == "__main__":
    run()
