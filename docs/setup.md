# 환경 준비: 강사용 / 새 Workspace용

**학습자는 [학습자 시작 안내](learner-start.md)로 이동합니다.** 이 문서의 Azure 생성·권한·네트워크 작업은 새 실습 환경을 준비하는 강사용입니다.

구성의 역할·VM 사양·다른 Compute/Endpoint 선택지는 [학습·추론 인프라 안내](infrastructure.md)에 있습니다. 이 문서는 그중 **현재 실습의 기본 구성**만 준비합니다.

최종 구성은 **Workspace managed network + keyless Storage**입니다. 학습 Compute와 Managed Online Endpoint가 각각 Storage에 접근할 수 있도록 Azure ML이 필요한 outbound Private Endpoint를 관리합니다. 사용자가 만든 VNet에 학습 클러스터만 넣는 것으로는 Online Endpoint의 Storage 접근까지 해결되지 않습니다.

**필수 경로는 1–4 → 학습자에게 전달입니다.** 아래 명령은 새 환경과 학습자 1명의 Instance를 준비합니다. 기존 환경이 있다면 생성 명령을 다시 실행하지 말고 학습자의 접근부터 확인합니다. runner와 기존 Workspace 전환은 마지막의 **선택 작업**입니다.

| 단계 | 하는 일 | 다음으로 가는 기준 |
|---|---|---|
| 1 | 관리 PC·설정·강사 로그인 준비 | 의도한 계정·구독·새 RG/Workspace 이름 확인 |
| 2 | 새 Workspace와 종속 리소스 생성 | 생성 성공, Storage의 공유 키·공개 접근 비활성화 |
| 3 | 학습자와 Compute의 역할 할당 | 학습자 Workspace 역할과 두 Storage 역할 할당 성공 |
| 4 | 네트워크·Compute 생성 | Instance가 해당 학습자에게 할당되고 학습 Cluster 준비 완료 |

## 1. 관리 PC와 계정 설정

**실행 위치:** 관리 PC의 **Bash**, 현재 가이드와 같은 브랜치의 전체 프로젝트 루트입니다. 학습자 Instance Terminal이 아닙니다. 필요한 도구는 Azure CLI, `ml` v2 extension, Python 3.12입니다.

```bash
az version &&
az extension show --name ml &&
python3.12 --version
```

`ml` extension만 없다면 `az extension add --name ml`로 설치하고 위 확인을 다시 수행합니다. **블록 하나 실행 → 결과 확인 → 다음 블록** 순서로 진행하며, 오류가 나면 다음 블록을 실행하지 않습니다. `&&`는 앞 명령이 실패했을 때 같은 블록의 후속 작업을 막습니다.

```bash
python3.12 -m venv .venv &&
source .venv/bin/activate &&
python -m pip install -r requirements-lock.txt &&
python -m pip install --no-deps -e . &&
if [ ! -f config.json ]; then
  cp config.example.json config.json
fi
```

기존 `config.json`은 덮어쓰지 않습니다. 파일을 열어 모든 `<...>`를 바꾸고, **새 RG/Workspace 이름**, 사용할 리전, 학습자 전용 `compute_instance`와 **리전 내 고유한 `endpoint_name`**, 학습 Cluster 이름을 저장합니다. 계정별 설정 파일은 Git 추적에서 제외합니다.

