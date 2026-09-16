import json
import math
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import numpy as np
from azure.ai.ml.entities import ManagedOnlineDeployment, ManagedOnlineEndpoint, Model
from azure.core.exceptions import ResourceNotFoundError

from components.common import passes_gate
from mlops_lab.config import ARTIFACTS, PURPOSE, ROOT, Settings, save_json
from mlops_lab.pipeline import build_pipeline, source_fingerprint

TERMINAL_STATES = {"Completed", "Failed", "Canceled", "NotResponding"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_path(label: str) -> Path:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", label):
        raise ValueError("Run label must contain 1-40 lowercase letters, digits, or hyphens.")
    return ARTIFACTS / "runs" / f"{label}.json"


def read_run(settings: Settings, label: str) -> dict:
    receipt = json.loads(run_path(label).read_text())
    if receipt["workspace_id"] != settings.workspace_id():
        raise RuntimeError("This run belongs to another workspace; check config.json.")
    return receipt


def studio_url(settings: Settings, job_name: str) -> str:
    workspace = (
        f"/subscriptions/{settings.subscription_id}/resourcegroups/{settings.resource_group}"
        f"/workspaces/{settings.workspace}"
    )
    return (
        f"https://ml.azure.com/runs/{quote(job_name)}"
        f"?wsid={quote(workspace, safe='')}&tid={settings.tenant_id}"
    )


def submit(client, settings: Settings, label: str, data_version: str, alpha: float, max_rmse: float, force_rerun: bool = False) -> dict:
    if run_path(label).exists():
        raise FileExistsError(f"Run label {label!r} already exists. Use a new label to preserve history.")
    if not math.isfinite(alpha) or alpha < 0:
        raise ValueError("alpha must be finite and nonnegative.")
    passes_gate({"rmse": 0.0}, max_rmse)
    job = build_pipeline(client, settings, data_version, alpha, max_rmse, force_rerun=force_rerun)
    job.display_name = label
    created = client.jobs.create_or_update(job, experiment_name=settings.experiment_name)
    receipt = {
        "label": label, "job_name": created.name, "workspace_id": settings.workspace_id(),
        "studio_url": studio_url(settings, created.name), "submitted_at": utc_now(),
        "data_version": data_version, "alpha": alpha, "max_rmse": max_rmse,
        "environment": settings.environment, "component_version": settings.component_version,
        "component_source_sha256": source_fingerprint(),
        "force_rerun": force_rerun,
    }
    save_json(run_path(label), receipt)
    return receipt


def snapshot_run(client, settings: Settings, label: str) -> dict:
    receipt = read_run(settings, label)
    job = client.jobs.get(receipt["job_name"])
    children = [{
        "name": child.name, "display_name": child.display_name, "status": child.status,
        "compute": child.compute,
    } for child in client.jobs.list(parent_job_name=job.name)]
    receipt.update({"status": job.status, "observed_at": utc_now(), "children": children})
    save_json(run_path(label), receipt)
    return receipt


def wait_for_run(client, settings: Settings, label: str, timeout: int = 2400) -> dict:
    receipt = read_run(settings, label)
    deadline = time.monotonic() + timeout
    last_status = None
    while time.monotonic() < deadline:
        job = client.jobs.get(receipt["job_name"])
        if job.status != last_status:
            print(f"{label}: {job.status}", flush=True)
            last_status = job.status
        if job.status in TERMINAL_STATES:
            snapshot = snapshot_run(client, settings, label)
            if job.status != "Completed":
                raise RuntimeError(
                    f"Pipeline {job.name} ended with {job.status}. "
                    f"Inspect {receipt['studio_url']} and the evaluate_gate logs."
                )
            return snapshot
        time.sleep(15)
    raise TimeoutError(f"Pipeline still running after {timeout}s. Resume wait; do not resubmit.")


def download_report(client, settings: Settings, label: str) -> dict:
    receipt = read_run(settings, label)
    directory = ARTIFACTS / "jobs" / receipt["job_name"]
    evaluations = [
        child for child in client.jobs.list(parent_job_name=receipt["job_name"])
        if child.display_name == "evaluate_gate"
    ]
    if len(evaluations) != 1:
        raise RuntimeError("Expected one evaluate_gate job. Evaluation may not have started.")
    client.jobs.download(name=evaluations[0].name, download_path=str(directory))
    path = directory / "artifacts" / "evaluation.json"
    if not path.is_file():
        raise RuntimeError(f"The durable MLflow evaluation artifact was not found at {path}.")
    report = json.loads(path.read_text())
    receipt["evaluation"] = report
    save_json(run_path(label), receipt)
    return report


def failed_step_logs(client, settings: Settings, label: str) -> dict:
    receipt = snapshot_run(client, settings, label)
    failed = [child for child in receipt["children"] if child["status"] == "Failed"]
    if not failed:
        raise RuntimeError(f"No failed child step found; pipeline status is {receipt['status']}.")
    logs = []
    for child in failed:
        directory = ARTIFACTS / "logs" / child["name"]
        client.jobs.download(name=child["name"], all=True, download_path=str(directory))
        paths = sorted(directory.rglob("std_log.txt"))
        if not paths:
            raise RuntimeError(f"No user stdout log found. Inspect system logs under {directory}.")
        for path in paths:
            text = path.read_text()[-2500:]
            text = re.sub(r"(?i)(sig=)[^&\s]+", r"\1[REDACTED]", text)
            text = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~-]+", r"\1[REDACTED]", text)
            logs.append({"step": child["display_name"], "job_name": child["name"], "log_tail": text})
    return {"pipeline_status": receipt["status"], "logs": logs}


