# 실제 Azure 실행 결과

**학습·재학습, 성능 미달 모델의 등록 차단, 실시간 추론, `blue → green → blue` 전환·롤백을 실제 Azure에서 확인했습니다.** 실행 후 추론 endpoint와 임시 runner를 삭제하고, Instance를 중지하며 학습 Cluster의 실제 노드 수가 0임을 확인했습니다.

검증일: **2026-09-16**. 최종 상태 확인: **20:10 KST / 11:10 UTC**.

## 실행 환경

| 항목 | 값 |
|---|---|
| Azure 리소스 생성 계정 | `junwoojeong@MngEnvMCAP757124.onmicrosoft.com` |
| 구독 | `51531604-2337-4c05-bc05-3c3d4ff154e5` |
| Tenant | `46e9cdaa-fed3-4131-aa28-c1fc8a8a043a` |
| 새 리소스 그룹 | `rg-aml-mlops-lab-20260916` |
| 최종 Workspace | `mlw-mlops-managed-20260916` |
| 리전 | East US 2 |
| 네트워크 | Workspace managed network, `AllowInternetOutbound`, `Active` |
| 개발 / 학습 Compute | `ci-mlops-private` / `cpu-private-only` |
| 모델 / 데이터 자산 | `mlops-ridge` v1·v2 / `mlops-synthetic-regression` v1·v2 |
| 환경 / 컴포넌트 | `sklearn-1.5:53` / prepare·train·evaluate v3 |

ARM 생성 작업은 지정 계정으로 수행했습니다. 학습과 private 실행 자동화는 이 구독의 전용 사용자 할당 관리 ID를 사용했습니다. 다른 작업에 영향을 주지 않도록 로컬 Azure CLI의 전역 기본 구독은 변경하지 않았습니다.

## 1. 파이프라인과 품질 게이트

| 시나리오 | 데이터 | alpha | 실제 RMSE | 실제 R² | 결과 |
|---|---:|---:|---:|---:|---|
| [기본 모델][baseline-job] | v1 | 1 | **1.836078** | 0.993756 | Completed, 모델 v1 등록 |
| [성능 미달 모델][rejected-job] | v1 | 1,000,000 | **23.399537** | -0.014159 | evaluate_gate Failed, 등록 차단 |
| [재학습 모델][retrain-job] | v2 | 0.1 | **1.823776** | 0.993839 | Completed, 모델 v2 등록 |

기준은 **RMSE ≤ 3.0**입니다. 성능 미달 모델은 단순 인프라 실패가 아니라, 평가 보고서의 `approved=false`와 실제 RMSE 초과를 확인했습니다. 등록 명령이 차단되고 거절한 모델 버전 `9`가 Registry에 없는 것도 확인했습니다.

기본 모델은 `--force-rerun`으로 실행해 최종 managed network에서 모든 단계가 실제 Compute에서 수행되도록 했습니다. v1/v2의 검증 데이터는 동일한 200행이며 SHA-256이 일치합니다. 학습 행만 800 → 1,200행으로 늘었습니다.

## 2. 실제 추론과 전환·롤백

검증 endpoint: `mlops-reg-20260916-515316`, 인증 방식: **Microsoft Entra ID (`aad_token`)**.

입력은 8개 feature를 가진 **5행**입니다. 각 응답이 유한한 숫자 5개이며, 버전별 학습 로직으로 계산한 예상 예측값과 일치하는지 검사했습니다.

| 호출 | 방식 | 확인된 모델 | 응답 첫 번째 값 |
|---|---|---|---:|
| 1 | blue 직접 호출 | v1 | 54.400175 |
| 2 | 기본 endpoint, blue 100% | v1 | 54.400175 |
| 3 | green 직접 호출 | v2 | 54.402844 |
| 4 | 기본 endpoint, green 100% | v2 | 54.402844 |
| 5 | 기본 endpoint, blue 100%로 롤백 | v1 | 54.400175 |

**직접 호출만 성공한 것이 아니라, 기본 경로에서 `blue → green → blue` 모델 응답을 확인**했습니다. Azure Monitor의 `RequestsPerMinute`에도 실제 요청 지표가 수집됐습니다. 소수 호출 검증이므로 부하 성능이나 SLA를 검증한 것은 아닙니다.

## 3. 최종 정리 상태

