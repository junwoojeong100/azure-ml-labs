import ast
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import nbformat
import pytest

from mlops_lab.config import ROOT

LABS = [
    ("01", "자산 등록"),
    ("02", "학습"),
    ("03", "품질 게이트"),
    ("04", "blue 배포"),
    ("05", "재학습"),
    ("06", "전환·롤백"),
    ("07", "비용 정리"),
]
NOTEBOOK = ROOT / "notebooks" / "01-studio-mlops.ipynb"


def notebook_cells():
    return nbformat.read(NOTEBOOK, as_version=4).cells


def prose(text):
    return re.sub(r"^```[^\n]*\n.*?^```\s*$", "", text, flags=re.MULTILINE | re.DOTALL)


def anchors(text):
    result = set(re.findall(r'<a\s+(?:id|name)="([^"]+)"', text))
    seen = {}
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*#*\s*$", prose(text), flags=re.MULTILINE):
        heading = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", heading)
        heading = re.sub(r"<[^>]+>", "", heading)
        slug = re.sub(r"[^\w -]", "", heading.lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        result.add(f"{slug}-{count}" if count else slug)
    return result


def guide_documents():
    documents = [(ROOT / "README.md", (ROOT / "README.md").read_text())]
    documents.extend((path, path.read_text()) for path in sorted((ROOT / "docs").glob("*.md")))
    documents.append((NOTEBOOK, "\n\n".join(
        cell.source for cell in notebook_cells() if cell.cell_type == "markdown"
    )))
    return documents


def test_local_links_and_section_anchors_resolve():
    errors = []
    for path, text in guide_documents():
        text = prose(text)
        targets = re.findall(r"\[[^\]]*\]\(([^)]+)\)", text)
        targets += re.findall(r"^\[[^\]]+\]:\s+(\S+)", text, flags=re.MULTILINE)
        for target in targets:
            url = urlsplit(target)
            if url.scheme or url.netloc:
                continue
            destination = (path.parent / unquote(url.path)).resolve() if url.path else path
            if not destination.is_relative_to(ROOT) or not destination.is_file():
                errors.append(f"{path.relative_to(ROOT)} -> {target}")
                continue
            if url.fragment and destination.suffix == ".md":
                if unquote(url.fragment) not in anchors(destination.read_text()):
                    errors.append(f"{path.relative_to(ROOT)} -> missing anchor: {target}")
    assert not errors, "\n".join(errors)


def test_all_paths_use_the_same_seven_labs_and_completion_cards():
    readme = (ROOT / "README.md").read_text()
    cli = (ROOT / "docs/lab-guide.md").read_text()
    notebook = "\n\n".join(cell.source for cell in notebook_cells() if cell.cell_type == "markdown")
    for document in (cli, notebook):
        headings = re.findall(r"^## (0[1-7]) · (.+)$", document, flags=re.MULTILINE)
        assert headings == LABS
        sections = re.split(r"^## 0[1-7] · .+$", document, flags=re.MULTILINE)[1:]
        for section in sections:
            for marker in ("**할 일:**", "**Studio에서 확인:**", "**완료 조건:**"):
                assert marker in section
    for number, title in LABS:
        assert f"| {number} {title} |" in readme


def test_learner_preparation_is_separate_and_has_a_ready_checkpoint():
    text = (ROOT / "docs/learner-start.md").read_text()
    for section in ("준비 A", "준비 B", "준비 C", "준비 D", "준비 E"):
        assert f"## {section}" in text
    for field in ("subscription_id", "tenant_id", "expected_account", "resource_group", "workspace", "endpoint_name"):
        assert f"`{field}`" in text
    assert "settings.verify_account()" in text
    assert 'print("준비 완료:"' in text
    assert "자동 반영되지 않습니다" in text
    assert "본인에게 할당" in text
    assert "cp -n " in text
    for forbidden in ("az group create", "az ml workspace create", "az role assignment create"):
        assert forbidden not in text


def test_notebook_splits_submission_from_waiting_and_keeps_failure_guards():
    cells = {cell.id: cell.source for cell in notebook_cells() if cell.cell_type == "code"}
    for source in cells.values():
        tree = ast.parse(source)
        functions = {node.func.id for node in ast.walk(tree)
                     if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
        assert not (functions & {"submit", "deploy"} and functions & {"wait_for_run", "wait_for_deployment"})
    for name in ("submit-blue-deployment", "submit-green-deployment"):
        calls = [node for node in ast.walk(ast.parse(cells[name]))
                 if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "deploy"]
        assert len(calls) == 1
        assert any(keyword.arg == "wait" and isinstance(keyword.value, ast.Constant)
                   and keyword.value.value is False for keyword in calls[0].keywords)
    for name, function in (
        ("expected-failed-job", "wait_for_run"),
        ("expected-registration-failure", "register_model"),
    ):
        assert function in cells[name]
        assert not any(isinstance(node, ast.Try) for node in ast.walk(ast.parse(cells[name])))
    rejection = cells["verify-rejection"]
    assert "bad_state['status'] == 'Failed'" in rejection
    assert "c['display_name'] == 'evaluate_gate'" in rejection
    assert "bad_report['approved'] is False and bad_report['rmse'] > 3.0" in rejection
    for name in ("blue-inference", "verify-green-route", "verify-blue-rollback"):
        assert "np.testing.assert_allclose" in cells[name]
        assert "invoke(client, settings)" in cells[name]


@pytest.mark.parametrize("resume", ["", "20260916204808", "20260916204808-abc123"])
def test_notebook_run_identifier_can_be_restored_without_cloud_calls(resume):
    source = next(cell.source for cell in notebook_cells() if cell.id == "connect")
    nodes = []
    for node in ast.parse(source).body:
        if isinstance(node, ast.If) and "RESUME_LAB_ID" in ast.unparse(node.test):
            nodes.append(node)
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id in {"lab_id", "baseline_run", "bad_run", "retrain_run", "version1"}
            for target in node.targets
        ):
            nodes.append(node)
    namespace = {
        "RESUME_LAB_ID": resume, "re": re, "datetime": datetime, "timezone": timezone, "uuid4": uuid4,
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), "<notebook-identifiers>", "exec"), namespace)
    if resume:
        assert namespace["lab_id"] == resume
    else:
        assert re.fullmatch(r"[0-9]{14}-[a-f0-9]{6}", namespace["lab_id"])


