# PRD: autoresearch researcher Tool Briefing Agent (v1)

## 개요

매주 1회 실행되어 **실험 자동화(experiment automation) 계열 자율 연구 도구**를 조사하고, 공개 발행 가능한 비교 가이드(MD)를 생성하는 멀티에이전트 시스템.

## v1의 목표

- 주 1회 자동 실행으로 도구 인벤토리 + 비교 가이드 발행
- 사람(본인)이 매주 검수하여 final 발행본 + feedback 작성
- v2에서 이 feedback을 system prompt 개선 데이터로 활용 (이번 v1 범위 아님)

## 스코프 정의 (이게 이 프로젝트의 가장 중요한 부분)

### IN: 실험 자동화 계열

코드 작성, 실험 실행, 논문/리포트 생성을 자동화하는 시스템.
가설 → 실험 → 결과 → 글쓰기 사이클의 일부 또는 전체를 수행.

카테고리 (에이전트가 직접 발견할 것 — 본 PRD에는 시드 도구명을 의도적으로 박지 않음):

- 종단간 논문 생성 시스템
- ML 실험 루프 자동화 도구
- 화학·생물 실험 자동화 시스템
- 가설 생성/탐색 에이전트

### OUT: 명시적 제외

- 딥 리서치(Deep Research) 계열 — 웹 문헌 종합·분석만 하고 실험 실행이 없는 시스템
- 일반 LLM 기반 RAG / 검색 보조
- 일반 코딩 어시스턴트 (Cursor, Copilot 등)
- 일반 AI 에이전트 (autoGPT 류)

**필터 룰** (ProfilerAgent가 자체 적용):
> 이 도구는 "실험을 실행하거나 코드/논문을 자율 생성"하는가? 단순 검색·요약·검토만 한다면 OUT.

## 입력

주차 식별자 (예: `2026-W19`). CLI로 받음, cron 등 자동화 가능.

## 출력 구조

```
weekly_runs/2026-W19/
├── draft.md                  # 메인 발행 초안
├── comparison_table.md       # 비교 표 단독 파일
├── tools/
│   ├── {tool_slug}.md        # 도구별 상세 카드
│   └── ...
├── sources.jsonl             # 모든 인용 출처
├── run_metadata.json         # 실행 정보 (시각, 모델, 토큰, 비용)
└── (이후 사람이 작성)
    ├── final.md              # 사람이 검수·수정한 발행본
    ├── feedback.md           # 구조화된 피드백
    └── diff.md               # draft vs final 자동 diff
```

## 발행물 형식 (draft.md)

### 필수 섹션
1. **헤더**: 주차, 발행일, 다룬 도구 수, 출처 수
2. **이번 주 하이라이트**: 새 출시·중대 업데이트 3-5개 (없으면 "주요 업데이트 없음" 명시)
3. **유스케이스별 추천 매트릭스**: "당신의 상황 → 추천 도구" 표
4. **전체 비교 표**: 도구 × 속성 매트릭스
5. **도구별 카드**: 각 도구 1단락 + 링크
6. **알려진 한계 / 신뢰성 이슈**: 카테고리 전체에 걸친 경고
7. **참고 출처**

### 비교 표 컬럼 (최소)

| 컬럼 | 예시 값 |
|------|---------|
| 도구 이름 | (도구명) |
| 라이선스 | Apache 2.0 / MIT / Commercial / Custom |
| 도메인 | ML / Chemistry / Biology / General |
| 자율성 수준 | Tool / Analyst / Scientist (또는 자체 정의 + 근거) |
| 인터페이스 | CLI / Python lib / Web / API |
| 리소스 요구사항 | 단일 GPU / 멀티 GPU / 실험실 장비 / Cloud only |
| GitHub 활성도 | 마지막 커밋 시점, stars |
| 가격 / TCO 메모 | 무료 / $X/mo / TCO 메모 |
| 핵심 한계 | 1줄 |

## 아키텍처: 3 에이전트

