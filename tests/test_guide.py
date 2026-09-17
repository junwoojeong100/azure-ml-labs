import ast
import json
import os
import re
import subprocess
import sys
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlsplit
from uuid import uuid4

import nbformat
import pytest
import yaml

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
CELL_STEPS = {
    "submit-baseline": "02-A",
    "baseline-report": "02-B",
    "expected-failed-job": "03-A",
    "verify-rejection": "03-A",
    "expected-registration-failure": "03-B",
    "register-blue-model": "04-A",
    "submit-blue-deployment": "04-B",
    "wait-blue-deployment": "04-C",
    "route-blue": "04-D",
    "blue-inference": "04-E",
    "submit-retrain": "05-A",
    "compare-retrain": "05-B",
    "register-retrain": "05-C",
    "submit-green-deployment": "06-A",
    "wait-and-test-green": "06-B",
    "promote-green": "06-C",
    "verify-green-route": "06-D",
    "rollback-blue": "06-E",
    "verify-blue-rollback": "06-F",
}


def notebook_cells():
    return nbformat.read(NOTEBOOK, as_version=4).cells


def bash_blocks(text):
    return re.findall(r"^```bash\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)


def preparation_block(letter):
    text = (ROOT / "docs/learner-start.md").read_text()
    section = text.split(f"## 준비 {letter} — ", 1)[1].split("\n## ", 1)[0]
    blocks = bash_blocks(section)
    assert len(blocks) == 1
    return blocks[0]


def setup_blocks(number):
    text = (ROOT / "docs/setup.md").read_text()
    section = text.split(f"## {number}. ", 1)[1].split("\n## ", 1)[0]
    return bash_blocks(section)


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


def unsupported_guide_letters(text):
    return {
        character for character in text
        if character.isalpha() and not character.isascii()
        and not unicodedata.name(character, "").startswith("HANGUL ")
    }


def test_guides_use_only_korean_and_english_letters():
    documents = [(path, text) for path, text in guide_documents() if path != NOTEBOOK]
    documents.append((NOTEBOOK, "\n".join(cell.source for cell in notebook_cells())))
    errors = []
    for path, text in documents:
        for number, line in enumerate(text.splitlines(), 1):
            unsupported = unsupported_guide_letters(line)
            if unsupported:
                codepoints = ", ".join(f"U+{ord(character):04X}" for character in sorted(unsupported))
                errors.append(f"{path.relative_to(ROOT)}:{number}: {codepoints}")
    assert not errors, "\n".join(errors)


def test_guide_language_guard_rejects_other_scripts_but_allows_notation():
    assert not unsupported_guide_letters("한글 English 00–07 · RMSE ≤ 3, R², `--no-wait`")
    for character in ("\u6f22", "\u3042", "\u30a2", "\uff71", "\U00020000", "\u0391", "\u0410"):
        assert unsupported_guide_letters(character), f"Expected rejection of U+{ord(character):04X}"


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


def test_infrastructure_page_matches_compute_and_deployment_defaults():
    text = (ROOT / "docs/infrastructure.md").read_text()
    config = json.loads((ROOT / "config.example.json").read_text())
    instance = yaml.safe_load((ROOT / "infra/compute-instance.yml").read_text())
    cluster = yaml.safe_load((ROOT / "infra/compute-cluster.yml").read_text())
    workspace = yaml.safe_load((ROOT / "infra/workspace.yml").read_text())
    rows = dict(re.findall(
        r"^\| (Notebook·제출|학습·평가|실시간 추론) \| (.+) \|$", text, flags=re.MULTILINE,
    ))
    assert len(rows) == 3
    for definition, role, name in (
        (instance, "Notebook·제출", config["compute_instance"]),
        (cluster, "학습·평가", config["compute_cluster"]),
    ):
        assert f"`{definition['size']}`" in rows[role]
        assert f"`{name}`" in rows[role]
        assert definition["enable_node_public_ip"] is False
        assert definition["ssh_public_access_enabled"] is False
    assert f"{instance['idle_time_before_shutdown_minutes']}분" in rows["Notebook·제출"]
    assert f"{cluster['min_instances']}–{cluster['max_instances']}노드" in rows["학습·평가"]
    assert f"{cluster['idle_time_before_scale_down']}초" in rows["학습·평가"]
    assert f"`{cluster['tier']}`" in rows["학습·평가"]
    assert f"`{config['deployment_instance_type']}`" in rows["실시간 추론"]
    assert f"`{workspace['managed_network']['isolation_mode']}`" in text

    tree = ast.parse((ROOT / "mlops_lab/operations.py").read_text())
    deploy = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "deploy")
    constructors = {
        node.func.id: {keyword.arg: keyword.value for keyword in node.keywords}
        for node in ast.walk(deploy)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id in {"ManagedOnlineEndpoint", "ManagedOnlineDeployment"}
    }
    deployment = constructors["ManagedOnlineDeployment"]
    assert ast.unparse(deployment["instance_type"]) == "settings.deployment_instance_type"
    count = ast.literal_eval(deployment["instance_count"])
    assert f"blue {count}대 + green {count}대" in rows["실시간 추론"]
    auth_mode = ast.literal_eval(constructors["ManagedOnlineEndpoint"]["auth_mode"])
    assert f"`{auth_mode}`" in text


