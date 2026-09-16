import hashlib
from pathlib import Path, PurePosixPath

from azure.core.exceptions import ResourceExistsError
from azure.identity import ManagedIdentityCredential
from azure.storage.fileshare import ShareServiceClient

from mlops_lab.config import ARTIFACTS, ROOT, Settings, save_json


def publish_notebooks(settings: Settings, client_id: str) -> dict:
    client = settings.client(managed_identity_client_id=client_id)
    datastore = client.datastores.get("workspacefilestore")
    credential = ManagedIdentityCredential(client_id=client_id)
    service = ShareServiceClient(
        account_url=f"https://{datastore.account_name}.file.core.windows.net",
        credential=credential,
        token_intent="backup",
    )
    share = service.get_share_client(datastore.file_share_name)
    folder = PurePosixPath("Users", settings.expected_account.split("@")[0], "azure-ml-labs")
    patterns = (
        "README.md", "pyproject.toml", "requirements-lock.txt", "config.json", "config.example.json",
        ".gitignore", ".github/workflows/*.yml", "components/*.py", "components/*.txt", "components/.amlignore",
        "mlops_lab/*.py", "scripts/*.py", "infra/*.yml", "infra/*.bicep",
        "tests/*.py", "notebooks/*.ipynb", "docs/*.md",
    )
    files = sorted({file for pattern in patterns for file in ROOT.glob(pattern)})
    directories = set()
    uploaded = []
    for file in files:
        destination = folder / file.relative_to(ROOT).as_posix()
        for parent in reversed(destination.parents):
            if parent == PurePosixPath(".") or str(parent) in directories:
                continue
            try:
                share.get_directory_client(str(parent)).create_directory()
            except ResourceExistsError:
                pass
            directories.add(str(parent))
        content = file.read_bytes()
        remote = share.get_file_client(str(destination))
        remote.upload_file(content)
        downloaded = remote.download_file().readall()
        if hashlib.sha256(downloaded).digest() != hashlib.sha256(content).digest():
            raise RuntimeError(f"Notebook share content verification failed for {destination}.")
        uploaded.append(str(destination))
    result = {
        "file_share": datastore.file_share_name, "folder": str(folder),
        "uploaded_files": uploaded, "verified_file_count": len(uploaded),
        "compute_instance_path": f"/home/azureuser/cloudfiles/code/{folder}",
    }
    save_json(ARTIFACTS / "published-notebooks.json", result)
    return result
