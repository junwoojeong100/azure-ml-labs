"""Run the same lab inside the private VNet through Azure VM Run Command, never SSH."""

import argparse
import base64
import io
import json
import re
import shlex
import subprocess
import sys
import time
import zipfile
import zlib
from pathlib import Path

from mlops_lab.config import ARTIFACTS, PURPOSE, ROOT, Settings, save_json

REMOTE_ROOT = "/opt/aml-lab"
VM_NAME = "vm-aml-lab-runner"
IDENTITY_NAME = "id-aml-mlops-compute"


def az_json(settings: Settings, arguments: list[str]) -> dict:
    process = subprocess.run(
        ["az", *arguments, "--subscription", settings.subscription_id, "-o", "json"],
        capture_output=True, text=True,
    )
    if process.stderr:
        print(process.stderr, file=sys.stderr, end="")
    if process.returncode:
        raise RuntimeError(f"Azure CLI failed with exit code {process.returncode}.")
    return json.loads(process.stdout)


def execute(settings: Settings, script: str, label: str) -> str:
    wrapped = (
        "set +e\n(\nset -eu\n" + script
        + "\n)\ncode=$?\nprintf '\\n__AML_LAB_EXIT_CODE__=%s\\n' \"$code\"\nexit \"$code\"\n"
    )
    result = az_json(settings, [
        "vm", "run-command", "invoke", "--resource-group", settings.resource_group,
        "--name", VM_NAME, "--command-id", "RunShellScript", "--scripts", wrapped,
    ])
    message = "\n".join(item["message"] for item in result["value"])
    save_json(ARTIFACTS / "remote" / f"{label}-{time.time_ns()}.json", result)
    print(message, flush=True)
    codes = re.findall(r"__AML_LAB_EXIT_CODE__=(\d+)", message)
    if len(codes) != 1 or codes[0] != "0":
        raise RuntimeError("Remote lab command failed or its exit status could not be verified.")
    return message


def bundle_files() -> list[Path]:
    files = [ROOT / name for name in ("pyproject.toml", "requirements-lock.txt", "config.json", "config.example.json")]
    for pattern in (
        "components/*.py", "components/*.txt", "components/.amlignore", "mlops_lab/*.py", "tests/*.py",
        "infra/*.yml", "infra/*.bicep", "scripts/*.py", ".github/workflows/*.yml",
        ".gitignore", "notebooks/*.ipynb", "docs/*.md", "docs/execution-evidence.json", "README.md",
    ):
        files.extend(ROOT.glob(pattern))
    return sorted(set(files))


def bootstrap_script() -> str:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in bundle_files():
            archive.writestr(file.relative_to(ROOT).as_posix(), file.read_bytes())
    payload = base64.b64encode(buffer.getvalue()).decode()
    return f"""mkdir -p {REMOTE_ROOT}
python3 - <<'PY'
import base64, io, zipfile
from pathlib import Path
root = Path("{REMOTE_ROOT}")
payload = "{payload}"
with zipfile.ZipFile(io.BytesIO(base64.b64decode(payload))) as archive:
    for name in archive.namelist():
        path = Path(name)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe archive path")
    archive.extractall(root)
print("Lab source package transferred through the Azure control plane.", flush=True)
PY
if [ ! -x /opt/aml-bootstrap/bin/python ]; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv
    python3 -m venv /opt/aml-bootstrap
fi
/opt/aml-bootstrap/bin/python -m pip install --quiet 'uv>=0.8,<1'
if [ ! -x {REMOTE_ROOT}/.venv/bin/python ]; then
    /opt/aml-bootstrap/bin/uv venv --python 3.12 {REMOTE_ROOT}/.venv
fi
cd {REMOTE_ROOT}
/opt/aml-bootstrap/bin/uv pip install --python .venv/bin/python -r requirements-lock.txt -e . --quiet
.venv/bin/python -c 'import sys, azure.ai.ml; print("Private runner ready:", sys.version)'
"""


