#!/usr/bin/env python3
"""QA 검증기 (크로스플랫폼) — codex_run 이 만든 격리 workdir 에 3계층 루브릭을 자동 적용한다.

작성: 브라이언(QA) 원안(qa_verify.sh) → 백팀장 크로스플랫폼 이식(2026-07-07, 스코프 C).
codex_run 은 "위임+diff캡처"까지, 이 스크립트가 "검증(done 판정)"을 담당.

사용: qa_verify.py <workdir> [expected_stdout_substring]
  exit 0 = done(전 게이트 통과) / exit 1 = 재작업(하나라도 미통과) / exit 2 = 사용법·환경 오류

원칙(원안 계승):
  - 자기보고 ≠ 검증. 테스트 파일 존재 ≠ 통과. 러너 없으면 함수 직접호출로 폴백해서라도 "실제로 돌린다".
  - exit 0/1 계약과 로그 포맷(===== QA VERIFY =====, [L1]/[L2], ===== 판정 =====)은 .sh 원안과 동일하게 유지.

크로스플랫폼 근거(백팀장):
  - 원안 .sh 는 find/grep/pytest·py_compile 을 bash 로 호출 → 윈도우(.NET/xUnit)에서 전면 무용.
    실제 하네스 대상이 윈도우 주력이므로 python3 단일 구현으로 재작성. python3 는 양 OS 공통.
  - L2 러너 자동감지: 프로젝트에 .sln/.csproj 있으면 `dotnet test`(xUnit 등), 아니면 test_*.py 로
    pytest(부재 시 함수 직접호출 폴백). "무엇이 있는가"로 러너를 고르되 "실제로 돌린다"는 불변.
  - 경계(L1)·문법도 OS 명령(find/py_compile CLI) 대신 pathlib + py_compile 모듈로 이식.
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

# ── dotnet invariant globalization: ICU 없는 환경(컨테이너 등)에서도 dotnet 가 죽지 않게. ──
#    윈도우 실기엔 영향 없음(ICU 존재). 안전하게 항상 자식 env 로 넘긴다.
_DOTNET_ENV = dict(os.environ)
_DOTNET_ENV.setdefault("DOTNET_CLI_TELEMETRY_OPTOUT", "1")
_DOTNET_ENV.setdefault("DOTNET_NOLOGO", "1")
_DOTNET_ENV.setdefault("DOTNET_SYSTEM_GLOBALIZATION_INVARIANT", "1")


def _run(cmd, cwd=None, env=None):
    """서브프로세스 실행 헬퍼. (rc, combined_output) 반환. 실행 자체 실패도 rc 로 표현."""
    try:
        p = subprocess.run(
            cmd, cwd=cwd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding="utf-8", errors="replace",
        )
        return p.returncode, p.stdout
    except FileNotFoundError:
        return 127, f"실행파일 없음: {cmd[0]}"
    except Exception as e:  # noqa: BLE001 - 검증기는 어떤 실패도 rc 로 표현
        return 1, f"실행 예외: {e}"


def _git_staged_names(wd: Path):
    rc, out = _run(["git", "diff", "--cached", "--name-only"], cwd=str(wd))
    if rc != 0:
        return []
    return [ln for ln in out.splitlines() if ln.strip()]


def _find_files(root: Path, suffixes, name_predicate=None):
    """.git 을 제외하고 root 하위에서 파일 탐색. suffixes 예: {'.py'}."""
    hits = []
    for p in root.rglob("*"):
        if ".git" in p.parts:
            continue
        if not p.is_file():
            continue
        if p.suffix in suffixes and (name_predicate is None or name_predicate(p)):
            hits.append(p)
    return hits


def check_l1(wd: Path):
    """L1 Mechanical: 변경파일이 workdir 경계 내인가 + (파이썬 있으면) 문법."""
    print("[L1] 경계·문법")
    fail = False
    # 경계: git 이 스테이징된 변경 이름 중 절대경로/상위탈출이 있으면 위반
    outside = [n for n in _git_staged_names(wd) if n.startswith("/") or n.startswith("../") or n.startswith("..\\")]
    if outside:
        print(f"  \u274c workdir 밖 변경: {outside}")
        fail = True
    else:
        print("  \u2705 변경파일 전부 workdir 경계 내")
    # 문법: 존재하는 .py 만 검사(파이썬 없는 .NET 프로젝트면 자동 스킵)
    import py_compile
    pyfiles = _find_files(wd, {".py"})
    py_bad = False
    for f in pyfiles:
        try:
            py_compile.compile(str(f), doraise=True)
        except py_compile.PyCompileError:
            print(f"  \u274c 문법오류: {f}")
            py_bad = True
            fail = True
    if pyfiles and not py_bad:
        print("  \u2705 py 문법 OK")
    return not fail


def _detect_runner(wd: Path):
    """L2 러너 자동감지. 우선순위: .NET(.sln/.csproj) > pytest(test_*.py) > 없음."""
    dotnet_projs = _find_files(wd, {".sln", ".csproj"})
    if dotnet_projs:
        return "dotnet", dotnet_projs
    pytests = _find_files(
        wd, {".py"},
        name_predicate=lambda p: p.name.startswith("test_") or p.name.endswith("_test.py"),
    )
    if pytests:
        return "pytest", pytests
    return None, []


def check_l2_dotnet(wd: Path, projs):
    """.NET: dotnet build → dotnet test. 테스트를 실제로 실행해 판정."""
    print("[L2] 테스트 실행")
    print("  (runner=dotnet: .sln/.csproj 감지)")
    if not shutil.which("dotnet", path=_DOTNET_ENV.get("PATH")):
        print("  \u274c dotnet 실행파일 없음 — .NET 게이트 실행 불가")
        return False
    # 빌드부터: 컴파일 실패를 테스트 실패와 구분해 명확히 보고
    rc, out = _run(["dotnet", "build", "--nologo", "-v", "quiet"], cwd=str(wd), env=_DOTNET_ENV)
    tail = "\n".join(out.splitlines()[-8:])
    if rc != 0:
        print(tail)
        print("  \u274c dotnet build 실패")
        return False
    print("  \u2705 dotnet build OK")
    # 테스트 실행: 빌드 재수행 방지(--no-build)로 위 결과 재사용
    rc, out = _run(["dotnet", "test", "--no-build", "--nologo", "-v", "quiet"], cwd=str(wd), env=_DOTNET_ENV)
    print("\n".join(out.splitlines()[-8:]))
    if rc != 0:
        print("  \u274c dotnet test 실패(테스트 미통과)")
        return False
    print("  \u2705 dotnet test 통과")
    return True


def check_l2_pytest(wd: Path, tests):
    """pytest 우선, 부재 시 test_ 함수 직접호출 폴백(원안 계승)."""
    print("[L2] 테스트 실행")
    # pytest 사용 가능?
    rc, _ = _run([sys.executable, "-m", "pytest", "--version"])
    if rc == 0:
        rc, out = _run([sys.executable, "-m", "pytest", "-q"], cwd=str(wd))
        print("\n".join(out.splitlines()[-5:]))
        print("  (runner=pytest)")
        return rc == 0
    # 폴백: test_*.py 의 test_ 함수 직접 import·호출
    print("  (runner=direct: pytest 부재 → 함수 직접호출 폴백)")
    ok_all = True
    for t in tests:
        mod = t.stem
        code = (
            "import importlib,sys,traceback\n"
            f"sys.path.insert(0, {str(t.parent)!r})\n"
            f"m=importlib.import_module({mod!r})\n"
            "fns=[f for f in dir(m) if f.startswith('test_')]\n"
            "ok=0\n"
            "for f in fns:\n"
            "    try: getattr(m,f)(); print('  \\u2705',f); ok+=1\n"
            "    except Exception: print('  \\u274c',f); traceback.print_exc(); sys.exit(1)\n"
            "print(f'  {ok}/{len(fns)} 통과')\n"
        )
        rc, out = _run([sys.executable, "-c", code], cwd=str(wd))
        print(out.rstrip())
        if rc != 0:
            ok_all = False
    return ok_all


def check_l2(wd: Path):
    runner, items = _detect_runner(wd)
    if runner == "dotnet":
        return check_l2_dotnet(wd, items)
    if runner == "pytest":
        return check_l2_pytest(wd, items)
    print("[L2] 테스트 실행")
    print("  \u26a0 테스트 파일 없음(.sln/.csproj/test_*.py 모두 없음) — L2 미검증(코딩 태스크면 테스트 요구 대상)")
    return True  # 원안과 동일: 테스트 부재는 FAIL 로 치지 않되 경고


def check_l2b_expected(wd: Path, expect: str):
    """지정 시: workdir 최상위 진입점 실행 stdout 에 기대문자열 포함 여부.
    .py 진입점만 지원(원안 계승). .NET 은 진입점 규약이 프로젝트마다 달라 dotnet test 로 판정하고 여기선 스킵."""
    if not expect:
        return True
    mains = [p for p in wd.glob("*.py") if not p.name.startswith("test_")]
    if not mains:
        # .NET 등 파이썬 진입점 없음 → L2b 비적용(경고만)
        print(f"  \u26a0 expected 지정됐으나 파이썬 진입점 없음 — L2b 스킵(.NET 은 dotnet test 로 판정)")
        return True
    rc, got = _run([sys.executable, str(mains[0])], cwd=str(wd))
    if expect in got:
        print(f"  \u2705 stdout에 기대문자열 포함: '{expect}'")
        return True
    print(f"  \u274c stdout 불일치: got='{got.strip()}' expect~='{expect}'")
    return False


def main():
    if len(sys.argv) < 2:
        print("사용법: qa_verify.py <workdir> [expected_substr]", file=sys.stderr)
        return 2
    wd = Path(sys.argv[1]).resolve()
    expect = sys.argv[2] if len(sys.argv) > 2 else ""
    if not wd.is_dir():
        print(f"FATAL: workdir 없음: {wd}", file=sys.stderr)
        return 2

    print(f"===== QA VERIFY: {wd} =====")
    l1 = check_l1(wd)
    l2 = check_l2(wd)
    l2b = check_l2b_expected(wd, expect)

    print("===== 판정 =====")
    if l1 and l2 and l2b:
        print("\u2705 L1·L2 PASS → L3(교차검증/diff리뷰) 후 done 가능")
        return 0
    print("\u274c 미통과 → 재작업. 증거 없이 done 금지.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
