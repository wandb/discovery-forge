# Q5: 상용 서비스 vs 오픈소스 구현 비교

## TL;DR

상용 딥 리서치 서비스(OpenAI·Google·Perplexity)는 성능·통합·엔터프라이즈 기능에서 앞서지만, 월 $20~$200 구독료·데이터 프라이버시·커스터마이징 제약이 따른다. 오픈소스(GPT-Researcher·Open Deep Research·STORM·autoresearch·AI Scientist)는 무료·완전 제어·로컬 배포가 가능하며, GPT-Researcher는 CMU DeepResearchGym 벤치마크에서 상용 서비스를 능가했다. 두 진영은 용도에 따라 상호 보완적으로 선택된다.

---

## 1. 상용 서비스

### 1-A. OpenAI Deep Research
- **가격**: Plus($20/월, 25쿼리) · Pro($200/월, 250쿼리) · Enterprise(협상제) [출처: OpenAI ChatGPT Pricing, https://chatgpt.com/pricing/, 2025]
- **핵심 기능**: o3 파워드, 5~30분 자율 탐색, 인용 포함 리포트; HLE 26.6%(출시 당시 최고) [출처: AI Unfiltered, https://www.arturmarkus.com/openai-deep-research-launches-february-2-with-26-6-on-humanitys-last-exam-o3-powered-agent-autonomously-researches-for-5-30-minutes-beats-deepseek-r1-by-177/, 2025-02]
- **엔터프라이즈**: Azure AI Foundry 통합; Google Drive·SharePoint·GitHub 등 MCP 커넥터 지원 [출처: AgentMarketCap, "OpenAI Deep Research Goes Enterprise", https://agentmarketcap.ai/blog/2026/04/08/openai-deep-research-enterprise-autonomous-research-agent, 2026-04]
- **데이터 프라이버시**: 소비자 플랜은 기본적으로 대화가 훈련에 사용될 수 있음(옵트아웃 가능); Enterprise는 AES-256 암호화, 훈련 미사용

### 1-B. Google Gemini Deep Research
- **가격**: Gemini Advanced($20/월 내 포함); Deep Research Max는 별도 [출처: AI Multiple, "AI Deep Research: Claude vs ChatGPT vs Grok", https://aimultiple.com/ai-deep-research, 2026]
- **핵심 기능**: Gemini 2.5 Pro(표준) · Gemini 3.1 Pro(Max); DeepSearchQA 93.3%, BrowseComp 85.9% [출처: davidborish.com, https://www.davidborish.com/post/google-s-new-deep-research-max-agent-scores-93-on-benchmarks, 2025]
- **강점**: 속도·멀티모달 처리; Google Workspace 생태계 통합

### 1-C. Perplexity Deep Research / Sonar API
- **가격**: Pro 구독($20/월) 포함 또는 Sonar Deep Research API ($2/$8 per million tokens — 유일 종량제 API) [출처: Glasp, "Deep Research Tools Compared", https://glasp.co/articles/deep-research-tools-compared, 2026]
- **특징**: 대부분 실행을 3분 이내 완료(최고 속도); 개발자 API 접근 용이
- **한계**: 보고서 깊이·추론 복잡도는 OpenAI 대비 낮음; Computer 에이전트는 Max 플랜($200/월) 한정

---

## 2. 오픈소스 구현

### 2-A. GPT-Researcher
- **특징**: 어떤 LLM(OpenAI·Anthropic·Llama 등 100종 이상)·검색엔진(Google·Bing·Tavily·DuckDuckGo)과도 연결 가능; 로컬 문서 + 웹 하이브리드 검색; MCP 통합 지원 [출처: gptr.dev, https://gptr.dev/, 2025]
- **성능**: CMU DeepResearchGym(1,000개 복잡 쿼리) 벤치마크에서 Perplexity·OpenAI·HuggingFace를 인용 품질·리포트 품질·정보 커버리지 모두에서 능가 [출처: GPT-Researcher 공식 사이트, gptr.dev]
- **출력**: 5~6페이지 리포트, PDF·Docx·Markdown·JSON·CSV 지원
- **커뮤니티**: 수백만 다운로드, 100개국 기여자

### 2-B. Open Deep Research (LangChain)
- **특징**: 연구 슈퍼바이저 에이전트가 복잡한 쿼리를 서브토픽으로 분해 → 병렬 서브에이전트 실행 → 인용 포함 결과 통합 [출처: GitHub langchain-ai/open_deep_research, https://github.com/langchain-ai/open_deep_research, 2025]
- **장점**: LLM·검색 도구 자유 선택; 완전 커스터마이저블 프롬프트·레이트 제한

### 2-C. STORM (Stanford)
- **특징**: Wikipedia 수준의 긴 기사 자동 작성에 특화된 Stanford 오픈소스 프로젝트 [출처: Simular AI, "Top 5 Open-Source Alternatives for OpenAI's Deep Research", https://www.simular.ai/blogs/top-5-open-source-alternatives-for-openais-deep-research, 2025]
- **활용**: 딥 리서치 구현들의 영감 원천; 긴 구조화 문서 생성 특화

### 2-D. Karpathy autoresearch
- **특징**: ML 실험 자동화 특화; 외부 의존성 최소화(PyTorch + 소형 패키지); 단일 GPU [출처: DataCamp, https://www.datacamp.com/tutorial/guide-to-autoresearch, 2026-03]
- **비용**: 완전 무료(하드웨어만 필요); 구독·API 비용 없음
- **한계**: ML 훈련 실험에 특화 — 범용 딥 리서치 불가

### 2-E. AI Scientist 시리즈 (Sakana AI, 오픈소스)
- **특징**: AI Scientist v1·v2 코드 GitHub 공개; SakanaAI/AI-Scientist 저장소 [출처: GitHub SakanaAI/AI-Scientist-v2, https://github.com/SakanaAI/AI-Scientist-v2, 2025]
- **비용**: 오픈소스이나 실행에는 강력한 LLM API(OpenAI·Anthropic) 비용 발생; 논문 1편당 ~$15
- **범위**: ML 분야 완전 종단간 연구 자동화

### 2-F. Agent Laboratory (오픈소스)
- **특징**: 3단계(문헌 검토→실험→리포트) 자율 연구 파이프라인; 인간 피드백 루프 지원 [출처: GitHub SamuelSchmidgall/AgentLaboratory, https://github.com/SamuelSchmidgall/AgentLaboratory, 2025]
- **비용**: 오픈소스; 기존 대비 연구 비용 84% 절감

---

## 3. 핵심 비교 표

| 차원 | 상용(OpenAI/Google/Perplexity) | 오픈소스(GPT-Researcher 등) |
|------|-------------------------------|----------------------------|
| **비용** | $20~$200/월 구독 | 무료(API 비용만 발생) |
| **성능(딥 리서치)** | 높음(특히 복잡한 추론) | GPT-Researcher는 CMU 벤치에서 상용 능가 |
| **데이터 프라이버시** | 소비자 플랜: 훈련 사용 가능 | 로컬 배포 시 완전 제어 |
| **커스터마이저빌리티** | 제한적 | 완전 자유(LLM·검색·프롬프트 교체) |
| **엔터프라이즈 통합** | 강력(MCP, Azure, Workspace) | 직접 구현 필요 |
| **설치 복잡도** | 없음(SaaS) | 중간~높음 |
| **LLM 종속성** | OpenAI/Google 모델 고정 | 100종 이상 선택 가능 |
| **ML 실험 자동화** | 불포함 | autoresearch·AI Scientist |
| **속도** | Perplexity 3분 / OpenAI 5~30분 | GPT-Researcher ~10분 내외 |

---

## 4. 선택 가이드

- **엔터프라이즈·규정 준수 요구**: 상용(OpenAI Enterprise) → AES-256, SOC2, 내부 지식베이스 통합
- **개발자·스타트업**: GPT-Researcher 또는 Open Deep Research → LLM 자유 선택, 무료, API 통합
- **ML 실험 자동화**: autoresearch(단일 GPU 빠른 실험) 또는 AI Scientist(종단간 논문 생성)
- **데이터 프라이버시 최우선**: 로컬 LLM(DeepSeek, Llama) + GPT-Researcher 셀프호스팅
- **속도 최우선 딥 리서치**: Perplexity Sonar API

---

## Counterpoints

- **오픈소스의 실질적 비용**: 오픈소스는 구독료가 없지만, 운영·유지보수·보안·인프라 비용이 상당하다. Gartner는 에이전트 배포에서 프레임워크가 전체 작업의 20%에 불과하고 나머지 80%가 인프라·보안·거버넌스라고 지적한다 [출처: 검색 결과 종합, aimultiple.com].
- **CMU 벤치마크 신뢰성 한계**: GPT-Researcher가 CMU DeepResearchGym에서 1위를 차지했지만, 이 벤치마크가 얼마나 널리 검증되었는지, 상용 서비스의 최신 버전을 비교 대상으로 포함했는지 독립 검증이 부족하다.
- **성능 격차 빠른 변동**: 상용 모델 업데이트 주기(수주~수개월)가 오픈소스보다 빠르므로 현재 비교 수치는 빠르게 구식이 될 수 있다.

---

## Open questions

- 완전 로컬 LLM 기반 오픈소스 연구 에이전트가 상용 GPT-4o급 성능에 근접하는 시점은 언제인가?
- 학술 기관·병원 등 데이터 규제가 엄격한 환경에서 오픈소스 자율 연구 에이전트 도입의 현실적 장벽은 무엇인가?
- 상용과 오픈소스의 하이브리드 모델(오픈소스 파이프라인 + 상용 LLM API)이 최적 균형점인가?