def require_approved_report(status: str, report: dict, expected_threshold: float) -> None:
    if status != "Completed":
        raise RuntimeError(f"Model registration blocked: pipeline status is {status}, not Completed.")
    if report["approved"] is not True:
        raise RuntimeError("Model registration blocked: quality gate did not approve this model.")
    if report["max_rmse"] != expected_threshold:
        raise RuntimeError("Evaluation threshold does not match the submitted run.")
    metrics = {key: float(report[key]) for key in ("rmse", "mae", "r2")}
    if not passes_gate(metrics, expected_threshold):
        raise RuntimeError("Model registration blocked: measured RMSE exceeds the threshold.")


def register_model(client, settings: Settings, label: str, version: str) -> dict:
    receipt = snapshot_run(client, settings, label)
    if receipt["status"] != "Completed":
        raise RuntimeError(f"Registration blocked: {label} is {receipt['status']}.")
    report = download_report(client, settings, label)
    require_approved_report(receipt["status"], report, receipt["max_rmse"])
    try:
        model = client.models.get(settings.model_name, version)
    except ResourceNotFoundError:
        model = client.models.create_or_update(Model(
            name=settings.model_name, version=version, type="mlflow_model",
            path=f"azureml://jobs/{receipt['job_name']}/outputs/approved_model",
            description="Quality-approved synthetic regression model; not for production decisions.",
            tags={
                "purpose": PURPOSE, "quality_gate": "passed",
                "source_job": receipt["job_name"], "data_version": receipt["data_version"],
                "rmse": str(report["rmse"]), "max_rmse": str(report["max_rmse"]),
                "model_sha256": report["model_sha256"],
            },
        ))
    if model.tags.get("source_job") != receipt["job_name"]:
        raise RuntimeError(f"Model version {version} already belongs to a different run.")
    result = {
        "name": model.name, "version": model.version, "id": model.id,
        "source_job": receipt["job_name"], "evaluation": report, "registered_at": utc_now(),
    }
    save_json(ARTIFACTS / "models" / f"v{version}.json", result)
    return result


def owned_endpoint(client, settings: Settings):
    endpoint = client.online_endpoints.get(settings.endpoint_name)
    if endpoint.tags.get("purpose") != PURPOSE or endpoint.tags.get("workspace") != settings.workspace:
        raise RuntimeError("Endpoint ownership tags do not match this lab; refusing to modify it.")
    return endpoint


def deployment_result(client, settings: Settings, deployment) -> dict:
    endpoint = owned_endpoint(client, settings)
    result = {
        "endpoint": endpoint.name, "deployment": deployment.name,
        "model": deployment.model, "provisioning_state": deployment.provisioning_state,
        "auth_mode": endpoint.auth_mode, "traffic": endpoint.traffic,
        "ready": deployment.provisioning_state == "Succeeded", "observed_at": utc_now(),
    }
    save_json(ARTIFACTS / "deployments" / f"{deployment.name}.json", result)
    return result


def deploy(client, settings: Settings, model_version: str, deployment_name: str, wait: bool = True) -> dict:
    if deployment_name not in {"blue", "green"}:
        raise ValueError("Use blue or green for this lab's deployments.")
    model = client.models.get(settings.model_name, model_version)
    if model.tags.get("quality_gate") != "passed" or model.tags.get("purpose") != PURPOSE:
        raise RuntimeError("Only models registered by this lab's quality gate may be deployed.")
    try:
        owned_endpoint(client, settings)
    except ResourceNotFoundError:
        client.online_endpoints.begin_create_or_update(ManagedOnlineEndpoint(
            name=settings.endpoint_name, auth_mode="aad_token",
            description="Temporary MLOps workshop endpoint; remove after the lab.",
            tags={"purpose": PURPOSE, "workspace": settings.workspace},
        )).result()
    poller = client.online_deployments.begin_create_or_update(ManagedOnlineDeployment(
        name=deployment_name, endpoint_name=settings.endpoint_name, model=model.id,
        instance_type=settings.deployment_instance_type, instance_count=1,
        tags={"purpose": PURPOSE, "model_version": model_version},
    ))
    if not wait:
        result = {
            "endpoint": settings.endpoint_name, "deployment": deployment_name,
            "model": model.id, "provisioning_state": "Submitted", "ready": False,
            "submitted_at": utc_now(),
        }
        save_json(ARTIFACTS / "deployments" / f"{deployment_name}.json", result)
        return result
    deployment = poller.result()
    if deployment.provisioning_state != "Succeeded":
        raise RuntimeError(f"Deployment did not succeed: {deployment.provisioning_state}")
    return deployment_result(client, settings, deployment)


