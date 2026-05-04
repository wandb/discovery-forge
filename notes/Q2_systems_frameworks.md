# Q2: 주요 시스템·프레임워크 (2024-2026, 학계+산업)

## TL;DR

2024-2026년 사이 학계와 산업계 모두에서 자율 연구 에이전트 구현이 폭발적으로 증가했다. Sakana AI의 AI Scientist 시리즈가 "AI가 피어리뷰를 통과한 논문을 생성"하는 이정표를 세웠고, HKUDS의 AI-Researcher(NeurIPS2025)·Schmidgall의 Agent Laboratory(ICLR2025)가 종단간 파이프라인을 고도화했다. 산업계에서는 OpenAI Deep Research·Google Gemini Deep Research·Perplexity가 상용 딥 리서치 에이전트 시장을 형성했으며, Karpathy의 autoresearch는 ML 실험 자동화를 대중화했다.

---

## 1. 학계 시스템

### 1-A. AI Scientist v1 (Sakana AI, 2024)
- **개요**: LLM이 아이디어 생성 → 코드 작성 → 실험 → 논문 작성 → 자체 동료 평가까지 완전 자동화하는 최초의 종단간 시스템 [출처: Sakana AI, "The AI Scientist", https://sakana.ai/ai-scientist/, 2024-08]
- **능력**: 논문 1편당 ~$15 비용, ML 분야(확산 모델·트랜스포머 등) 집중
- **한계**: 인간 작성 코드 템플릿에 의존; 특정 ML 도메인에 한정
- **Nature 게재**: AI Scientist v1 논문이 Nature(2026)에 게재 [출처: Sakana AI, "The AI Scientist: Now Published in Nature", https://sakana.ai/ai-scientist-nature/, 2026]

### 1-B. AI Scientist v2 (Sakana AI, 2025)
- **개요**: 코드 템플릿 의존성 제거, Agentic Tree Search 방법론으로 개방형 아이디어 탐색 [출처: arXiv 2504.08066, "The AI Scientist-v2: Workshop-Level Automated Scientific Discovery", https://arxiv.org/abs/2504.08066, 2025-04]
- **핵심 성과**: ICLR 2025 워크숍에 3편 제출 → 1편 동료 평가 통과 (평균 점수 6.33, 리뷰어 점수 6/7/6). 완전 AI 생성 논문이 피어리뷰를 통과한 최초 사례 [출처: Sakana AI blog, "The AI Scientist Generates its First Peer-Reviewed Scientific Publication", https://sakana.ai/ai-scientist-first-publication/, 2025-03]
- **설계**: 전담 실험 관리 에이전트(experiment manager agent)가 트리 탐색 관리

### 1-C. AI-Researcher (HKUDS, NeurIPS 2025 Spotlight)
- **개요**: 완전 자율 연구 시스템으로 문헌 검토 → 아이디어 생성 → 알고리즘 설계·구현·검증 → 논문 작성 3단계 구조 [출처: arXiv 2505.18705, "AI-Researcher: Autonomous Scientific Innovation", https://arxiv.org/abs/2505.18705, 2025-05]
- **사용자 입력**: 수준 1(상세 아이디어 설명) 또는 수준 2(참고 논문만 제공, 아이디어는 시스템이 생성)
- **성과**: 22개 벤치마크 논문에서 인간 수준에 근접하는 구현 성공률; NeurIPS2025 Spotlight 채택
- **상용화**: novix.science에서 프로덕션 버전 운영

### 1-D. Agent Laboratory (Schmidgall et al., ICLR/EMNLP 2025)
- **개요**: 인간이 제공한 연구 아이디어를 받아 문헌 검토 → 실험 → 리포트 작성 3단계 자율 수행 [출처: arXiv 2501.04227, "Agent Laboratory: Using LLM Agents as Research Assistants", https://arxiv.org/abs/2501.04227, 2025-01]
- **특징**: 인간 피드백 루프 제공 시 품질 유의미하게 향상; o1-preview 백엔드에서 최고 성과
- **비용 절감**: 기존 자율 연구 방법 대비 연구 비용 84% 감소
- **코드**: GitHub SamuelSchmidgall/AgentLaboratory

### 1-E. ResearchAgent (Baek et al., 2024)
- **개요**: 리뷰 에이전트 피드백을 반영해 연구 아이디어 생성·실험 설계·반복 개선 자동화 [출처: 검색 결과 종합, "Agentic AI for Scientific Discovery Survey", https://arxiv.org/html/2503.08979v1, 2025-03]
- **한계**: 체계적 문헌 검토 기능 부재 — 아이디어가 기존 지식에 기반하지 않을 위험

### 1-F. AgentRxiv (2025)
- **개요**: 자율 연구 에이전트들이 프리프린트를 공유·상호 참조하며 협력하는 분산 연구 인프라 [출처: arXiv 2503.18102, "AgentRxiv: Towards Collaborative Autonomous Research", https://arxiv.org/html/2503.18102v1, 2025-03]
- **의의**: 멀티에이전트 협업 연구 생태계 구축 시도

### 1-G. Coscientist (CMU/Boiko et al., Nature 2023)
- **개요**: GPT-4 기반으로 화학 실험을 자율 설계·계획·실행하는 시스템 [출처: Nature, "Autonomous chemical research with large language models", https://www.nature.com/articles/s41586-023-06792-0, 2023-12]
- **능력**: 웹 검색·문서 분석·코드 실행·로봇 자동화 통합; 팔라듐 촉매 크로스커플링 반응 최적화 성공
- **의의**: 자연과학 영역 자율 실험의 선구적 구현; 재현 가능하고 재사용 가능한 데이터셋 생성 강조

---

## 2. 산업계 시스템

### 2-A. OpenAI Deep Research (출시 2025-02-02)
- **개요**: 단일 프롬프트를 받아 5~30분간 수십 개 출처를 자율 탐색 후 인용 포함 리포트 반환 [출처: AI Unfiltered, "OpenAI Deep Research Launches February 2", https://www.arturmarkus.com/openai-deep-research-launches-february-2-with-26-6-on-humanitys-last-exam-o3-powered-agent-autonomously-researches-for-5-30-minutes-beats-deepseek-r1-by-177/, 2025-02]
- **성능**: Humanity's Last Exam 26.6% (출시 시점 최고), o3 파워드
- **엔터프라이즈**: Azure AI Foundry에서 프로그래밍 방식 호출; Google Drive·SharePoint 등 MCP 커넥터 지원 [출처: AgentMarketCap, "OpenAI Deep Research Goes Enterprise", https://agentmarketcap.ai/blog/2026/04/08/openai-deep-research-enterprise-autonomous-research-agent, 2026-04]

### 2-B. Google Gemini Deep Research (출시 2024-12)
- **개요**: Gemini 2.5 Pro(2025-05 업그레이드) 기반 자율 연구 에이전트 [출처: TechCrunch, "Google launched its deepest AI research agent", https://techcrunch.com/2025/12/11/google-launched-its-deepest-ai-research-agent-yet-on-the-same-day-openai-dropped-gpt-5-2/, 2025-12]
- **Deep Research Max**: Gemini 3.1 Pro 기반, DeepSearchQA 93.3%, BrowseComp 85.9% [출처: davidborish.com, "Google's New Deep Research Max Agent Scores 93%", https://www.davidborish.com/post/google-s-new-deep-research-max-agent-scores-93-on-benchmarks, 2025]

### 2-C. Perplexity Deep Research / Sonar API (출시 2025-02-14)
- **개요**: 딥 리서치를 3분 내 완료하는 속도 중심 설계; 유일하게 종량제 API 제공 ($2/$8 per million tokens) [출처: Glasp, "Deep Research Tools Compared", https://glasp.co/articles/deep-research-tools-compared, 2026]
- **규모**: 2026년 초 기준 $200억 밸류에이션, 월 7.8억 쿼리, $2억 ARR [출처: 검색 결과 종합]

### 2-D. Karpathy autoresearch (출시 2026-03-06)
- **개요**: 단일 GPU 위에서 AI 에이전트가 밤새 ML 실험을 자율 반복하는 630줄 Python 프레임워크 [출처: DataCamp, "A Guide to Andrej Karpathy's AutoResearch", https://www.datacamp.com/tutorial/guide-to-autoresearch, 2026-03]
- **특징**: 외부 의존성 최소화; 1주일 만에 GitHub 스타 30,307개
- **범위**: ML 훈련 실험 자동화에 특화

---

## 3. 주요 인프라·프로토콜

- **MCP (Anthropic Model Context Protocol)**: 에이전트가 외부 도구·DB·API에 연결하는 표준 프로토콜로 2025년 광범위 채택 [출처: 검색 결과 종합]
- **A2A (Google Agent-to-Agent Protocol)**: 에이전트 간 통신 표준
- **시장 전망**: 에이전틱 AI 시장 $78억(현재) → $520억+(2030) 예상; 2026년 말 기업 애플리케이션의 40%에 AI 에이전트 내장 예상 [출처: MachineLearningMastery, "7 Agentic AI Trends to Watch in 2026", https://machinelearningmastery.com/7-agentic-ai-trends-to-watch-in-2026/, 2026]

---

## 4. 시스템 비교 요약표

| 시스템 | 주체 | 연도 | 도메인 | 자율성 | 특이점 |
|--------|------|------|--------|--------|--------|
| Coscientist | CMU | 2023 | 화학 | 높음 | 실제 로봇 실험 실행 |
| AI Scientist v1 | Sakana AI | 2024 | ML | 매우 높음 | 종단간, $15/편 |
| ResearchAgent | Baek et al. | 2024 | ML | 중간 | 아이디어 생성 특화 |
| Gemini Deep Research | Google | 2024-12 | 범용 | 높음 | 93.3% DeepSearchQA |
| OpenAI Deep Research | OpenAI | 2025-02 | 범용 | 높음 | HLE 26.6%, 엔터프라이즈 |
| AI Scientist v2 | Sakana AI | 2025 | ML | 매우 높음 | 최초 피어리뷰 통과 |
| Agent Laboratory | Schmidgall | 2025 | ML | 높음 | 비용 84% 절감 |
| AI-Researcher | HKUDS | 2025 | ML/범용 | 매우 높음 | NeurIPS Spotlight |
| AgentRxiv | 오픈 | 2025 | 범용 | 높음 | 분산 협력 생태계 |
| autoresearch | Karpathy | 2026 | ML 실험 | 높음 | 단일 GPU, 오픈소스 |

---

## Counterpoints

- **AI Scientist 피어리뷰 통과의 한계**: TechCrunch 등이 지적하듯, 3편 중 1편만 통과했고 리뷰어에게 AI 생성 가능성을 사전 고지했다 — 진정한 블라인드 피어리뷰 통과와는 다르다는 비판 존재 [출처: TechCrunch, "Sakana claims its AI-generated paper passed peer review — but it's a bit more nuanced", https://techcrunch.com/2025/03/12/sakana-claims-its-ai-paper-passed-peer-review-but-its-a-bit-more-nuanced-than-that/, 2025-03]
- **도메인 편향**: 대부분 시스템이 ML·화학에 집중; 사회과학·인문학·복잡계 연구로의 확장은 검증이 부족하다.
- **비교 기준 부재**: 시스템들이 서로 다른 벤치마크를 사용해 직접 비교가 어렵다 (→ Q3에서 상세).
- **산업계 딥리서치의 한계**: OpenAI/Google/Perplexity의 딥 리서치는 정보 검색·종합에 집중하며 실험 실행·가설 검증은 불포함 — 학술 자율 연구 에이전트와는 범위가 다르다.

---

## Open questions

- 다양한 자율 연구 시스템 간의 능력 직접 비교가 가능한 공통 벤치마크는 무엇인가?
- 멀티에이전트 협업(AgentRxiv 모델)이 단일 에이전트 대비 연구 품질을 실질적으로 향상시키는가?
- 산업계 딥 리서치와 학계 자율 연구 에이전트의 융합 경향이 나타나고 있는가?
