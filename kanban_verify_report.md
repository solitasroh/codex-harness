# 슬랙 칸반 적용 로드맵 — 단계 1까지 실측 검증 보고서

작성: 자비서(PM) · 2026-07-05 · 근거: 실제 CLI 실행 + 프로세스/파일/git 교차검증 (봇 자기보고 불신 원칙 적용)
대상: `slack_kanban_analysis.md` §4 로드맵의 단계 0·1

---

## TL;DR
- **단계 0(빈 보드 워커 스폰) — 성공.** dispatcher가 태스크를 claim → 백팀장(baek) 워커를 실제 OS 프로세스(PID 493154)로 스폰 → 27초 만에 done. 산출물 `STEP0_OK.txt`를 직접 읽어 교차검증.
- **단계 1(cc-plugin 보드 신설 + 실전 태스크 + worktree 격리) — 성공.** 별도 DB 보드 생성, worktree 격리(`.worktrees/t_93a0cb2a` [wt/plugin-skeleton])에서 실제 코딩, master 브랜치 무오염 확인.
- **덤으로 fail-closed 회로도 실증됨.** worktree repo 경로 누락 시 조용히 죽지 않고 정확한 해법 메시지와 함께 block, unblock으로 재개.
- **결론: 문서의 주장은 실측으로 사실.** 슬랙 칸반은 우리 4봇 협업의 정식 인프라로 즉시 가동 가능.

---

## 단계 0 — 워커 스폰 검증 (리스크 0)

**설정:** default 보드(비어있음), baek 앞 테스트 태스크, `dir:` 워크스페이스, max-runtime 5m, max-retries 1.

**실측된 상태머신 전이:**
```
created → ready → claimed(lock) → spawned(PID 493154) → heartbeat → completed → done   (27초)
```

**교차검증(자기보고 불신):**
- 워커가 완전한 독립 OS 프로세스임을 `ps`로 확인:
  `hermes -p baek ... chat -q work kanban task t_8ef42a74`, 부모=게이트웨이(433987)
- 산출물 `/opt/data/projects/kanban-verify/STEP0_OK.txt`를 직접 read → 정확한 내용 확인
- 태스크 이벤트에 `artifacts` 경로가 자동 기록됨

→ 문서 인용 "every worker is a full OS process with its own identity" = **사실**.

---

## 단계 1 — cc-plugin 보드 + worktree 격리 실전

**보드 격리:** `hermes kanban boards create cc-plugin` → 별도 DB `/opt/data/kanban/boards/cc-plugin/kanban.db`.
default(done=1)와 완전 분리 확인. 크로스보드 격리 = 사실.

**실전 태스크:** `.claude-plugin` 골격(plugin.json + /diff-digest 커맨드 + README) 작성을 baek에게 worktree로 위임.

**실측된 전이(재개 경로 포함):**
```
ready → claimed → gave_up(fail-closed) → unblocked → ready → claimed → spawned(PID 493882) → running → done
```

**fail-closed 실증(핵심 소득):**
- worktree인데 repo 경로 미지정 → dispatcher가 **조용히 죽지 않고** 정확한 원인+해법을 남기며 block:
  > "workspace_kind=worktree but no workspace_path ... Set a board default workdir (a git repo) or create the task with --workspace worktree:<absolute-repo-path>."
- max-retries=1이라 1회 실패에 즉시 회로 차단(thrashing 방지) — circuit breaker 실측 확인
- 해결: `boards set-default-workdir` + `unblock` → 정상 재개. **실패가 감사 로그에 영구 기록됨**(과거 "침묵 단절" 결함의 정반대).

**worktree 격리 무결성(교차검증):**
- git worktree list: `.worktrees/t_93a0cb2a [wt/plugin-skeleton]` 실제 생성
- **master HEAD 9607ba9 무변경, `.claude-plugin` 0건** → main 오염 전혀 없음
- 신규 4파일 267줄은 wt/plugin-skeleton 브랜치에만 존재 (커밋 3c3c012)

**산출물 품질(자기보고 불신, 직접 검사):**
- plugin.json: 유효 JSON, 필드 name/version/description/author/keywords 정상
- commands/diff-digest.md: frontmatter(description/argument-hint/allowed-tools) 갖춘 정식 슬래시 커맨드 형식
- README.md: 플러그인 요약 정상, Python stdlib 전용 명시

---

## 검증으로 확정된 사실 요약

| 항목 | 문서 주장 | 실측 결과 |
|---|---|---|
| dispatcher 게이트웨이 내 자동 실행 | dispatch_in_gateway | ✅ 60초 주기 claim·spawn 확인 |
| 워커 = 이름있는 독립 프로세스 | full OS process | ✅ PID·프로필·툴셋 확인 |
| 상태머신 + 재개성 | block→unblock→재실행 | ✅ 전 전이 실측 |
| fail-closed(침묵 단절 방지) | crash/실패 감사 남음 | ✅ gave_up 이벤트+해법 메시지 |
| circuit breaker | failure_limit | ✅ max-retries=1 1회차단 |
| 보드 격리 | 보드별 독립 DB | ✅ 별도 kanban.db |
| worktree 격리 | git worktree 자동 | ✅ 브랜치 격리, main 무오염 |
| 산출물 감사 | artifacts rows | ✅ 이벤트에 경로 기록 |

---

## 남은 것 (단계 2~3, 미착수)
- **단계 2:** `swarm`(백팀장 구현 + 브라이언 verifier + 자비서 synthesizer) 팬아웃/팬인 한 바퀴. cc-plugin의 qa_verify.sh를 verifier에 결합.
- **단계 3:** 슬랙 `/kanban`로 수장님이 직접 지시 → 자동 처리 → 알림. (슬래시 커맨드는 게이트웨이 어댑터 경유; 별도 실측 필요)
- 정리 필요: 검증용 임시 산출물(`kanban-verify/`, `.worktrees/`), wt/plugin-skeleton 브랜치 병합 여부 결정.

---

## 한 줄 총평
> 단계 0·1은 문서 주장대로 실제로 돈다. 특히 "실패해도 조용히 안 죽고 감사에 남는다"는 점이 우리가 과거 멘션 핑퐁에서 겪은 침묵 단절을 구조적으로 해결한다. 단계 2(swarm)·3(슬랙 /kanban) 진행 승인을 요청드림.
