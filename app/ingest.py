import argparse
from contextlib import ExitStack
from pathlib import Path

from app.config import Settings
from app.contracts import ServiceError
from app.main import build_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description="Index the synthetic support corpus")
    parser.add_argument("--docs", type=Path, default=Path("data/docs"))
    args = parser.parse_args()
    with ExitStack() as stack:
        index = build_pipeline(Settings(), stack).retriever
        try:
            name, count = index.ingest(args.docs)
        except (ServiceError, ValueError, OSError) as exc:
            parser.exit(2, f"Ingestion failed: {exc}\n")
    print(f"Indexed {count} passages in {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
