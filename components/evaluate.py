import argparse
import json
import shutil
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd

from common import directory_sha256, passes_gate, score_model, write_json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-input", type=Path, required=True)
    parser.add_argument("--validation-data", type=Path, required=True)
    parser.add_argument("--max-rmse", type=float, required=True)
    parser.add_argument("--approved-model", type=Path, required=True)
    parser.add_argument("--report-output", type=Path, required=True)
    args = parser.parse_args()
    with mlflow.start_run():
        model = mlflow.sklearn.load_model(str(args.model_input))
        validation = pd.read_csv(args.validation_data / "validation.csv")
        metrics = score_model(model, validation)
        metadata = json.loads((args.validation_data / "metadata.json").read_text())
        approved = passes_gate(metrics, args.max_rmse)
        report = {
            **metrics, "max_rmse": args.max_rmse, "approved": approved,
            "validation_rows": len(validation),
            "validation_sha256": metadata["validation_sha256"],
            "source_sha256": metadata["source_sha256"],
            "model_sha256": directory_sha256(args.model_input),
        }
        write_json(args.report_output / "evaluation.json", report)
        mlflow.log_metrics({**metrics, "quality_gate_passed": int(approved)})
        mlflow.log_param("max_rmse", args.max_rmse)
        mlflow.log_dict(report, "evaluation.json")
        print(json.dumps(report, indent=2), flush=True)
        if not approved:
            raise RuntimeError(
                f"QUALITY_GATE_FAILED: RMSE {metrics['rmse']:.6f} exceeds {args.max_rmse}. "
                "No approved model was exported; model registration is blocked."
            )
        shutil.copytree(args.model_input, args.approved_model, dirs_exist_ok=True)
        if directory_sha256(args.approved_model) != report["model_sha256"]:
            raise RuntimeError("Approved model content does not match the evaluated model.")


if __name__ == "__main__":
    main()
