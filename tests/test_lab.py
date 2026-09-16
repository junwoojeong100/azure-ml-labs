import json
import ast
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import nbformat
from azure.core.exceptions import ResourceNotFoundError

from components.common import (
    FEATURES, directory_sha256, fit_model, passes_gate, score_model, split_data, validate_frame,
)
from mlops_lab.config import ROOT, Settings
from mlops_lab.data import generate_data, make_dataset
from mlops_lab.operations import require_approved_report, run_path
from mlops_lab.pipeline import build_pipeline, component_definitions


@pytest.fixture
def settings():
    values = json.loads((ROOT / "config.example.json").read_text())
    values.update(
        subscription_id="00000000-0000-0000-0000-000000000001",
        tenant_id="00000000-0000-0000-0000-000000000002",
        expected_account="lab@example.test",
        resource_group="rg-unit-test", workspace="mlw-unit-test", endpoint_name="ep-unit-test",
    )
    return Settings(**values)


def test_data_versions_append_only_and_share_fixed_validation(tmp_path):
    first, second = make_dataset("1"), make_dataset("2")
    pd.testing.assert_frame_equal(first, second.iloc[:1000])
    train1, validation1 = split_data(first)
    train2, validation2 = split_data(second)
    pd.testing.assert_frame_equal(validation1, validation2)
    assert (len(train1), len(train2), len(validation1)) == (800, 1200, 200)
    assert not set(train2.row_id) & set(validation2.row_id)
    manifest = generate_data(tmp_path)
    assert manifest["1"]["sha256"] != manifest["2"]["sha256"]
    assert manifest["1"]["validation_sha256"] == manifest["2"]["validation_sha256"]
    request = json.loads((tmp_path / "sample-request.json").read_text())
    assert request["input_data"]["columns"] == FEATURES
    assert len(request["input_data"]["data"]) == 5


@pytest.mark.parametrize(("version", "alpha", "approved"), [
    ("1", 1.0, True), ("1", 1_000_000.0, False), ("2", 0.1, True),
])
def test_real_metrics_enforce_quality_gate(version, alpha, approved):
    train, validation = split_data(make_dataset(version))
    model = fit_model(train, alpha)
    metrics = score_model(model, validation)
    assert passes_gate(metrics, 3.0) is approved
    np.testing.assert_allclose(model["scaler"].mean_, train[FEATURES].mean())
    assert model.feature_names_in_.tolist() == FEATURES


@pytest.mark.parametrize("threshold", [0, -1, float("nan"), float("inf")])
def test_invalid_threshold_cannot_pass(threshold):
    with pytest.raises(ValueError):
        passes_gate({"rmse": 2.0}, threshold)


def test_gate_boundary_and_nonfinite_metrics():
    assert passes_gate({"rmse": 3.0}, 3.0)
    assert not passes_gate({"rmse": 3.000001}, 3.0)
    with pytest.raises(ValueError):
        passes_gate({"rmse": float("nan")}, 3.0)


def test_bad_data_is_rejected():
    frame = make_dataset("1")
    with pytest.raises(ValueError, match="Schema"):
        validate_frame(frame.drop(columns=["feature_0"]))
    frame.loc[0, "row_id"] = frame.loc[1, "row_id"]
    with pytest.raises(ValueError, match="unique"):
        validate_frame(frame)
    frame = make_dataset("1")
    frame.loc[0, "feature_0"] = np.inf
    with pytest.raises(ValueError, match="finite"):
        validate_frame(frame)
    with pytest.raises(ValueError, match="training rows only"):
        fit_model(make_dataset("1"), 1.0)


def test_registration_requires_success_and_measured_approval():
    report = {"approved": True, "rmse": 2.0, "mae": 1.5, "r2": 0.99, "max_rmse": 3.0}
    require_approved_report("Completed", report, 3.0)
    for status in ("Failed", "Canceled", "Running"):
        with pytest.raises(RuntimeError):
            require_approved_report(status, report, 3.0)
    with pytest.raises(RuntimeError, match="did not approve"):
        require_approved_report("Completed", {**report, "approved": False}, 3.0)
    with pytest.raises(RuntimeError, match="exceeds"):
        require_approved_report("Completed", {**report, "rmse": 30.0}, 3.0)
    with pytest.raises(RuntimeError, match="threshold"):
        require_approved_report("Completed", report, 4.0)


def test_wrong_azure_account_is_rejected(settings, monkeypatch):
    result = SimpleNamespace(stdout=json.dumps({
        "id": settings.subscription_id, "tenantId": settings.tenant_id,
        "state": "Enabled", "user": {"name": "wrong@example.test"},
    }))
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs: result)
    with pytest.raises(RuntimeError, match="mismatch"):
        settings.verify_account()