def wait_for_deployment(client, settings: Settings, deployment_name: str, timeout: int = 2400) -> dict:
    owned_endpoint(client, settings)
    deadline = time.monotonic() + timeout
    visibility_deadline = time.monotonic() + 60
    last_status = None
    while time.monotonic() < deadline:
        try:
            deployment = client.online_deployments.get(
                name=deployment_name, endpoint_name=settings.endpoint_name
            )
        except ResourceNotFoundError:
            if time.monotonic() >= visibility_deadline:
                raise RuntimeError(f"Deployment {deployment_name} is still not visible after 60 seconds.")
            if last_status != "NotYetVisible":
                print(f"{deployment_name}: submitted resource is not yet visible", flush=True)
                last_status = "NotYetVisible"
            time.sleep(5)
            continue
        status = deployment.provisioning_state
        if status != last_status:
            print(f"{deployment_name}: {status}", flush=True)
            last_status = status
        if status == "Succeeded":
            return deployment_result(client, settings, deployment)
        if status in {"Failed", "Canceled", "Deleting"}:
            raise RuntimeError(f"Deployment {deployment_name} is {status}; inspect its build/container logs.")
        time.sleep(15)
    raise TimeoutError("Deployment is still pending. Resume wait-deployment; do not assume it is ready.")


def set_traffic(client, settings: Settings, deployment_name: str) -> dict:
    endpoint = owned_endpoint(client, settings)
    deployment = client.online_deployments.get(
        name=deployment_name, endpoint_name=settings.endpoint_name
    )
    if deployment.provisioning_state != "Succeeded":
        raise RuntimeError("Cannot route traffic to a deployment that is not Succeeded.")
    endpoint.traffic = {deployment_name: 100}
    endpoint = client.online_endpoints.begin_create_or_update(endpoint).result()
    result = {"endpoint": endpoint.name, "traffic": endpoint.traffic, "updated_at": utc_now()}
    save_json(ARTIFACTS / "traffic" / f"{time.time_ns()}.json", result)
    return result


def invoke(client, settings: Settings, deployment_name: str | None = None) -> dict:
    owned_endpoint(client, settings)
    request_path = ROOT / "data" / "sample-request.json"
    request = json.loads(request_path.read_text())
    start = time.monotonic()
    response = client.online_endpoints.invoke(
        endpoint_name=settings.endpoint_name, deployment_name=deployment_name,
        request_file=str(request_path),
    )
    predictions = json.loads(response)
    expected = len(request["input_data"]["data"])
    if not isinstance(predictions, list) or len(predictions) != expected:
        raise RuntimeError(f"Expected a list of {expected} predictions, received {response}.")
    if not all(isinstance(value, (int, float)) and not isinstance(value, bool) for value in predictions):
        raise RuntimeError("Predictions must be numeric values.")
    if not np.isfinite(predictions).all():
        raise RuntimeError("Endpoint returned non-finite predictions.")
    result = {
        "endpoint": settings.endpoint_name, "deployment": deployment_name or "traffic-routed",
        "rows": expected, "predictions": predictions,
        "elapsed_seconds": round(time.monotonic() - start, 3), "invoked_at": utc_now(),
    }
    save_json(ARTIFACTS / "inference" / f"{time.time_ns()}.json", result)
    return result


def cleanup_runtime(client, settings: Settings, delete_endpoint: bool) -> dict:
    result = {"workspace_id": settings.workspace_id(), "observed_at": utc_now()}
    if delete_endpoint:
        try:
            owned_endpoint(client, settings)
        except ResourceNotFoundError:
            result["endpoint"] = "absent"
        else:
            client.online_endpoints.begin_delete(settings.endpoint_name).result()
            try:
                client.online_endpoints.get(settings.endpoint_name)
            except ResourceNotFoundError:
                result["endpoint"] = "deleted"
            else:
                raise RuntimeError("Endpoint deletion did not complete.")
    cluster = client.compute.get(settings.compute_cluster)
    result["cluster_min_instances"] = cluster.min_instances
    result["cluster_max_instances"] = cluster.max_instances
    # Stop last: this command can be running on the compute instance itself.
    instance = client.compute.get(settings.compute_instance)
    if instance.state != "Stopped":
        client.compute.begin_stop(settings.compute_instance).result()
    result["compute_instance_state"] = client.compute.get(settings.compute_instance).state
    if result["compute_instance_state"] != "Stopped":
        raise RuntimeError("Compute instance has not stopped.")
    save_json(ARTIFACTS / "cleanup.json", result)
    return result