def test_notebook_wrong_folder_fails_before_authentication(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    source = next(cell.source for cell in notebook_cells() if cell.id == "connect")
    with pytest.raises(RuntimeError, match="프로젝트 전체 폴더"):
        exec(compile(source, "<notebook-preflight>", "exec"), {})


@pytest.mark.parametrize("restart_before_promotion", [False, True])
def test_notebook_sequence_and_kernel_resume_without_azure(tmp_path, monkeypatch, restart_before_promotion):
    import mlops_lab.config as config
    import mlops_lab.operations as operations
    import mlops_lab.pipeline as pipeline

    (tmp_path / "pyproject.toml").touch()
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "mlops_lab").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    settings = SimpleNamespace(
        expected_account="lab@example.test", workspace="test-workspace",
        compute_cluster="test-compute", component_version="3", client=lambda: object(),
    )
    monkeypatch.setattr(config.Settings, "load", lambda: settings)
    monkeypatch.setattr(pipeline, "register_assets", lambda *args: {
        "environment": "pinned-environment",
        "data": {
            "1": {"training_rows": 800, "validation_rows": 200, "validation_sha256": "fixed"},
            "2": {"training_rows": 1200, "validation_rows": 200, "validation_sha256": "fixed"},
        },
    })
    jobs, models, deployments, ready, events = {}, {}, {}, set(), []
    traffic = {"deployment": None}

    def submit(client, settings, label, version, alpha, max_rmse):
        assert label not in jobs, "A resumed notebook must not resubmit jobs."
        jobs[label] = {
            "approved": alpha < 1000000, "rmse": 23.4 if alpha >= 1000000 else 1.84,
            "validation_sha256": "fixed",
        }
        events.append(("submit", label))
        return {"studio_url": f"https://example.test/jobs/{label}"}

    def wait_for_run(client, settings, label):
        if not jobs[label]["approved"]:
            raise RuntimeError("Expected failed quality gate")

    def register(client, settings, label, version):
        if not jobs[label]["approved"]:
            raise RuntimeError("Registration blocked")
        models[version] = label
        return {"id": f"model:{version}"}

    def deploy(client, settings, version, name, wait=True):
        assert version in models and name not in deployments
        assert wait is False
        deployments[name] = version
        events.append(("deploy", name))
        return {"ready": False}

    def wait_for_deployment(client, settings, name):
        assert name in deployments
        ready.add(name)

    def set_traffic(client, settings, name):
        assert name in ready
        traffic["deployment"] = name
        events.append(("traffic", name))

    def invoke(client, settings, name=None):
        name = name or traffic["deployment"]
        assert name in ready
        return {"predictions": [1.0 if name == "blue" else 2.0] * 5}

    def cleanup(client, settings, delete_endpoint):
        assert delete_endpoint is True
        events.append(("cleanup", True))

    monkeypatch.setattr(operations, "submit", submit)
    monkeypatch.setattr(operations, "wait_for_run", wait_for_run)
    monkeypatch.setattr(operations, "download_report", lambda client, settings, label: jobs[label])
    monkeypatch.setattr(operations, "snapshot_run", lambda *args: {
        "status": "Failed", "children": [{"display_name": "evaluate_gate", "status": "Failed"}],
    })
    monkeypatch.setattr(operations, "register_model", register)
    monkeypatch.setattr(operations, "deploy", deploy)
    monkeypatch.setattr(operations, "wait_for_deployment", wait_for_deployment)
    monkeypatch.setattr(operations, "set_traffic", set_traffic)
    monkeypatch.setattr(operations, "invoke", invoke)
    monkeypatch.setattr(operations, "cleanup_runtime", cleanup)

    cells = notebook_cells()
    connect = next(cell.source for cell in cells if cell.id == "connect")
    namespace = {}
    expected_errors = {
        "expected-failed-job": "Expected failed quality gate",
        "expected-registration-failure": "Registration blocked",
    }
    for cell in cells:
        if cell.cell_type != "code":
            continue
        if restart_before_promotion and cell.id == "promote-green":
            identifier = namespace["lab_id"]
            tree = ast.parse(connect)
            assignment = next(node for node in tree.body if isinstance(node, ast.Assign)
                              and any(isinstance(target, ast.Name) and target.id == "RESUME_LAB_ID"
                                      for target in node.targets))
            assignment.value = ast.Constant(identifier)
            namespace = {}
            exec(compile(ast.fix_missing_locations(tree), "<resume>", "exec"), namespace)
            assert namespace["lab_id"] == identifier
        code = compile(cell.source, f"<notebook:{cell.id}>", "exec")
        if cell.id in expected_errors:
            with pytest.raises(RuntimeError, match=expected_errors[cell.id]):
                exec(code, namespace)
        else:
            exec(code, namespace)
    assert len(jobs) == 3 and len(models) == 2
    assert [value for action, value in events if action == "deploy"] == ["blue", "green"]
    assert [value for action, value in events if action == "traffic"] == ["blue", "green", "blue"]
    assert events[-1] == ("cleanup", True)


