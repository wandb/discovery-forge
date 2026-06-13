# Offline Evaluation Guide

이 문서는 `ResearcherAgent`의 offline evaluation을 어떻게 만들고, Weave에 등록하고, 결과를 해석하는지 설명한다.

핸즈온 시나리오의 핵심은 처음부터 완성된 gold dataset이 있는 것이 아니라는 점이다. 먼저 daily run을 실행하고, 사람이 Weave Annotation Queue에서 결과를 리뷰한다. 그 annotation이 충분히 쌓이면 일부를 고정 eval dataset으로 승격한다. 이후 prompt나 scope rule을 바꿀 때 같은 dataset으로 다시 평가해 regression을 확인한다.

## 평가 대상

**Verdict Quality Eval**은 후보가 이미 주어졌을 때 agent가 accept/reject를 제대로 하는지 본다. curated list, cookbook, generic framework, memory-only component 같은 것을 잘 reject하는지가 핵심이다.

## Dataset Files

평가용 dataset은 **Weave에 publish된 versioned Dataset**으로 관리한다.

- `verdict_quality_dataset`

`evaluate.py`는 `evaluation/evaluation_config.yaml`에 고정된 published ref를 기본값으로 읽으므로, 인자 없이도 published 버전 기준으로 평가가 돈다. 새 버전을 만들려면 reviewed rows를 `publish_eval_dataset(...)`으로 다시 publish하고 `evaluation_config.yaml`의 해당 ref를 갱신한다.

## Verdict Quality Eval

Verdict eval은 "이 후보를 accept해야 하는가, reject해야 하는가?"를 측정한다. 각 row는 하나의 고정 candidate이며, `ResearcherAgent`는 row의 후보 이름, URL, 설명을 입력으로 받아 scope/profile 결정을 내린다.

주요 row 필드:

- `id`: eval row id
- `input_tool_name`: 후보 이름
- `input_candidate_url`: 후보 URL
- `input_candidate_description`: 후보 설명
- `expected_scope_status`: `accepted` 또는 `rejected`
- `expected_issue_category`: reject일 때 기대하는 이유 범주. 예: `out_of_scope`, `missing_url`, `duplicate_known_tool`
- `label_reason`: 사람이 남긴 판정 근거
- `annotation_source`: 어떤 Weave annotation에서 왔는지 기록하는 provenance

현재 verdict dataset은 Weave의 `research_annotation` queue에 붙은 human annotation만 사용한다. 자동 scorer feedback은 gold label로 쓰지 않는다.

각 row의 accept/reject 라벨링 기준, metadata vs scope 처리, row input hygiene 규칙은 [`verdict_dataset_rubric.md`](./verdict_dataset_rubric.md)에 정리되어 있다.

Scorer 해석:

- `verdict_quality_scorer.is_correct`: observed `scope_status`가 `expected_scope_status`와 같은지 본다.

판정 기준:

- expected가 `accepted`이고 observed도 `accepted`이면 correct다.
- expected가 `rejected`이고 observed도 `rejected`이면 correct다.
- expected와 observed가 다르면 incorrect다.

개선 방향:

- `verdict_quality_scorer.is_correct`가 낮으면 reject/accept 기준이 흔들린 것이다. Scope definition, curated list/cookbook/generic framework rejection rule, primary-source requirement를 강화한다.
- Profile metadata, source, rejected reason 품질은 이 eval에서 보지 않는다. 필요하면 별도의 profile/output quality eval로 분리한다.

실행:

```bash
uv run python evaluate.py --limit 5
uv run python evaluate.py --verdict-dataset-key verdict_quality
```

새 버전 publish는 `publish_eval_dataset(rows_path, name="verdict_quality_dataset")`로 수행하고 `evaluation_config.yaml`의 `datasets.verdict_quality.ref` 값을 갱신한다.

## Recommended Workflow

1. Daily run을 실행한다.
2. Weave의 `research_run_<i>` traces를 `research_annotation` queue에서 리뷰한다.
3. 충분한 annotation이 쌓이면 `research_annotation`만 사용해 verdict dataset을 만든다.
4. Dataset을 Weave에 publish한다.
5. Prompt 변경 전후로 같은 dataset ref를 사용해 eval을 반복한다.
6. Weave Evaluation에서 verdict quality를 비교한다.

## Guardrails

- 자동 scorer output을 gold label로 쓰지 않는다.
- `research_annotation` queue 밖의 annotation은 verdict dataset seed로 섞지 않는다.
- Dataset이나 scorer를 prompt 성능에 맞춰 몰래 바꾸지 않는다.