| 항목 | 확인한 상태 |
|---|---|
| Online Endpoint / blue·green 추론 VM | 삭제됨 |
| `ci-mlops-private` | Stopped |
| `cpu-private-only` | min 0, 실제 current/target 0 |
| 임시 runner VM / OS disk / NIC | 삭제됨 |
| 임시 runner용 사용자 VNet·NSG·Private Endpoint·DNS | 삭제됨 |
| 임시 SSH 개인 키·공개 키 | 삭제됨 |
| Storage | 공유 키·익명 Blob·공개 네트워크 비활성화 유지 |
| Workspace managed network | Active, 유지 |
| Job 이력·모델·데이터·Notebook | 보관 |

**지속 비용은 남습니다.** 특히 Premium ACR의 East US 2 공개 표시 가격은 약 **USD 1.6666/일**이며, managed-network Private Endpoint·Storage·디스크 등의 비용은 별도입니다. 더 이상 보관할 필요가 없으면 [전용 RG 정리](troubleshooting.md#전체-환경이-더-이상-필요하지-않은-경우)를 수행합니다.

## 4. 가이드와 실행 증빙

직관성은 요청에 따라 **한 번의 최종 점검**을 수행했습니다. 첫 화면을 68줄의 Notebook 중심 안내로 줄이고, 상세 CLI 절차와 강사용 네트워크 준비를 분리했습니다. 잘못된 문서 anchor와 로그 확인 위치를 수정했으며, 롤백 뒤 불필요한 재전환을 제거했습니다.

검토한 소스·가이드·Notebook **33개 파일**을 Workspace 파일 공유의 다음 위치에 게시하고, 각각 다시 다운로드해 SHA-256으로 대조했습니다.

```text
Users/junwoojeong/azure-ml-labs
/home/azureuser/cloudfiles/code/Users/junwoojeong/azure-ml-labs
```

최종 결과 보고서와 기계 판독 증빙은 이 저장소에 보관합니다.

- [검증된 실행 증빙 JSON](execution-evidence.json)
- [검증 스크립트](../scripts/verify_execution.py)
- [Notebook](../notebooks/01-studio-mlops.ipynb)
- [상세 실습 가이드](lab-guide.md)

`verify_execution`은 실제 Job 상태, 코드·환경 버전, RMSE 기준, 모델 lineage, 5행 응답, 기본 경로 전환·롤백, 최종 리소스 상태를 검사한 후 증빙을 생성했습니다. 관련 테스트 28개도 통과했습니다.

## 확인 범위와 시행착오

최종 검증은 위의 **managed-network Workspace에서 전체 흐름을 다시 실행**한 결과입니다. 초기 `mlw-mlops-lab-20260916` Workspace는 시행착오의 이력 보관용이며 Compute와 Endpoint는 남기지 않았습니다. 두 Workspace는 같은 실습 RG와 일부 종속 리소스를 공유합니다.

초기에는 공인 IP 생성 제한, MLflow 3 API 지원 차이, private Storage의 이미지 빌드/추론 접근 문제가 있었습니다. 최종 가이드에는 **처음부터 managed network + Premium ACR**, private 빌드 Compute, MLflow run-artifact 기록 방식을 반영했습니다.

실제 실행은 가이드와 동일한 Python 코드의 CLI/SDK 경로로 수행했습니다. Studio 메뉴 안내와 Notebook은 제공하지만, 브라우저 로그인 세션이 없어 **Studio의 모든 클릭과 Notebook 전체 셀을 UI로 자동 실행했다고 주장하지 않습니다.** 자동 CD, 일정 기반 재학습, 데이터 drift 감시, canary 비율 테스트는 이번 범위에 포함하지 않았습니다.

[baseline-job]: https://ml.azure.com/runs/gray_skin_l29cw3mkv0?wsid=%2Fsubscriptions%2F51531604-2337-4c05-bc05-3c3d4ff154e5%2Fresourcegroups%2Frg-aml-mlops-lab-20260916%2Fworkspaces%2Fmlw-mlops-managed-20260916&tid=46e9cdaa-fed3-4131-aa28-c1fc8a8a043a
[rejected-job]: https://ml.azure.com/runs/careful_beard_mk7l7y9z2p?wsid=%2Fsubscriptions%2F51531604-2337-4c05-bc05-3c3d4ff154e5%2Fresourcegroups%2Frg-aml-mlops-lab-20260916%2Fworkspaces%2Fmlw-mlops-managed-20260916&tid=46e9cdaa-fed3-4131-aa28-c1fc8a8a043a
[retrain-job]: https://ml.azure.com/runs/tidy_lion_5qghlpm9j9?wsid=%2Fsubscriptions%2F51531604-2337-4c05-bc05-3c3d4ff154e5%2Fresourcegroups%2Frg-aml-mlops-lab-20260916%2Fworkspaces%2Fmlw-mlops-managed-20260916&tid=46e9cdaa-fed3-4131-aa28-c1fc8a8a043a
