# Build Conventions for Claude Code (Ralph Loop)

이 파일은 Claude Code가 매 이터레이션마다 읽는 **빌드 가이드**.
"리서치 에이전트의 런타임 가이드"가 아니라 "에이전트를 빌드하는 코더의 가이드".

---

## Stack

- Python 3.11+
- 패키지 관리자: **`uv`** (pip 사용 금지)
- 프레임워크: `openai-agents` (OpenAI Agents SDK)
- **관측성: `weave` (W&B Weave) — OpenAI Agents SDK trace processor로 자동 통합**
- 모델: `gpt-5` (메인), `gpt-5-mini` (비용 민감 단계)
- 테스트: `pytest`, `pytest-asyncio`
- 환경 변수: `python-dotenv`로 `.env` 로드
  - `OPENAI_API_KEY` (필수)
  - `WANDB_API_KEY` (필수, Weave 트레이싱용)
  - `GITHUB_TOKEN` (선택, GitHub API rate limit 회피용)

---

## 디렉토리 구조

```
src/autoresearch_researcher/
├── __init__.py
├── cli.py                  # 엔트리포인트 (Click 또는 Typer)
├── orchestrator.py         # 흐름 제어
├── agents/
│   ├── __init__.py
│   ├── discovery.py
│   ├── profiler.py
│   └── writer.py
├── instructions/           # 에이전트 프롬프트 (분리 저장)
│   ├── discovery.md
│   ├── profiler.md
│   └── writer.md
├── tools/                  # function_tool 정의
│   ├── __init__.py
│   ├── persistence.py      # save_candidate_tool, save_tool_profile, save_draft, ...
│   ├── github.py           # fetch_github_metadata
│   └── diff.py             # draft vs final diff
└── schemas/                # pydantic 모델
    ├── __init__.py
    ├── candidate.py
    ├── tool_profile.py
    └── sources.py

tests/
├── conftest.py
├── unit/
├── e2e/
└── fixtures/

weekly_runs/                # 출력 (.gitignore)
└── .gitkeep
```

---

## OpenAI Agents SDK 핵심 패턴

### Agent 정의

```python
from agents import Agent, WebSearchTool

def build_profiler_agent() -> Agent:
    return Agent(
        name="ProfilerAgent",
        instructions=load_instructions("profiler"),
        tools=[
            WebSearchTool(),
            fetch_github_metadata,
            save_tool_profile,
        ],
        model="gpt-5",
    )
```

### Function tool

```python
from agents import function_tool
from pydantic import BaseModel

class ToolProfile(BaseModel):
    slug: str
    name: str
    license: str
    domains: list[str]
    autonomy_level: str
    interface: str
    resource_requirements: str
    last_commit: str | None
    stars: int | None
    pricing_note: str
    key_limitations: list[str]
    sources: list[int]  # source IDs

@function_tool
def save_tool_profile(profile: ToolProfile) -> str:
    """Persist a tool profile as tools/{slug}.md with YAML front-matter."""
    ...
```

### Runner

```python
from agents import Runner

result = await Runner.run(
    agent,
    input=prompt,
    max_turns=15,
)
```

### Tracing (W&B Weave)

Weave는 OpenAI Agents SDK의 trace processor를 통해 모든 에이전트 실행, 도구 호출, 모델 추론을 자동으로 캡처. 코드는 init + processor 등록 한 번이면 끝.
Read from https://docs.wandb.ai/weave/quickstart.md so I can ask questions about it.

```python
# orchestrator.py 시작부 (앱 lifecycle 1회만)
import weave
from agents import set_trace_processors
from weave.integrations.openai_agents.openai_agents import WeaveTracingProcessor

def init_observability(week_id: str):
    weave.init("wandb-smle/autoresearch-researcher")
    set_trace_processors([WeaveTracingProcessor()])

# 실행 시점에 attribute로 태깅 (주차별 필터링 가능)
import weave

async def run_briefing(week_id: str):
    with weave.attributes({"week": week_id, "stage": "discovery"}):
        await Runner.run(discovery_agent, ...)
    with weave.attributes({"week": week_id, "stage": "profiling"}):
        for candidate in candidates:
            await Runner.run(profiler_agent, ...)
    with weave.attributes({"week": week_id, "stage": "writing"}):
        await Runner.run(writer_agent, ...)
```

