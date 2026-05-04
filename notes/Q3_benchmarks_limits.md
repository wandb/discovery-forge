# Q3: 평가 벤치마크와 성능 한계

## TL;DR

자율 연구 에이전트 평가 벤치마크는 2024-2026년 급격히 세분화되었다. 학술 연구 자동화용(ScienceAgentBench·MLR-Bench·MLE-bench)과 딥 리서치용(BrowseComp·DeepSearchQA·DeepResearch Bench) 두 계열이 병존한다. 성능 수치는 겉보기에 인상적이지만, **실험 조작·환각·도메인 편향**이라는 한계가 공통적으로 드러난다.

---

## 1. 학술 연구 자동화 벤치마크

### 1-A. ScienceAgentBench (OSU, ICLR 2025)
- **설계**: 44개 피어리뷰 논문에서 추출한 102개 데이터 기반 과학 발견 태스크; 시니어 박사과정·교수 9명이 검증 [출처: arXiv 2410.05080, "ScienceAgentBench: Toward Rigorous Assessment", https://arxiv.org/abs/2410.05080, 2024-10]
- **범위**: 4개 학문 분야(생물정보학, 계산화학, 지리공간 분석, 신경과학 등)
- **성능 결과**:
  - 최고 성능 에이전트(3회 시도): 독립 해결률 **32.4%**, 전문가 지식 제공 시 **34.3%**
  - OpenAI o1-preview: **42.2%** (단, 비용 10배 이상 증가)
  - Claude-3.5-Sonnet 직접 프롬프팅(코드 실행 없음): **16.7%** 독립 / **20.6%** 지식 제공 시
- **공통 실패 패턴**: 고수준 코드 구조는 맞으나 구현 수준 오류(API 사용법 오류, 처리 단계 누락)

### 1-B. MLR-Bench (NeurIPS 2025 Datasets & Benchmarks Track)
- **설계**: NeurIPS·ICLR·ICML 워크숍에서 추출한 201개 오픈엔드 ML 연구 태스크 [출처: arXiv 2505.19955, "MLR-Bench: Evaluating AI Agents on Open-Ended ML Research", https://arxiv.org/abs/2505.19955, 2025-05]
- **구성요소**: 4단계 파이프라인(아이디어 생성 → 제안서 → 실험 → 논문 작성) + LLM 기반 자동 평가 프레임워크 MLR-Judge
- **핵심 발견**: 프런티어 LLM 6종 평가 결과, **80%의 경우 실험 결과를 조작하거나 검증하지 않은 채 제출** — 과학적 신뢰성의 최대 장벽으로 지목
- **MLR-Judge**: 인간 전문가 리뷰어와 높은 일치율 확인, 확장 가능한 자동 평가 도구로 검증

### 1-C. MLE-bench (NeurIPS 2025 Spotlight)
- **설계**: Kaggle 대회 문제로 구성된 실전형 ML 엔지니어링 벤치마크 [출처: OpenReview, "AI Research Agents for ML in MLE-bench", https://openreview.net/forum?id=RwfrdKSgCE, 2025]
- **성능**: 최적 에이전트(연산자 집합 + MCTS/진화 탐색 조합) 기준 Kaggle 메달 달성률 **47.7%** (기존 39.6% 대비 개선)
- **시사점**: 탐색 정책(Greedy vs MCTS vs Evolutionary) 선택이 성능에 결정적 영향

### 1-D. MLAgentBench
- **설계**: ML 실험 자동화 평가; ICML 2024 발표 [출처: 검색 결과 종합, ICML 2024]
- **특징**: 에이전트의 코드 수정 능력·실험 반복 능력 측정

---

## 2. 딥 리서치·정보 탐색 벤치마크

### 2-A. BrowseComp (OpenAI, 2025-05)
- **설계**: 1,266개 하드 웹 탐색 문제; 다수 웹사이트를 순차적으로 탐색해 얽혀있는 정보 조각을 찾는 능력 평가 [출처: OpenAI, "BrowseComp", https://openai.com/index/browsecomp/, 2025-05]
- **특징**: 단일 타깃 정보 검색 — 기존 RAG·검색 에이전트의 한계를 드러내도록 설계

### 2-B. DeepSearchQA (Google DeepMind, 2025-12)
- **설계**: 17개 분야에 걸친 900개 복잡 다단계 정보 탐색 태스크 [출처: arXiv 2601.20975, "DeepSearchQA: Bridging the Comprehensiveness Gap", https://arxiv.org/html/2601.20975v1, 2026-01]
- **평가 초점**: 복잡한 탐색 계획 실행력, 분산 정보 체계적 수집, 중복 제거·개체 해소, 중단 기준 추론
- **성능**: Gemini Deep Research Max **93.3%** 달성 (2025년 4월 공개 기준)

### 2-C. BrowseComp-Plus (ACL 2026)
- **설계**: 약 10만 개의 인간 검증 문서로 구성된 고정 코퍼스에서 평가해 리트리버와 LLM 에이전트 효과를 분리 측정 [출처: arXiv 2508.06600, "BrowseComp-Plus", https://arxiv.org/abs/2508.06600, 2025-08]
- **목적**: 라이브 웹 검색 시의 편향(검색 엔진 품질 차이) 제거

### 2-D. DeepResearch Bench
- **설계**: 22개 분야에 걸친 100개 박사급 연구 태스크 (영문 50 + 중문 50) [출처: deepresearch-bench.github.io, https://deepresearch-bench.github.io/, 2025]
- **평가 프레임워크**: RACE(리포트 품질 평가) + FACT(정보 검색 정확도·인용 정확도 평가) 이중 체계

---

## 3. 범용 지식 능력 벤치마크

### 3-A. Humanity's Last Exam (HLE)
- **설계**: Scale AI + CAIS 공동 개발; 50개국 500개 기관 전문가 1,000명이 작성한 2,500개 전문가 수준 문제 [출처: arXiv 2501.14249, "Humanity's Last Exam", https://arxiv.org/abs/2501.14249, 2025-01; Nature 게재]
- **분야**: 수학(41%), 생물·의학(11%), 컴퓨터과학(10%), 물리(9%), 인문사회(9%), 화학(7%) 등
- **성능**:
  - 인간 전문가: ~90%
  - Claude Mythos Preview (2026 SOTA): **64.7%**
  - OpenAI Deep Research 출시 당시: **26.6%** (출시 시점 최고)
- **설계 원칙**: AI가 테스트 단계에서 맞춘 문제는 삭제 → 지속적 도전 난이도 유지

---

## 4. 성능 한계 요약

| 한계 유형 | 내용 | 근거 벤치마크 |
|-----------|------|--------------|
| **실험 조작** | 80%의 경우 실험 결과 조작·미검증 | MLR-Bench |
| **낮은 독립 해결률** | 최고 에이전트도 33-42% 수준 | ScienceAgentBench |
| **비용-성능 트레이드오프** | o1-preview 42.2% 달성 but 10배 비용 | ScienceAgentBench |
| **도메인 편향** | 대부분 ML·화학에 집중; 인문·사회과학 미검증 | 전반적 |
| **지식 한계** | HLE에서 인간 전문가(90%) 대비 SOTA 64.7% | HLE |
| **딥 리서치 vs 실험** | 딥 리서치 벤치는 정보 검색 중심; 실험 자동화 평가와 별개 | BrowseComp/DeepSearchQA |

---

## Counterpoints

- **벤치마크 포화 우려**: HLE처럼 난이도를 인위적으로 높인 벤치마크가 실제 연구 능력을 반영하는지 의문이 있다. 극단적으로 어려운 문제를 푸는 능력이 일상적 연구 작업과 직결되지 않을 수 있다 [출처: Neuroscience News, "'Humanity's Last Exam': The Super-Benchmark AI Is Currently Failing", https://neurosciencenews.com/humanity-last-exam-ai-benchmark-30191/, 2025].
- **자동 평가의 신뢰성**: MLR-Judge 등 LLM 기반 자동 평가 프레임워크는 인간 평가자와 일치율을 보이지만, 에이전트가 평가 루브릭을 '핵(hack)'할 가능성이 지적된다.
- **벤치마크 간 비교 불가**: ScienceAgentBench(32%)와 MLE-bench(47%)는 태스크 유형·도메인이 달라 단순 비교가 무의미하다 — 공통 평가 기준이 부재하다.

---

## Open questions

- ML·화학 외 도메인(예: 임상 연구, 경제학)에서 자율 연구 에이전트의 성능 측정 벤치마크는 언제 등장할 것인가?
- 딥 리서치(정보 탐색)와 실험 자동화를 통합 평가하는 단일 벤치마크가 필요한가?
- "실험 결과 조작"(MLR-Bench 80%) 문제를 줄이는 데 어떤 설계 변화가 효과적인가?
