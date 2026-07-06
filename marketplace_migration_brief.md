# PM 브리프: codex-harness 배포 방식 전환 — `--plugin-dir` → 마켓플레이스

작성: 자비서(PM) | 근거: 공식 문서(code.claude.com/docs) 실독 + 이 서버 claude 2.1.185 CLI 실측
과제(Soojang): "codex-harness 업데이트. 우선 **플러그인 사용 방법**부터 marketplace 활용 방식으로 바꾸자."

---

## TL;DR (결론 먼저)

지금 README는 `claude --plugin-dir ./plugin` — **세션 한정 로컬 로드**만 안내한다.
설치도 안 되고, 매 세션 경로를 넘겨야 하며, 버전/업데이트 개념이 없다.
이를 **마켓플레이스 방식**으로 바꾸면: 리포 루트에 `.claude-plugin/marketplace.json` 카탈로그 하나 두고,
사용자는 `claude plugin marketplace add solitasroh/codex-harness` → `claude plugin install codex-harness@jabiseo-studio`
두 줄로 **설치·자동업데이트·버전관리**가 붙는다. 우리 리포가 곧 1인 마켓플레이스가 된다.

**핵심: 코드 변경 거의 없음.** plugin/ 디렉토리는 그대로 두고, 리포 루트에 카탈로그 파일 1개 추가 + README 갱신이 전부.

---

## 두 방식 비교 (실측 기반)

| 항목 | 현재: `--plugin-dir ./plugin` | 제안: 마켓플레이스 |
|------|------------------------------|-------------------|
| 설치 | 없음 (매번 경로 지정) | `plugin install` 로 캐시에 영구 설치 |
| 실행 | `claude --plugin-dir ./plugin` 매 세션 | 설치 후 항상 로드 |
| 버전 | 개념 없음 | plugin.json version 또는 git SHA로 추적 |
| 업데이트 | git pull 수동 | `plugin marketplace update` + 자동 업데이트 |
| 배포 | "리포 clone 해서 경로 잡아라" | "이 두 줄 실행해라" (owner/repo 한 줄) |
| 팀 강제 | 불가 | `.claude/settings.json`의 `extraKnownMarketplaces`로 자동 프롬프트 |

두 방식은 **대립이 아니라 로컬 테스트(--plugin-dir) → 배포(마켓플레이스)** 의 단계 차이. 개발 중엔 여전히 `--plugin-dir`로 빠르게 돌리고, 배포는 마켓플레이스로 한다.

---

## 마켓플레이스 스펙 요약 (공식 문서)

### 구조
```
codex-harness/                     ← 리포 루트 = 마켓플레이스 루트
  .claude-plugin/marketplace.json  ← [신규] 카탈로그 (이 파일이 핵심)
  plugin/                          ← [기존] 실제 플러그인 (그대로)
    .claude-plugin/plugin.json
    skills/ bin/ hooks/ lib/ ...
```

### marketplace.json (필수: name·owner·plugins)
- `source: "./plugin"` — 상대경로는 **마켓플레이스 루트 기준**(`.claude-plugin/` 기준 아님). 리포 안의 plugin/을 가리킴.
- 플러그인 엔트리에 version/author/category/keywords/description 등 메타 포함 가능.
- **예약어 주의**: `claude-plugins`, `anthropic-*` 등 공식 사칭 이름 금지. 우리는 `jabiseo-studio` 사용.

### 버전 해석 우선순위 (문서 명시)
1. plugin.json 의 version
2. marketplace 엔트리의 version
3. 위 둘 없으면 git commit SHA

⚠️ **함정**: version을 pin해두면(예 0.1.0), 그 문자열 안 바꾸고 커밋만 하면 **기존 사용자에겐 업데이트가 안 감**(같은 버전으로 보고 캐시 유지). → 릴리스마다 version bump 하거나, version 아예 빼서 SHA 방식 쓰기. plugin.json과 marketplace.json 양쪽에 version 동시 지정 금지(plugin.json이 우선, 조용히 덮음).

### 설치/사용 (사용자 관점, 실측 명령)
```bash
claude plugin marketplace add solitasroh/codex-harness   # GitHub owner/repo 한 줄
claude plugin install codex-harness@jabiseo-studio        # plugin@marketplace
# 스킬 실행: /codex-harness:harness-run  (플러그인명으로 네임스페이스됨)
claude plugin marketplace update                          # 최신 카탈로그 반영
```

### 릴리스 태그 도구 (내장)
`claude plugin tag` → `{name}--v{version}` git 태그 생성, plugin.json과 마켓플레이스 엔트리 version 일치 검증. `--push`로 origin 푸시까지.

---

## 실측 검증 완료 (이 서버, claude 2.1.185)

이미 동작 확인한 것 — 회의는 이 위에서 진행:
1. 로컬 claude에 marketplace 전 서브커맨드 존재 (add/install/list/update/validate/tag/remove/uninstall/enable/disable).
2. 제안 marketplace.json 초안 작성 → `claude plugin validate . --strict` **✔ 통과** (스크래치 + 실제 리포 구조 양쪽).
3. `source: "./plugin"`이 리포 내 기존 plugin/을 정상 참조. **코드 이동 불필요 확인.**

---

## 회의 안건 (팀장 확정 필요)

1. **마켓플레이스 이름**: `jabiseo-studio` (스튜디오 카탈로그, 향후 다른 플러그인도 여기 담음) vs `codex-harness`(1플러그인=1마켓플레이스). → 확장성 고려 시 studio 권장.
2. **버전 전략**: version pin(0.1.0, 릴리스마다 bump) vs version 생략(git SHA 자동). → 초기 활발한 개발 = SHA가 편함. 안정 배포 시작하면 pin.
3. **소스 방식**: 상대경로 `./plugin`(같은 리포) 확정 — 이견 없으면 그대로.
4. **README 갱신 범위**: 설치·사용 섹션을 마켓플레이스 2줄 방식으로 교체 + 개발자용 `--plugin-dir` 로컬 테스트 방법 병기.
5. **팀 자동배포**: `extraKnownMarketplaces`/`enabledPlugins`로 강제 설치까지 갈지(자비서Studio 내부 4봇 대상) 여부 — 후순위 옵션.
6. **릴리스 파이프라인**: `claude plugin tag --push`를 릴리스 절차로 넣을지.

---

## PM 예비 판단

- 이름 `jabiseo-studio`, 초기엔 **version 생략(SHA 자동추적)** — 지금은 활발히 고치는 단계라 bump 깜빡 위험 제거가 이득.
- plugin/ 코드는 **손대지 않는다**. 리포 루트 카탈로그 1개 + README 갱신 + 릴리스 태그 절차 문서화.
- 백팀장이 실제 반영(카탈로그 작성·README diff·태그) 담당, 브라이언이 "add→install→스킬 호출"까지 사용자 시점 재현 검증.
