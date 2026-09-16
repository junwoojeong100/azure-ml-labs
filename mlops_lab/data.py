import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from components.common import FEATURES, TARGET
from mlops_lab.config import ROOT, save_json


def make_dataset(version: str) -> pd.DataFrame:
    if version not in {"1", "2"}:
        raise ValueError("This lab defines data versions 1 and 2 only.")
    # Generate once at the maximum size so v2 appends rows without changing v1.
    values = np.random.default_rng(42).normal(size=(1400, len(FEATURES) + 1))
    coefficients = np.array([15.0, -10.0, 5.0, 0.0, 12.0, -7.0, 3.0, 0.0])
    frame = pd.DataFrame(values[:, :-1], columns=FEATURES)
    frame[TARGET] = 50 + values[:, :-1] @ coefficients + 2 * values[:, -1]
    frame.insert(0, "partition", np.where(np.arange(len(frame)) < 200, "validation", "train"))
    frame.insert(0, "row_id", np.arange(len(frame)))
    return frame.iloc[:1000 if version == "1" else 1400].copy()


def generate_data(directory: Path = ROOT / "data") -> dict:
    directory.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for version in ("1", "2"):
        frame = make_dataset(version)
        path = directory / f"regression-v{version}.csv"
        frame.to_csv(path, index=False, float_format="%.12g")
        validation = frame.loc[frame["partition"] == "validation"]
        manifest[version] = {
            "path": str(path),
            "rows": len(frame),
            "training_rows": int((frame["partition"] == "train").sum()),
            "validation_rows": len(validation),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "validation_sha256": hashlib.sha256(
                validation.to_csv(index=False, float_format="%.12g").encode()
            ).hexdigest(),
        }
    sample = make_dataset("1").loc[:4, FEATURES].round(8)
    save_json(directory / "sample-request.json", {
        "input_data": {"columns": FEATURES, "index": sample.index.tolist(), "data": sample.values.tolist()}
    })
    save_json(directory / "manifest.json", manifest)
    return manifest
