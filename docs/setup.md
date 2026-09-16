# 환경 준비: 강사용 / 새 Workspace용

**학습자는 이미 준비된 Workspace를 사용하고, 아래의 “Compute Instance에서 실행 준비”부터 진행합니다.** 새 Azure 환경을 만드는 강사만 1–4단계를 수행합니다.

최종 구성은 **Workspace managed network + keyless Storage**입니다. 학습 Compute와 Managed Online Endpoint가 각각 Storage에 접근할 수 있도록 Azure ML이 필요한 outbound Private Endpoint를 관리합니다. 사용자가 만든 VNet에 학습 클러스터만 넣는 것으로는 Online Endpoint의 Storage 접근까지 해결되지 않습니다.

## 1. 관리 PC와 계정 설정

필요한 도구는 Azure CLI, `ml` v2 extension, Python 3.12입니다. 프로젝트 루트에서:

```bash
az version
az extension show --name ml
# extension이 없는 경우에만: az extension add --name ml

python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-lock.txt
python -m pip install --no-deps -e .
cp -n config.example.json config.json
```

기존 `config.json`은 덮어쓰지 않습니다. 구독·tenant·로그인 계정, **새 RG/Workspace 이름**, 리전 내 고유한 endpoint 이름을 설정합니다. 계정별 설정 파일은 Git 추적에서 제외합니다.

```bash
SUB=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().subscription_id)')
TENANT=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().tenant_id)')
RG=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().resource_group)')
WS=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().workspace)')
LOCATION=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().location)')
CLUSTER=$(python -c 'from mlops_lab.config import Settings; print(Settings.load().compute_cluster)')

# 해당 계정이 아직 로그인되지 않았다면:
az login --tenant "$TENANT"
az account show --subscription "$SUB" \
  --query '{user:user.name,subscription:name,tenant:tenantId}' -o json
```

코드는 UPN·tenant·구독을 검사하고 `AzureCliCredential(subscription=...)`을 사용합니다. 전역 기본 구독을 바꿀 필요가 없습니다. 현재 CLI에서는 `tenant`와 `subscription`을 자격 증명에 동시에 전달하면 충돌하므로 tenant는 사전 검사로 확인합니다.

## 2. 새 리소스 그룹과 managed-network Workspace

```bash
az group exists --name "$RG" --subscription "$SUB"
# true라면 기존 환경을 건드리지 말고 새 RG 이름을 정합니다.

for PROVIDER in Microsoft.MachineLearningServices Microsoft.Network Microsoft.Compute Microsoft.ManagedIdentity; do
  az provider register --namespace "$PROVIDER" --subscription "$SUB" --wait
done

az group create --name "$RG" --location "$LOCATION" --subscription "$SUB" \
  --tags purpose=aml-mlops-hands-on environment=lab

# Managed network에는 Premium ACR이 필요합니다. 처음부터 Premium으로 준비합니다.
ACR_NAME=$(python -c 'import hashlib; from mlops_lab.config import Settings; print("acrml" + hashlib.sha256(Settings.load().workspace_id().encode()).hexdigest()[:18])')
az acr create --name "$ACR_NAME" -g "$RG" --location "$LOCATION" \
  --sku Premium --subscription "$SUB"
ACR_ID=$(az acr show --name "$ACR_NAME" -g "$RG" --subscription "$SUB" --query id -o tsv)

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

Workspace와 함께 Storage, Key Vault, Application Insights, Log Analytics가 생성되며 앞에서 만든 Premium Container Registry를 연결합니다. Workspace의 public endpoint는 인증된 Studio/관리 API 접속을 위해 유지하며, 이것은 Storage 익명 접근 허용과 다릅니다.

**비용 주의:** Premium ACR의 East US 2 공개 종량제 표시 가격은 2026-09-16 기준 약 **USD 1.6666/일**입니다. VM을 중지해도 이 비용과 Private Endpoint·Storage 등은 남습니다. 실제 요율은 계약에 따라 다르므로 실습 후 RG 보관 여부를 결정합니다.

```bash
STORAGE_ID=$(az ml workspace show --name "$WS" -g "$RG" --subscription "$SUB" \
  --query storage_account -o tsv)
STORAGE_NAME="${STORAGE_ID##*/}"

az storage account update --name "$STORAGE_NAME" -g "$RG" --subscription "$SUB" \
  --public-network-access Disabled --allow-shared-key-access false \
  --allow-blob-public-access false --bypass AzureServices