**이 문서의 `expected_account`는 리소스를 만드는 강사 계정**입니다. 3단계의 `USER_OBJECT_ID`는 Instance를 사용할 학습자의 ID로, 강사와 다를 수 있습니다. 학습자가 실행할 때는 [준비 C](learner-start.md#준비-c--설정-파일-준비)에서 자신의 계정으로 별도 설정합니다.

```bash
SUB=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().subscription_id)') &&
TENANT=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().tenant_id)') &&
RG=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().resource_group)') &&
WS=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().workspace)') &&
LOCATION=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().location)') &&
CLUSTER=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().compute_cluster)')
```

같은 Bash에서 해당 tenant의 강사 계정으로 로그인하고 설정과 대조합니다.

```bash
az login --tenant "$TENANT" &&
python - <<'PY'
from mlops_lab.config import Settings
settings = Settings.load()
settings.verify_account()
print("계정 확인:", settings.expected_account, settings.subscription_id)
print("생성 대상:", settings.resource_group, "/", settings.workspace)
print("학습자 Instance:", settings.compute_instance)
PY
```

코드는 UPN·tenant·구독을 검사하고 `AzureCliCredential(subscription=...)`을 사용합니다. 전역 기본 구독을 바꿀 필요가 없습니다. 현재 CLI에서는 `tenant`와 `subscription`을 자격 증명에 동시에 전달하면 충돌하므로 tenant는 사전 검사로 확인합니다.

**생성 전 확인:** 강사는 리소스 생성·역할 할당·필요한 리소스 공급자 등록 권한과 비용 승인을 확보합니다. 공급자 등록 권한이 없으면 구독 관리자에게 사전 등록을 요청합니다. Azure portal의 Quotas 또는 기존 Workspace의 **Manage → Quota**에서 해당 리전의 Azure ML 쿼터를 확인합니다. 일반 VM 쿼터와 AML Compute 쿼터는 별도입니다. DS3_v2의 4코어 기준 학습 최대 2노드, Instance 1대, blue/green 각각 1대와 배포 업그레이드 예약 여유를 고려합니다.

**완료 조건:** 출력된 계정·구독·생성 대상이 의도한 값입니다. 이후 1–4는 같은 Bash에서 수행합니다. 다시 연결했다면 설정 변수와 로그인부터 복원하고 이미 생성한 리소스를 조회합니다.

## 2. 새 리소스 그룹과 managed-network Workspace

**할 일:** 존재하지 않는 새 RG에만 생성합니다. RG가 이미 있거나 존재 확인에 실패하면 아래 블록은 생성 전에 중단합니다. 기존 환경을 지우거나 재사용해서 우회하지 않습니다.

```bash
: "${SUB:?1단계 설정 필요}" "${RG:?1단계 설정 필요}" \
  "${WS:?1단계 설정 필요}" "${LOCATION:?1단계 설정 필요}" &&
RG_EXISTS=$(az group exists --name "$RG" --subscription "$SUB" -o tsv) &&
if [ "$RG_EXISTS" != "false" ]; then
  printf '새 RG만 생성합니다. 존재 확인 결과: %s. 이름과 권한을 확인하세요.\n' "$RG_EXISTS" >&2
  false
fi &&
(
  for PROVIDER in Microsoft.MachineLearningServices Microsoft.Network \
    Microsoft.Compute Microsoft.ManagedIdentity Microsoft.Storage Microsoft.KeyVault \
    Microsoft.ContainerRegistry Microsoft.Insights Microsoft.OperationalInsights; do
    az provider register --namespace "$PROVIDER" --subscription "$SUB" --wait || exit "$?"
  done
) &&
az group create --name "$RG" --location "$LOCATION" --subscription "$SUB" \
  --tags purpose=aml-mlops-hands-on environment=lab &&
ACR_NAME=$(python -c 'import hashlib; from mlops_lab.config import Settings; print("acrml" + hashlib.sha256(Settings.load().workspace_id().encode()).hexdigest()[:18])') &&
az acr create --name "$ACR_NAME" -g "$RG" --location "$LOCATION" \
  --sku Premium --subscription "$SUB" &&
ACR_ID=$(az acr show --name "$ACR_NAME" -g "$RG" --subscription "$SUB" --query id -o tsv) &&
az ml workspace create --file infra/workspace.yml --name "$WS" \
  --resource-group "$RG" --location "$LOCATION" --subscription "$SUB" \
  --container-registry "$ACR_ID"
```

Workspace YAML에는 다음 두 설정이 명시되어 있습니다.

```yaml
system_datastores_auth_mode: identity
managed_network:
  isolation_mode: allow_internet_outbound
```

Workspace와 함께 Storage, Key Vault, Application Insights, Log Analytics가 생성되며 앞에서 만든 **Premium ACR(Container Registry: 환경 이미지를 보관하는 저장소)**을 연결합니다. 이 private 연결 구성에 필요한 SKU를 처음부터 선택합니다. Workspace의 public endpoint는 인증된 Studio/관리 API 접속을 위해 유지하며, 이것은 Storage 익명 접근 허용과 다릅니다.

**비용 주의:** Premium ACR의 East US 2 공개 종량제 표시 가격은 2026-09-16 기준 약 **USD 1.6666/일**입니다. VM을 중지해도 이 비용과 Private Endpoint·Storage 등은 남습니다. 실제 요율은 계약에 따라 다르므로 실습 후 RG 보관 여부를 결정합니다.

```bash
WS_ID=$(az ml workspace show --name "$WS" -g "$RG" --subscription "$SUB" \
  --query id -o tsv) &&
STORAGE_ID=$(az ml workspace show --name "$WS" -g "$RG" --subscription "$SUB" \
  --query storage_account -o tsv) &&
STORAGE_NAME="${STORAGE_ID##*/}" &&
az storage account update --name "$STORAGE_NAME" -g "$RG" --subscription "$SUB" \
  --public-network-access Disabled --allow-shared-key-access false \
  --allow-blob-public-access false --bypass AzureServices
```

권한을 가진 Azure 서비스의 trusted-service 예외는 유지합니다. 그러나 **이 예외만으로 Managed Online Endpoint의 private Storage 연결이 해결된다고 가정하지 않습니다.** managed network의 outbound Private Endpoint가 필요합니다.

**완료 조건:** Workspace 생성이 성공했고 Storage의 공개 네트워크·공유 키·익명 Blob 접근이 비활성화됐습니다. 아직 학습자 Terminal이나 endpoint가 없는 것은 정상입니다.

일부 리소스 생성 후 실패했다면 Azure portal에서 생성된 범위를 확인하고 **원인을 해결한 명령부터** 이어갑니다. 2단계를 통째로 반복하면 이미 만들어진 RG를 보호하기 위해 중단됩니다.

## 3. 사용자·Compute 관리 ID의 최소 역할

**할 일:** 학습자 계정과 **UAMI(사용자 할당 관리 ID: Compute가 Azure에 접근할 때 쓰는 ID)**에 각각 필요한 역할을 부여합니다. 둘은 같은 ID가 아닙니다.

| 주체 | 범위와 역할 |
|---|---|
| 강사 | 실습 리소스 생성·역할 할당 권한 |
| 학습자 | Workspace의 AzureML Data Scientist |
| 학습자와 Compute UAMI | 실습 Storage의 Storage Blob Data Contributor / Storage File Data Privileged Contributor |
| 무인 runner의 UAMI | 위 역할 + 해당 Workspace의 AzureML Data Scientist |

`Owner`/`Contributor` 같은 관리 평면 역할이 Storage 데이터 평면 역할을 대신하지 않습니다. 학생에게 구독 Owner를 일괄 부여하지 않습니다.

아래 `USER_OBJECT_ID`의 `<실습 사용자 Object ID>`를 **Azure portal → Microsoft Entra ID → 해당 tenant의 학습자 → Object ID**로 바꿉니다. 로그인 이메일(UPN)이 아닙니다. 강사가 직접 실습할 때만 강사 자신의 Object ID를 넣습니다. 잘못된 형식이면 역할 할당 전에 중단합니다.

```bash
: "${SUB:?1단계 설정 필요}" "${RG:?1단계 설정 필요}" \
  "${LOCATION:?1단계 설정 필요}" "${WS_ID:?2단계 Workspace ID 필요}" \
  "${STORAGE_ID:?2단계 Storage ID 필요}" &&
USER_OBJECT_ID="<실습 사용자 Object ID>" &&
python -c 'import sys; from uuid import UUID; UUID(sys.argv[1])' "$USER_OBJECT_ID" &&
IDENTITY_NAME=id-aml-mlops-compute &&
az identity create --name "$IDENTITY_NAME" -g "$RG" --location "$LOCATION" \
  --subscription "$SUB" --tags purpose=aml-mlops-hands-on &&
MI_ID=$(az identity show --name "$IDENTITY_NAME" -g "$RG" --subscription "$SUB" --query id -o tsv) &&
MI_OBJECT_ID=$(az identity show --name "$IDENTITY_NAME" -g "$RG" --subscription "$SUB" --query principalId -o tsv) &&
az role assignment create --assignee-object-id "$USER_OBJECT_ID" \
  --assignee-principal-type User --role "AzureML Data Scientist" \
  --scope "$WS_ID" --subscription "$SUB" &&
(
  for ROLE in "Storage Blob Data Contributor" "Storage File Data Privileged Contributor"; do
    az role assignment create --assignee-object-id "$USER_OBJECT_ID" \
      --assignee-principal-type User --role "$ROLE" --scope "$STORAGE_ID" --subscription "$SUB" &&
    az role assignment create --assignee-object-id "$MI_OBJECT_ID" \
      --assignee-principal-type ServicePrincipal --role "$ROLE" --scope "$STORAGE_ID" --subscription "$SUB" || exit "$?"
  done
)
```

**완료 조건:** 학습자의 Workspace 역할 1개와 Storage 역할 2개, UAMI의 Storage 역할 2개가 할당됐습니다. keyless Compute Instance의 파일 마운트 요구사항에 맞춰 UAMI를 사용합니다. 역할 전파에는 시간이 걸릴 수 있으며, Workspace가 자동으로 생성한 관리 ID의 역할도 유지해야 합니다.

## 4. 네트워크 프로비저닝과 Compute 생성

**할 일:** managed network를 준비하고 학습 Cluster와 학습자 전용 Instance를 만듭니다. `--user-object-id`·`--user-tenant-id`로 **3단계의 학습자에게 Instance를 할당**합니다. Workspace 역할을 부여하는 것만으로 다른 사람의 Instance에 로그인할 수는 없습니다.

```bash
: "${MI_ID:?3단계 ID 필요}" "${USER_OBJECT_ID:?3단계 학습자 ID 필요}" \
  "${TENANT:?1단계 tenant 필요}" &&
az ml workspace provision-network --name "$WS" -g "$RG" --subscription "$SUB" &&
python -m scripts.render_compute --identity-id "$MI_ID" &&
az ml compute create --file artifacts/infra/compute-cluster.yml \
  -g "$RG" -w "$WS" --subscription "$SUB" &&
az ml compute create --file artifacts/infra/compute-instance.yml \
  --user-object-id "$USER_OBJECT_ID" --user-tenant-id "$TENANT" \
  -g "$RG" -w "$WS" --subscription "$SUB" &&
az ml workspace update --name "$WS" -g "$RG" --subscription "$SUB" \
  --image-build-compute "$CLUSTER"
```

Compute YAML에는 사용자 VNet의 `network_settings.subnet`을 넣지 않습니다. Workspace managed network를 자동으로 사용합니다. Cluster는 최소 0 / 최대 2노드, 120초 idle 축소이며 Instance는 30분 idle shutdown입니다. 둘 다 공인 IP/공개 SSH 없이 구성합니다.

Private Link와 제한된 Storage를 함께 사용할 때 이미지 빌드도 Storage에 접근 가능한 CPU Cluster로 지정합니다. 기본 serverless builder를 그대로 두면 추론 환경 이미지 빌드가 실패할 수 있습니다.

**확인 위치:** Studio의 **Compute → Compute instances**에서 이름·할당 사용자를 확인하고 **Compute clusters**에서 지정한 Cluster의 생성 성공과 0–2노드 설정을 확인합니다. 이미지 빌드 대상은 아래 출력이 `$CLUSTER`와 같아야 합니다.

```bash
az ml workspace show --name "$WS" -g "$RG" --subscription "$SUB" \
  --query image_build_compute -o tsv
```

**완료 조건:** 생성이 성공하고 Instance의 할당 사용자가 해당 학습자이며 이미지 빌드 대상이 학습 Cluster입니다. 최종 사용 가능 여부는 아래에서 **학습자 자신의 로그인**으로 확인합니다.

## Compute Instance에서 실행 준비

**강사의 필수 생성 절차는 여기서 끝납니다.** 학습자가 자신의 계정으로 [학습자 시작 안내](learner-start.md)의 준비 A–E를 수행합니다. 파일 배치·설정·kernel·로그인 절차는 그 문서 하나에서 관리합니다.

**학습자에게 전달할 것:** 가이드와 같은 브랜치의 전체 프로젝트 ZIP, 구독·tenant·RG·Workspace 정보, 본인 Instance·학습 Cluster·본인 endpoint 이름입니다. Studio의 본인 사용자 폴더도 함께 확인합니다. 여러 학습자가 실습할 때 **Instance와 endpoint는 개인별로 지정**하고, `config.json`의 Compute 이름까지 본인 환경과 맞는지 확인합니다. 학습 Cluster가 전용인지 공유인지도 알려 주며, 공유 Cluster의 최종 0노드 확인은 모든 학습자 종료 후 강사가 수행합니다. Notebook 한 파일이나 강사 계정의 설정만 전달하지 않습니다.

**인계 완료 조건:** 학습자가 본인 Instance의 Terminal을 열고 `준비 완료`를 확인한 뒤 01의 자산 등록까지 성공합니다. 강사의 리소스 생성 성공만으로 학습자의 파일·데이터 접근이 확인된 것은 아닙니다.

## 선택: 대화형 로그인 없이 실행하는 강사용 runner

**일반 학습자 실습에서는 건너뜁니다.** 관리 PC가 private Storage에 접근할 수 없고 강사가 무인 실행을 해야 할 때만 `infra/private-access.bicep`로 **별도 private runner**를 만듭니다. 이 VM은 학습 서버가 아니라 동일 SDK 명령을 실행하는 임시 제어용 VM이며 **VM 비용이 추가**됩니다.

이 선택적 템플릿은 runner용 VNet, Blob/File/Workspace Private Endpoint와 DNS, 공인 IP 없는 VM, 인바운드 차단 NSG를 만듭니다. 이 VNet은 Workspace managed network와 별개이며 **학습 Compute를 이 VNet에 주입하지 않습니다.** 실습용 outbound에는 `defaultOutboundAccess: true`를 사용하므로 운영에서는 명시적 NAT/Firewall 설계가 필요합니다.

```bash
mkdir -p artifacts &&
if [ -e artifacts/runner-rsa ] || [ -e artifacts/runner-rsa.pub ]; then
  printf '기존 runner 키가 있습니다. 덮어쓰지 말고 이전 runner 사용 여부를 확인하세요.\n' >&2
  false
fi &&
ssh-keygen -t rsa -b 3072 -N '' -f artifacts/runner-rsa &&
az deployment group create --name aml-private-access -g "$RG" --subscription "$SUB" \
  --template-file infra/private-access.bicep \
  --parameters storageAccountName="$STORAGE_NAME" workspaceName="$WS" \
    managedIdentityName="$IDENTITY_NAME" sshPublicKey="$(cat artifacts/runner-rsa.pub)" \
    location="$LOCATION" &&
az role assignment create --assignee-object-id "$MI_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal --role "AzureML Data Scientist" \
  --scope "$WS_ID" --subscription "$SUB"
```

배포가 성공한 뒤 프로젝트를 전달하고 자산을 등록합니다.

```bash
python -m scripts.remote_runner bootstrap &&
python -m scripts.remote_runner run assets
```

아래는 **새 실행 한 번의 예시**입니다. 기존 실행을 이어가려면 새 ID를 만들지 말고 기록한 실행명으로 조회·대기합니다.

```bash
LAB_ID="$(date -u +%Y%m%d%H%M%S)-$(python -c 'import uuid; print(uuid.uuid4().hex[:6])')" &&
BASELINE_RUN="baseline-${LAB_ID}" &&
printf '기록할 LAB_ID: %s\n' "$LAB_ID" &&
python -m scripts.remote_runner run submit --run "$BASELINE_RUN" \
  --data-version 1 --alpha 1 --max-rmse 3
```

```bash
python -m scripts.remote_runner run wait --run "$BASELINE_RUN" &&
python -m scripts.remote_runner run report --run "$BASELINE_RUN"
```

**완료 조건:** `Completed`, `approved=true`, RMSE ≤ 3입니다. `submit`의 URL만 출력된 것은 완료가 아닙니다.

개인 키는 Azure나 GitHub에 전송하지 않습니다. VM은 SSH로 관리하지 않고 Azure VM Run Command를 사용합니다. 헬퍼는 계정/VM 태그와 실제 내부 종료 코드를 검사합니다.

나머지 CLI 명령에도 `python -m scripts.remote_runner run ...`을 사용할 수 있습니다. 관리 PC에서 제출한 Job의 기록을 runner로 옮기려면 `sync-runs`를 사용합니다. 배포는 `--no-wait`로 제출하고 관리 PC에서 `wait-deployment`로 기다리면 runner를 점유하지 않습니다. **Submitted / ready=false는 배포 성공이 아닙니다.**

| 필요한 작업만 실행 | 의미 |
|---|---|
| `python -m scripts.remote_runner test` | runner 안에서 코드·문서 검사 |
| `python -m scripts.remote_runner publish` | 설정 계정의 Studio 파일 공유에 게시. 같은 경로의 파일은 덮어씀 |
| `python -m scripts.remote_runner collect` | runner의 실행 기록을 관리 PC로 회수 |

게시 대상은 `Users/<expected_account의 @ 앞부분>/azure-ml-labs`이며 `config.json`도 포함됩니다. **실제 본인 사용자 폴더와 일치하고 이전 작업을 덮어써도 되는 경우에만** 게시합니다. 학습자 배포에는 [준비 B](learner-start.md#준비-b--최신-프로젝트를-별도-폴더에-풀기)의 새 ZIP 폴더를 사용합니다.

게시 시 각 파일을 다시 읽어 해시를 대조합니다. 작업 후 기록을 회수하고 임시 VM을 삭제합니다. 자세한 내용은 [문제 해결·정리](troubleshooting.md)를 참고합니다.

## 기존 Workspace를 managed network로 바꾸는 경우

새 환경은 처음부터 managed network를 사용하므로 이 작업이 필요 없습니다. 기존 환경의 전환은 별도 작업입니다.

**공식 요구사항:** 기존 Compute Instance, Compute Cluster, Managed Online Endpoint를 먼저 삭제하고 managed network를 활성화한 뒤 재생성해야 합니다. Storage의 데이터/Notebook, Job 이력, Models의 등록 모델과 Compute의 로컬 디스크는 구분해야 합니다. 로컬 작업을 백업하고 대상 리소스를 확인하지 않은 채 전환하지 않습니다. 활성화한 managed network는 다시 Disabled로 되돌릴 수 없습니다.

```bash
# 필요한 백업과 해당 Workspace의 Compute/endpoint 정리가 끝난 뒤에만:
az ml workspace update --name "$WS" -g "$RG" --subscription "$SUB" \
  --managed-network allow_internet_outbound &&
az ml workspace provision-network --name "$WS" -g "$RG" --subscription "$SUB"
```

이 전환은 새 환경 준비의 완료 조건이 아닙니다. 검증된 최종 구성과 초기 시행착오는 [과거 실행 보고서](execution-report.md)에 구분해 기록합니다.

공식 참고: [Compute Instance 생성·사용자 할당](https://learn.microsoft.com/azure/machine-learning/how-to-create-compute-instance?view=azureml-api-2#create-on-behalf-of), [Compute 관리 권한](https://learn.microsoft.com/azure/machine-learning/how-to-manage-compute-instance?view=azureml-api-2#manage), [CLI Compute 생성 옵션](https://learn.microsoft.com/cli/azure/ml/compute?view=azure-cli-latest#az-ml-compute-create).
