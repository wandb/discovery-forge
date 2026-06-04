# Offline Evaluation Guide

이 문서는 `ResearcherAgent`의 offline evaluation을 어떻게 만들고, Weave에 등록하고, 결과를 해석하는지 설명한다.

핸즈온 시나리오의 핵심은 처음부터 완성된 gold dataset이 있는 것이 아니라는 점이다. 먼저 daily run을 실행하고, 사람이 Weave Annotation Queue에서 결과를 리뷰한다. 그 annotation이 충분히 쌓이면 일부를 고정 eval dataset으로 승격한다. 이후 prompt나 scope rule을 바꿀 때 같은 dataset으로 다시 평가해 regression을 확인한다.

## 평가가 두 개인 이유

이 프로젝트는 두 가지 질문을 따로 평가한다.

**Verdict Quality Eval**은 후보가 이미 주어졌을 때 agent가 accept/reject를 제대로 하는지 본다. curated list, cookbook, generic framework, memory-only component 같은 것을 잘 reject하는지가 핵심이다.

**Discovery Quality Eval**은 agent가 직접 검색해서 찾아온 accepted finding이 좋은 discovery인지 본다. 이 문제는 완전한 gold answer를 미리 만들기 어렵다. 우리가 아는 tool 목록이 있더라도 agent가 새로 찾은 항목이 더 좋을 수 있기 때문이다. 그래서 recall보다 accepted result의 quality를 보는 것이 자연스럽다.

## Dataset Files

현재 `eval/` 아래에는 두 JSONL dataset을 둔다.

- `eval/researcher_verdict_dataset.jsonl`
- `eval/researcher_discovery_precision.jsonl`

`eval/`은 `.gitignore` 대상이다. 재현 가능한 hands-on을 위해서는 Weave Dataset으로 publish해서 버전을 고정하는 편이 좋다.

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
uv run discovery-forge eval run-researcher \
  --dataset-ref 'weave:///wandb-smle/discovery-forge/object/researcher_verdict_dataset:<version>' \
  --output-dir eval_runs/verdict \
  --limit 5
```

Publish:

```bash
uv run discovery-forge eval publish-dataset \
  --dataset eval/researcher_verdict_dataset.jsonl \
  --name researcher_verdict_dataset
```

## Discovery Quality Eval

Discovery quality eval은 "주어진 search brief에서 agent가 찾아온 accepted finding이 좋은가?"를 측정한다.

현재 `ResearcherAgent`는 한 번의 eval row에서 하나의 item만 찾는다. 100개 결과를 평가하려면 100개의 서로 다른 search brief가 필요하다. 이 dataset은 정답 tool을 미리 적는 방식이 아니라, search brief를 고정하고 agent가 찾은 결과를 LLM-as-judge scorer가 `good`, `neutral`, `bad`로 채점하는 방식이다.

현재 topic:

- autonomous coding
- autonomous research
- self-improving agents
- recursive improvement
- evaluation loops
- agent memory
- long-running agent workflows
- self-correction
- autonomous experimentation

`DiscoveryQualityJudge`는 품질 판단만 담당한다. Agent가 accepted profile을 저장했는지는 judge metric이 아니라 predict output의 `scope_status`에서 확인한다.

- `quality_score`: accepted finding의 품질 점수. `good=1.0`, `neutral=0.5`, `bad=0.0`
- `bad_accept`: accepted finding이 judge 기준으로 bad인지 여부

`rating`, `reason`, `failure_modes`도 row-level 디버깅을 위해 남기지만, summary에서 볼 핵심 judge metric은 `quality_score`와 `bad_accept`다.

왜 strict/lenient metric을 따로 두지 않는가:

- `strict`는 `quality_score == 1.0`으로 계산할 수 있다.
- `lenient`는 `quality_score >= 0.5`로 계산할 수 있다.
- `bad_accept`는 `quality_score == 0.0`으로도 계산할 수 있지만, 위험 신호라서 별도 boolean으로 남긴다.
- Accepted rate가 필요하면 `DiscoveryQualityJudge`가 아니라 predict output의 `scope_status` 집계를 본다.

개선 방향:

- `scope_status=accepted` 비율이 낮으면 agent가 후보를 잘 못 찾거나 너무 자주 reject/no-new 한다는 뜻이다. Search query generation, source selection, scope filter가 너무 보수적인지 본다.
- `quality_score`가 낮으면 accepted는 했지만 발견 품질이 약하다는 뜻이다. Primary docs 확인, improvement loop evidence, metadata extraction을 강화한다.
- `quality_score`가 0.5 근처이고 `bad_accept`가 낮으면 대부분 neutral이다. 큰 scope 실패보다는 evidence 부족이나 borderline framework 문제가 많을 가능성이 높다.
- `bad_accept`가 높으면 가장 먼저 고쳐야 한다. Feed에 들어가면 안 되는 curated list, cookbook, topic page, generic framework, memory-only infrastructure가 accepted되고 있다는 뜻이다.

실행:

```bash
uv run discovery-forge eval run-discovery \
  --dataset-ref 'weave:///wandb-smle/discovery-forge/object/researcher_discovery_precision_dataset:<version>' \
  --output-dir eval_runs/discovery \
  --limit 5
```

Publish:

```bash
uv run discovery-forge eval publish-dataset \
  --dataset eval/researcher_discovery_precision.jsonl \
  --name researcher_discovery_precision_dataset
```

## Recommended Workflow

1. Daily run을 실행한다.
2. Weave의 `research_run_<i>` traces를 `research_annotation` queue에서 리뷰한다.
3. 충분한 annotation이 쌓이면 `research_annotation`만 사용해 verdict dataset을 만든다.
4. Discovery dataset은 사람이 손으로 작성한 diverse search brief로 유지한다.
5. Dataset을 Weave에 publish한다.
6. Prompt 변경 전후로 같은 dataset ref를 사용해 eval을 반복한다.
7. Weave Evaluation에서 verdict quality와 discovery quality를 비교한다.

## Guardrails

- 자동 scorer output을 gold label로 쓰지 않는다.
- `research_annotation` queue 밖의 annotation은 verdict dataset seed로 섞지 않는다.
- Discovery dataset에는 정답 tool을 미리 넣지 않는다.
- Dataset이나 scorer를 prompt 성능에 맞춰 몰래 바꾸지 않는다.
