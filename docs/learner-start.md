# 학습자 시작 안내

**준비 A–E를 끝낸 뒤 Notebook 00으로 이동합니다.** Azure 리소스를 만드는 명령은 없습니다. 새 환경이 필요한 경우에만 강사가 [환경 준비](setup.md)를 수행합니다.

개발·학습·추론 VM의 역할이나 다른 선택지가 궁금하면 [학습·추론 인프라 안내](infrastructure.md)를 참고합니다. **선택 읽기**이며 준비 절차는 아래 A부터 시작합니다.

## 시작 전 확인

| 필요한 것 | 확인 기준 |
|---|---|
| Azure 계정 | 강사가 지정한 tenant·구독·Workspace에 접근 가능 |
| 본인 Compute Instance | 본인에게 할당된 Instance를 Start하고 Terminal을 열 수 있음 |
| Storage 접근 | Notebook 파일을 읽고 쓸 수 있는 역할과 private 네트워크 경로 |
| 최신 프로젝트 | 현재 읽는 가이드와 같은 브랜치의 전체 ZIP 또는 강사가 제공한 해당 버전 ZIP |
| 비용 승인 | 학습 VM과 04–06의 추론 VM 비용을 사용할 수 있음 |

**같은 Workspace의 사용자라도 다른 사람의 Compute Instance를 공동 사용하지 않습니다.** Instance가 보이지 않거나 Terminal에 연결할 수 없으면 강사에게 할당·권한·네트워크 확인을 요청합니다. 방화벽이나 공유 키를 켜서 해결하지 않습니다.

