"""Phase 2 spike: reads the Parquet output with pyarrow and pandas and prints rows, schema and timestamp encoding.

Run with the JobManager's Python (PyFlink brings pyarrow and pandas):
  python /opt/spikes/phase-2/check_parquet.py /opt/ingestion/spike-out/postgres/orders
Spark and Delta readers are checked separately (roadmap: Parquet timestamp encoding spike).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pyarrow.dataset as ds
import pyarrow.parquet as pq


def main(root: str) -> None:
    """Prints the file and row counts, the schemas and the first rows of the Parquet output under ``root``."""
    files = sorted(Path(root).rglob("*.parquet")) or sorted(p for p in Path(root).rglob("part-*") if p.is_file())
    if not files:
        sys.exit(f"No Parquet files under {root}")
    dataset = ds.dataset([str(f) for f in files], format="parquet")
    print(f"files: {len(files)}, rows: {dataset.count_rows()}")
    print(f"arrow schema:\n{dataset.schema}")
    physical = pq.ParquetFile(files[0]).schema
    for i in range(len(physical)):
        column = physical.column(i)
        print(f"  parquet {column.name}: physical={column.physical_type} logical={column.logical_type}")
    print(dataset.head(3).to_pandas().to_string())


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "/opt/ingestion/spike-out")