**자체 함수 트레이싱**: `@weave.op` 데코레이터로 일반 함수도 트레이스에 포함.
```python
@weave.op
def verify_citations(report: str, sources: list[Source]) -> list[str]:
    ...
```

**Weave 셋업**:
- `wandb login` 으로 로컬 인증 (또는 `WANDB_API_KEY` 환경변수)
- 첫 실행 시 콘솔에 트레이스 URL 출력됨 — 이걸 CLI 출력에도 echo

---

## WebSearchTool 제약

- **Responses API 모델 한정**: `gpt-5`, `gpt-5-mini`, `gpt-4o` 계열
- 다른 provider 모델은 빌트인 검색 안 됨 (필요시 Tavily/Brave를 function_tool로 wrap)

---

## 테스트 비용 절감

### 단위 테스트 (mocked LLM)

```python
from unittest.mock import AsyncMock, patch

async def test_profiler_filters_out_deep_research():
    with patch("agents.Runner.run") as mock_run:
        mock_run.return_value.final_output = ToolProfile(
            slug="some-deep-research-tool",
            autonomy_level="analyst",  # 실험 실행 안 함
            ...
        )
        result = await profile_candidate(candidate)
        assert result.is_rejected
        assert "deep research" in result.rejection_reason.lower()
```

### E2E 테스트

- 작은 카테고리 1개만 (`--max-tools 3`)
- `@pytest.mark.expensive` 마커
- CI에서는 스킵, 로컬 `pytest -m expensive`로만
- 비용 상한 강제 (`--max-cost-usd 2`)

```python
@pytest.mark.expensive
async def test_e2e_smoke_run(tmp_path):
    result = await run_weekly_briefing(
        week="2026-W99-test",
        max_tools=3,
        max_cost_usd=2.0,
        output_dir=tmp_path,
    )
    assert (tmp_path / "draft.md").exists()
    assert (tmp_path / "comparison_table.md").exists()
    tools_dir = tmp_path / "tools"
    assert len(list(tools_dir.glob("*.md"))) >= 3
```

---

## 에이전트 instructions 작성 규칙

`src/autoresearch_researcher/instructions/{agent_name}.md`로 분리.

이유:
1. 코드 변경 없이 프롬프트 튜닝
2. v2에서 feedback 반영 시 이 파일만 수정
3. 버전 관리로 프롬프트 변천 추적

`load_instructions("profiler")` 함수가 파일 읽어서 string 반환.

---

## 인용 무결성 (US6)

```python
# schemas/sources.py
class Source(BaseModel):
    id: int
    url: str
    title: str
    fetched_at: datetime
    used_in: list[str]  # tool slugs

# WriterAgent 출력 검증
import re
def verify_citations(report: str, sources: list[Source]) -> list[str]:
    cited_ids = {int(m) for m in re.findall(r'\[\^(\d+)\]', report)}
    available_ids = {s.id for s in sources}
    
    errors = []
    if not cited_ids.issubset(available_ids):
        errors.append(f"Missing source IDs: {cited_ids - available_ids}")
    
    orphans = available_ids - cited_ids
    if orphans:
        errors.append(f"Orphan sources (in jsonl but never cited): {orphans}")
    
    return errors
```

---

## Sources of Truth (의문이 들 때 참조)

- OpenAI Agents SDK 문서: https://openai.github.io/openai-agents-python/
- WebSearchTool / FileSearchTool: docs/tools/ 페이지
- 공식 cookbook: https://cookbook.openai.com (Deep Research API와 Agents SDK 패턴)
- **W&B Weave + OpenAI Agents 통합**: https://weave-docs.wandb.ai/guides/integrations/openai_agents/
- **Weave 기본 사용법**: https://weave-docs.wandb.ai/ (`@weave.op`, `weave.attributes`, evaluations)

---

## 절대 금지 (Ralph가 자주 깨는 부분)

- ❌ **시드 도구명을 코드에 하드코딩** ("AI Scientist", "Agent Laboratory" 등). 
  → DiscoveryAgent가 검색으로 발견해야 함. 카테고리 정의만 instructions에.
