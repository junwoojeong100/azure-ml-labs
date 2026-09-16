import argparse
import hashlib
from pathlib import Path

import mlflow
import pandas as pd

from common import split_data, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-data", type=Path, required=True)
    parser.add_argument("--train-data", type=Path, required=True)
    parser.add_argument("--validation-data", type=Path, required=True)
    args = parser.parse_args()
    with mlflow.start_run():
        train, validation = split_data(pd.read_csv(args.raw_data))
        args.train_data.mkdir(parents=True, exist_ok=True)
        args.validation_data.mkdir(parents=True, exist_ok=True)
        train.to_csv(args.train_data / "train.csv", index=False)
        validation.to_csv(args.validation_data / "validation.csv", index=False)
        metadata = {
            "source_sha256": hashlib.sha256(args.raw_data.read_bytes()).hexdigest(),
            "train_rows": len(train),
            "validation_rows": len(validation),
            "overlapping_row_ids": len(set(train["row_id"]) & set(validation["row_id"])),
            "validation_sha256": hashlib.sha256(
                (args.validation_data / "validation.csv").read_bytes()
            ).hexdigest(),
        }
        write_json(args.validation_data / "metadata.json", metadata)
        mlflow.log_metrics({key: metadata[key] for key in (
            "train_rows", "validation_rows", "overlapping_row_ids"
        )})
        mlflow.log_dict(metadata, "data-lineage.json")
        print(metadata, flush=True)


if __name__ == "__main__":
    main()