def test_cli_credential_uses_subscription_without_conflicting_tenant(settings, monkeypatch):
    import azure.ai.ml
    import azure.identity

    calls = {}
    monkeypatch.setattr(Settings, "verify_account", lambda self: {})
    monkeypatch.setattr(
        azure.identity, "AzureCliCredential",
        lambda **kwargs: calls.update(kwargs) or SimpleNamespace(),
    )
    monkeypatch.setattr(azure.ai.ml, "MLClient", lambda *args: args)
    settings.client()
    assert calls["subscription"] == settings.subscription_id
    assert "tenant_id" not in calls


def test_explicit_managed_identity_does_not_use_an_unrelated_cli_login(settings, monkeypatch):
    import azure.ai.ml
    import azure.identity

    calls = {}
    monkeypatch.setattr(
        Settings, "verify_account",
        lambda self: pytest.fail("Explicit managed identity must not use the CLI account."),
    )
    monkeypatch.setattr(
        azure.identity, "ManagedIdentityCredential",
        lambda **kwargs: calls.update(kwargs) or SimpleNamespace(),
    )
    monkeypatch.setattr(azure.ai.ml, "MLClient", lambda *args: args)
    settings.client(managed_identity_client_id="specific-compute-client-id")
    assert calls == {"client_id": "specific-compute-client-id"}


def test_endpoint_is_deleted_before_stopping_the_callers_compute(settings, monkeypatch, tmp_path):
    import mlops_lab.operations as operations

    events = []
    state = {"deleted": False, "stopped": False}

    def endpoint_get(name):
        if state["deleted"]:
            raise ResourceNotFoundError("Endpoint no longer exists.")
        return SimpleNamespace(tags={"purpose": "aml-mlops-hands-on", "workspace": settings.workspace})

    def delete_endpoint(name):
        events.append("delete_endpoint")
        state["deleted"] = True
        return SimpleNamespace(result=lambda: None)

    def compute_get(name):
        if name == settings.compute_cluster:
            return SimpleNamespace(min_instances=0, max_instances=2)
        return SimpleNamespace(state="Stopped" if state["stopped"] else "Running")

    def stop_compute(name):
        events.append("stop_compute")
        state["stopped"] = True
        return SimpleNamespace(result=lambda: None)

    client = SimpleNamespace(
        online_endpoints=SimpleNamespace(get=endpoint_get, begin_delete=delete_endpoint),
        compute=SimpleNamespace(get=compute_get, begin_stop=stop_compute),
    )
    monkeypatch.setattr(operations, "ARTIFACTS", tmp_path)
    result = operations.cleanup_runtime(client, settings, delete_endpoint=True)
    assert events == ["delete_endpoint", "stop_compute"]
    assert result["endpoint"] == "deleted"
    assert result["compute_instance_state"] == "Stopped"


def test_studio_notebook_is_valid_and_its_cells_parse():
    notebook = nbformat.read(ROOT / "notebooks/01-studio-mlops.ipynb", as_version=4)
    nbformat.validate(notebook)
    for cell in notebook.cells:
        if cell.cell_type == "code":
            ast.parse(cell.source)