```
Orchestrator (CLI entrypoint)
  │
  ├─→ DiscoveryAgent
  │     입력: PRD의 IN/OUT 스코프 정의
  │     도구: WebSearchTool, save_candidate_tool
  │     출력: tools/_candidates.jsonl
  │
  ├─→ ProfilerAgent (도구별 1회 호출)
  │     입력: 후보 도구 1개
  │     도구: WebSearchTool, fetch_github_metadata, save_tool_profile
  │     스코프 필터: "이게 정말 실험 자동화인가?" 자체 검증
  │     출력: tools/{slug}.md
  │
  └─→ WriterAgent
        입력: 모든 tools/{slug}.md
        도구: save_draft, save_comparison_table
        출력: draft.md, comparison_table.md
```

핸드오프는 직접 안 시키고 Orchestrator가 흐름 제어. 디버깅 단순화 + 비용 추적 일원화.

## User Stories

### US1: 프로젝트 부트스트랩
- [x] `uv` + `pyproject.toml` 설정
- [x] 의존성: `openai-agents`, `weave`, `pytest`, `pytest-asyncio`, `python-dotenv`
- [x] `.env.example` 템플릿 (`OPENAI_API_KEY`, `WANDB_API_KEY`, `GITHUB_TOKEN` 선택)
- [x] `.gitignore` (`.env`, `weekly_runs/`, `__pycache__/`, `.venv/`, `wandb/`)
- [x] `tests/` 폴더와 `conftest.py` 셋업

### US2: CLI 엔트리포인트
- [x] `autoresearch-researcher run --week 2026-W19 [--max-tools 12] [--max-cost-usd 20] [--dry-run]`
- [x] `weekly_runs/{week}/` 폴더 자동 생성 (이미 존재 시 `--rerun` 없으면 abort)
- [x] `run_metadata.json` 시작 시점 기록
- [x] 종료 시 토큰/비용/소요시간 누적 기록

### US3: DiscoveryAgent
- [x] 스코프 정의를 `instructions/discovery.md`에 분리 저장
- [x] WebSearchTool로 카테고리별 검색 자동 수행
- [x] **검색어는 카테고리·일반 용어만**, 구체적 도구명 시드 금지
- [x] 후보 N개를 `_candidates.jsonl`로 저장 (이름, URL, 1줄 설명, 발견 카테고리)
- [x] 명백한 OUT 카테고리(딥 리서치 제품 등)는 발견 즉시 제외하고 reason 기록

### US4: ProfilerAgent
- [x] 각 후보에 대해 다음 수집:
  - 공식 페이지 / 논문 / GitHub URL
  - 라이선스 (LICENSE 파일 또는 페이지에서 추출)
  - GitHub 활성도 (마지막 커밋, stars, open issues) — `fetch_github_metadata` 도구
  - 도메인 분류 (다중 가능)
  - 자율성 수준 (자체 정의 + 근거)
  - 인터페이스 / 리소스 요구사항
  - 알려진 한계 (1차 출처 우선)
- [x] **자체 스코프 필터**: 수집 후 "실험 자동화 정의에 맞는가" 자기 검증, 불일치 시 reject
- [x] 결과는 `tools/{slug}.md` (YAML front-matter + 본문)
- [x] 모든 사실 주장에 출처 (sources.jsonl 등록)

### US5: WriterAgent
- [x] 모든 `tools/*.md`를 읽고 통합
- [x] 비교 표 자동 생성 (모든 컬럼 채워짐, 빈 셀은 "unknown" 명시)
- [x] 유스케이스별 매트릭스 (단일 GPU / 멀티 GPU / 엔터프라이즈 / 데이터 프라이버시 등)
- [x] 이번 주 하이라이트 식별 (지난 주 폴더가 있으면 비교, 없으면 "첫 발행")
- [x] 모든 사실 주장에 인용 (`[^N]` + sources.jsonl 매핑)
- [x] 톤: 정보 제공 위주, 마케팅 언어 금지

### US6: 출처 무결성
- [x] 모든 인용은 sources.jsonl 등록된 URL만 사용
- [x] sources.jsonl 항목: `id, url, title, fetched_at, used_in (도구 slug 목록)`
- [x] 자동 검증: `[^N]` 참조가 모두 sources.jsonl에 존재하는가
- [x] 자동 검증: sources.jsonl의 모든 URL이 본문 어딘가에서 인용되는가 (orphan 출처 경고)

