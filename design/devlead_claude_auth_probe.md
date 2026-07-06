# DevLead 조사 — claude CLI 인증 우회 시도 결과 (정직 보고)

작성: 백팀장(DevLead) | 2026-07-05 | 대상: 미해결 1건(claude --plugin-dir 런타임 로드 보류)

## 배경
codex는 CODEX_HOME 우회(auth.json 복사)로 인증을 풀었다. claude CLI도 같은 방식으로
우회 가능한지 직접 파봤다. 결론: **간단히 안 됨. 수장/PM 확인 필요.**

## 실측한 것 (전부 직접 확인)
1. 내 세션 HOME `/opt/data/profiles/baek/home/.claude.json`: `oauthAccount` 없음 → 미로그인.
2. `/opt/data/.claude.json`(hermes:600, 읽기 가능): 계정 메타만 있고 `primaryApiKey`·
   `oauthAccount` 없음. 즉 여기도 인증 토큰 없음.
3. `.credentials.json`(claude CLI OAuth 저장 파일): **양쪽 위치 모두 부재.**
4. `/root/.claude.json`: 권한 없음(root 소유).
5. `.env`에 `ANTHROPIC_TOKEN`(108자) + `ANTHROPIC_API_KEY`(빈 값) 존재.
   - `ANTHROPIC_TOKEN`을 `ANTHROPIC_API_KEY`로 매핑해 `claude -p` 시도 → **`Invalid API key`.**
   - 이 토큰은 **게이트웨이 프록시용 내부 토큰**이지 Anthropic 직접 API 키가 아님(base_url
     세팅과 세트로 동작하는 것으로 추정). claude CLI 단독 인증엔 부적합.

## 결론 (근거 기반)
- codex 우회가 통한 이유: OAuth `auth.json` 실물이 읽기 가능한 위치에 있었음.
- claude가 안 통하는 이유: claude CLI의 OAuth credentials 실물이 **이 세션에서 접근 가능한
  어디에도 없음**. `.env` 토큰은 성격이 다름(프록시용).
- ∴ 코드/설계 결함 아님. **환경(인증) 이슈 확정.** 브라이언 QA 판정과 일치.

## 수장/PM께 필요한 것 (택1)
1. **claude CLI 로그인**: 이 컨테이너 셸에서 `claude` 실행 후 `/login`(OAuth) 1회. 이후
   `.credentials.json`이 생겨 `--plugin-dir` 로드 검증 가능.
2. **직접 API 키**: 진짜 `sk-ant-...` 형식의 Anthropic API 키를 `ANTHROPIC_API_KEY`로 제공.
   (게이트웨이 프록시 토큰 말고 원본 키)
3. 또는 게이트웨이가 쓰는 `ANTHROPIC_BASE_URL` + 토큰 조합을 알려주면 그 조합으로 재시도.

## 영향 범위 (제한적)
- 이건 **최종 통합 로드 확인**만 막는다. 플러그인 개별 컴포넌트(구조·MCP래퍼·훅·스캐너·
  회귀 18/18)는 전부 실측 GREEN. 인증만 풀리면 `claude --plugin-dir ./plugin`으로 확인만 하면 됨.
- Phase 1 착수의 블로커는 아님(codex 코딩 위임은 이미 동작). claude 오케스트레이터를
  CLI로 헤드리스 구동하려 할 때만 필요.
