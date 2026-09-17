# 문제 해결과 비용 정리

학습자는 먼저 [기다릴지 고칠지 판단표](learner-start.md#기다릴지-고칠지-판단하기)를 사용합니다. **03의 품질 게이트 실패 외의 오류를 정상으로 넘기지 않습니다.** 아래 기술 진단은 그 다음에 확인합니다.

**처음부터 읽거나 명령을 모두 실행하지 않습니다.** 현재 상황에 해당하는 곳만 엽니다.

| 현재 상황 | 이동할 곳 |
|---|---|
| 파일·kernel·로그인 준비에서 막힘 | [준비 단계](#준비-단계에서-막혔다면) |
| 브라우저·Terminal·kernel을 다시 연결함 | [기존 실행 이어가기](#기존-실행을-이어가기) |
| 실행이 실패했거나 오래 기다리고 있음 | [증상별 확인](#증상별-확인-순서) |
| 중간에 그만두거나 실습이 끝남 | [본인 리소스 정리](#리소스-정리) |
| 강사가 전체 환경을 폐기함 | [전용 RG 삭제](#전체-환경이-더-이상-필요하지-않은-경우) |

## 준비 단계에서 막혔다면

| 보이는 오류 | 돌아갈 위치 |
|---|---|
| ZIP·`pyproject.toml`·Notebook 파일을 찾지 못함 | [준비 B](learner-start.md#준비-b--최신-프로젝트를-별도-폴더에-풀기): 업로드한 본인 폴더와 프로젝트 루트 확인 |
| `config.json` 없음 / `Replace every placeholder` | [준비 C](learner-start.md#준비-c--설정-파일-준비): 예제 복사, 8개 값 확인·저장 |
| Python 버전 오류 / `ModuleNotFoundError` | [준비 D](learner-start.md#준비-d--python-312-kernel-준비): 설치 성공 후 Python 3.12 kernel 선택 |
| `Azure identity/subscription mismatch` / 인증 오류 | [준비 E](learner-start.md#준비-e--cli-로그인과-준비-완료-확인): 본인 계정·tenant·구독 확인 |
| Notebook에서 `NameError` | 00을 실행하지 않았다면 00부터. 진행 중 변수가 사라졌다면 아래 [이어가기](#기존-실행을-이어가기)에서 기존 `LAB_ID` 복원 |

직접 해결되지 않으면 **단계 번호, 오류 메시지, `LAB_ID`, 해당 Job URL**을 강사에게 전달합니다. `config.json` 전체나 토큰·키를 공유할 필요는 없습니다.

## 기존 실행을 이어가기

**새 Job이나 배포를 만드는 것이 아니라, 기존 실행을 조회하고 기다리는 것이 먼저입니다.**

먼저 본인 Instance가 `Running`인지 확인하고 **기존 프로젝트 폴더**를 엽니다. CLI 인증이 만료됐다면 기존 프로젝트 루트의 Instance Terminal에서 `source "$HOME/.venvs/aml-mlops-lab/bin/activate"`로 환경을 활성화한 뒤 [준비 E](learner-start.md#준비-e--cli-로그인과-준비-완료-확인)를 다시 수행합니다.

Notebook에서 kernel/Compute를 바꿨다면 00의 `RESUME_LAB_ID`에 기록한 `LAB_ID`를 넣고 **00만 재실행**합니다. 이전 프로젝트의 `artifacts/runs/`가 있어야 하며, 이후 위치는 다음과 같습니다.

| 마지막으로 완료한 일 | 이어갈 셀 |
|---|---|
| 02 Job 제출 | **02-B · 대기·결과 확인** |
| 03 Job 제출 | 03-A 대기 → 실패 원인 확인 → 03-B 등록 차단 |
| 04 blue 배포 제출 | **04-C · blue 배포 대기** |
| 05 재학습 제출 | **05-B · 대기·비교** |
| 06 green 배포 제출 | **06-B · green 대기·직접 호출** |
| green traffic 전환 요청 | **06-D · green 기본 응답 확인** |
| blue 롤백 요청 | **06-F · blue 기본 응답 확인** |

Notebook 목차에서 위 번호를 선택합니다. **제출·traffic 요청부터 반복하지 않습니다.** 브라우저만 다시 연결했고 같은 kernel의 변수가 남아 있다면 00을 반복할 필요 없이 해당 대기/확인 셀부터 이어갑니다.

Terminal을 다시 열었다면 기존 프로젝트 루트로 `cd`합니다. **`LAB_ID="기록한 기존 값"`을 먼저 설정한 뒤** [CLI 준비 블록](lab-guide.md#준비--실행명-한-번-정하기)을 실행해 환경과 모든 실행명·모델 버전 변수를 복원합니다.

아래는 **02의 baseline 조회 예시**입니다. 03을 확인하려면 `$BASELINE_RUN`을 `$BAD_RUN`으로, 05라면 `$RETRAIN_RUN`으로 바꿉니다.

```bash
: "${BASELINE_RUN:?CLI 준비 블록에서 기존 LAB_ID와 실행명을 먼저 복원하세요.}" &&
python -m mlops_lab.cli inspect --run "$BASELINE_RUN"
```

조회 결과가 `Queued`/`Running`이면 **대기 명령만** 실행합니다.

```bash
python -m mlops_lab.cli wait --run "$BASELINE_RUN"
```

`Completed`를 확인했으면 보고서를 읽습니다.

```bash
python -m mlops_lab.cli report --run "$BASELINE_RUN"
```

03의 `Failed`라면 [03-A의 실패 원인 확인](lab-guide.md#03-a--의도된-오류-12)으로 돌아갑니다. 다른 실패는 원인 해결 전 다음 단계로 넘어가지 않습니다.

배포가 `Submitted`/`Creating`이면 새로 배포하지 않고 기다립니다. 대상이 green이면 `blue`를 `green`으로 바꿉니다.

```bash
python -m mlops_lab.cli wait-deployment --deployment blue
```

**Job URL은 새 탭에서 확인합니다.** Notebook의 실행 중 탭을 다른 Workspace 메뉴로 전환하거나 kernel을 바꾸면 셀 실행/변수 상태에 영향을 줄 수 있습니다. [공식 Notebook 동작](https://learn.microsoft.com/azure/machine-learning/how-to-run-jupyter-notebooks?view=azureml-api-2#change-the-notebook-environment)을 참고합니다.

## 증상별 확인 순서

### 학습자가 먼저 확인할 증상

| 증상 | 먼저 확인할 것 | 이 실습의 대응 |
|---|---|---|
| 다른 계정/구독에 접근 | [준비 E](learner-start.md#준비-e--cli-로그인과-준비-완료-확인)의 계정·tenant·구독 | 올바른 계정으로 로그인. 전역 default 변경이나 다른 계정의 `az logout`은 하지 않음 |
| Instance는 보이지만 Terminal에 연결 불가 | Instance의 상태와 **할당 사용자** | 본인 Instance를 Start. 다른 사용자에게 할당됐으면 강사에게 확인 |
| `Queued` / `Running`, 새 출력 없음 | Studio의 해당 Job 상태 | 같은 상태에서는 출력이 추가되지 않을 수 있음. 재제출하지 말고 대기. 계속 Queued면 강사가 쿼터·가용량 확인 |
| 부모 Job Metrics가 비어 있음 | `evaluate_gate` 자식 Job 선택 여부 | 자식의 Metrics / Outputs + logs 확인 |
| `QUALITY_GATE_FAILED` | 실습 단계, 실측 RMSE와 alpha | 03-A의 네 조건을 만족할 때만 의도된 실패. 02/05라면 멈춤 |
| `Run label ... already exists` | 로컬 `artifacts/runs` 실행 기록 | 이어가기라면 기존 실행 조회·대기. 완전히 새 실습일 때만 새 `LAB_ID` 사용. 기록 삭제/덮어쓰기 금지 |
| Model version이 다른 Job에 속함 | 이미 등록된 같은 모델 버전 | 새 버전 사용. 동일 버전을 새 모델로 위장하지 않음 |
| endpoint `invoke` 401/403 | 로그인 계정·tenant와 endpoint 이름 | 준비 E로 계정을 확인. 여전히 실패하면 강사가 `aad_token` 호출 권한 확인 |
| 직접 green 호출만 정상 | endpoint의 traffic 분배 | green 직접 호출과 기본 경로 호출을 따로 검증 |

`wait`와 `wait-deployment`의 기본 대기 제한은 **40분**입니다. timeout은 Job/배포의 취소나 실패를 뜻하지 않습니다. 같은 대상의 **대기 명령만** 다시 실행합니다. 무조건 다시 제출하면 중복 작업과 추가 과금이 생깁니다.

### 강사가 확인할 권한·네트워크·환경 오류

학습자는 아래 설정을 임의로 바꾸지 않고 오류와 실행 정보를 전달합니다. **역할 추가와 네트워크 연결은 별개**이며, 방화벽이나 공유 키를 켜서 해결하지 않습니다.

| 증상 | 먼저 확인할 것 | 이 실습의 대응 |
|---|---|---|
| Azure MCP는 403인데 CLI는 성공 | 두 도구가 실제로 같은 principal인지 | MCP의 다른 캐시 계정 권한을 확대하지 않고 검증된 CLI 사용 |
| `Please specify only one of subscription and tenant` | AzureCliCredential 초기화 | subscription만 지정하고 tenant는 사전에 검증 |
| Graph `InteractionRequired` | 브라우저/CLI/Graph의 서로 다른 토큰·정책 | 필요한 계정의 대화형 인증을 갱신. 다른 계정까지 `az logout`하지 않음 |
| `KeyBasedAuthenticationNotPermitted` | Workspace의 system datastore auth mode | identity 모드와 최소 Storage 역할 사용 |
| Blob/File `AuthorizationFailure` | DNS, Private Endpoint, Storage firewall, 해당 ID의 데이터 역할 | private 경로가 구성된 Compute Instance/runner에서 실행. 키를 켜서 해결하지 않음 |
| 데이터 업로드는 되지만 학습 입력을 못 읽음 | **실행 Compute의 관리 ID**와 blob 역할 | 제어용 사용자 역할만으로 학습 ID에 권한이 생기지 않음 |
| Notebook 파일 공유를 못 마운트함 | UAMI와 File Data Privileged Contributor | keyless Compute Instance 요구사항과 file Private Endpoint/DNS 확인 |
| `Resizing`, 실제 노드 0, allocationErrors 없음 | RG Activity log의 `publicIPAddresses/write` 실패 | 과거 실행에서 Public IP feature 오류가 있었음. 같은 원인인지 로그로 확인하고 no-public-IP 구성 점검 |
| Endpoint 생성 실패 | deployment 상태, container/storage initializer 로그, ACR/Storage 네트워크 | 실제 오류를 고친 뒤 같은 deployment 재시도 |
| `ImageBuildFailure`, build log에 시작 문구만 존재 | Workspace Private Link와 image_build_compute | private Storage에 접근 가능한 `cpu-private-only`를 빌드 Compute로 지정 |
| 이미지 pull은 성공하지만 model download가 403 | inference의 outbound 네트워크 | 학습용 VNet만으로 해결되지 않음. Workspace managed network와 Storage outbound Private Endpoint 필요 |
| managed network 설정 시 ACR Premium 요구 오류 | 실제 ACR SKU와 Workspace 연결 | 새 환경에서는 Premium ACR을 먼저 만들고 연결. 기존 리소스 업그레이드 후 제어 평면 반영 지연에 유의 |
| 초기 배포가 `unrecoverable state`라고 표시됨 | 초기 provisioning 자체가 실패했는지 | 로그 확인·원인 수정 후 **실패한 deployment만** 삭제하고 재생성. 정상 서비스나 Models의 모델을 삭제하지 않음 |
| `No package metadata was found for mlflow` | curated image가 full MLflow 대신 `mlflow-skinny`를 제공하는지 | import 가능한 모듈 버전인 `mlflow.__version__` 기록 |
| MLflow `/logged-models` API 404 | curated image의 MLflow 3와 Azure ML 추적 API의 지원 범위 | 모델을 MLflow 형식으로 save한 뒤 run artifact로 기록. 최종 component v3 사용 |

실패한 Python 단계의 stdout/traceback은 private 네트워크에서 `python -m mlops_lab.cli logs --run "<실행명>"`으로 조회할 수 있습니다. Python이 시작되기도 전에 실패했다면 user log가 없을 수 있으므로 Studio의 system logs와 RG Activity log를 확인합니다.

초기 생성이 실패한 `blue`를 다시 만들라는 오류가 나오면, 강사가 endpoint 트래픽이 해당 배포를 사용하지 않고 있는지 확인한 뒤 아래처럼 **그 배포만** 삭제합니다. 이번 실습의 endpoint와 실패한 배포인지 확인하고 삭제 프롬프트에 직접 응답합니다.

먼저 [상태 확인 명령](#상태를-확인하는-명령)의 첫 블록으로 `SUB`·`RG`·`WS`·`ENDPOINT`를 읽습니다.

```bash
: "${SUB:?상태 확인 변수를 먼저 읽으세요.}" "${RG:?상태 확인 변수를 먼저 읽으세요.}" \
  "${WS:?상태 확인 변수를 먼저 읽으세요.}" "${ENDPOINT:?상태 확인 변수를 먼저 읽으세요.}" &&
az ml online-deployment delete --name blue --endpoint-name "$ENDPOINT" \
  -g "$RG" -w "$WS" --subscription "$SUB"
```

실패한 단계에서는 named output 업로드가 완료되지 않을 수 있습니다. 평가 코드는 예외 발생 **전에** `evaluation.json`을 MLflow run artifact로 기록하며, `report` 명령도 이 영속 artifact를 읽습니다. 성공한 Job의 named output이 보인다는 사실만으로 실패 경로까지 검증되었다고 판단하지 않습니다.

## 상태를 확인하는 명령

프로젝트 루트에서 활성화된 Python 환경과 Azure CLI의 `ml` v2 extension을 사용합니다. 학습자는 기존 Instance Terminal, 강사는 [환경 준비](setup.md#1-관리-pc와-계정-설정)의 관리 PC를 사용합니다. **먼저 아래 블록으로 로그인과 대상을 확인**합니다. 리소스 생성 명령을 다시 실행할 필요는 없습니다.

```bash
python -c 'from mlops_lab.config import Settings; Settings.load().verify_account()' &&
SUB=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().subscription_id)') &&
RG=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().resource_group)') &&
WS=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().workspace)') &&
CLUSTER=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().compute_cluster)') &&
ENDPOINT=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().endpoint_name)') &&
printf '조회 대상: %s / %s / %s\n' "$SUB" "$RG" "$WS"
```

**Compute 상태가 필요할 때:**

```bash
az ml compute list -g "$RG" -w "$WS" --subscription "$SUB" \
  --query "[].{name:name,type:type,state:state}" -o table
```

**Job 오류가 필요할 때:** `<JOB_NAME>`을 `artifacts/runs/<실행명>.json`의 **`job_name` 값**으로 바꿉니다. `baseline-...` 같은 실습 실행명이나 `LAB_ID`가 아닙니다.

```bash
az ml job show --name "<JOB_NAME>" -g "$RG" -w "$WS" --subscription "$SUB" \
  --query '{name:name,status:status,error:error}'
```

**배포 로그가 필요할 때:** 실패한 대상이 green이면 `blue`를 `green`으로 바꿉니다.

```bash
az ml online-deployment get-logs --name blue --endpoint "$ENDPOINT" \
  -g "$RG" -w "$WS" --subscription "$SUB" --lines 100
```

CLI의 간략 표시에서 클러스터 노드 수가 `null`이면 0으로 해석하지 말고 ARM의 runtime property를 확인합니다.

```bash
az rest --method get --subscription "$SUB" \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.MachineLearningServices/workspaces/$WS/computes/$CLUSTER?api-version=2024-04-01" \
  --query 'properties.properties.{current:currentNodeCount,target:targetNodeCount,allocation:allocationState,errors:allocationErrors}'
```

**network=Disabled와 keyless는 독립적인 제어입니다.** 로그인이나 RBAC 추가만으로 firewall을 통과할 수 없습니다. 반대로 네트워크가 연결되어 있어도 올바른 ID와 데이터 평면 권한이 필요합니다.

## 공유 학습 클러스터의 정리

07의 **Cluster 실제 0노드**는 전용 실습 환경의 완료 기준입니다. 학습 Cluster를 공유하면 다른 학습자의 Job이나 이미지 빌드 때문에 노드가 남을 수 있습니다. **0노드를 만들려고 다른 사람의 Job을 취소하거나 Cluster를 삭제·강제 축소하지 않습니다.**

공유 환경에서 개인의 종료 기준은 **본인 실행 중 Job 없음 / 본인 endpoint 없음 / 본인 Instance Stopped**입니다. 공유 Cluster 상태는 강사에게 알리고, 모든 학습자의 작업이 끝난 뒤 강사가 실제 0노드와 잔존 비용을 확인합니다. 현재 구성과 과금 단위는 [인프라 안내](infrastructure.md#비용과-정리에서-헷갈리지-않기)를 참고합니다.

## 리소스 정리

**먼저:** 실행 중인 본인 Job이 있다면 **Studio → Jobs → 해당 실행 → Cancel** 후 `Canceled`를 확인합니다. Notebook과 `LAB_ID`·프로젝트 루트를 저장합니다. Instance만 중지해도 Job과 endpoint가 함께 끝나는 것은 아닙니다.

**순서:** 본인 endpoint 삭제 → Instance 중지 → 전용 Cluster 0노드 확인. 공유 Cluster는 [개인 종료 기준](#공유-학습-클러스터의-정리)을 따릅니다. 강사가 임시 runner를 만들었다면 추가로 실행 기록 회수 → runner 삭제를 수행합니다.

**학습자 — 프로젝트 루트의 Instance Terminal에서 실행:** `config.json`의 `endpoint_name`·`compute_instance`가 본인 것인지 확인합니다.

```bash
source "$HOME/.venvs/aml-mlops-lab/bin/activate" &&
python -m mlops_lab.cli cleanup-runtime --delete-endpoint
```

**강사 — Instance 대신 private runner를 사용했을 때만 관리 PC에서 실행:**

```bash
python -m scripts.remote_runner run cleanup-runtime --delete-endpoint &&
python -m scripts.remote_runner collect
```

위 두 실행 경로 중 하나를 선택합니다. Compute Instance 자신을 중지하면 터미널/Notebook 연결이 끊길 수 있습니다. Studio에서 최종 상태를 확인합니다.

**이 아래 VM/RG 삭제 명령은 강사용입니다.** 먼저 [상태 확인 블록](#상태를-확인하는-명령)으로 `SUB`·`RG`를 읽습니다. runner를 만들지 않았다면 VM 삭제는 건너뜁니다.

runner VM은 학습 데이터나 모델의 원본 저장소가 아닙니다. 기록을 회수한 뒤 **아래 조회만 먼저 실행**합니다.

```bash
: "${SUB:?상태 확인 변수를 먼저 읽으세요.}" "${RG:?상태 확인 변수를 먼저 읽으세요.}" &&
az vm show --name vm-aml-lab-runner -g "$RG" --subscription "$SUB" \
  --query '{id:id,tags:tags,osDisk:storageProfile.osDisk.name}' -o json
```

출력의 RG·VM 이름과 `purpose=aml-mlops-hands-on`, `lifecycle=temporary-private-orchestrator` 태그를 확인합니다. **이번 실습의 임시 VM이 맞을 때만** 다음 블록을 실행하고 삭제 프롬프트에 직접 응답합니다.

```bash
: "${SUB:?상태 확인 변수를 먼저 읽으세요.}" "${RG:?상태 확인 변수를 먼저 읽으세요.}" &&
az vm delete --name vm-aml-lab-runner -g "$RG" --subscription "$SUB"
```

템플릿은 runner의 OS disk / NIC를 `deleteOption: Delete`로 설정합니다. 삭제 후 RG 목록에서 해당 디스크/NIC가 남지 않았는지도 확인합니다. NSG, VNet, DNS, Private Endpoint는 이 명령으로 삭제되지 않습니다. 생성한 임시 SSH 개인 키·공개 키도 **자신이 이번 실습에서 만든 구체적인 파일만** 삭제합니다.

### 전체 환경이 더 이상 필요하지 않은 경우

**강사만 수행합니다.** Workspace의 Job 이력·모델·데이터·Notebook까지 더 이상 필요하지 않고, RG 안의 다른 학습자·다른 Workspace도 모두 종료했을 때만 전용 RG 전체를 삭제합니다. 복구를 보장할 수 없는 파괴적 작업이므로 자동 실행 흐름에는 포함하지 않았습니다. [상태 확인 블록](#상태를-확인하는-명령)으로 `SUB`·`RG`를 읽은 뒤 아래 조회만 먼저 실행합니다.

```bash
: "${SUB:?상태 확인 변수를 먼저 읽으세요.}" "${RG:?상태 확인 변수를 먼저 읽으세요.}" &&
az resource list -g "$RG" --subscription "$SUB" \
  --query '[].{name:name,type:type}' -o table
```

출력된 리소스가 **모두 폐기 대상**이고 보관할 기록을 회수했을 때만 실행합니다. 확인 프롬프트에 직접 응답합니다.

```bash
: "${SUB:?상태 확인 변수를 먼저 읽으세요.}" "${RG:?상태 확인 변수를 먼저 읽으세요.}" &&
az group delete --name "$RG" --subscription "$SUB"
```

Private Endpoint, Storage, 디스크, 로그, Container Registry에는 지속 비용이 발생할 수 있습니다. “VM을 Stopped로 바꿨으므로 Azure 비용이 완전히 0”이라고 해석하지 않습니다.

특히 이 구성의 **Premium ACR은 East US 2 공개 종량제 표시 가격 기준 약 USD 1.6666/일**입니다(2026-09-16 조회, 계약 할인·추가 Storage·Private Endpoint 별도). 실습을 보관하지 않을 경우 전용 RG 삭제가 지속 비용을 끝내는 가장 명확한 방법입니다. 가격 출처: [Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices), [Container Registry 요금](https://azure.microsoft.com/pricing/details/container-registry/).

## 실행 증빙 읽는 법

| 경로 | 내용 |
|---|---|
| `artifacts/runs/<label>.json` | Job ID, 입력, 환경, 코드 해시, 상태, 자식 Job, 평가 결과 |
| `artifacts/models/v<version>.json` | 등록 모델과 원본 Job, 실측 평가 |
| `artifacts/inference/*.json` | 입력 행 수, 응답 배열, 직접/기본 경로 구분, 호출 시각 |
| `artifacts/traffic/*.json` | blue/green 전환 설정값과 시각 |
| `artifacts/cleanup.json` | endpoint/Instance 확인 결과 |
| `docs/execution-report.md` | 2026-09-16 당시 Azure 실행에서 확인한 내용과 확인하지 않은 내용 |

Run Command 바깥쪽의 `Provisioning succeeded`는 내부 Python 실행의 성공 증거가 아닙니다. 제공 헬퍼는 내부 종료 코드를 검사하며 비정상 종료를 성공으로 처리하지 않습니다.