def test_infrastructure_reference_is_optional_and_reachable_from_each_entry():
    text = (ROOT / "docs/infrastructure.md").read_text()
    assert "선택 읽기" in text
    assert not bash_blocks(text)
    for term in ("Serverless Compute", "Kubernetes Compute", "Kubernetes Online Endpoint", "Batch Endpoint"):
        assert term in text
    assert "대안 비교이며 전환 절차가 아닙니다" in text
    required = {"README.md", "learner-start.md", "lab-guide.md", "setup.md", NOTEBOOK.name}
    linked = set()
    for path, source in guide_documents():
        if path.name in required:
            assert re.search(r"\]\((?:\.\./)?(?:docs/)?infrastructure\.md\)", source), path
            linked.add(path.name)
    assert linked == required


def test_cli_quality_gate_completes_only_after_registration_blocking():
    text = (ROOT / "docs/lab-guide.md").read_text()
    section = text.split("## 03 · 품질 게이트", 1)[1].split("\n## ", 1)[0]
    assert section.count("**완료 조건:**") == 1
    assert section.index("**완료 조건:**") > section.index('register --run "$BAD_RUN"')
    completion = section.split("**완료 조건:**", 1)[1]
    for condition in ("03-A", "Registration blocked", "${LAB_ID}9", "없음"):
        assert condition in completion


def test_shared_cluster_cleanup_is_distinguished_from_dedicated_zero_nodes():
    documents = dict(guide_documents())
    for path in (ROOT / "README.md", ROOT / "docs/learner-start.md", ROOT / "docs/lab-guide.md", NOTEBOOK):
        text = documents[path]
        assert "전용 Cluster" in text
        assert "troubleshooting.md#공유-학습-클러스터의-정리" in text
    section = documents[ROOT / "docs/troubleshooting.md"].split(
        "## 공유 학습 클러스터의 정리", 1,
    )[1].split("\n## ", 1)[0]
    for condition in ("본인 실행 중 Job 없음", "본인 endpoint 없음", "본인 Instance Stopped"):
        assert condition in section
    assert "다른 사람의 Job을 취소하거나" in section


def test_learner_preparation_is_separate_and_has_a_ready_checkpoint():
    text = (ROOT / "docs/learner-start.md").read_text()
    for section in ("준비 A", "준비 B", "준비 C", "준비 D", "준비 E"):
        assert f"## {section}" in text
    for field in (
        "subscription_id", "tenant_id", "expected_account", "resource_group",
        "workspace", "compute_instance", "compute_cluster", "endpoint_name",
    ):
        assert f"`{field}`" in text
    assert "settings.verify_account()" in text
    assert 'print("준비 완료:"' in text
    assert "자동 반영되지 않습니다" in text
    assert "본인에게 할당" in text
    assert "cp -n config.example.json config.json" in text
    assert not re.search(r"cp -n .*cloudfiles", text)
    assert 'Users/<본인 폴더>' in preparation_block("B")
    assert "같은 브랜치" in text
    assert "private GitHub" not in text
    assert "azure-ml-labs-main.zip" not in preparation_block("B")
    for field in ("compute_instance", "compute_cluster", "endpoint_name"):
        assert f"settings.{field}" in preparation_block("E")
    for forbidden in ("az group create", "az ml workspace create", "az role assignment create"):
        assert forbidden not in text


