import argparse
import importlib.metadata
import json
from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from mlflow.models import infer_signature

from common import FEATURES, fit_model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-data", type=Path, required=True)
    parser.add_argument("--alpha", type=float, required=True)
    parser.add_argument("--model-output", type=Path, required=True)
    args = parser.parse_args()
    with mlflow.start_run():
        train = pd.read_csv(args.train_data / "train.csv")
        model = fit_model(train, args.alpha)
        example = train[FEATURES].head(5)
        signature = infer_signature(example, model.predict(example))
        packages = {
            name: importlib.metadata.version(name)
            for name in ("scikit-learn", "numpy", "pandas", "cloudpickle")
        }
        packages["mlflow"] = mlflow.__version__
        requirements = [f"{name}=={version}" for name, version in packages.items()]
        requirements.extend(
            line for line in Path(__file__).with_name("inference-requirements.txt").read_text().splitlines()
            if line and not line.startswith("#")
        )
        mlflow.log_params({"alpha": args.alpha, "train_rows": len(train), "features": len(FEATURES)})
        mlflow.log_dict(packages, "runtime-versions.json")
        print(json.dumps({"alpha": args.alpha, "runtime": packages}), flush=True)
        mlflow.sklearn.save_model(
            model, path=str(args.model_output), signature=signature,
            input_example=example, pip_requirements=requirements,
        )
        # Azure ML supports run artifacts, not MLflow 3's separate logged-models API.
        mlflow.log_artifacts(str(args.model_output), artifact_path="candidate_model")


if __name__ == "__main__":
    main()
