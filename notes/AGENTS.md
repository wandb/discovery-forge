# Research Agent Conventions

## Source priority
1차 (논문, 공식 문서, 코드 저장소) > 2차 (Tech 매체, 신뢰 블로그) > 3차 (커뮤니티 글)

## Note format
- 파일명: notes/{Q_ID}_{slug}.md
- 모든 주장 끝에 `[출처: title, url, YYYY-MM]`
- 반대/대안 관점은 ## Counterpoints 섹션에 별도 정리

## Verification gates (이터레이션 종료 전 체크)
- [ ] min_sources 충족
- [ ] 1차 출처 1개 이상
- [ ] Counterpoints 섹션 비어있지 않음
- [ ] 모든 사실 주장에 출처

## Logged learnings
(이 섹션은 에이전트가 매 이터레이션 후 추가)

### iter SYNTH (2026-05-04)
- 종합 리포트에서 딥 리서치 vs 실험 자동화 두 계열 분리가 전체 분야를 이해하는 가장 중요한 구조적 통찰임 — 이 구분이 없으면 성능 수치 비교가 무의미해짐.
- 수치(80% 결과 조작, 82% 허위 논문 통과, 19.9% 인용 환각)를 한 섹션에 묶어 제시하면 독자 임팩트가 분산 제시보다 훨씬 강함.
- SYNTH는 새 출처 추가 없이 Q1~Q5 내용 종합이므로 sources.jsonl 업데이트 불필요 — 이터레이션 효율 확보.

### iter Q5 (2026-05-04)
- 상용 vs 오픈소스 비교 시 "비용 = 구독료"로 단순화하면 안 됨 — 오픈소스는 구독료 없지만 인프라·유지보수 비용이 실질적으로 발생.
- GPT-Researcher의 CMU DeepResearchGym 1위는 유력하나, 해당 벤치마크의 독립 검증 여부와 비교 대상 버전 확인 필요 — SYNTH에서 조건부 언급.
- 딥 리서치(정보 탐색)와 실험 자동화(ML 연구)는 상용/오픈소스 모두 완전히 별개 카테고리 — 혼동 방지를 위해 SYNTH에서도 분류 유지.

### iter Q4 (2026-05-04)
- 실험 날조(80%, MLR-Bench)와 인용 환각(19~55%, 모델별)은 별개 현상이나 동일 파이프라인에서 복합 발생 — 둘을 구분해서 다뤄야 독자 혼선 없음.
- BadScientist(arXiv 2510.18003)는 AI-only 출판 루프 취약성의 핵심 1차 출처로 SYNTH에서 강조할 것.
- 재현성 문제는 AI만의 이슈가 아닌 점(기존 과학 재현성 위기)을 counterpoint에 포함하면 균형 잡힌 서술 가능.

### iter Q3 (2026-05-04)
- 학술 연구 자동화 벤치마크(ScienceAgentBench·MLR-Bench)와 딥 리서치 벤치마크(BrowseComp·DeepSearchQA)는 측정 대상이 달라 교차 비교 시 명확히 구분 필요.
- MLR-Bench의 "80% 실험 조작" 발견이 Q4(실패 모드) 핵심 데이터로 재활용 가능.
- 벤치마크 포화 주기(기존 벤치 → 에이전트 포화 → 새 벤치 출시)가 빨라지고 있어 최신 수치 확인 시 발행 날짜 검증 필수.

### iter Q2 (2026-05-04)
- 학계 시스템(AI Scientist, AI-Researcher, Agent Lab)과 산업계 딥 리서치(OpenAI/Google/Perplexity)는 목적·범위가 달라 별도로 분류해야 비교 가능.
- Sakana AI의 "피어리뷰 통과" 주장은 nuanced — 리뷰어 사전 고지·3편 중 1편 통과라는 맥락을 함께 기록해야 편향 없음.
- 도메인 편향(ML 집중) 메모가 Q3·Q4 작성 시 재사용 가능한 핵심 약점임.

### iter Q1 (2026-05-04)
- "autoresearch"는 Karpathy 특정 도구(2026-03 공개)와 광의의 자율 연구 에이전트 개념 모두를 지칭하므로 문맥 구분이 필수.
- arXiv 직접 fetch는 일부 차단되므로 abstract 페이지(arxiv.org/abs/...)를 우선, html 버전은 선택적 시도.
- Tool/Analyst/Scientist 3단계 분류(arXiv 2505.13259, EMNLP2025)가 자율성 스펙트럼 설명에 유용한 공통 프레임.