강사에게 **구독·tenant·RG·Workspace, 본인 Instance·학습 Cluster·본인 endpoint 이름**을 받습니다. 사용자 파일 폴더는 Studio **Notebooks → User files → Users** 아래의 본인 폴더입니다. [이전 실행 환경](execution-report.md#실행-환경)의 이름을 다른 학습자에게 그대로 적용하지 않습니다.

이전 검증 종료 때 Instance는 중지하고 endpoint는 삭제했습니다. **endpoint가 아직 없는 것은 정상**이며, 04에서 만듭니다. 현재 상태는 Studio에서 확인합니다.

## 준비 A — Instance 시작과 Terminal 열기

**할 일:** [Azure ML Studio](https://ml.azure.com)에서 Workspace를 선택합니다. **Compute → Compute instances → 본인 Instance → Start**를 누릅니다.

**확인 위치:** 상태가 `Running`이 되면 **Notebooks → 상단 Terminal 아이콘**을 엽니다.

**완료 조건:** 내 PC 터미널이 아니라 **Azure Compute Instance의 Terminal**에 연결됐습니다. 이후 `bash` 블록은 모두 이 Terminal에서 실행합니다.

## 준비 B — 최신 프로젝트를 별도 폴더에 풀기

**GitHub 업데이트는 Studio 파일 공유에 자동 반영되지 않습니다.** 이전 게시본에 덮어쓰지 말고 최신 프로젝트를 별도 폴더에 둡니다. 강사가 최신 전체 프로젝트를 이미 배치했다면 그 폴더로 `cd`하고 아래 파일 3개가 있는지 확인한 뒤 **준비 C**로 이동합니다.

1. GitHub의 [저장소](https://github.com/junwoojeong100/azure-ml-labs)에서 **현재 읽는 가이드와 같은 브랜치**를 선택한 뒤 **Code → Download ZIP**을 누릅니다. 브랜치가 다르면 가이드와 코드 버전이 어긋날 수 있습니다. 접근할 수 없으면 강사에게 해당 버전 ZIP을 받습니다.
2. 받은 ZIP의 파일명을 **`azure-ml-labs.zip`으로 바꾼 뒤**, Studio **Notebooks → User files → Users → 본인 폴더**의 **Upload files(파일 업로드)**로 올립니다. 개인 PC에서만 압축을 풀어 두는 것으로는 충분하지 않습니다.
3. **Instance Terminal**에서 실행합니다. 첫 줄의 `<본인 폴더>` 전체를 Studio에 보이는 폴더명으로 바꿉니다. 꺾쇠도 제거합니다.

```bash
cd "$HOME/cloudfiles/code/Users/<본인 폴더>" &&
ls azure-ml-labs.zip &&
WORKDIR="mlops-$(date -u +%Y%m%d%H%M%S)" &&
mkdir "$WORKDIR" &&
python -m zipfile -e azure-ml-labs.zip "$WORKDIR" &&
PROJECTS=("$WORKDIR"/azure-ml-labs-*/) &&
if [ "${#PROJECTS[@]}" -eq 1 ] && [ -d "${PROJECTS[0]}" ]; then
  cd "${PROJECTS[0]}"
else
  printf '프로젝트 폴더가 하나가 아닙니다. 전체 프로젝트 ZIP을 확인하세요.\n' >&2
  false
fi &&
pwd &&
ls pyproject.toml config.example.json notebooks/01-studio-mlops.ipynb
```

**완료 조건:** 마지막 명령에 파일 3개가 모두 표시됩니다. `pwd`의 경로가 이후 말하는 **프로젝트 루트**입니다. 이 경로를 기록하세요. Terminal을 새로 열면 이 경로로 다시 `cd`합니다.

`&&`로 연결한 명령은 앞 명령이 실패하면 다음 명령을 실행하지 않습니다. `azure-ml-labs-*/`는 브랜치마다 달라지는 압축 내부 폴더명에 대응합니다. 해당 폴더가 하나가 아니거나 파일이 빠졌다면 진행하지 말고 ZIP을 확인합니다. Notebook 한 개만 업로드해서는 실행할 수 없습니다.

## 준비 C — 설정 파일 준비

프로젝트 루트의 `config.json`을 사용합니다. **GitHub에는 계정별 `config.json`이 없으며 정상입니다.**

다음 명령으로 예제를 복사합니다. 강사가 `config.json`을 이미 제공했다면 `cp -n`은 기존 파일을 덮어쓰지 않습니다.

```bash
cp -n config.example.json config.json
```

Studio 파일 목록에서 **새 프로젝트 폴더 → `config.json`**을 열고 아래 **8개 값**을 확인·수정한 뒤 저장합니다. 다른 사람의 설정을 복사해 그대로 실행하지 않습니다.

| 확인·수정할 값 | 넣을 내용 |
|---|---|
| `subscription_id` | 강사가 준 Azure 구독 ID |
| `tenant_id` | 해당 계정의 tenant ID |
| `expected_account` | Terminal에서 로그인할 **본인의** Azure UPN(로그인 계정) |
| `resource_group` | 준비된 Workspace의 RG 이름 |
| `workspace` | 준비된 Workspace 이름 |
| `compute_instance` | **본인에게 할당된** Instance 이름 |
| `compute_cluster` | 강사가 지정한 학습 Cluster 이름 |
| `endpoint_name` | 강사가 지정한 본인 전용 이름. 동시 실습자는 공유하지 않음 |

**정리 명령은 Studio에서 선택한 Instance가 아니라 `config.json`의 `compute_instance`를 중지합니다.** Compute 이름에 기본값이 있어도 반드시 본인 환경과 대조합니다.

나머지 자산·환경 설정은 강사가 변경하라고 안내하지 않았다면 유지합니다. RG/Workspace를 **새로 만드는 단계가 아닙니다**.

**완료 조건:** `<...>`가 하나도 없고 계정·Workspace가 본인에게 지정된 값입니다. `config.json`이나 로그인 토큰을 GitHub에 올리지 않습니다.

## 준비 D — Python 3.12 kernel 준비

**할 일:** Instance Terminal의 **프로젝트 루트**에서 아래 블록을 한 번 실행합니다. `uv`는 Python 환경 준비용 도구이며, 학습은 별도 Azure ML Cluster에서 실행합니다.

```bash
VENV="$HOME/.venvs/aml-mlops-lab"
if [ ! -x "$VENV/bin/python" ]; then
  python -m pip install --user 'uv>=0.8,<1' &&
  python -m uv venv --python 3.12 --seed "$VENV"
fi &&
"$VENV/bin/python" -m ensurepip --upgrade &&
"$VENV/bin/python" -m pip install -r requirements-lock.txt -e . &&
"$VENV/bin/python" -m ipykernel install --user --name aml-mlops-lab \
  --display-name "AML MLOps Lab (Python 3.12)" &&
source "$VENV/bin/activate" &&
python --version
```

**확인 위치:** 마지막 줄에 `Python 3.12.x`가 표시돼야 합니다. `3.10`이나 다른 버전이면 다음으로 진행하지 않습니다.

**완료 조건:** Notebook의 kernel 목록을 새로 고쳤을 때 **AML MLOps Lab (Python 3.12)**가 보입니다. 개발 kernel과 학습용 환경의 Python 버전은 별개입니다.

## 준비 E — CLI 로그인과 준비 완료 확인

브라우저에서 Studio에 로그인한 것과 Terminal의 Azure CLI 로그인은 별개입니다. 같은 Terminal에서:

```bash
TENANT=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().tenant_id)') &&
az login --tenant "$TENANT" --use-device-code &&
python - <<'PY'
import sys
from mlops_lab.config import Settings
assert sys.version_info[:2] == (3, 12), "Python 3.12 환경을 선택하세요."
settings = Settings.load()
account = settings.verify_account()
print("준비 완료:", account["user"]["name"], settings.workspace)
print("Instance / Cluster:", settings.compute_instance, "/", settings.compute_cluster)
print("Endpoint:", settings.endpoint_name)
PY
```

**완료 조건:** `준비 완료: <본인 계정> <의도한 Workspace>`와 본인 Instance·Cluster·endpoint 이름이 표시됩니다. 이 단계는 **로그인 계정과 설정 확인**이며, 실제 데이터 접근은 01에서 확인합니다. 오류가 나면 실습을 시작하지 말고 [준비 단계 문제 해결](troubleshooting.md#준비-단계에서-막혔다면)로 이동합니다.

## Notebook 시작

Studio 파일 목록에서 **준비 B의 새 프로젝트 폴더 → `notebooks/01-studio-mlops.ipynb`**를 엽니다. 상단 Compute와 **AML MLOps Lab (Python 3.12)** kernel을 선택합니다.

**[Notebook 00부터 시작 →](../notebooks/01-studio-mlops.ipynb)**

각 단계의 **할 일 → Studio에서 확인 → 완료 조건**을 따라 `Shift+Enter`로 셀을 하나씩 실행합니다. 이전 셀이 끝난 뒤 다음 셀을 실행하며 `Run all`은 사용하지 않습니다. **제출 셀의 URL은 접수 확인일 뿐, Job 완료 표시가 아닙니다.** 이어지는 대기 셀까지 수행합니다.

출력된 `LAB_ID`를 기록하고, Job URL은 **새 탭**으로 엽니다. 실행 중 같은 Notebook 탭에서 다른 Workspace 메뉴로 이동하거나 kernel/Compute를 바꾸지 않습니다.

## 기다릴지 고칠지 판단하기

| 보이는 상태 | 할 일 | 다음 실습으로 이동 |
|---|---|---|
| `Queued` / `Running` | Job URL을 새 탭에서 확인하고 같은 실행을 기다림. 다시 submit하지 않음 | 아직 안 됨 |
| `Submitted` / `Creating`, `ready=false` | 배포가 `Succeeded`가 될 때까지 기다림 | 아직 안 됨 |
| 03의 `Failed` + `evaluate_gate` 실패 + `approved=false` + RMSE > 3 | 의도된 실패. **03-B의 등록 차단 확인**으로 이동 | 아직 04로 가지 않음 |
| 03의 `Registration blocked` | 위 네 조건과 거절 모델 버전 부재를 **모두** 확인. 등록 차단 메시지만으로 정상 판정하지 않음 | 모두 맞으면 04로 |
| `Failed`인데 위 조건이 다르거나 보고서 없음 | 실제 오류. [상세 진단](troubleshooting.md)에서 원인 해결 | 안 됨 |
| `wait` timeout | Job이 취소된 것이 아님. 같은 실행의 대기 셀만 다시 실행 | 아직 안 됨 |

## 중단 후 이어하기

**kernel을 바꾸거나 재시작하면 변수는 사라져도 Azure Job은 남을 수 있습니다.**

| 상황 | 다시 시작하는 위치 |
|---|---|
| 같은 kernel에서 기다리다 멈춤 | 기존 대기/결과 확인 셀만 다시 실행 |
| 다시 연결했지만 같은 kernel의 변수가 남아 있음 | 마지막으로 실행하던 대기/확인 셀부터 |
| kernel을 재시작했거나 `NameError`로 변수가 없음 | Notebook 00의 `RESUME_LAB_ID`에 기록한 `LAB_ID`를 넣고 00만 실행 |
| Job이 이미 제출됐음 | submit 셀을 건너뛰고 해당 단계의 대기 셀부터 |
| 배포가 이미 제출됐음 | **04-C 또는 06-B의 배포 대기**부터. `Succeeded` 확인 후 호출 |
| 완전히 새 실습을 시작함 | 먼저 이전 리소스를 정리하고 `RESUME_LAB_ID`를 빈 문자열로 둠 |

다시 연결한 프로젝트에는 기존 `artifacts/runs/`가 있어야 합니다. **다른 새 폴더로 옮긴 뒤 ID만 입력하면 실행 기록을 찾을 수 없습니다.** 기록을 복원하거나 강사에게 확인하고, 무조건 새 Job을 제출하지 않습니다.

목차에서 **02-B, 04-C, 05-B, 06-B**처럼 표시된 대기 단계를 찾습니다. 정확한 재개 위치는 [마지막 완료 지점별 안내](troubleshooting.md#기존-실행을-이어가기)를 따릅니다.

## 중간에 그만둘 때

실행 중인 **본인 Job만** **Studio → Jobs → 해당 실행 → Cancel** 후 `Canceled`를 확인합니다. **Instance만 멈추면 Cluster의 Job이나 endpoint까지 멈추는 것은 아닙니다.**

Notebook을 사용 중이면 저장하고 `LAB_ID`·프로젝트 루트를 기록한 뒤, 프로젝트 루트의 Instance Terminal에서:

```bash
source "$HOME/.venvs/aml-mlops-lab/bin/activate" &&
python -m mlops_lab.cli cleanup-runtime --delete-endpoint
```

endpoint를 먼저 삭제하고 Instance를 마지막에 중지하므로 연결이 끊길 수 있습니다. Studio에서 **본인 endpoint 없음 / Instance Stopped / 전용 Cluster 실제 0노드**를 확인합니다. 공유 Cluster는 [개인 종료 기준](troubleshooting.md#공유-학습-클러스터의-정리)을 따르며 다른 사람의 Job을 취소하지 않습니다.

Premium ACR·Private Endpoint·Storage·디스크의 지속 비용은 남습니다. 전체 RG 삭제는 강사와 보관 필요성을 확인한 뒤 [정리 문서](troubleshooting.md#전체-환경이-더-이상-필요하지-않은-경우)를 따릅니다.

공식 참고: [Instance Terminal](https://learn.microsoft.com/azure/machine-learning/how-to-access-terminal?view=azureml-api-2), [Notebook 실행·kernel·상태 보존](https://learn.microsoft.com/azure/machine-learning/how-to-run-jupyter-notebooks?view=azureml-api-2).
