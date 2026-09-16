import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
PURPOSE = "aml-mlops-hands-on"


@dataclass(frozen=True)
class Settings:
    subscription_id: str
    tenant_id: str
    expected_account: str
    resource_group: str
    workspace: str
    location: str
    compute_cluster: str
    compute_instance: str
    endpoint_name: str
    data_name: str
    model_name: str
    experiment_name: str
    environment: str
    component_version: str
    deployment_instance_type: str

    @classmethod
    def load(cls, path: Path = ROOT / "config.json") -> "Settings":
        values = json.loads(path.read_text())
        if any(not isinstance(value, str) or not value or "<" in value for value in values.values()):
            raise ValueError("Replace every placeholder in config.json with an explicit value.")
        settings = cls(**values)
        if "/versions/" not in settings.environment:
            raise ValueError("Pin an exact environment version; do not use labels/latest.")
        return settings

    def verify_account(self) -> dict:
        result = subprocess.run(
            ["az", "account", "show", "--subscription", self.subscription_id, "-o", "json"],
            check=True,
            capture_output=True,
            text=True,
        )
        account = json.loads(result.stdout)
        if (
            account["id"] != self.subscription_id
            or account["tenantId"] != self.tenant_id
            or account["user"]["name"].casefold() != self.expected_account.casefold()
            or account["state"] != "Enabled"
        ):
            raise RuntimeError("Azure identity/subscription mismatch; no changes were made.")
        return account

    def client(self, managed_identity_client_id: str | None = None):
        from azure.ai.ml import MLClient
        from azure.identity import AzureCliCredential, ManagedIdentityCredential

        if managed_identity_client_id:
            credential = ManagedIdentityCredential(client_id=managed_identity_client_id)
        else:
            self.verify_account()
            credential = AzureCliCredential(subscription=self.subscription_id, process_timeout=60)
        return MLClient(credential, self.subscription_id, self.resource_group, self.workspace)

    def scope(self) -> list[str]:
        return [
            "--subscription", self.subscription_id,
            "--resource-group", self.resource_group,
            "--workspace-name", self.workspace,
        ]

    def workspace_id(self) -> str:
        return (
            f"/subscriptions/{self.subscription_id}/resourceGroups/{self.resource_group}"
            f"/providers/Microsoft.MachineLearningServices/workspaces/{self.workspace}"
        )


def save_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
