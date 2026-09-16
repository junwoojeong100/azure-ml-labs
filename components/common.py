import hashlib
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

FEATURES = [f"feature_{index}" for index in range(8)]
TARGET = "target"
COLUMNS = ["row_id", "partition", *FEATURES, TARGET]


def validate_frame(frame: pd.DataFrame) -> None:
    if frame.columns.tolist() != COLUMNS:
        raise ValueError(f"Schema mismatch. Expected columns in this order: {COLUMNS}")
    if frame.empty or frame.isna().any().any():
        raise ValueError("Dataset must be nonempty and must not contain missing values.")
    if frame["row_id"].duplicated().any():
        raise ValueError("row_id must be unique to prevent train/validation overlap.")
    if not set(frame["partition"]).issubset({"train", "validation"}):
        raise ValueError("partition must contain only 'train' or 'validation'.")
    if not np.isfinite(frame[FEATURES + [TARGET]].to_numpy(dtype=float)).all():
        raise ValueError("Features and target must be finite numeric values.")


def split_data(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    validate_frame(frame)
    train = frame.loc[frame["partition"] == "train"].copy()
    validation = frame.loc[frame["partition"] == "validation"].copy()
    if len(train) < 50 or len(validation) < 20:
        raise ValueError("At least 50 training and 20 validation rows are required.")
    return train, validation


def fit_model(train: pd.DataFrame, alpha: float) -> Pipeline:
    validate_frame(train)
    if set(train["partition"]) != {"train"}:
        raise ValueError("The training component accepts training rows only.")
    if not math.isfinite(alpha) or alpha < 0:
        raise ValueError("alpha must be finite and nonnegative.")
    model = Pipeline([("scaler", StandardScaler()), ("ridge", Ridge(alpha=alpha))])
    model.fit(train[FEATURES], train[TARGET])
    return model


def score_model(model: Pipeline, validation: pd.DataFrame) -> dict[str, float]:
    validate_frame(validation)
    if set(validation["partition"]) != {"validation"}:
        raise ValueError("The evaluator accepts validation rows only.")
    prediction = model.predict(validation[FEATURES])
    return {
        "rmse": float(math.sqrt(mean_squared_error(validation[TARGET], prediction))),
        "mae": float(mean_absolute_error(validation[TARGET], prediction)),
        "r2": float(r2_score(validation[TARGET], prediction)),
    }


def passes_gate(metrics: dict[str, float], max_rmse: float) -> bool:
    if not math.isfinite(max_rmse) or max_rmse <= 0:
        raise ValueError("max_rmse must be finite and positive.")
    if not all(math.isfinite(value) for value in metrics.values()):
        raise ValueError("Non-finite evaluation metrics cannot pass the quality gate.")
    return metrics["rmse"] <= max_rmse


def directory_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file.relative_to(path).as_posix().encode() + b"\0")
        digest.update(file.read_bytes())
    return digest.hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
