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

### iter Q1 (2026-05-04)
- "autoresearch"는 Karpathy 특정 도구(2026-03 공개)와 광의의 자율 연구 에이전트 개념 모두를 지칭하므로 문맥 구분이 필수.
- arXiv 직접 fetch는 일부 차단되므로 abstract 페이지(arxiv.org/abs/...)를 우선, html 버전은 선택적 시도.
- Tool/Analyst/Scientist 3단계 분류(arXiv 2505.13259, EMNLP2025)가 자율성 스펙트럼 설명에 유용한 공통 프레임.