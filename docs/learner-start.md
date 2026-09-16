# 학습자 시작 안내

**이 문서만 따라 준비한 뒤 Notebook으로 이동합니다.** Azure 리소스를 만드는 명령은 없습니다. 새 환경이 필요한 경우에만 강사가 [환경 준비](setup.md)를 수행합니다.

## 시작 전 확인

| 필요한 것 | 확인 기준 |
|---|---|
| Azure 계정 | 강사가 지정한 tenant·구독·Workspace에 접근 가능 |
| 본인 Compute Instance | 본인에게 할당된 Instance를 Start하고 Terminal을 열 수 있음 |
| Storage 접근 | Notebook 파일을 읽고 쓸 수 있는 역할과 private 네트워크 경로 |
| 최신 프로젝트 | 이 private GitHub 저장소를 읽을 권한 또는 강사가 제공한 최신 전체 ZIP |
| 비용 승인 | 학습 VM과 04–06의 추론 VM 비용을 사용할 수 있음 |

**같은 Workspace의 사용자라도 다른 사람의 Compute Instance를 공동 사용하지 않습니다.** Instance가 보이지 않거나 Terminal에 연결할 수 없으면 강사에게 할당·권한·네트워크 확인을 요청합니다. 방화벽이나 공유 키를 켜서 해결하지 않습니다.

아래 이름은 준비된 **개인 실습 환경**의 값입니다. 다른 계정/팀은 강사가 준 이름과 사용자 폴더로 바꿉니다.

| 항목 | 준비된 환경 |
|---|---|
| Workspace | `mlw-mlops-managed-20260916` |
| 개발 Instance | `ci-mlops-private` |
| 학습 Cluster | `cpu-private-only` |
| 사용자 파일 폴더 | `Users/junwoojeong` |
| 기존 게시본 | `Users/junwoojeong/azure-ml-labs` |

이전 검증 종료 때 Instance는 중지하고 endpoint는 삭제했습니다. **endpoint가 아직 없는 것은 정상**이며, 04에서 다시 만듭니다. 현재 상태는 Studio에서 확인합니다.

## 준비 A — Instance 시작과 Terminal 열기

