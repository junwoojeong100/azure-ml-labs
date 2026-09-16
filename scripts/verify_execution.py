import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from components.common import FEATURES, fit_model, split_data
from mlops_lab.config import ARTIFACTS, ROOT, Settings, save_json
from mlops_lab.data import make_dataset
from mlops_lab.operations import require_approved_report
from mlops_lab.pipeline import source_fingerprint


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def verify(baseline: str, rejected: str, retrain: str, baseline_version: str, retrain_version: str) -> dict:
    settings = Settings.load()
    runs = {name: load(ARTIFACTS / "runs" / f"{label}.json") for name, label in (
        ("baseline", baseline), ("rejected", rejected), ("retrain", retrain),
    )}
    for name, run in runs.items():
        if run["workspace_id"] != settings.workspace_id():
            raise AssertionError(f"{name} belongs to another workspace.")
        if run["component_source_sha256"] != source_fingerprint():
            raise AssertionError(f"{name} did not use the current component sources.")
        if run["component_version"] != settings.component_version or run["environment"] != settings.environment:
            raise AssertionError(f"{name} used different versioned assets.")
        if not any(
            child["display_name"] == "evaluate_gate" and settings.compute_cluster in child["compute"]
            for child in run["children"]
        ):
            raise AssertionError(f"{name} did not evaluate on the required Azure ML compute.")
    for name in ("baseline", "retrain"):
        run = runs[name]
        require_approved_report(run["status"], run["evaluation"], run["max_rmse"])
    bad = runs["rejected"]
    if (
        bad["status"] != "Failed" or bad["evaluation"]["approved"] is not False
        or bad["evaluation"]["rmse"] <= bad["max_rmse"]
        or not any(c["display_name"] == "evaluate_gate" and c["status"] == "Failed" for c in bad["children"])
    ):
        raise AssertionError("The rejection must be a measured quality-gate failure, not an infrastructure failure.")
    if runs["baseline"]["evaluation"]["validation_sha256"] != runs["retrain"]["evaluation"]["validation_sha256"]:
        raise AssertionError("Baseline and retraining did not use the same validation data.")
    models = {}
    for name, version in (("baseline", baseline_version), ("retrain", retrain_version)):
        model = load(ARTIFACTS / "models" / f"v{version}.json")
        if model["source_job"] != runs[name]["job_name"]:
            raise AssertionError("Registered model does not originate from its approved pipeline.")
        models[name] = model
    rejection = load(ARTIFACTS / "rejection-verification.json")
    if (
        rejection["workspace"] != settings.workspace
        or rejection["registration_blocked"] is not True
        or rejection["rejected_model_version_absent"] is not True
    ):
        raise AssertionError("The rejected model's registration block was not verified in this workspace.")
    request = load(ROOT / "data" / "sample-request.json")
    features = pd.DataFrame(request["input_data"]["data"], columns=request["input_data"]["columns"])
    if features.columns.tolist() != FEATURES:
        raise AssertionError("Unexpected inference feature schema.")
    expected = {
        "blue": fit_model(split_data(make_dataset("1"))[0], 1.0).predict(features),
        "green": fit_model(split_data(make_dataset("2"))[0], 0.1).predict(features),
    }
    if np.allclose(expected["blue"], expected["green"], rtol=1e-6, atol=1e-6):
        raise AssertionError("The sample does not distinguish the model versions for rollback verification.")
    responses = sorted(
        [load(path) for path in (ARTIFACTS / "inference").glob("*.json")],
        key=lambda item: item["invoked_at"],
    )
    direct = set()
    routed = []
    for response in responses:
        predictions = np.asarray(response["predictions"])
        if predictions.shape != (5,) or not np.isfinite(predictions).all() or response["rows"] != 5:
            raise AssertionError("Inference must return exactly five finite predictions.")
        matches = [name for name, values in expected.items()
                   if np.allclose(predictions, values, rtol=1e-6, atol=1e-6)]
        if len(matches) != 1:
            raise AssertionError("Endpoint predictions do not match the versioned training logic.")
        if response["deployment"] == "traffic-routed":
            routed.append(matches[0])
        else:
            if response["deployment"] != matches[0]:
                raise AssertionError("A named deployment served the wrong model.")
            direct.add(matches[0])
    if direct != {"blue", "green"}:
        raise AssertionError("Both deployments must be tested directly.")
    if not any(routed[index:index + 3] == ["blue", "green", "blue"] for index in range(len(routed) - 2)):
        raise AssertionError("Default-route promotion and rollback have not both been demonstrated.")
    cleanup = load(ARTIFACTS / "cleanup.json")
    state = load(ARTIFACTS / "final-resource-state.json")
    if cleanup["endpoint"] not in {"deleted", "absent"} or cleanup["compute_instance_state"] != "Stopped":
        raise AssertionError("Runtime cleanup is incomplete.")
    if state["cluster_current_nodes"] != 0 or state["cluster_min_instances"] != 0:
        raise AssertionError("The cluster has not actually scaled to zero.")
    if state["endpoint_exists"] or state["runner_exists"] or state["compute_instance_state"] != "Stopped":
        raise AssertionError("A temporary endpoint, runner, or running compute instance remains.")
    if state["managed_network_mode"] != "AllowInternetOutbound":
        raise AssertionError("The final workspace does not use the required managed outbound network.")
    managed_check = load(ARTIFACTS / "runs" / "managed-network-check.json")
    require_approved_report(
        managed_check["status"], managed_check["evaluation"], managed_check["max_rmse"]
    )
    if not managed_check["force_rerun"]:
        raise AssertionError("Managed-network validation must not reuse the old compute's cached outputs.")
    if not all(settings.compute_cluster in (child["compute"] or "") for child in managed_check["children"]):
        raise AssertionError("The final managed-network check did not execute every step on compute.")
    result = {
        "workspace": settings.workspace, "resource_group": settings.resource_group,
        "environment": settings.environment, "component_version": settings.component_version,
        "component_source_sha256": source_fingerprint(),
        "runs": {name: {key: run[key] for key in (
            "job_name", "studio_url", "status", "data_version", "alpha", "evaluation"
        )} for name, run in runs.items()},
        "models": {name: {key: model[key] for key in ("id", "version", "source_job")} for name, model in models.items()},
        "inference_calls": len(responses), "direct_deployments": sorted(direct),
        "rejected_registration_verified": True,
        "verified_routed_model_sequence": routed, "final_resource_state": state,
        "managed_network_validation": {
            key: managed_check[key] for key in ("job_name", "studio_url", "status", "force_rerun", "evaluation")
        },
    }
    save_json(ROOT / "docs" / "execution-evidence.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify real Azure execution evidence before publishing the guide")
    parser.add_argument("--baseline", default="managed-network-check")
    parser.add_argument("--rejected", default="bad-model-v3")
    parser.add_argument("--retrain", default="retrain-v3")
    parser.add_argument("--baseline-version", default="1")
    parser.add_argument("--retrain-version", default="2")
    args = parser.parse_args()
    result = verify(args.baseline, args.rejected, args.retrain, args.baseline_version, args.retrain_version)
    print(json.dumps({
        "verified": True, "inference_calls": result["inference_calls"],
        "routed_models": result["verified_routed_model_sequence"],
    }, indent=2))


if __name__ == "__main__":
    main()
