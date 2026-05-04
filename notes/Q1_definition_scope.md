# Q1: autoresearch의 정의·범위와 인접 용어 비교

## TL;DR

"autoresearch"는 좁은 의미로 Karpathy(2026)가 공개한 LLM 자동 ML실험 루프 도구를 지칭하지만, 넓은 의미로는 **LLM 기반 자율 연구 에이전트(autonomous research agent)** 전반을 아우른다. 인접 용어들은 자율성 수준에 따라 구분되며, "자동화(automation)"보다 "자율성(autonomy)"이 핵심 축이다.

---

## 1. 협의의 autoresearch — Karpathy 프레임워크

Andrej Karpathy가 2026년 3월 공개한 630줄 Python 스크립트로, AI 에이전트(Claude Code 등)에게 최소한의 LLM 훈련 환경을 주고 밤새 자율 실험하도록 한다 [출처: DataCamp, "A Guide to Andrej Karpathy's AutoResearch", https://www.datacamp.com/tutorial/guide-to-autoresearch, 2026-03].

- **작동 방식**: 에이전트가 코드를 수정 → 5분간 학습 → val_bpb 계산 → 개선 시 유지, 아니면 롤백 → 반복 (약 12 실험/시간)
- **범위**: 단일 GPU, 단일 파일, 단일 지표 — ML 실험 자동화에 특화
- **영향**: 공개 1주일 만에 GitHub 스타 30,307개 획득 [출처: n1n.ai blog, "Running Karpathy's Autoresearch", https://explore.n1n.ai/blog/running-karpathy-autoresearch-local-llm-zero-cost-2026-03-23, 2026-03]

---

## 2. 광의의 autoresearch — 자율 연구 에이전트

넓게 보면 autoresearch는 **LLM이 문헌 탐색, 가설 수립, 실험 설계·실행, 논문 작성까지 주요 단계를 최소 인간 개입으로 수행하는 시스템** 전반을 가리킨다 [출처: arXiv 2505.18705, "AI-Researcher: Autonomous Scientific Innovation", https://arxiv.org/html/2505.18705v1, 2025-05].

핵심 특성:
- **적응적 가설 생성**: 명시적 지시 없이 연구 방향 자체를 탐색
- **메타인지**: 유망한 방향과 비생산적인 방향을 스스로 판단
- **종단간(end-to-end) 파이프라인**: 아이디어 → 코드 → 실험 → 결과 분석 → 논문

---

## 3. 자율성 수준 분류법 (Tool → Analyst → Scientist)

arXiv 2505.13259 (Zheng et al., EMNLP 2025)은 LLM의 과학적 발견 참여를 세 단계로 분류한다 [출처: arXiv 2505.13259, "From Automation to Autonomy", https://arxiv.org/abs/2505.13259, 2025-05]:

| 수준 | 명칭 | 정의 | 예시 |
|------|------|------|------|
| 1 | **LLM as Tool** | 인간 감독 하에 특정·정해진 작업 수행 | 논문 요약, 문법 교정 |
| 2 | **LLM as Analyst** | 복잡한 정보 처리·분석을 상당한 자율성으로 수행 | 문헌 메타분석, 인사이트 도출 |
| 3 | **LLM as Scientist** | 가설 수립부터 결과 해석까지 주요 연구 단계를 자율 수행 | AI Scientist, AI-Researcher |

"autoresearch"는 주로 수준 2~3에 해당한다.

---

## 4. 인접 용어 비교

### Research Automation (연구 자동화)
- **정의**: 사전에 정해진 연구 절차의 특정 구성요소를 자동화
- **특징**: 좁은 범위, 규칙 기반, 인간이 프로세스 설계
- **예시**: 자동 문헌 수집 봇, CI 파이프라인 내 실험 재현
- **vs autoresearch**: autoresearch는 방향 자체를 스스로 결정; automation은 인간이 정한 절차 실행

### Autonomous Research Agent (자율 연구 에이전트)
- **정의**: 스스로 연구 방향을 탐색하고 자원을 활용해 목표 달성
- **특징**: 적응적 의사결정, 도구 사용, 멀티스텝 추론
- **관계**: autoresearch의 구현 형태; 더 넓은 범주

### AI Scientist
- **정의**: Sakana AI(2024)가 제시한 완전 자동화 과학적 발견 시스템 — 아이디어 생성 → 실험 → 논문 작성 → 동료 평가까지 자동화 [출처: Sakana AI, "The AI Scientist", https://sakana.ai/ai-scientist/, 2024-08]
- **특징**: 논문 1편당 약 $15 비용, 상위 학회 수준의 논문 품질 (Weak Accept)
- **vs autoresearch**: AI Scientist는 완전 종단간 자율 연구의 특정 구현체; autoresearch는 더 넓은 개념 또는 실험 자동화에 특화

### Deep Research
- **정의**: 복잡한 질문에 대해 광범위한 웹 문헌을 종합·분석하는 LLM 기반 탐색 [출처: arXiv 2508.12752, "Deep Research: A Survey", https://arxiv.org/html/2508.12752v1, 2025-08]
- **특징**: 정보 수집·합성 중심; 실험 실행은 포함하지 않는 경우 많음
- **예시**: OpenAI Deep Research, Perplexity
- **vs autoresearch**: Deep Research는 정보 수집·분석 단계에 집중; autoresearch는 실험 실행과 과학적 발견까지 포함

### Auto-Research (OpenAGS 등 시스템명)
- **정의**: 특정 프레임워크(openags/Auto-Research 등)가 사용하는 용어로, 자율 과학 연구 전 주기 자동화를 뜻함 [출처: GitHub openags/Auto-Research, https://github.com/openags/Auto-Research, 2024]
- **특징**: 멀티에이전트 협업으로 문헌 검토 → 가설 → 실험 → 논문까지 일관 처리

---

## 5. 용어 정리 요약표

| 용어 | 자율성 수준 | 범위 | 핵심 특징 |
|------|------------|------|----------|
| Research Automation | 낮음 | 좁음 (단일 작업) | 규칙 기반, 인간 설계 절차 |
| Deep Research | 중간 | 중간 (정보 탐색) | 문헌 종합, 분석 중심 |
| autoresearch (Karpathy) | 높음 | 좁음 (ML 실험) | 실험 루프, 단일 GPU 특화 |
| Autonomous Research Agent | 높음 | 넓음 | 적응적, 종단간, 도구 사용 |
| AI Scientist | 매우 높음 | 넓음 (전 주기) | 아이디어→논문 완전 자동화 |

---

## Counterpoints

- **"자율성" 과장 우려**: 현재 시스템들은 설정된 도메인 내에서만 작동하며, 진정한 개방형(open-ended) 과학 발견은 아직 달성하지 못했다는 비판이 있다. Sakana AI의 AI Scientist 논문도 주로 ML 분야에 한정됨 [출처: arXiv 2601.03315, "Why LLMs Aren't Scientists Yet", https://www.arxiv.org/pdf/2601.03315, 2026-01].
- **재현성 문제**: 자율 실험 시스템이 생성한 결과의 재현성과 신뢰성에 대한 검증이 충분하지 않다는 지적 (→ Q4에서 상세 다룸).
- **용어 혼용**: 학계·산업계에서 "autoresearch", "AI scientist", "research agent"가 명확한 구분 없이 혼용되어 개념 경계가 유동적임.

---

## Open questions

- Deep Research와 Autonomous Research Agent의 경계는 어디인가? 실험 실행 능력이 기준인가?
- autoresearch의 범위가 ML 실험을 넘어 자연과학, 사회과학으로 확장될 때 동일한 분류법이 적용 가능한가?
- 자율성 3단계 분류(Tool/Analyst/Scientist)는 멀티에이전트 협업 시스템에도 유효한가?