def test_entry_points_distinguish_one_notebook_from_resuming_an_existing_run():
    documents = dict(guide_documents())
    for path in (ROOT / "README.md", ROOT / "docs/learner-start.md", NOTEBOOK):
        text = documents[path]
        assert "파일 하나" in text
        assert re.search(r"\]\([^)]*#(?:기존-실행을-이어가기|중단-후-이어하기)\)", text)
    cli = documents[ROOT / "docs/lab-guide.md"]
    assert "기존 프로젝트 루트" in cli and "01부터 다시 실행하는 절차가 아닙니다" in cli


def test_notebook_and_cli_substeps_match_the_code_they_introduce():
    cells = notebook_cells()
    pattern = r"^### (0[2-6]-[A-F]) · (.+)$"
    cli = (ROOT / "docs/lab-guide.md").read_text()
    notebook = "\n\n".join(cell.source for cell in cells if cell.cell_type == "markdown")
    headings = re.findall(pattern, notebook, flags=re.MULTILINE)
    assert headings == re.findall(pattern, cli, flags=re.MULTILINE)
    assert len(headings) == len(set(CELL_STEPS.values()))
    assert {step for step, _ in headings} == set(CELL_STEPS.values())
    current_step = None
    seen = set()
    for cell in cells:
        if cell.cell_type == "markdown":
            substeps = re.findall(pattern, cell.source, flags=re.MULTILINE)
            if substeps:
                current_step = substeps[-1][0]
        elif cell.id in CELL_STEPS:
            assert current_step == CELL_STEPS[cell.id], cell.id
            seen.add(cell.id)
    assert seen == set(CELL_STEPS)
    rejection_index = next(index for index, cell in enumerate(cells) if cell.id == "verify-rejection")
    assert cells[rejection_index - 1].id == "rejection-check-explanation"
    assert cells[rejection_index - 2].id == "expected-failed-job"


def test_cli_separates_submission_waiting_and_each_traffic_change():
    blocks = bash_blocks((ROOT / "docs/lab-guide.md").read_text())
    deployments = []
    for script in blocks:
        commands = re.findall(r"python -m mlops_lab\.cli ([a-z-]+)", script)
        assert not (
            set(commands) & {"submit", "deploy"}
            and set(commands) & {"wait", "wait-deployment", "invoke", "register"}
        )
        assert commands.count("traffic") <= 1
        if "traffic" in commands:
            assert commands == ["traffic"]
        if "deploy" in commands:
            assert "--no-wait" in script
            deployments.append(script)
    assert len(deployments) == 2
    for name in ("blue", "green"):
        assert any(f"wait-deployment --deployment {name}" in script for script in blocks)
    comparison = next(script for script in blocks if 'wait --run "$RETRAIN_RUN"' in script)
    assert 'report --run "$BASELINE_RUN"' in comparison
    assert 'report --run "$RETRAIN_RUN"' in comparison


def test_cli_route_checks_fetch_both_responses_without_saved_terminal_output():
    text = (ROOT / "docs/lab-guide.md").read_text()
    for step, deployment in (("04-E", "blue"), ("06-D", "green"), ("06-F", "blue")):
        section = text.split(f"### {step} · ", 1)[1].split("\n### ", 1)[0].split("\n## ", 1)[0]
        script = bash_blocks(section)[0]
        assert script.strip().splitlines() == [
            f"python -m mlops_lab.cli invoke --deployment {deployment} &&",
            "python -m mlops_lab.cli invoke",
        ]


@pytest.mark.parametrize("state, archive_root", [
    ("missing-folder", "azure-ml-labs-main"),
    ("missing-zip", "azure-ml-labs-main"),
    ("ready", "azure-ml-labs-main"),
    ("ready", "azure-ml-labs-docs-straightforwardness-95"),
    ("multiple-projects", "azure-ml-labs-main"),
])
def test_project_unpacking_requires_the_correct_folder_and_zip(tmp_path, state, archive_root):
    user_folder = tmp_path / "cloudfiles/code/Users/test-learner"
    files = ("pyproject.toml", "config.example.json", "notebooks/01-studio-mlops.ipynb")
    if state != "missing-folder":
        user_folder.mkdir(parents=True)
    if state in {"ready", "multiple-projects"}:
        with zipfile.ZipFile(user_folder / "azure-ml-labs.zip", "w") as archive:
            for name in files:
                archive.writestr(f"{archive_root}/{name}", "{}")
            if state == "multiple-projects":
                archive.writestr("azure-ml-labs-other/pyproject.toml", "")
    script = preparation_block("B").replace("<본인 폴더>", "test-learner")
    result = subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "HOME": str(tmp_path),
             "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]},
    )
    workdirs = list(tmp_path.rglob("mlops-*"))
    if state == "ready":
        assert result.returncode == 0, result.stderr
        assert len(workdirs) == 1
        for name in files:
            assert (workdirs[0] / archive_root / name).is_file()
        assert str(workdirs[0] / archive_root) in result.stdout
    else:
        assert result.returncode != 0
        assert result.stderr
        if state == "multiple-projects":
            assert "프로젝트 폴더가 하나가 아닙니다" in result.stderr
            assert "pyproject.toml" not in result.stdout
        else:
            assert not workdirs, "A failed path/ZIP check must not create an unrelated project folder."


