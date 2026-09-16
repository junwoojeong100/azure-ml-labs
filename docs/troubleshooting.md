# 문제 해결과 비용 정리

## 증상별 확인 순서

| 증상 | 먼저 확인할 것 | 이 실습의 대응 |
|---|---|---|
| 다른 계정/구독에 접근 | CLI `account show --subscription ...`의 UPN·tenant·구독 | 전역 default를 바꾸지 않고 구독 지정, SDK 계정 검사 |
| Azure MCP는 403인데 CLI는 성공 | 두 도구가 실제로 같은 principal인지 | MCP의 다른 캐시 계정 권한을 확대하지 않고 검증된 CLI 사용 |
| `Please specify only one of subscription and tenant` | AzureCliCredential 초기화 | subscription만 지정하고 tenant는 사전에 검증 |
| Graph `InteractionRequired` | 브라우저/CLI/Graph의 서로 다른 토큰·정책 | 필요한 계정의 대화형 인증을 갱신. 다른 계정까지 `az logout`하지 않음 |
| `KeyBasedAuthenticationNotPermitted` | Workspace의 system datastore auth mode | identity 모드와 최소 Storage 역할 사용 |
| Blob/File `AuthorizationFailure` | DNS, Private Endpoint, Storage firewall, 해당 ID의 데이터 역할 | private 경로가 구성된 Compute Instance/runner에서 실행. 키를 켜서 해결하지 않음 |
| 데이터 업로드는 되지만 학습 입력을 못 읽음 | **실행 Compute의 관리 ID**와 blob 역할 | 제어용 사용자 역할만으로 학습 ID에 권한이 생기지 않음 |
| Notebook 파일 공유를 못 마운트함 | UAMI와 File Data Privileged Contributor | keyless CI 요구사항과 file Private Endpoint/DNS 확인 |
| Job이 `Queued`에 머묾 | AML 쿼터, 실제 클러스터 allocation, VM SKU 가용성 | 부족한 원인을 해결한 후 기존 Job을 계속 관찰 |
| `Resizing`, 실제 노드 0, allocationErrors 없음 | RG Activity log의 `publicIPAddresses/write` 실패 | 이 계정에서는 Public IP feature 오류 확인. Workspace Private Endpoint + no-public-IP cluster 사용 |
| 부모 Job Metrics가 비어 있음 | `evaluate_gate` 자식 Job 선택 여부 | 자식의 Metrics / Outputs + logs 확인 |
| `QUALITY_GATE_FAILED` | 실측 RMSE와 alpha | 나쁜 모델 시나리오만 의도된 실패. 네트워크 실패와 구별 |
| `Run label ... already exists` | 로컬 `artifacts/runs` 실행 기록 | 새 run label 사용. 기존 기록 삭제/덮어쓰기 금지 |
| Model version이 다른 Job에 속함 | 이미 등록된 같은 모델 버전 | 새 버전 사용. 동일 버전을 새 모델로 위장하지 않음 |
| endpoint `invoke` 401/403 | `aad_token`용 score 권한과 호출 ID | 토큰 원문/키를 출력하지 않고 역할·tenant 확인 |
| 직접 green 호출만 정상 | endpoint의 traffic 분배 | green 직접 호출과 기본 경로 호출을 따로 검증 |
| Endpoint 생성 실패 | deployment 상태, container/storage initializer 로그, ACR/Storage 네트워크 | 실제 오류를 고친 뒤 같은 deployment 재시도 |
| `ImageBuildFailure`, build log에 시작 문구만 존재 | Workspace Private Link와 image_build_compute | private Storage에 접근 가능한 `cpu-private-only`를 빌드 Compute로 지정 |
| 이미지 pull은 성공하지만 model download가 403 | inference의 outbound 네트워크 | 학습용 VNet만으로 해결되지 않음. Workspace managed network와 Storage outbound Private Endpoint 필요 |
| managed network 설정 시 ACR Premium 요구 오류 | 실제 ACR SKU와 Workspace 연결 | 새 환경에서는 Premium ACR을 먼저 만들고 연결. 기존 리소스 업그레이드 후 제어 평면 반영 지연에 유의 |
| 초기 배포가 `unrecoverable state`라고 표시됨 | 초기 provisioning 자체가 실패했는지 | 로그 확인·원인 수정 후 **실패한 deployment만** 삭제하고 재생성. 정상 서비스나 Registry 모델을 삭제하지 않음 |
| kernel에서 import 실패 | kernel Python과 패키지 설치 환경 | Python 3.12 전용 kernel 선택. 실행은 프로젝트 루트에서 `python -m ...` |
| `No package metadata was found for mlflow` | curated image가 full MLflow 대신 `mlflow-skinny`를 제공하는지 | import 가능한 모듈 버전인 `mlflow.__version__` 기록 |
| MLflow `/logged-models` API 404 | curated image의 MLflow 3와 Azure ML 추적 API의 지원 범위 | 모델을 MLflow 형식으로 save한 뒤 run artifact로 기록. 최종 component v3 사용 |

`wait`가 timeout이면 Job이 자동 취소된 것은 아닙니다. 같은 run label로 다시 `wait`합니다. 무조건 다시 제출하면 중복 학습과 추가 과금이 생깁니다.

