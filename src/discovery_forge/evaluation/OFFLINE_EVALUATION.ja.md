# Offline Evaluation Guide

この文書では、`ResearcherAgent` の offline evaluation を作成し、Weave に publish し、実行結果をどう解釈するかを説明する。

ハンズオンの前提は、最初から完全な gold dataset が存在するわけではないということ。まず daily run を実行し、人間が Weave Annotation Queue で結果をレビューする。十分な annotation が集まったら、その一部を固定 eval dataset に昇格させる。その後、prompt や scope rule を変更したときに同じ dataset で再評価し、regression を確認する。

## 評価対象

**Verdict Quality Eval** は、候補がすでに与えられているとき、agent が accept/reject を正しく判断できるかを見る。curated list、cookbook、generic framework、memory-only component など、本来 reject すべきものを accept しないことが重要。

## Dataset Files

評価用 dataset は **Weave に publish された versioned Dataset** で管理する。

- `verdict_quality_dataset`

`evaluate.py` は `evaluation/evaluation_config.yaml` に固定された published ref をデフォルトで読み込むため、引数なしでも published バージョンで評価が走る。新しいバージョンを作るには reviewed rows を `publish_eval_dataset(...)` で再 publish し、`evaluation_config.yaml` の該当 ref を更新する。

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

各 row の accept/reject ラベリング基準、metadata vs scope の扱い、row input hygiene のルールは [`verdict_dataset_rubric.md`](./verdict_dataset_rubric.md) にまとめている。

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
uv run python evaluate.py --limit 5
uv run python evaluate.py --verdict-dataset-key verdict_quality
```

新しいバージョンの publish は `publish_eval_dataset(rows_path, name="verdict_quality_dataset")` で行い、`evaluation_config.yaml` の `datasets.verdict_quality.ref` 値を更新する。

## Recommended Workflow

1. Daily briefing を実行する。
2. `research_annotation` queue で `research_run_<i>` traces をレビューする。
3. Verdict dataset は `research_annotation` の human labels だけから作る。
4. Dataset を Weave に publish する。
5. Prompt 変更の前後で同じ dataset refs を使って eval を繰り返す。
6. Weave Evaluation で verdict quality を比較する。

## Guardrails

- 自動 scorer output を gold label として使わない。
- `research_annotation` queue 外の annotations を verdict dataset に混ぜない。
- Prompt の見た目を良くするために dataset や scorer をこっそり変えない。