@pytest.mark.parametrize("failed_module", ["version", "ensurepip", "pip", "ipykernel"])
def test_kernel_preparation_stops_at_the_failed_install(tmp_path, failed_module):
    binary = tmp_path / ".venvs/aml-mlops-lab/bin/python"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        "#!/bin/bash\n"
        'printf "%s\\n" "$*" >> "$HOME/python-calls"\n'
        f'if [ "$1" = "-c" ] && [ "{failed_module}" = "version" ]; then exit 23; fi\n'
        f'if [ "$2" = "{failed_module}" ]; then exit 23; fi\n'
        "exit 0\n"
    )
    binary.chmod(0o755)
    (binary.parent / "activate").write_text("return 0\n")
    result = subprocess.run(
        ["bash", "-c", preparation_block("D")], cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "HOME": str(tmp_path),
             "PATH": str(binary.parent) + os.pathsep + os.environ["PATH"]},
    )
    assert result.returncode == 23
    calls = (tmp_path / "python-calls").read_text().splitlines()
    if failed_module == "version":
        assert len(calls) == 1 and calls[0].startswith("-c ")
        assert "sys.version_info[:2] == (3, 12)" in calls[0]
    else:
        assert calls[-1].split()[1] == failed_module
    assert "--version" not in calls


def test_failed_cli_login_does_not_run_the_ready_checkpoint(tmp_path):
    stubs = (
        'python() { if [ "$1" = "-c" ]; then printf "test-tenant"; '
        'else printf "UNEXPECTED_READY_CHECK"; fi; }\n'
        "az() { return 29; }\n"
    )
    result = subprocess.run(
        ["bash", "-c", stubs + preparation_block("E")], cwd=tmp_path,
        capture_output=True, text=True,
    )
    assert result.returncode == 29
    assert "UNEXPECTED_READY_CHECK" not in result.stdout


@pytest.mark.parametrize("exists, failed_command", [
    ("false", ""),
    ("true", ""),
    ("", ""),
    ("unexpected", ""),
    ("false", "group exists"),
    ("false", "provider register --namespace Microsoft.Network"),
    ("false", "group create"),
    ("false", "acr create"),
    ("false", "acr show"),
    ("false", "ml workspace create"),
])
def test_setup_resource_creation_requires_a_new_rg_and_stops_on_failure(
    tmp_path, exists, failed_command,
):
    stubs = r'''
az() {
  printf '%s\n' "$*" >> "$TRACE"
  if [ -n "$FAIL_COMMAND" ] && [[ "$*" == "$FAIL_COMMAND"* ]]; then
    printf 'Simulated Azure failure\n' >&2
    return 29
  fi
  case "$1 $2" in
    "group exists") printf '%s\n' "$RG_EXISTS_RESULT" ;;
    "acr show") printf '/test/registry\n' ;;
  esac
}
python() { printf 'acr-test\n'; }
'''
    trace = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-c", stubs + setup_blocks(2)[0]], cwd=tmp_path,
        capture_output=True, text=True,
        env={**os.environ, "TRACE": str(trace), "RG_EXISTS_RESULT": exists,
             "FAIL_COMMAND": failed_command, "SUB": "test-sub", "RG": "test-rg",
             "WS": "test-workspace", "LOCATION": "test-location"},
    )
    calls = trace.read_text().splitlines()
    if failed_command:
        assert result.returncode == 29
        assert calls[-1].startswith(failed_command)
        assert result.stderr
    elif exists != "false":
        assert result.returncode != 0
        assert len(calls) == 1 and calls[0].startswith("group exists")
        assert "새 RG만 생성합니다" in result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert calls[-1].startswith("ml workspace create")
        providers = {call.split()[3] for call in calls if call.startswith("provider register")}
        assert providers == {
            "Microsoft.MachineLearningServices", "Microsoft.Network", "Microsoft.Compute",
            "Microsoft.ManagedIdentity", "Microsoft.Storage", "Microsoft.KeyVault",
            "Microsoft.ContainerRegistry", "Microsoft.Insights", "Microsoft.OperationalInsights",
        }
    assert all("--subscription test-sub" in call for call in calls)


