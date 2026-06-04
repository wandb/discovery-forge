# Offline Evaluation Guide

この文書では、`ResearcherAgent` の offline evaluation を作成し、Weave に publish し、実行結果をどう解釈するかを説明する。

ハンズオンの前提は、最初から完全な gold dataset が存在するわけではないということ。まず daily run を実行し、人間が Weave Annotation Queue で結果をレビューする。十分な annotation が集まったら、その一部を固定 eval dataset に昇格させる。その後、prompt や scope rule を変更したときに同じ dataset で再評価し、regression を確認する。

## 評価が二つある理由

このプロジェクトでは二つの別々の問いを評価する。

**Verdict Quality Eval** は、候補がすでに与えられているとき、agent が accept/reject を正しく判断できるかを見る。curated list、cookbook、generic framework、memory-only component など、本来 reject すべきものを accept しないことが重要。

**Discovery Quality Eval** は、agent が自分で検索して accepted finding として保存したものが本当に良い discovery かを見る。この評価では完全な gold answer を事前に作るのが難しい。既知の tool 一覧があっても、agent が新しく見つけたものの方が良い可能性があるため、recall より accepted result の quality を見る方が自然。

## Dataset Files

ローカル dataset は `eval/` 配下に置く。

- `eval/researcher_verdict_dataset.jsonl`
- `eval/researcher_discovery_precision.jsonl`

`eval/` は gitignore 対象。再現可能なハンズオンには、Weave Dataset として publish し、versioned ref を使うのが望ましい。

## Verdict Quality Eval

Verdict eval は「この候補を accept すべきか、reject すべきか」を測る。各 row は固定 candidate であり、`ResearcherAgent` は候補名、URL、説明を入力として scope/profile decision を行う。

主な row fields:

- `id`: eval row id
- `input_tool_name`: 候補名
- `input_candidate_url`: 候補 URL
- `input_candidate_description`: 候補説明
- `expected_scope_status`: `accepted` または `rejected`
- `expected_issue_category`: reject 時に期待する理由カテゴリ。例: `out_of_scope`, `missing_url`, `duplicate_known_tool`
- `label_reason`: 人間が残した判断理由
- `annotation_source`: label の元になった Weave annotation の provenance

現在の verdict dataset は、Weave の `research_annotation` queue に付いた human annotation だけを使う。自動 scorer feedback は gold label として使わない。

Scorer の解釈:

- `verdict_quality_scorer.is_correct`: observed `scope_status` が `expected_scope_status` と一致するか。

判定基準:

- expected が `accepted` で observed も `accepted` なら correct。
- expected が `rejected` で observed も `rejected` なら correct。
- expected と observed が異なれば incorrect。

改善方向:

- `verdict_quality_scorer.is_correct` が低い場合、accept/reject 基準が不安定。Scope definition、curated list/cookbook/generic framework の rejection rule、primary-source requirement を強化する。
- Profile metadata、sources、rejected reason quality はこの eval では見ない。必要なら別の profile/output quality eval に分ける。

実行:

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

Discovery quality eval は「この search brief に対して agent が accepted finding として保存したものは良い discovery か」を測る。

現在の `ResearcherAgent` は eval row 一つにつき item を一つ返す。100 個の結果を評価するには、100 個の異なる search brief が必要。この dataset は gold tool answer を持たず、search task を固定し、LLM-as-judge scorer が accepted finding を `good`, `neutral`, `bad` に評価する。

現在の topics:

- autonomous coding
- autonomous research
- self-improving agents
- recursive improvement
- evaluation loops
- agent memory
- long-running agent workflows
- self-correction
- autonomous experimentation

`DiscoveryQualityJudge` は品質判断だけを担当する。Agent が accepted profile を保存したかどうかは judge metric ではなく、predict output の `scope_status` で確認する。

- `quality_score`: accepted finding の品質点。`good=1.0`, `neutral=0.5`, `bad=0.0`
- `bad_accept`: accepted finding が judge 基準で bad か

Row-level の `rating`, `reason`, `failure_modes` は debugging 用に残すが、summary で見るべき judge metric は `quality_score` と `bad_accept`。

strict/lenient metrics を別に出さない理由:

- Strict success は `quality_score == 1.0` で計算できる。
- Lenient success は `quality_score >= 0.5` で計算できる。
- Bad accept も `quality_score == 0.0` で計算できるが、最重要リスク信号なので boolean として残す。
- Acceptance rate が必要な場合は、`DiscoveryQualityJudge` ではなく predict output の `scope_status` を集計する。

改善方向:

- `scope_status=accepted` の比率が低い場合、agent が候補を見つけられていない、または reject/no-new が多すぎる可能性がある。Search query generation、source selection、scope filter が保守的すぎないか確認する。
- `quality_score` が低い場合、accepted finding の品質が弱い。Primary docs の確認、improvement-loop evidence requirement、metadata extraction を強化する。
- `quality_score` が 0.5 付近で `bad_accept` が低い場合、ほとんどが neutral。深刻な scope failure より、evidence 不足や borderline framework の可能性が高い。
- `bad_accept` が高い場合、最優先で直す。Curated lists、cookbooks、topic pages、generic frameworks、memory-only infrastructure が accepted item として feed に入っている。

実行:

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

1. Daily briefing を実行する。
2. `research_annotation` queue で `research_run_<i>` traces をレビューする。
3. Verdict dataset は `research_annotation` の human labels だけから作る。
4. Discovery dataset は人間が手書きした多様な search briefs として保つ。
5. Dataset を Weave に publish する。
6. Prompt 変更の前後で同じ dataset refs を使って eval を繰り返す。
7. Weave Evaluation で verdict quality と discovery quality を比較する。

## Guardrails

- 自動 scorer output を gold label として使わない。
- `research_annotation` queue 外の annotations を verdict dataset に混ぜない。
- Discovery dataset に gold tool answer を入れない。
- Prompt の見た目を良くするために dataset や scorer をこっそり変えない。
