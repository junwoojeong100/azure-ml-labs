# CLI 실습 — Notebook과 동일한 01–07

**Notebook 대신 Terminal을 선택한 학습자용입니다.** [학습자 시작 안내](learner-start.md)의 준비 A–E에서 `준비 완료`를 확인한 뒤 진행합니다. Notebook 경로를 이미 실행했다면 이 문서를 중복 실행하지 않습니다.

모든 명령은 **Azure Compute Instance의 Terminal, 프로젝트 루트**에서 실행합니다. `config.json`의 Workspace·Compute·endpoint가 본인에게 지정된 값인지 확인합니다. Studio의 Job/Endpoint 화면은 **새 탭**에서 엽니다.

## 준비 — 실행명 한 번 정하기

처음에는 아래 블록을 그대로 실행합니다. 다시 연결했다면 먼저 기록한 값으로 `LAB_ID="기존 값"`을 설정한 뒤 실행합니다.

```bash
source "$HOME/.venvs/aml-mlops-lab/bin/activate"
LAB_ID="${LAB_ID:-$(date -u +%Y%m%d%H%M%S)-$(python -c 'import uuid; print(uuid.uuid4().hex[:6])')}"
export LAB_ID
BASELINE_RUN="baseline-${LAB_ID}"
BAD_RUN="bad-${LAB_ID}"
RETRAIN_RUN="retrain-${LAB_ID}"
MODEL_V1="${LAB_ID}1"
MODEL_V2="${LAB_ID}2"
printf '기록할 LAB_ID: %s\n' "$LAB_ID"
```

실행명과 모델 버전에 시간·고유 suffix를 넣어 기존 결과와 충돌하지 않게 합니다. **아래 단계는 같은 Terminal에서 계속 실행**합니다. `artifacts/runs/`를 지우지 않습니다.

## 01 · 자산 등록

**할 일:** 데이터 버전 2개와 재사용할 처리 단계 3개를 등록합니다.

```bash
python -m mlops_lab.cli generate-data
python -m mlops_lab.cli assets
```

**Studio에서 확인:** **Data → `mlops-synthetic-regression` → v1/v2**, **Components → `mlops_prepare` / `mlops_train` / `mlops_evaluate`**.

**완료 조건:** 데이터는 `uri_file`, 컴포넌트는 v3, 환경은 `sklearn-1.5:53`입니다. `data/manifest.json`에서 두 데이터의 전체 hash는 다르고 검증 데이터 hash는 같습니다.

| 데이터 | 학습 행 | 검증 행 |
|---|---:|---:|
| v1 | 800 | 200 |
| v2 | 1,200 | **v1과 동일한 200** |

외부 개인정보 없이 seed 42로 만든 합성 회귀 데이터입니다. 입력은 `feature_0`–`feature_7`, 예측 대상은 `target`입니다. `row_id`/`partition`은 모델 입력이 아닙니다.

## 02 · 학습

**할 일:** 데이터 v1으로 기본 모델을 학습합니다. RMSE는 예측 오차이며 **작을수록 좋습니다**.

```bash
python -m mlops_lab.cli submit --run "$BASELINE_RUN" \
  --data-version 1 --alpha 1 --max-rmse 3
```

출력된 `studio_url`을 새 탭에서 엽니다. 이어서 같은 실행을 기다립니다.

```bash
python -m mlops_lab.cli wait --run "$BASELINE_RUN"
python -m mlops_lab.cli report --run "$BASELINE_RUN"
```

**Studio에서 확인:** **Jobs → 해당 실행 → `evaluate_gate` → Metrics**. 파이프라인은 `prepare_data → train_model → evaluate_gate`입니다. 모델 파일은 `train_model → Outputs + logs`, 평가 보고서는 `evaluate_gate → Outputs + logs`에 있습니다.

**완료 조건:** `Completed`, `approved=true`, **RMSE ≤ 3**. 예상 RMSE는 약 **1.84**이며 실측값으로 판단합니다.