@pytest.mark.parametrize("user_id, failed_role", [
    ("00000000-0000-0000-0000-000000000001", ""),
    ("<실습 사용자 Object ID>", ""),
    ("learner@example.test", ""),
    ("00000000-0000-0000-0000-000000000001", "AzureML Data Scientist"),
    ("00000000-0000-0000-0000-000000000001", "Storage Blob Data Contributor"),
    ("00000000-0000-0000-0000-000000000001", "Storage File Data Privileged Contributor"),
])
def test_setup_assigns_learner_roles_and_rejects_invalid_or_failed_assignments(
    tmp_path, user_id, failed_role,
):
    stubs = r'''
az() {
  printf '%s\n' "$*" >> "$TRACE"
  if [ -n "$FAIL_ROLE" ] && [[ "$*" == *"--role $FAIL_ROLE"* ]]; then
    printf 'Simulated role assignment failure\n' >&2
    return 31
  fi
  if [ "$1 $2" = "identity show" ]; then printf 'test-compute-identity\n'; fi
}
'''
    trace = tmp_path / "calls"
    script = setup_blocks(3)[0].replace("<실습 사용자 Object ID>", user_id)
    result = subprocess.run(
        ["bash", "-c", stubs + script], cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "TRACE": str(trace), "FAIL_ROLE": failed_role,
             "SUB": "test-sub", "RG": "test-rg", "LOCATION": "test-location",
             "WS_ID": "workspace-scope", "STORAGE_ID": "storage-scope",
             "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]},
    )
    if user_id.startswith("<") or "@" in user_id:
        assert result.returncode != 0
        assert result.stderr and not trace.exists()
        return
    calls = trace.read_text().splitlines()
    if failed_role:
        assert result.returncode == 31
        assert f"--role {failed_role}" in calls[-1]
        return
    assert result.returncode == 0, result.stderr
    assignments = [call for call in calls if call.startswith("role assignment create")]
    assert len(assignments) == 5
    assert f"--assignee-object-id {user_id}" in assignments[0]
    assert "--role AzureML Data Scientist --scope workspace-scope" in assignments[0]
    for role in ("Storage Blob Data Contributor", "Storage File Data Privileged Contributor"):
        matches = [call for call in assignments if f"--role {role} --scope storage-scope" in call]
        assert len(matches) == 2
        assert any(f"--assignee-object-id {user_id}" in call for call in matches)
        assert any("--assignee-object-id test-compute-identity" in call for call in matches)


@pytest.mark.parametrize("failed_command", [
    "",
    "ml workspace provision-network",
    "python -m scripts.render_compute",
    "ml compute create --file artifacts/infra/compute-cluster.yml",
    "ml compute create --file artifacts/infra/compute-instance.yml",
    "ml workspace update",
])
def test_setup_assigns_the_instance_to_the_learner_and_stops_after_failure(tmp_path, failed_command):
    stubs = r'''
az() {
  printf '%s\n' "$*" >> "$TRACE"
  if [ -n "$FAIL_COMMAND" ] && [[ "$*" == "$FAIL_COMMAND"* ]]; then
    printf 'Simulated compute setup failure\n' >&2
    return 37
  fi
}
python() { az python "$@"; }
'''
    trace = tmp_path / "calls"
    result = subprocess.run(
        ["bash", "-c", stubs + setup_blocks(4)[0]], cwd=tmp_path,
        capture_output=True, text=True,
        env={**os.environ, "TRACE": str(trace), "FAIL_COMMAND": failed_command,
             "SUB": "test-sub", "RG": "test-rg", "WS": "test-workspace",
             "CLUSTER": "test-cluster", "TENANT": "learner-tenant",
             "USER_OBJECT_ID": "learner-object", "MI_ID": "compute-identity"},
    )
    calls = trace.read_text().splitlines()
    if failed_command:
        assert result.returncode == 37
        assert calls[-1].startswith(failed_command)
        assert result.stderr
    else:
        assert result.returncode == 0, result.stderr
        assert len(calls) == 5
        instance = next(call for call in calls if "artifacts/infra/compute-instance.yml" in call)
        assert "--user-object-id learner-object --user-tenant-id learner-tenant" in instance
        assert "--image-build-compute test-cluster" in calls[-1]


