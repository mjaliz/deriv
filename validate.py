from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from validation import ArtifactValidationError, validate_artifacts


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated compliance diff artifacts.")
    parser.add_argument("--output-dir", default=".", help="Directory containing generated artifacts.")
    parser.add_argument("--source-file", default="sources.json", help="Path to sources.json.")
    parser.add_argument(
        "--previous-snapshot-file",
        default="previous_snapshot_document_a.txt",
        help="Path to previous_snapshot_document_a.txt.",
    )
    args = parser.parse_args()
    try:
        validate_artifacts(
            Path(args.output_dir),
            source_file=Path(args.source_file),
            previous_snapshot_file=Path(args.previous_snapshot_file),
        )
    except ArtifactValidationError as exc:
        for error in exc.errors:
            logger.error(error)
        raise SystemExit(1) from exc
    logger.info("Validation passed")


if __name__ == "__main__":
    main()
