# 확정 스펙: envlint (.env 파일 검증기)
확정일: 2026-07-05 · 그릴링 라운드: 1 (소재가 표준적이라 대부분 CONSENSUS 자동 해소)

## 1줄 정의
`.env` 파일을 읽어 형식 오류·중복 키·빈 값·(스키마 제공 시) 필수 키 누락을 검사하는 CLI.

## Goals (성공의 정의)
- 배포 전 `.env`의 흔한 실수(오타 키, 빈 값, 중복, 형식 깨짐)를 사람이 보기 전에 잡아준다.
- 통과/실패를 종료코드로 명확히 내 CI·훅에 물릴 수 있다.

## Acceptance (완료 기준 / 핵심 유저플로)
- `envlint .env` → 문제 목록을 줄번호와 함께 출력. 문제 없으면 "ok" + exit 0.
- `envlint .env --schema required.txt` → required.txt의 키가 .env에 다 있는지 확인, 누락 시 보고.
- `envlint .env --strict` → 경고(빈 값 등)도 실패로 취급(exit 1). 기본은 오류만 exit 1.
- `--json` → 결과를 JSON으로(기계 판독용).
- 유저플로: 파일 경로 받음 → 파싱 → 4종 검사 → 텍스트/JSON 리포트 → 종료코드.

## Boundaries (범위)
- 안: 형식검사(KEY=VALUE), 중복키, 빈값, 필수키 누락(스키마), 주석(#)·빈줄 무시, `export KEY=` 접두 허용.
- 밖: .env 값의 의미 검증(URL 유효성 등) 안 함. 변수 치환(${VAR}) 평가 안 함. 파일 수정 안 함(읽기 전용).
- 경계: stdin 입력도 허용(`-`). 따옴표 값(KEY="a b") 허용.

## Alternatives (선택과 근거)
- [CONSENSUS] Python3 표준 라이브러리만 (외부 의존 0) ← 이식성·검증 단순. 버린 안: python-dotenv 의존(설치 부담).
- [CONSENSUS] 종료코드 규약 = 0 통과 / 1 문제발견 / 2 사용법오류 ← 유닉스 관행.
- [CONSENSUS] 검사 항목을 함수로 분리(parse/check_duplicates/check_empty/check_format/check_schema) ← 테스트 용이.

## Assumptions (가정과 리스크)
- 가정: .env는 UTF-8 텍스트. 틀리면: 인코딩 에러를 사용법오류(exit 2)로 처리.
- 가정: 한 줄 = 한 항목(멀티라인 값 미지원). 틀리면: 따옴표 안 줄바꿈은 범위 밖으로 명시.

## 엣지케이스·에러
- 빈 파일 → "ok"(문제 없음) exit 0.
- 파일 없음 → 사용법오류 exit 2.
- `KEY`(=없음) → 형식 오류로 보고.
- `KEY=`(값 없음) → 빈 값 경고(기본 통과, --strict에서 실패).
- `# 주석`, 빈 줄 → 무시.
- 같은 KEY 2회 → 중복 보고(줄번호 둘 다).
- `export KEY=val` → KEY=val로 정상 파싱.

## 결정 로그
- [CONSENSUS] 언어=Python3 표준라이브러리 (근거: 이식성, 외부의존 0, 프로젝트 관행)
- [CONSENSUS] 종료코드 0/1/2 (근거: 유닉스 CLI 관행, CI 연동)
- [CONSENSUS] 읽기전용(파일 수정 안 함) (근거: 검증기의 안전 원칙)
- [CONSENSUS] 4종 검사(형식/중복/빈값/스키마) (근거: .env 실수의 대표 유형)
- [NEEDS MAX] 없음 — 이 소재는 표준적이라 사업/취향 판단 갈림 지점이 없음. 전부 CONSENSUS로 해소.
- [UNRESOLVED] 없음 — 5차원 미해소 0개.