### US7: 비용·실행 가드레일 + 트레이싱
- [x] `--max-cost-usd 20` (기본값) 도달 시 graceful 종료
  - 진행 중 단계까지의 산출물은 보존
- [x] **W&B Weave 트레이싱** 활성화
  - `weave.init(project="autoresearch-researcher")` 1회 호출
  - `set_trace_processors([WeaveTracingProcessor()])`로 OpenAI Agents 자동 캡처
  - 각 주차 실행을 Weave attribute로 태깅: `weave.attributes({"week": week_id})`
  - 모든 LLM 호출, function tool, 에이전트 핸드오프가 자동으로 트레이스 트리에 기록
- [x] 토큰/비용 누적 기록을 `run_metadata.json`에 (Weave는 별도 대시보드, 로컬 사본도 보관)
- [x] CLI 출력에 Weave 트레이스 URL 표시 (사후 검수 시 바로 클릭 가능)

### US8: Diff 인프라 (피드백 루프 시드)
- [ ] CLI 서브커맨드: `autoresearch-researcher diff --week 2026-W19`
  - 본인이 `final.md` 작성 후 실행
  - `draft.md` vs `final.md`를 라인별 + 의미 분류 diff로 `diff.md` 생성
  - 분류: ADD(추가된 도구), FIX(사실 수정), REMOVE, REWORD, BALANCE
- [ ] `feedback.md` 템플릿 자동 생성 (사람이 채워넣을 양식, 아래 참조)

### US9: 재실행 안전성
- [ ] `--rerun` 플래그로 같은 주차 재실행 허용 (이전 폴더 백업)
- [ ] 부분 실패 시 `_candidates.jsonl` 활용해 ProfilerAgent부터 재개

## feedback.md 템플릿 (US8에서 자동 생성)

```markdown
# Week {week} Feedback

## 발행 결정: ✅ as-is / ⚠️ minor edits / 🔴 major rewrite / ❌ reject

## 정량 점수 (1-5)
- 정확성: 
- 완전성 (누락 도구 없는가): 
- 표 가독성: 
- 균형성 (낙관/비관 출처): 
- 최신성: 

## 수정 사항 (구조화)
- [ADD] 
- [FIX] 
- [REMOVE] 
- [REWORD] 
- [BALANCE] 

## 시스템 개선 제안
- DiscoveryAgent: 
- ProfilerAgent: 
- WriterAgent: 

## 패턴 메모 (3주 이상 반복되는 이슈만)
```

## 검증 (smoke test 수준)

빌드 통과 기준:
- [ ] `uv run pytest tests/` 전체 통과
- [ ] 단위 테스트: 각 에이전트 (LLM 모킹)
- [ ] e2e 테스트 1개: `--max-tools 3 --max-cost-usd 2` dry-run, 비용 < $2
- [ ] e2e 산출물 검증:
  - tools/ 폴더에 도구 3개 이상 (스코프 IN인 것만)
  - comparison_table.md 모든 컬럼 채워짐 (unknown OK)
  - 인용 무결성 통과
  - 명백한 OUT 도구(예: GPT-Researcher, Perplexity)가 결과에 안 들어감

**의도적으로 측정하지 않는 것**: 발행물의 "품질". 이건 사람 검수가 평가. v1은 "동작하는 파이프라인" 검증까지.

## 완료 조건

모든 User Stories 체크박스 ✅ + smoke test 전체 통과 + 실제 1회 dry-run으로 `weekly_runs/2026-W19/`에 유효한 산출물 생성 시:

`<promise>BRIEFING_AGENT_READY</promise>`

## v1 명시적 비-목표 (v2 이후)

- feedback.md를 자동으로 system prompt에 반영하는 메커니즘
- 도구 출시·업데이트 자동 알림 (RSS, GitHub releases watching)
- HTML/대시보드 출력
- 다국어
- 도구별 GitHub stars 추이 그래프
- 에이전트 자가 학습 / RL