@pytest.mark.parametrize("command", [
    "az ml online-deployment delete", "az vm delete", "az group delete",
])
def test_manual_deletion_blocks_require_targets_and_keep_confirmation(tmp_path, command):
    blocks = bash_blocks((ROOT / "docs/troubleshooting.md").read_text())
    script = next(block for block in blocks if command in block)
    assert "--yes" not in script
    assert "az vm show" not in script and "az resource list" not in script
    result = subprocess.run(
        ["bash", "-c", "az() { printf 'UNEXPECTED_DELETE'; }\n" + script],
        cwd=tmp_path, capture_output=True, text=True,
        env={**os.environ, "SUB": "", "RG": "", "WS": "", "ENDPOINT": ""},
    )
    assert result.returncode != 0
    assert result.stderr and "UNEXPECTED_DELETE" not in result.stdout


def test_runner_bundle_contains_the_guides_and_their_execution_evidence():
    from scripts.remote_runner import bundle_files

    required = {path for path, _ in guide_documents()}
    required.add(ROOT / "docs/execution-evidence.json")
    assert required <= set(bundle_files())


def test_studio_publication_contains_the_guides_and_their_execution_evidence(tmp_path, monkeypatch):
    import mlops_lab.publish as publication

    uploaded = {}

    def file_client(name):
        return SimpleNamespace(
            upload_file=lambda content: uploaded.update({name: content}),
            download_file=lambda: SimpleNamespace(readall=lambda: uploaded[name]),
        )

    share = SimpleNamespace(
        get_directory_client=lambda name: SimpleNamespace(create_directory=lambda: None),
        get_file_client=file_client,
    )
    monkeypatch.setattr(publication, "ARTIFACTS", tmp_path)
    monkeypatch.setattr(publication, "ManagedIdentityCredential", lambda **kwargs: object())
    monkeypatch.setattr(publication, "ShareServiceClient", lambda **kwargs: SimpleNamespace(
        get_share_client=lambda name: share,
    ))
    settings = SimpleNamespace(
        expected_account="learner@example.test",
        client=lambda **kwargs: SimpleNamespace(datastores=SimpleNamespace(
            get=lambda name: SimpleNamespace(account_name="test-storage", file_share_name="test-share"),
        )),
    )
    result = publication.publish_notebooks(settings, "test-identity")
    required = {path for path, _ in guide_documents()}
    required.add(ROOT / "docs/execution-evidence.json")
    for path in required:
        destination = f"Users/learner/azure-ml-labs/{path.relative_to(ROOT).as_posix()}"
        assert uploaded[destination] == path.read_bytes()
        assert destination in result["uploaded_files"]
    assert result["verified_file_count"] == len(uploaded)


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


@pytest.mark.parametrize("restart_at", [
    None, "baseline-report", "expected-failed-job", "wait-blue-deployment",
    "compare-retrain", "wait-and-test-green", "promote-green", "verify-green-route", "verify-blue-rollback",
])
def test_notebook_sequence_and_kernel_resume_without_azure(tmp_path, monkeypatch, capsys, restart_at):
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
        compute_instance="test-instance", compute_cluster="test-compute",
        endpoint_name="test-endpoint", component_version="3", client=lambda: object(),
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
        if cell.id == restart_at:
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
    output = capsys.readouterr().out
    for step in ("01", "02", "04", "05", "06"):
        assert f"{step} 완료:" in output


@pytest.mark.parametrize("cell_id", ["blue-inference", "verify-green-route", "verify-blue-rollback"])
def test_inference_mismatch_does_not_print_completion(cell_id, capsys):
    import numpy as np

    def invoke(client, settings, deployment=None):
        return {"predictions": [1.0 if deployment else 2.0] * 5}

    source = next(cell.source for cell in notebook_cells() if cell.id == cell_id)
    with pytest.raises(AssertionError):
        exec(compile(source, f"<notebook:{cell_id}>", "exec"), {
            "np": np, "invoke": invoke, "client": object(), "settings": object(),
        })
    assert "완료" not in capsys.readouterr().out


def test_documented_bash_blocks_are_syntactically_valid():
    for path, text in guide_documents():
        for index, script in enumerate(bash_blocks(text)):
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
