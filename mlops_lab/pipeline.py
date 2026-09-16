import hashlib
from azure.ai.ml import Input, Output, dsl
from azure.ai.ml.entities import CommandComponent, Data, ManagedIdentityConfiguration
from azure.core.exceptions import ResourceNotFoundError

from mlops_lab.config import ARTIFACTS, PURPOSE, ROOT, Settings, save_json
from mlops_lab.data import generate_data


def component_definitions(settings: Settings) -> dict[str, CommandComponent]:
    common = {
        "version": settings.component_version,
        "code": str(ROOT / "components"),
        "environment": settings.environment,
        "is_deterministic": True,
        "tags": {"purpose": PURPOSE},
    }
    return {
        "prepare": CommandComponent(
            name="mlops_prepare", display_name="Prepare and validate data",
            command=(
                "python prepare.py --raw-data ${{inputs.raw_data}} "
                "--train-data ${{outputs.train_data}} "
                "--validation-data ${{outputs.validation_data}}"
            ),
            inputs={"raw_data": Input(type="uri_file", mode="download")},
            outputs={
                "train_data": Output(type="uri_folder", mode="upload"),
                "validation_data": Output(type="uri_folder", mode="upload"),
            },
            **common,
        ),
        "train": CommandComponent(
            name="mlops_train", display_name="Train and track with MLflow",
            command=(
                "python train.py --train-data ${{inputs.train_data}} "
                "--alpha ${{inputs.alpha}} --model-output ${{outputs.model}}"
            ),
            inputs={
                "train_data": Input(type="uri_folder", mode="download"),
                "alpha": Input(type="number", min=0),
            },
            outputs={"model": Output(type="mlflow_model", mode="upload")},
            **common,
        ),
        "evaluate": CommandComponent(
            name="mlops_evaluate", display_name="Evaluate and enforce quality gate",
            command=(
                "python evaluate.py --model-input ${{inputs.model}} "
                "--validation-data ${{inputs.validation_data}} "
                "--max-rmse ${{inputs.max_rmse}} "
                "--approved-model ${{outputs.approved_model}} "
                "--report-output ${{outputs.report}}"
            ),
            inputs={
                "model": Input(type="mlflow_model", mode="download"),
                "validation_data": Input(type="uri_folder", mode="download"),
                "max_rmse": Input(type="number", min=0.000001),
            },
            outputs={
                "approved_model": Output(type="mlflow_model", mode="upload"),
                "report": Output(type="uri_folder", mode="upload"),
            },
            **common,
        ),
    }


def register_assets(client, settings: Settings) -> dict:
    manifest = generate_data()
    assets = {}
    for version, metadata in manifest.items():
        try:
            asset = client.data.get(settings.data_name, version)
        except ResourceNotFoundError:
            asset = client.data.create_or_update(Data(
                name=settings.data_name, version=version, type="uri_file",
                path=metadata["path"],
                description="Deterministic synthetic regression data; no personal information.",
                tags={
                    "purpose": PURPOSE, "sha256": metadata["sha256"],
                    "validation_sha256": metadata["validation_sha256"],
                },
            ))
        if asset.tags.get("sha256") != metadata["sha256"]:
            raise RuntimeError(f"Data version {version} already exists with different content.")
        assets[version] = {"id": asset.id, **metadata}

    components = {}
    for key, component in component_definitions(settings).items():
        registered = client.components.create_or_update(component)
        components[key] = registered.id
    result = {"data": assets, "components": components, "environment": settings.environment}
    save_json(ARTIFACTS / "assets.json", result)
    return result


def build_pipeline(client, settings: Settings, data_version: str, alpha: float, max_rmse: float, force_rerun: bool = False):
    if data_version not in {"1", "2"}:
        raise ValueError("Register and use data version 1 or 2.")
    components = {
        key: client.components.get(f"mlops_{key}", version=settings.component_version)
        for key in ("prepare", "train", "evaluate")
    }

    @dsl.pipeline(name="studio_compute_mlops", description="Versioned data to quality-approved MLflow model")
    def training_pipeline(raw_data, ridge_alpha: float, quality_threshold: float):
        prepare_data = components["prepare"](raw_data=raw_data)
        prepare_data.display_name = "prepare_data"
        prepare_data.identity = ManagedIdentityConfiguration()
        train_model = components["train"](train_data=prepare_data.outputs.train_data, alpha=ridge_alpha)
        train_model.display_name = "train_model"
        train_model.identity = ManagedIdentityConfiguration()
        evaluate_gate = components["evaluate"](
            model=train_model.outputs.model,
            validation_data=prepare_data.outputs.validation_data,
            max_rmse=quality_threshold,
        )
        evaluate_gate.display_name = "evaluate_gate"
        evaluate_gate.identity = ManagedIdentityConfiguration()
        return {
            "approved_model": evaluate_gate.outputs.approved_model,
            "evaluation_report": evaluate_gate.outputs.report,
        }

    job = training_pipeline(
        raw_data=Input(type="uri_file", path=f"azureml:{settings.data_name}:{data_version}", mode="download"),
        ridge_alpha=alpha,
        quality_threshold=max_rmse,
    )
    job.settings.default_compute = settings.compute_cluster
    job.settings.continue_on_step_failure = False
    job.settings.force_rerun = force_rerun
    job.outputs.approved_model.mode = "upload"
    job.outputs.evaluation_report.mode = "upload"
    job.tags = {
        "purpose": PURPOSE, "data_version": data_version, "alpha": str(alpha),
        "max_rmse": str(max_rmse), "environment": settings.environment,
    }
    return job


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    sources = [
        file for file in (ROOT / "components").iterdir()
        if file.suffix in {".py", ".txt"} or file.name == ".amlignore"
    ]
    for file in sorted(sources):
        digest.update(file.name.encode() + b"\0")
        digest.update(file.read_bytes())
    return digest.hexdigest()