**할 일:** [Azure ML Studio](https://ml.azure.com)에서 Workspace를 선택합니다. **Compute → Compute instances → 본인 Instance → Start**를 누릅니다.

**확인 위치:** 상태가 `Running`이 되면 **Notebooks → 상단 Terminal 아이콘**을 엽니다.

**완료 조건:** 내 PC 터미널이 아니라 **Azure Compute Instance의 Terminal**에 연결됐습니다. 이후 `bash` 블록은 모두 이 Terminal에서 실행합니다.

## 준비 B — 최신 프로젝트를 별도 폴더에 풀기

**GitHub 업데이트는 Studio 파일 공유에 자동 반영되지 않습니다.** 이전 게시본에 덮어쓰지 말고 최신 프로젝트를 별도 폴더에 둡니다. 강사가 이미 이번 개정의 전체 프로젝트를 배치했다면 아래 압축 해제만 건너뛰고 그 폴더로 이동합니다.

1. GitHub의 [저장소](https://github.com/junwoojeong100/azure-ml-labs)에서 **Code → Download ZIP**을 선택합니다. 권한이 없으면 강사에게 최신 ZIP을 받습니다.
2. Studio **Notebooks → User files → `Users/junwoojeong`**에서 **Upload files(파일 업로드)**로 `azure-ml-labs-main.zip`을 올립니다. 개인 PC에서만 압축을 풀어 두는 것으로는 충분하지 않습니다.
3. **Instance Terminal**에서 실행합니다. 다른 사용자는 첫 줄의 사용자 폴더를 자신의 경로로 바꿉니다.

```bash
cd "$HOME/cloudfiles/code/Users/junwoojeong"
test -f azure-ml-labs-main.zip
WORKDIR="mlops-$(date -u +%Y%m%d%H%M%S)"
mkdir "$WORKDIR"
python -m zipfile -e azure-ml-labs-main.zip "$WORKDIR"
cd "$WORKDIR/azure-ml-labs-main"
pwd
ls pyproject.toml config.example.json notebooks/01-studio-mlops.ipynb
```

**완료 조건:** 마지막 명령에 파일 3개가 모두 표시됩니다. `pwd`의 경로가 이후 말하는 **프로젝트 루트**입니다. Terminal을 새로 열면 이 경로로 다시 `cd`합니다.

ZIP에 파일이 없거나 이름이 다르면 다음 명령을 진행하지 말고 업로드 위치·파일명을 확인합니다. Notebook 한 개만 업로드해서는 실행할 수 없습니다.

## 준비 C — 설정 파일 준비

프로젝트 루트의 `config.json`을 사용합니다. **GitHub에는 계정별 `config.json`이 없으며 정상입니다.**

준비된 개인 환경의 기존 설정을 복사하려면:

```bash
cp -n "$HOME/cloudfiles/code/Users/junwoojeong/azure-ml-labs/config.json" config.json
```

기존 게시본/설정이 없는 학습자는 다음 명령으로 예제를 복사하고 Studio 편집기에서 아래 여섯 값을 채웁니다. 둘 중 **한 방법만** 사용합니다.

```bash
cp -n config.example.json config.json
```

| 바꿀 값 | 넣을 내용 |
|---|---|
| `subscription_id` | 강사가 준 Azure 구독 ID |
| `tenant_id` | 해당 계정의 tenant ID |
| `expected_account` | Terminal에서 로그인할 **본인의** Azure UPN |
| `resource_group` | 준비된 Workspace의 RG 이름 |
| `workspace` | 준비된 Workspace 이름 |
| `endpoint_name` | 강사가 지정한 본인 전용 이름. 동시 실습자는 공유하지 않음 |

나머지 자산·환경·Compute 이름은 강사가 변경하라고 안내하지 않았다면 유지합니다. RG/Workspace를 **새로 만드는 단계가 아닙니다**. 구독 정보가 필요하면 [이전 실행 환경](execution-report.md#실행-환경)을 참고하되, 다른 사용자라면 `expected_account`를 그대로 복사하지 않습니다.

**완료 조건:** `<...>`가 하나도 없고 계정·Workspace가 본인에게 지정된 값입니다. `config.json`이나 로그인 토큰을 GitHub에 올리지 않습니다.

## 준비 D — Python 3.12 kernel 준비

**할 일:** Instance Terminal의 **프로젝트 루트**에서 아래 블록을 한 번 실행합니다. `uv`는 Python 환경 준비용 도구이며, 학습은 별도 Azure ML Cluster에서 실행합니다.

```bash
VENV="$HOME/.venvs/aml-mlops-lab"
if [ ! -x "$VENV/bin/python" ]; then
  python -m pip install --user 'uv>=0.8,<1'
  python -m uv venv --python 3.12 --seed "$VENV"
fi
"$VENV/bin/python" -m ensurepip --upgrade
"$VENV/bin/python" -m pip install -r requirements-lock.txt -e .
"$VENV/bin/python" -m ipykernel install --user --name aml-mlops-lab \
  --display-name "AML MLOps Lab (Python 3.12)"
source "$VENV/bin/activate"
python --version
```

**확인 위치:** 마지막 줄에 `Python 3.12.x`가 표시돼야 합니다. `3.10`이나 다른 버전이면 다음으로 진행하지 않습니다.

**완료 조건:** Notebook의 kernel 목록을 새로 고쳤을 때 **AML MLOps Lab (Python 3.12)**가 보입니다. 개발 kernel과 학습용 환경의 Python 버전은 별개입니다.

## 준비 E — CLI 로그인과 준비 완료 확인

브라우저에서 Studio에 로그인한 것과 Terminal의 Azure CLI 로그인은 별개입니다. 같은 Terminal에서:

```bash
TENANT=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().tenant_id)')
az login --tenant "$TENANT" --use-device-code
python - <<'PY'
import sys
from mlops_lab.config import Settings
assert sys.version_info[:2] == (3, 12), "Python 3.12 환경을 선택하세요."
settings = Settings.load()
account = settings.verify_account()
print("준비 완료:", account["user"]["name"], settings.workspace)
PY
```

**완료 조건:** `준비 완료: <본인 계정> <의도한 Workspace>`가 표시됩니다. 계정 불일치나 인증 오류가 나면 실습 01을 실행하지 않습니다.

## Notebook 시작

Studio 파일 목록에서 **준비 B의 새 프로젝트 폴더 → `notebooks/01-studio-mlops.ipynb`**를 엽니다. 상단 Compute와 **AML MLOps Lab (Python 3.12)** kernel을 선택합니다.

**[Notebook 00부터 시작 →](../notebooks/01-studio-mlops.ipynb)**

각 단계의 **할 일 → Studio에서 확인 → 완료 조건**을 따라 `Shift+Enter`로 셀을 하나씩 실행합니다. `Run all`은 사용하지 않습니다.

출력된 `LAB_ID`를 기록하고, Job URL은 **새 탭**으로 엽니다. 실행 중 같은 Notebook 탭에서 다른 Workspace 메뉴로 이동하거나 kernel/Compute를 바꾸지 않습니다.

## 기다릴지 고칠지 판단하기

| 보이는 상태 | 할 일 | 다음 실습으로 이동 |
|---|---|---|
| `Queued` / `Running` | Job URL을 새 탭에서 확인하고 같은 실행을 기다림. 다시 submit하지 않음 | 아직 안 됨 |
| `Submitted` / `Creating`, `ready=false` | 배포가 `Succeeded`가 될 때까지 기다림 | 아직 안 됨 |
| 03의 `Failed` + `evaluate_gate` 실패 + `approved=false` + RMSE > 3 | 의도된 실패. Notebook의 등록 차단 확인까지 수행 | 조건 확인 후 04로 |
| 03의 `Registration blocked` | 거절 모델 버전이 등록되지 않았는지 확인 | 04로 |
| `Failed`인데 위 조건이 다르거나 보고서 없음 | 실제 오류. [상세 진단](troubleshooting.md)에서 원인 해결 | 안 됨 |
| `wait` timeout | Job이 취소된 것이 아님. 같은 실행의 대기 셀만 다시 실행 | 아직 안 됨 |

## 중단 후 이어하기

**kernel을 바꾸거나 재시작하면 변수는 사라져도 Azure Job은 남을 수 있습니다.**

| 상황 | 다시 시작하는 위치 |
|---|---|
| 같은 kernel에서 기다리다 멈춤 | 기존 대기/결과 확인 셀만 다시 실행 |
| kernel/브라우저를 다시 연결함 | Notebook 00의 `RESUME_LAB_ID`에 기록한 `LAB_ID`를 넣고 00만 실행 |
| Job이 이미 제출됐음 | submit 셀을 건너뛰고 해당 단계의 대기 셀부터 |
| 배포가 이미 제출됐음 | [배포 상태 확인](troubleshooting.md#기존-실행을-이어가기) 후 호출 셀부터 |
| 완전히 새 실습을 시작함 | 먼저 이전 리소스를 정리하고 `RESUME_LAB_ID`를 빈 문자열로 둠 |

다시 연결한 프로젝트에는 기존 `artifacts/runs/`가 있어야 합니다. **다른 새 폴더로 옮긴 뒤 ID만 입력하면 실행 기록을 찾을 수 없습니다.** 기록을 복원하거나 강사에게 확인하고, 무조건 새 Job을 제출하지 않습니다.

## 중간에 그만둘 때

실행 중인 Job이 있다면 **Studio → Jobs → 해당 실행 → Cancel** 후 `Canceled`를 확인합니다. **Instance만 멈추면 Cluster의 Job이나 endpoint까지 멈추는 것은 아닙니다.**

프로젝트 루트의 Instance Terminal에서:

```bash
source "$HOME/.venvs/aml-mlops-lab/bin/activate"
python -m mlops_lab.cli cleanup-runtime --delete-endpoint
```

endpoint를 먼저 삭제하고 Instance를 마지막에 중지하므로 연결이 끊길 수 있습니다. Studio에서 **endpoint 없음 / Instance Stopped / Cluster 실제 0노드**를 확인합니다. Premium ACR·Private Endpoint·Storage·디스크의 지속 비용은 남습니다. 전체 RG 삭제는 강사와 보관 필요성을 확인한 뒤 [정리 문서](troubleshooting.md#전체-환경이-더-이상-필요하지-않은-경우)를 따릅니다.

공식 참고: [Instance Terminal](https://learn.microsoft.com/azure/machine-learning/how-to-access-terminal?view=azureml-api-2), [Notebook 실행·kernel·상태 보존](https://learn.microsoft.com/azure/machine-learning/how-to-run-jupyter-notebooks?view=azureml-api-2).