def test_documented_bash_blocks_are_syntactically_valid():
    for path, text in guide_documents():
        for index, script in enumerate(re.findall(r"^```bash\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)):
            result = subprocess.run(["bash", "-n"], input=script, capture_output=True, text=True)
            assert result.returncode == 0, f"{path.relative_to(ROOT)} block {index}: {result.stderr}"


def test_rubric_reserves_the_unperformed_user_walkthrough():
    text = (ROOT / "docs/guide-quality.md").read_text()
    rows = re.findall(r"^\| ([SU]\d\d) \|.*?\| (\d+) \|\s*$", text, flags=re.MULTILINE)
    scores = {identifier: int(score) for identifier, score in rows}
    assert len(rows) == len(scores) == 20
    assert set(scores) == {f"S{index:02d}" for index in range(1, 20)} | {"U20"}
    assert sum(scores.values()) == 95
    assert scores["U20"] == 0
    assert "자체 문서 평가" in text and "미실시" in text
    assert "Azure 리소스 생성·학습·추론·삭제를 다시 수행하지 않습니다" in text


def test_historical_azure_evidence_is_not_relabelled_as_new_execution():
    report = (ROOT / "docs/execution-report.md").read_text()
    assert "fcc0d95" in report and "당시 Azure 실행 기록" in report
    evidence = json.loads((ROOT / "docs/execution-evidence.json").read_text())
    assert evidence["inference_calls"] == 5
    assert evidence["verified_routed_model_sequence"] == ["blue", "green", "blue"]