- ❌ **pip 사용**. 항상 `uv add`, `uv run`, `uv sync`.
- ❌ API 키를 코드/테스트/주석/git에 노출.
- ❌ E2E 테스트에서 `--max-cost-usd` 미설정.
- ❌ ProfilerAgent의 자체 스코프 필터 우회 (딥 리서치 도구가 슬그머니 들어가는 흔한 실패).
- ❌ Agent의 instructions를 코드에 하드코딩. 항상 `instructions/*.md` 파일에서 로드.
- ❌ `WebSearchTool` 빌트인을 일반 ChatCompletions 모델에 사용 시도 (Responses API 모델 한정).
- ❌ **`weave.init()`을 매 실행마다 여러 번 호출** — 앱 lifecycle 1회만 (orchestrator 진입점에서).
- ❌ **`set_trace_processors`로 OpenAI 기본 processor를 덮어쓰지 않고 추가** — 항상 `set_trace_processors([WeaveTracingProcessor()])`로 *교체* (add 아님).
- ❌ 단위 테스트(모킹)에서 실제 `weave.init` 호출 — 토큰 절감 + 테스트 격리 위해 fixture로 mock.

---

## TDD 규칙

매 User Story마다:

1. **Red**: 실패하는 테스트 먼저 작성. 단위 테스트 1개 + (관련되면) e2e 1개.
2. **Green**: 최소 구현으로 통과.
3. **Refactor**: 통과 상태 유지하며 정리.
4. **Commit**: `uv run pytest tests/` 통과 후 커밋. 커밋 메시지는 `US{N}: {간단 설명}`.

---

## Logged learnings

(Ralph가 매 이터레이션 후 1줄씩 추가)

<!-- 여기 아래로 빈 칸. Ralph가 채움. -->
- US1: uv sync 후 VIRTUAL_ENV 환경변수가 다른 venv를 가리키면 경고 발생 — `uv run`은 정상 동작하지만, `.venv` 활성화 전에 다른 venv가 VIRTUAL_ENV에 설정된 상태이면 경고 출력됨 (무시 가능).
- US2: Typer CLI에서 `asyncio.run()`으로 async orchestrator 호출 시 테스트에서 `AsyncMock` patch 위치는 `autoresearch_researcher.cli.run_briefing`으로 지정해야 함 — 모듈 경로가 틀리면 mock이 적용 안 됨.
- US3: `@function_tool`로 정의된 도구는 Agent 생성자 내부 클로저에서 `output_dir`를 캡처해야 함 — 외부에서 파일 경로를 인자로 받으면 Agent가 경로를 모르므로, `build_*_agent(output_dir)` 패턴으로 클로저 바인딩 필수.
- US4: `is_experiment_automation()` 같은 순수 헬퍼 함수를 에이전트 모듈에 분리하면 LLM 모킹 없이 스코프 필터 로직을 단위 테스트할 수 있음 — LLM 판단과 규칙 기반 필터를 레이어로 분리하는 것이 테스트 가능성의 핵심.
- US5: WriterAgent의 `read_tool_profiles_tool`은 `_body` 키를 제거하고 JSON 직렬화해야 context window를 낭비하지 않음 — 전체 본문이 필요할 때는 `get_tool_body_tool(slug)`를 별도 호출하는 패턴이 토큰 효율적.
- US6: `SourceRegistry`에서 같은 URL 재등록 시 `used_in`을 업데이트하고 파일 전체 재작성 필요 — append-only JSONL은 중복 ID 생성 위험이 있어 dedup은 in-memory dict + 재작성이 안전.
- US7: `CostBudget.add()`는 내부적으로 `check()`를 호출해 즉시 raise함 — 테스트에서 "이미 초과된 상태"를 만들려면 `budget._total`을 직접 설정한 뒤 `check()`를 별도 호출해야 함. add로 over 상태를 만들려 하면 test setup 단계에서 raise됨.
- US8: `difflib.unified_diff`의 출력 라인은 `\n`으로 끝나므로 classify 시 `line.rstrip()` 후 패턴 매칭 필요 — 그렇지 않으면 정규식 앵커(`^`)가 줄 끝 공백과 충돌해 오탐 발생 가능.
- US9: `shutil.move(str(src), str(dst))`에서 경로를 `str()`로 변환해야 함 — Python 3.11 이하에서 `Path` 객체 직접 전달 시 타입 오류 가능, `str()` 래핑이 안전.