```

권한을 가진 Azure 서비스의 trusted-service 예외는 유지합니다. 그러나 **이 예외만으로 Managed Online Endpoint의 private Storage 연결이 해결된다고 가정하지 않습니다.** managed network의 outbound Private Endpoint가 필요합니다.

## 3. 사용자·Compute 관리 ID의 최소 역할

| 주체 | 범위와 역할 |
|---|---|
| 강사 | 실습 리소스 생성·역할 할당 권한 |
| 학습자 | Workspace의 AzureML Data Scientist |
| 학습자와 Compute UAMI | 실습 Storage의 Storage Blob Data Contributor / Storage File Data Privileged Contributor |
| 무인 runner의 UAMI | 위 역할 + 해당 Workspace의 AzureML Data Scientist |

`Owner`/`Contributor` 같은 관리 평면 역할이 Storage 데이터 평면 역할을 대신하지 않습니다. 학생에게 구독 Owner를 일괄 부여하지 않습니다.

```bash
IDENTITY_NAME=id-aml-mlops-compute
az identity create --name "$IDENTITY_NAME" -g "$RG" --location "$LOCATION" \
  --subscription "$SUB" --tags purpose=aml-mlops-hands-on
MI_ID=$(az identity show --name "$IDENTITY_NAME" -g "$RG" --subscription "$SUB" --query id -o tsv)
MI_OBJECT_ID=$(az identity show --name "$IDENTITY_NAME" -g "$RG" --subscription "$SUB" --query principalId -o tsv)

# Azure portal → Microsoft Entra ID → 해당 사용자 → Object ID
USER_OBJECT_ID="<실습 사용자 Object ID>"
for ROLE in "Storage Blob Data Contributor" "Storage File Data Privileged Contributor"; do
  az role assignment create --assignee-object-id "$USER_OBJECT_ID" \
    --assignee-principal-type User --role "$ROLE" --scope "$STORAGE_ID" --subscription "$SUB"
  az role assignment create --assignee-object-id "$MI_OBJECT_ID" \
    --assignee-principal-type ServicePrincipal --role "$ROLE" --scope "$STORAGE_ID" --subscription "$SUB"
done
```

keyless Compute Instance의 파일 마운트 요구사항에 맞춰 UAMI를 사용합니다. 역할 전파에는 시간이 걸릴 수 있습니다. Workspace가 자동으로 생성한 관리 ID의 역할도 유지해야 합니다.

## 4. 네트워크 프로비저닝과 Compute 생성

```bash
az ml workspace provision-network --name "$WS" -g "$RG" --subscription "$SUB"

python -m scripts.render_compute --identity-id "$MI_ID"
az ml compute create --file artifacts/infra/compute-cluster.yml \
  -g "$RG" -w "$WS" --subscription "$SUB"
az ml compute create --file artifacts/infra/compute-instance.yml \
  -g "$RG" -w "$WS" --subscription "$SUB"

az ml workspace update --name "$WS" -g "$RG" --subscription "$SUB" \
  --image-build-compute "$CLUSTER"
```

Compute YAML에는 사용자 VNet의 `network_settings.subnet`을 넣지 않습니다. Workspace managed network를 자동으로 사용합니다. Cluster는 최소 0 / 최대 2노드, 120초 idle 축소이며 Instance는 30분 idle shutdown입니다. 둘 다 공인 IP/공개 SSH 없이 구성합니다.

Private Link와 제한된 Storage를 함께 사용할 때 이미지 빌드도 Storage에 접근 가능한 CPU Cluster로 지정합니다. 기본 serverless builder를 그대로 두면 추론 환경 이미지 빌드가 실패할 수 있습니다.

Studio의 **Manage → Quota**에서 AML 코어 쿼터를 확인합니다. 일반 VM 쿼터와 AML Compute 쿼터는 별도입니다. DS3_v2의 4코어 기준으로 학습 최대 2노드, Instance 1대, blue/green 각각 1대와 배포 업그레이드 예약 여유를 고려합니다.

## Compute Instance에서 실행 준비

1. Studio → **Compute → Compute instances**에서 `ci-mlops-private`를 시작합니다.
2. **Notebooks**의 사용자 폴더에 전체 실습 프로젝트를 배치합니다. Notebook 하나만 업로드하면 모듈·컴포넌트·설정 파일을 찾을 수 없습니다.
3. 해당 Instance의 Terminal에서 프로젝트 루트로 이동합니다. 계정별 `config.json`도 준비합니다.

```bash
command -v uv || python -m pip install --user uv
uv venv --python 3.12 "$HOME/.venvs/aml-mlops-lab"
source "$HOME/.venvs/aml-mlops-lab/bin/activate"
uv pip install -r requirements-lock.txt -e ".[dev]"
python -m ipykernel install --user --name aml-mlops-lab \
  --display-name "AML MLOps Lab (Python 3.12)"