부모 Job의 Metrics가 비어 있어도 자식 `evaluate_gate`를 확인합니다. `Queued`/`Running`/timeout이면 [판단표](learner-start.md#기다릴지-고칠지-판단하기)를 따릅니다. **다시 submit하지 않습니다.**

## 03 · 품질 게이트

**할 일:** 큰 규제로 성능이 나빠지는 모델을 만들고, Registry(모델 보관소)에 들어가지 못하는지 확인합니다.

```bash
python -m mlops_lab.cli submit --run "$BAD_RUN" \
  --data-version 1 --alpha 1000000 --max-rmse 3
```

**다음 명령은 오류로 끝나야 정상**입니다. 이후 확인 명령은 별도로 실행합니다.

```bash
python -m mlops_lab.cli wait --run "$BAD_RUN"
```

```bash
python -m mlops_lab.cli inspect --run "$BAD_RUN"
python -m mlops_lab.cli report --run "$BAD_RUN"
```

**Studio에서 확인:** **Jobs → 해당 실행 → `evaluate_gate` → Metrics / Outputs + logs**.

**완료 조건:** 네 가지가 모두 맞아야 합니다: 부모 `Failed`, 실패 단계 `evaluate_gate`, `approved=false`, **RMSE > 3**(예상 약 23.4). 다른 단계/인증/네트워크 오류면 의도된 실패가 아니므로 멈춥니다.

마지막으로 다음 등록 명령을 실행합니다. **`Registration blocked`로 실패**해야 하며, Models에 `${LAB_ID}9` 버전이 없어야 합니다.

```bash
python -m mlops_lab.cli register --run "$BAD_RUN" --version "${LAB_ID}9"
```

두 실패와 등록 부재를 확인했으면 **04로 진행**합니다. 이것은 제공 코드의 승격 통제이며, Workspace 관리자의 모든 별도 API 등록을 금지하는 조직 정책은 아닙니다.

## 04 · blue 배포

**할 일:** 02에서 통과한 모델을 등록하고 `blue`(기존 모델)에 배포합니다. **여기부터 학습과 별개의 추론 VM 비용이 발생합니다.**

```bash
python -m mlops_lab.cli register --run "$BASELINE_RUN" --version "$MODEL_V1"
python -m mlops_lab.cli deploy --model-version "$MODEL_V1" --deployment blue
```

배포가 `Succeeded`가 된 뒤 호출합니다. `Submitted`/`Creating`/`ready=false`는 완료가 아닙니다.

```bash
python -m mlops_lab.cli invoke --deployment blue
python -m mlops_lab.cli traffic --deployment blue
python -m mlops_lab.cli invoke
```

**Studio에서 확인:** **Models → `mlops-ridge` → 해당 버전**의 `source_job` / `quality_gate=passed`; **Endpoints → 해당 endpoint → blue**의 상태와 traffic.

**완료 조건:** blue `Succeeded`, 기본 경로 blue 100%, 두 호출 모두 **5행 요청 → 유한한 숫자 5개**입니다. 요청 파일은 `data/sample-request.json`이며 MLflow의 `input_data` / `columns` / `data` 형식입니다.

모델의 signature(입출력 형식)로 no-code deployment를 사용하므로 별도 `score.py`는 필요 없습니다. 인증은 endpoint key가 아니라 **Microsoft Entra ID (`aad_token`)**입니다.

## 05 · 재학습

**할 일:** 학습 행 400개가 추가된 데이터 v2로 같은 파이프라인을 실행합니다.

```bash
python -m mlops_lab.cli submit --run "$RETRAIN_RUN" \
  --data-version 2 --alpha 0.1 --max-rmse 3
python -m mlops_lab.cli wait --run "$RETRAIN_RUN"
python -m mlops_lab.cli report --run "$RETRAIN_RUN"
python -m mlops_lab.cli register --run "$RETRAIN_RUN" --version "$MODEL_V2"
```

**Studio에서 확인:** 두 실행의 **`evaluate_gate → Metrics`**, Models의 서로 다른 모델 버전과 원본 Job.

**완료 조건:** 새 실행 `Completed`, `approved=true`, RMSE ≤ 3(예상 약 **1.82**), 두 보고서의 `validation_sha256` 일치, 새 모델 버전 등록.

새 검증 데이터로 교체해 유리한 결과를 만든 것이 아닙니다. 자동 게이트는 절대 RMSE 기준이며, 이전 모델보다 개선됐는지 비교한 뒤 **사람이 06에서 전환을 결정**합니다.

## 06 · 전환·롤백

**할 일:** `green`(새 모델)을 먼저 직접 확인하고 기본 endpoint를 전환했다가 blue로 되돌립니다.

```bash
python -m mlops_lab.cli deploy --model-version "$MODEL_V2" --deployment green
python -m mlops_lab.cli invoke --deployment green
```

green 준비·직접 호출 성공을 확인한 뒤:

```bash
python -m mlops_lab.cli traffic --deployment green
python -m mlops_lab.cli invoke
python -m mlops_lab.cli traffic --deployment blue
python -m mlops_lab.cli invoke
```

**Studio에서 확인:** **Endpoints → 해당 endpoint → traffic**이 green 100% → blue 100%로 바뀝니다.

**완료 조건:** 기본 경로 응답이 **02의 모델(blue) → 05의 모델(green) → blue** 순서로 확인됩니다. 직접 호출의 `--deployment green`은 traffic 설정을 우회하므로 그것만으로 전환을 증명하지 않습니다.

새 모델의 직접 응답과 일반 호출 응답을 비교합니다. 다르면 전환 반영 여부를 확인하고 일반 호출만 다시 수행합니다. 90/10 canary나 shadow traffic은 이번 실습에 포함하지 않습니다.

## 07 · 비용 정리

**할 일:** endpoint를 삭제하고 Instance를 중지합니다. 중도 종료라면 먼저 [실행 중인 Job 취소](learner-start.md#중간에-그만둘-때)를 수행합니다.

```bash
python -m mlops_lab.cli cleanup-runtime --delete-endpoint
```

**Studio에서 확인:** **Endpoints**, **Compute → Compute instances / Compute clusters**.

**완료 조건:** endpoint 없음, Instance `Stopped`, Cluster **실제 노드 0**. Instance 자신을 중지하므로 Terminal/Notebook 연결이 끊기는 것은 정상일 수 있습니다.

최소 노드 0 설정만 보고 끝내지 않습니다. 마지막 Job/이미지 빌드 후 120초 idle 축소를 기다리고 실제 0노드를 확인합니다. Instance 중지만으로 Cluster Job과 endpoint가 종료되지는 않습니다.

**남는 비용:** Premium ACR·Private Endpoint·Storage·디스크 등은 별도입니다. 보관하지 않을 때만 강사가 [전체 RG 정리](troubleshooting.md#전체-환경이-더-이상-필요하지-않은-경우)를 수행합니다.

## 참고 — 기록과 재현

| 확인할 것 | 위치 |
|---|---|
| 제출한 Job ID·입력·상태 | `artifacts/runs/<실행명>.json` |
| MLflow 매개변수·지표·모델 파일 | 해당 자식 Job의 Metrics / Outputs + logs |
| 모델 lineage(원본 실행 연결) | Models의 `source_job`, `data_version` |
| 실제 endpoint 요청 수·latency | Endpoint → Details → View metrics |
| 중단/timeout/재시작 | [이어하기](troubleshooting.md#기존-실행을-이어가기) |

코드·환경·입력이 같으면 이전 단계가 재사용될 수 있습니다. 새 Compute/네트워크에서 **실제 재실행**을 확인해야 할 때만 `submit`에 `--force-rerun`을 추가합니다.

RMSE ≤ 3은 합성 데이터 전용이며 운영 SLA가 아닙니다. 이 검증 세트는 반복 비교에 쓰므로 독립 최종 테스트 세트라고 부르지 않습니다. 운영에서는 별도 holdout·업무 기준·champion 대비 회귀 방지가 필요합니다.

[GitHub CI](../.github/workflows/ci.yml)는 코드/가이드 검사를 수행합니다. 자동 Azure CD·예약 재학습·drift 감시는 별도 확장입니다. 과거 실측 결과는 [실행 보고서](execution-report.md), 환경별 진단은 [문제 해결](troubleshooting.md)을 봅니다.

공식 참고: [SDK v2 파이프라인](https://learn.microsoft.com/azure/machine-learning/tutorial-pipeline-python-sdk?view=azureml-api-2), [MLflow 배포](https://learn.microsoft.com/azure/machine-learning/how-to-deploy-mlflow-models-online-endpoints?view=azureml-api-2), [전환·롤백](https://learn.microsoft.com/azure/machine-learning/how-to-safely-rollout-online-endpoints?view=azureml-api-2).