def test_failed_evaluation_report_uses_mlflow_artifact_not_named_output(settings, monkeypatch, tmp_path):
    import mlops_lab.operations as operations

    receipt = {"job_name": "parent", "workspace_id": settings.workspace_id()}
    report = {"approved": False, "rmse": 23.4, "max_rmse": 3.0}
    calls = []

    def download(**kwargs):
        calls.append(kwargs)
        path = Path(kwargs["download_path"]) / "artifacts" / "evaluation.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(report))

    client = SimpleNamespace(jobs=SimpleNamespace(
        list=lambda **kwargs: [SimpleNamespace(name="failed-evaluator", display_name="evaluate_gate")],
        download=download,
    ))
    monkeypatch.setattr(operations, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(operations, "read_run", lambda *args: receipt)
    monkeypatch.setattr(operations, "run_path", lambda label: tmp_path / f"{label}.json")
    assert operations.download_report(client, settings, "bad") == report
    assert calls[0]["name"] == "failed-evaluator"
    assert "output_name" not in calls[0]


def test_creating_deployment_is_not_reported_as_ready(settings, monkeypatch, tmp_path):
    import mlops_lab.operations as operations

    endpoint = SimpleNamespace(
        name=settings.endpoint_name, auth_mode="aad_token", traffic={},
        tags={"purpose": "aml-mlops-hands-on", "workspace": settings.workspace},
    )
    client = SimpleNamespace(online_endpoints=SimpleNamespace(get=lambda name: endpoint))
    deployment = SimpleNamespace(name="blue", model="azureml:model:1", provisioning_state="Creating")
    monkeypatch.setattr(operations, "ARTIFACTS", tmp_path)
    assert operations.deployment_result(client, settings, deployment)["ready"] is False


def test_async_deployment_does_not_require_immediate_resource_visibility(settings, monkeypatch, tmp_path):
    import mlops_lab.operations as operations

    endpoint = SimpleNamespace(tags={"purpose": "aml-mlops-hands-on", "workspace": settings.workspace})
    model = SimpleNamespace(
        id="azureml:model:1", tags={"quality_gate": "passed", "purpose": "aml-mlops-hands-on"}
    )
    client = SimpleNamespace(
        models=SimpleNamespace(get=lambda *args: model),
        online_endpoints=SimpleNamespace(get=lambda name: endpoint),
        online_deployments=SimpleNamespace(
            begin_create_or_update=lambda definition: SimpleNamespace(),
            get=lambda **kwargs: pytest.fail("A newly accepted deployment may still return 404."),
        ),
    )
    monkeypatch.setattr(operations, "ARTIFACTS", tmp_path)
    result = operations.deploy(client, settings, "1", "blue", wait=False)
    assert result["provisioning_state"] == "Submitted"
    assert result["ready"] is False


def test_failed_deployment_wait_raises(settings):
    from mlops_lab.operations import wait_for_deployment

    endpoint = SimpleNamespace(tags={"purpose": "aml-mlops-hands-on", "workspace": settings.workspace})
    client = SimpleNamespace(
        online_endpoints=SimpleNamespace(get=lambda name: endpoint),
        online_deployments=SimpleNamespace(get=lambda **kwargs: SimpleNamespace(provisioning_state="Failed")),
    )
    with pytest.raises(RuntimeError, match="Failed"):
        wait_for_deployment(client, settings, "blue")


def test_source_fingerprint_covers_inference_dependency_manifest(monkeypatch, tmp_path):
    import mlops_lab.pipeline as pipeline

    directory = tmp_path / "components"
    directory.mkdir()
    (directory / "train.py").write_text("print('train')\n")
    requirements = directory / "inference-requirements.txt"
    requirements.write_text("dependency==1\n")
    monkeypatch.setattr(pipeline, "ROOT", tmp_path)
    before = pipeline.source_fingerprint()
    requirements.write_text("dependency==2\n")
    assert pipeline.source_fingerprint() != before


@pytest.mark.parametrize("label", ["../outside", "/tmp/file", "UpperCase", "a" * 41, ""])
def test_run_labels_cannot_escape_artifacts(label):
    with pytest.raises(ValueError):
        run_path(label)


def test_sdk_pipeline_graph_and_pinned_environment(settings, tmp_path):
    definitions = component_definitions(settings)
    client = SimpleNamespace(components=SimpleNamespace(
        get=lambda name, version: definitions[name.removeprefix("mlops_")]
    ))
    job = build_pipeline(client, settings, "1", 1.0, 3.0)
    assert job.settings.default_compute == settings.compute_cluster
    assert job.settings.continue_on_step_failure is False
    assert set(job.jobs) == {"prepare_data", "train_model", "evaluate_gate"}
    assert set(job.outputs) == {"approved_model", "evaluation_report"}
    assert all(output.mode == "upload" for output in job.outputs.values())
    path = tmp_path / "pipeline.yml"
    job.dump(path)
    content = path.read_text()
    assert "/environments/sklearn-1.5/versions/53" in content
    assert "labels/latest" not in content
    assert "parent.jobs.prepare_data.outputs.train_data" in content
    forced = build_pipeline(client, settings, "1", 1.0, 3.0, force_rerun=True)
    assert forced.settings.force_rerun is True


def test_portable_components_success_and_failure_exit_codes(tmp_path):
    generate_data(tmp_path / "data")
    env = {**os.environ, "MLFLOW_TRACKING_URI": (tmp_path / "mlruns").as_uri()}

    def run(script, *args, check=True):
        return subprocess.run(
            [sys.executable, str(ROOT / "components" / script), *map(str, args)],
            env=env, check=check, capture_output=True, text=True,
        )

    run("prepare.py", "--raw-data", tmp_path / "data/regression-v1.csv",
        "--train-data", tmp_path / "train", "--validation-data", tmp_path / "validation")
    run("train.py", "--train-data", tmp_path / "train", "--alpha", 1,
        "--model-output", tmp_path / "candidate")
    run("evaluate.py", "--model-input", tmp_path / "candidate",
        "--validation-data", tmp_path / "validation", "--max-rmse", 3,
        "--approved-model", tmp_path / "approved", "--report-output", tmp_path / "pass-report")
    report = json.loads((tmp_path / "pass-report/evaluation.json").read_text())
    assert report["approved"] is True
    assert report["model_sha256"] == directory_sha256(tmp_path / "approved")
    assert (tmp_path / "approved/MLmodel").is_file()
    requirements = (tmp_path / "approved/requirements.txt").read_text()
    assert "azureml-inference-server-http==1.5.1" in requirements
    assert "azureml-ai-monitoring==1.0.0" in requirements
    failed = run("evaluate.py", "--model-input", tmp_path / "candidate",
        "--validation-data", tmp_path / "validation", "--max-rmse", 0.01,
        "--approved-model", tmp_path / "rejected", "--report-output", tmp_path / "fail-report",
        check=False)
    assert failed.returncode != 0
    assert "QUALITY_GATE_FAILED" in failed.stderr
    assert not (tmp_path / "rejected").exists()
    assert json.loads((tmp_path / "fail-report/evaluation.json").read_text())["approved"] is False