def collect(settings: Settings) -> None:
    message = execute(settings, f"""cd {REMOTE_ROOT}
.venv/bin/python - <<'PY'
import base64, json, zlib
from pathlib import Path
patterns = ["artifacts/runs/*.json", "artifacts/models/*.json", "artifacts/deployments/*.json",
            "artifacts/inference/*.json", "artifacts/traffic/*.json", "artifacts/assets.json",
            "artifacts/cleanup.json", "artifacts/published-notebooks.json", "data/manifest.json"]
files = {{str(path): json.loads(path.read_text()) for pattern in patterns for path in Path(".").glob(pattern)}}
encoded = base64.b64encode(zlib.compress(json.dumps(files, separators=(",", ":")).encode(), 9)).decode()
Path("artifacts/export.txt").write_text(encoded)
print("__EXPORT_LENGTH__=" + str(len(encoded)))
PY
""", "collect-index")
    length = int(re.search(r"__EXPORT_LENGTH__=(\d+)", message).group(1))
    parts = []
    for offset in range(0, length, 2500):
        message = execute(settings, f"""cd {REMOTE_ROOT}
.venv/bin/python - <<'PY'
from pathlib import Path
print("__EXPORT_BEGIN__" + Path("artifacts/export.txt").read_text()[{offset}:{offset + 2500}] + "__EXPORT_END__")
PY
""", "collect-chunk")
        parts.append(re.search(r"__EXPORT_BEGIN__(.*?)__EXPORT_END__", message).group(1))
    files = json.loads(zlib.decompress(base64.b64decode("".join(parts))))
    for relative, content in files.items():
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path.parts[0] not in {"artifacts", "data"}:
            raise ValueError("Unsafe artifact export path.")
        save_json(ROOT / path, content)
    print(f"Collected {len(files)} persistent execution artifacts.", flush=True)


def sync_runs(settings: Settings) -> None:
    receipts = {}
    for path in (ARTIFACTS / "runs").glob("*.json"):
        receipt = json.loads(path.read_text())
        if receipt["workspace_id"] != settings.workspace_id():
            raise RuntimeError("A local run receipt belongs to another workspace.")
        if not re.fullmatch(r"[a-z][a-z0-9-]{0,39}", path.stem) or receipt["label"] != path.stem:
            raise ValueError("Invalid run receipt label.")
        receipts[path.stem] = receipt
    payload = base64.b64encode(json.dumps(receipts).encode()).decode()
    execute(settings, f"""cd {REMOTE_ROOT}
.venv/bin/python - <<'PY'
import base64, json
from pathlib import Path
receipts = json.loads(base64.b64decode("{payload}"))
directory = Path("artifacts/runs")
directory.mkdir(parents=True, exist_ok=True)
for label, receipt in receipts.items():
    path = directory / (label + ".json")
    if path.exists():
        existing = json.loads(path.read_text())
        if existing["job_name"] != receipt["job_name"]:
            raise RuntimeError("Run label collision; refusing to overwrite remote history.")
        receipt = {{**receipt, **existing}}
    path.write_text(json.dumps(receipt, indent=2) + "\\n")
print("Synchronized run receipts:", sorted(receipts))
PY
""", "sync-runs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["bootstrap", "run", "test", "collect", "publish", "sync-runs"])
    parser.add_argument("arguments", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    settings = Settings.load()
    settings.verify_account()
    vm = az_json(settings, ["vm", "show", "-g", settings.resource_group, "-n", VM_NAME])
    if vm["tags"].get("purpose") != PURPOSE or vm["tags"].get("lifecycle") != "temporary-private-orchestrator":
        raise RuntimeError("Refusing to execute on a VM that is not the temporary lab runner.")
    identity = az_json(settings, ["identity", "show", "-g", settings.resource_group, "-n", IDENTITY_NAME])
    if args.action == "bootstrap":
        execute(settings, bootstrap_script(), "bootstrap")
    elif args.action == "run":
        if not args.arguments:
            parser.error("Pass a lab CLI command after 'run'.")
        command = shlex.join([
            f"{REMOTE_ROOT}/.venv/bin/python", "-m", "mlops_lab.cli",
            "--managed-identity-client-id", identity["clientId"], *args.arguments,
        ])
        execute(settings, f"cd {REMOTE_ROOT}\n{command}", "lab")
    elif args.action == "test":
        execute(settings, f"cd {REMOTE_ROOT}\n.venv/bin/python -m pytest --disable-warnings", "test")
    elif args.action == "sync-runs":
        sync_runs(settings)
    elif args.action == "publish":
        script = f"""cd {REMOTE_ROOT}
.venv/bin/python - <<'PY'
import json
from mlops_lab.config import Settings
from mlops_lab.publish import publish_notebooks
result = publish_notebooks(Settings.load(), "{identity['clientId']}")
print(json.dumps({{key: value for key, value in result.items() if key != "uploaded_files"}}, indent=2))
PY
"""
        execute(settings, script, "publish")
    else:
        collect(settings)


if __name__ == "__main__":
    main()