실패한 Python 단계의 stdout/traceback은 private 네트워크에서 `python -m mlops_lab.cli logs --run "<실행명>"`으로 조회할 수 있습니다. Python이 시작되기도 전에 실패했다면 user log가 없을 수 있으므로 Studio의 system logs와 RG Activity log를 확인합니다.

초기 생성이 실패한 `blue`를 다시 만들라는 오류가 나오면, endpoint 트래픽이 해당 배포를 사용하지 않고 있는지 확인한 뒤 아래처럼 **그 배포만** 삭제합니다. `--yes`를 사용하기 전에 반드시 이번 실습의 endpoint와 배포인지 확인합니다.

```bash
az ml online-deployment delete --name blue --endpoint-name "<실습 ENDPOINT_NAME>" \
  -g "$RG" -w "$WS" --subscription "$SUB" --yes
```

실패한 단계에서는 named output 업로드가 완료되지 않을 수 있습니다. 평가 코드는 예외 발생 **전에** `evaluation.json`을 MLflow run artifact로 기록하며, `report` 명령도 이 영속 artifact를 읽습니다. 성공한 Job의 named output이 보인다는 사실만으로 실패 경로까지 검증되었다고 판단하지 않습니다.

## 상태를 확인하는 명령

먼저 [환경 준비](setup.md)의 `SUB`, `RG`, `WS` 변수를 설정합니다. 아래 명령은 관리 PC에서도 사용할 수 있는 관리 평면 조회입니다.

```bash
az ml compute list -g "$RG" -w "$WS" --subscription "$SUB" \
  --query "[].{name:name,type:type,state:state}" -o table

az ml job show --name "<JOB_NAME>" -g "$RG" -w "$WS" --subscription "$SUB" \
  --query '{name:name,status:status,error:error}'

az ml online-deployment get-logs --name blue --endpoint "<ENDPOINT_NAME>" \
  -g "$RG" -w "$WS" --subscription "$SUB" --lines 100
```

CLI의 간략 표시에서 클러스터 노드 수가 `null`이면 0으로 해석하지 말고 ARM의 runtime property를 확인합니다.

```bash
az rest --method get --subscription "$SUB" \
  --url "https://management.azure.com/subscriptions/$SUB/resourceGroups/$RG/providers/Microsoft.MachineLearningServices/workspaces/$WS/computes/cpu-private-only?api-version=2024-04-01" \
  --query 'properties.properties.{current:currentNodeCount,target:targetNodeCount,allocation:allocationState,errors:allocationErrors}'
```

**network=Disabled와 keyless는 독립적인 제어입니다.** 로그인이나 RBAC 추가만으로 firewall을 통과할 수 없습니다. 반대로 네트워크가 연결되어 있어도 올바른 ID와 데이터 평면 권한이 필요합니다.

## 리소스 정리

**순서:** endpoint 삭제 → Instance 중지 → Cluster 0노드 확인 → 실행 기록 회수 → 임시 runner 삭제.

```bash
# private VNet 안에서 실행합니다. endpoint를 먼저 삭제하고 Instance를 마지막에 중지합니다.
python -m mlops_lab.cli cleanup-runtime --delete-endpoint

# runner를 사용했다면 관리 PC에서 이 경로를 이용합니다.
python -m scripts.remote_runner run cleanup-runtime --delete-endpoint
python -m scripts.remote_runner collect
```

위 두 실행 경로 중 하나를 선택합니다. Compute Instance 자신을 중지하면 터미널/Notebook 연결이 끊길 수 있습니다. Studio에서 최종 상태를 확인합니다.

runner VM은 학습 데이터나 모델의 원본 저장소가 아닙니다. 기록을 회수한 뒤, **이번 실습의 VM 이름과 RG인지 확인한 후** 삭제합니다.

```bash
az vm show --name vm-aml-lab-runner -g "$RG" --subscription "$SUB" \
  --query '{id:id,tags:tags,osDisk:storageProfile.osDisk.name}' -o json

az vm delete --name vm-aml-lab-runner -g "$RG" --subscription "$SUB" --yes
```

템플릿은 runner의 OS disk / NIC를 `deleteOption: Delete`로 설정합니다. 삭제 후 RG 목록에서 해당 디스크/NIC가 남지 않았는지도 확인합니다. NSG, VNet, DNS, Private Endpoint는 이 명령으로 삭제되지 않습니다. 생성한 임시 SSH 개인 키·공개 키도 **자신이 이번 실습에서 만든 구체적인 파일만** 삭제합니다.

### 전체 환경이 더 이상 필요하지 않은 경우

Workspace의 Job 이력·모델·데이터·Notebook까지 더 이상 필요하지 않을 때만 전용 RG 전체를 삭제합니다. 복구를 보장할 수 없는 파괴적 작업이므로 자동 실행 흐름에는 포함하지 않았습니다.

```bash
az resource list -g "$RG" --subscription "$SUB" \
  --query '[].{name:name,type:type}' -o table

# 이름과 내용을 확인하고, 확인 프롬프트에 직접 응답합니다.
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
| `docs/execution-report.md` | 이번 실행에서 확인한 내용과 확인하지 않은 내용 |

Run Command 바깥쪽의 `Provisioning succeeded`는 내부 Python 실행의 성공 증거가 아닙니다. 제공 헬퍼는 내부 종료 코드를 검사하며 비정상 종료를 성공으로 처리하지 않습니다.
