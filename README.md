# autoresearch-researcher

주 1회 실행되어 **실험 자동화(experiment automation) 계열 자율 연구 도구**를 조사하고, 공개 가능한 비교 가이드(Markdown)를 생성하는 멀티에이전트 시스템.

## 개요

3개의 에이전트가 순차적으로 동작합니다.

```
Orchestrator (CLI)
  ├─ DiscoveryAgent   — 웹 검색으로 후보 도구 발굴 (_candidates.jsonl)
  ├─ ProfilerAgent    — 도구별 메타데이터 수집 + 스코프 필터 (tools/{slug}.md)
  └─ WriterAgent      — 비교표 + 발행 초안 생성 (draft.md, comparison_table.md)
```

**스코프**: "가설 → 실험 → 결과 → 글쓰기" 사이클을 자동화하는 시스템만 포함합니다. 딥 리서치(웹 검색·요약만 하는) 도구는 자동 제외됩니다.

## 설치

Python 3.11+, [uv](https://docs.astral.sh/uv/) 필요.

```bash
git clone <repo>
cd autoresearch-researcher
uv sync
cp .env.example .env
# .env에 OPENAI_API_KEY, WANDB_API_KEY 입력
```

## 환경 변수

| 변수 | 필수 | 설명 |
|------|------|------|
| `OPENAI_API_KEY` | ✅ | OpenAI API 키 |
| `WANDB_API_KEY` | ✅ | W&B Weave 트레이싱용 |
| `GITHUB_TOKEN` | 선택 | GitHub API rate limit 회피 |
| `WANDB_ENTITY` | 선택 | W&B entity (기본: `wandb-smle`) |
| `WANDB_PROJECT` | 선택 | W&B project (기본: `autoresearch-researcher`) |

## 사용법

### 주간 브리핑 실행

```bash
uv run autoresearch-researcher run --week 2026-W19
```

옵션:

| 플래그 | 기본값 | 설명 |
|--------|--------|------|
| `--week` | (필수) | ISO 주차 식별자 (예: `2026-W19`) |
| `--max-tools` | 12 | 프로파일링할 최대 도구 수 |
| `--max-cost-usd` | 20.0 | 비용 상한 (초과 시 graceful 종료) |
| `--dry-run` | false | 실제 LLM 호출 없이 파이프라인 검증 |
| `--rerun` | false | 이미 존재하는 주차 폴더 재실행 (이전 폴더 백업) |

### 출력 구조

```
weekly_runs/2026-W19/
├── draft.md                  # 메인 발행 초안
├── comparison_table.md       # 도구 비교 표
├── tools/
│   └── {tool-slug}.md        # 도구별 상세 카드 (YAML front-matter)
├── sources.jsonl             # 모든 인용 출처
├── _candidates.jsonl         # DiscoveryAgent 발굴 후보 목록
├── run_metadata.json         # 실행 시각, 모델, 토큰, 비용
│
└── (사람이 작성)
    ├── final.md              # 검수·수정한 발행본
    ├── feedback.md           # 구조화된 피드백
    └── diff.md               # draft vs final 자동 diff
```

### 검수 후 diff 생성

`final.md`를 직접 작성한 뒤:

```bash
uv run autoresearch-researcher diff --week 2026-W19
```

`diff.md` (변경 분류: ADD / FIX / REMOVE / REWORD / BALANCE) 와 `feedback.md` 템플릿이 자동 생성됩니다.

## 아키텍처

### 에이전트

| 에이전트 | 입력 | 도구 | 출력 |
|----------|------|------|------|
| **DiscoveryAgent** | 스코프 정의 | `WebSearchTool`, `save_candidate` | `_candidates.jsonl` |
| **ProfilerAgent** | 후보 1개 | `WebSearchTool`, `fetch_github_metadata`, `save_tool_profile` | `tools/{slug}.md` |
| **WriterAgent** | 모든 `tools/*.md` | `save_draft`, `save_comparison_table` | `draft.md`, `comparison_table.md` |

### 스코프 필터 (ProfilerAgent)

ProfilerAgent는 수집 후 자기 검증을 수행합니다.

> "이 도구는 실험을 실행하거나 코드/논문을 자율 생성하는가?"
> 단순 검색·요약·검토만 한다면 → **제외**

### 관측성 (W&B Weave)

실행 시 Weave 트레이스 URL이 CLI에 출력됩니다. 모든 LLM 호출, 도구 실행, 에이전트 핸드오프가 자동으로 기록됩니다.

```python
# orchestrator.py — 앱 lifecycle 1회만
weave.init("wandb-smle/autoresearch-researcher")
set_trace_processors([WeaveTracingProcessor()])
```

## 테스트

```bash
# 단위 테스트 (LLM 모킹, 무료)
uv run pytest tests/unit/

# e2e 스모크 테스트 (dry-run, 실제 API 호출 없음)
uv run pytest -m expensive tests/e2e/

# 전체
uv run pytest tests/
```

e2e 테스트는 `@pytest.mark.expensive`로 분리되어 CI에서는 자동 스킵됩니다.

## 비용 가드레일

`--max-cost-usd`(기본 $20) 도달 시 graceful 종료합니다. 진행 중 단계까지의 산출물은 보존됩니다. 부분 실패 후 재실행 시 `_candidates.jsonl`이 있으면 Discovery를 건너뛰고 ProfilerAgent부터 재개합니다.

## 에이전트 프롬프트 커스터마이징

모든 에이전트 지시사항은 `src/autoresearch_researcher/instructions/` 아래 Markdown 파일로 분리되어 있습니다. 코드 수정 없이 프롬프트를 튜닝할 수 있습니다.

```
instructions/
├── discovery.md   # 스코프 정의, 검색 전략
├── profiler.md    # 수집 항목, 스코프 필터 규칙
└── writer.md      # 발행 형식, 톤 가이드
```

## v1 비-목표 (v2 이후)

- feedback.md를 system prompt에 자동 반영
- GitHub releases / RSS 알림
- HTML / 대시보드 출력
- 에이전트 자가 학습
