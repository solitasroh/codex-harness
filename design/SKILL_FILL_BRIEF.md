# 작업 배분 — 설계(grill me)·ADR 스킬 알맹이 채우기 (수장 지시 "1번")

목표: 현재 harness-run SKILL.md는 4단계를 얇게 요약만 함. 1·2단계(설계·ADR)를 각각
**독립 스킬 파일 + 실전 알맹이**로 채워, 재사용·확장 가능하게 한다.
참조: research_pipeline.md(§2 grill me 계열 정리), max4c/skills, RobMitt/grill-me-skill(92★)

## 현재 상태 (PM 실측)
- plugin/skills/에 harness-run/SKILL.md 하나만 존재. 설계·ADR은 그 안에 4~5줄 요약뿐.
- research_pipeline.md에 grill-me(5차원 Goals/Acceptance/Boundaries/Alternatives/Assumptions),
  grill-with-docs(CONTEXT.md 용어집+ADR 대조), CONSENSUS/NEEDS MAX 자동해소 개념 정리됨.

## 배분

### 엘레나(DX/설계) — 설계 스킬 알맹이
plugin/skills/design-grill/SKILL.md 신설. 담을 것:
- AskUserQuestion 툴 사용 규칙(평문 금지, 한번에 하나, 2~4선택지+Other)
- 5차원 모호성 해소 루프(Goals/Acceptance/Boundaries/Alternatives/Assumptions)
- DX 4원칙(이미 엘레나가 설계): 인지부하 분배(쉬운 80% [CONSENSUS] 자동, 진짜만 [NEEDS MAX]) /
  진행감 표시(N/5 해소) / "왜 묻는지" 한 줄 / 핸드오프(결정요약→ADR 입력)
- 끝나면 확정 스펙 산출 포맷

### 백팀장(개발) — ADR 스킬 알맹이 + 구조 분리
plugin/skills/adr-check/SKILL.md 신설. 담을 것:
- ADR 기록 포맷(제목/컨텍스트/결정/대안/결과)
- CONTEXT.md 용어집 대조 로직, 충돌 감지 시 사용자 알림
- 결정 확정 시 관련 문서 인라인 갱신(드리프트 차단)
- harness-run이 이 두 스킬을 참조하도록 연결(중복 제거)

### 브라이언(QA) — 검증 기준
채워진 두 스킬이 "실제로 작동하는 지침"인지 검증 기준 정의:
- 설계 스킬: 모호성 미해소 시 진행 안 되는지(게이트 실효)
- ADR 스킬: 기존 ADR과 충돌하는 결정을 실제로 잡는지

### 자비서(PM)
- 배분·참조 제공, 세 산출물 통합, harness-run 정합성 교차검증, 수장 보고
- 스킬 알맹이가 실전인지(뼈대 아님) 직접 확인