az login --tenant "<config.json의 tenant_id>" --use-device-code
python -m pytest --disable-warnings
```

가상환경은 네트워크 파일 공유가 아닌 CI 로컬 디스크에 두고, 소스/Notebook은 Workspace 파일 공유에 유지합니다. Notebook에서 **AML MLOps Lab (Python 3.12)** kernel을 선택합니다. 브라우저 로그인과 CLI 로그인은 별개입니다.

## 선택: 대화형 로그인 없이 실행하는 강사용 runner

관리 PC가 private Storage에 접근할 수 없다면 `infra/private-access.bicep`로 **별도 private runner**를 만들 수 있습니다. 이 VM은 학습 서버가 아니라 동일 SDK 명령을 실행하는 임시 제어용 VM입니다.

이 선택적 템플릿은 runner용 VNet, Blob/File/Workspace Private Endpoint와 DNS, 공인 IP 없는 VM, 인바운드 차단 NSG를 만듭니다. 이 VNet은 Workspace managed network와 별개이며 **학습 Compute를 이 VNet에 주입하지 않습니다.** 실습용 outbound에는 `defaultOutboundAccess: true`를 사용하므로 운영에서는 명시적 NAT/Firewall 설계가 필요합니다.

```bash
mkdir -p artifacts
# 같은 경로에 기존 키가 있으면 다른 파일명을 선택합니다.
ssh-keygen -t rsa -b 3072 -N '' -f artifacts/runner-rsa
az deployment group create --name aml-private-access -g "$RG" --subscription "$SUB" \
  --template-file infra/private-access.bicep \
  --parameters storageAccountName="$STORAGE_NAME" workspaceName="$WS" \
    managedIdentityName="$IDENTITY_NAME" sshPublicKey="$(cat artifacts/runner-rsa.pub)" \
    location="$LOCATION"

WS_ID=$(az ml workspace show --name "$WS" -g "$RG" --subscription "$SUB" --query id -o tsv)
az role assignment create --assignee-object-id "$MI_OBJECT_ID" \
  --assignee-principal-type ServicePrincipal --role "AzureML Data Scientist" \
  --scope "$WS_ID" --subscription "$SUB"

python -m scripts.remote_runner bootstrap
python -m scripts.remote_runner run assets
python -m scripts.remote_runner run submit --run baseline \
  --data-version 1 --alpha 1 --max-rmse 3
```

개인 키는 Azure나 GitHub에 전송하지 않습니다. VM은 SSH로 관리하지 않고 Azure VM Run Command를 사용합니다. 헬퍼는 계정/VM 태그와 실제 내부 종료 코드를 검사합니다.

나머지 CLI 명령에도 `python -m scripts.remote_runner run ...`을 사용할 수 있습니다. 관리 PC에서 제출한 Job의 기록을 runner로 옮기려면 `sync-runs`를 사용합니다. 배포는 `--no-wait`로 제출하고 관리 PC에서 `wait-deployment`로 기다리면 runner를 점유하지 않습니다. **Submitted / ready=false는 배포 성공이 아닙니다.**

```bash
python -m scripts.remote_runner test
python -m scripts.remote_runner publish
python -m scripts.remote_runner collect
```

게시 시 각 파일을 다시 읽어 해시를 대조합니다. 작업 후 기록을 회수하고 임시 VM을 삭제합니다. 자세한 내용은 [문제 해결·정리](troubleshooting.md)를 참고합니다.

## 기존 Workspace를 managed network로 바꾸는 경우

새 환경은 처음부터 managed network를 사용하므로 이 작업이 필요 없습니다. 기존 환경의 전환은 별도 작업입니다.

**공식 요구사항:** 기존 Compute Instance, Compute Cluster, Managed Online Endpoint를 먼저 삭제하고 managed network를 활성화한 뒤 재생성해야 합니다. Storage의 데이터/Notebook, Job 이력, Registry 모델과 Compute의 로컬 디스크는 구분해야 합니다. 로컬 작업을 백업하고 대상 리소스를 확인하지 않은 채 전환하지 않습니다. 활성화한 managed network는 다시 Disabled로 되돌릴 수 없습니다.

```bash
# 필요한 백업과 해당 Workspace의 Compute/endpoint 정리가 끝난 뒤에만:
az ml workspace update --name "$WS" -g "$RG" --subscription "$SUB" \
  --managed-network allow_internet_outbound
az ml workspace provision-network --name "$WS" -g "$RG" --subscription "$SUB"
```

검증된 최종 구성과 초기 시행착오의 차이는 실행 보고서에 구분해서 기록합니다.
