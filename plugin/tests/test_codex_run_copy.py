#!/usr/bin/env python3
"""codex_run.sh 사본 기반(A안) 위임 경로 회귀 — codex 를 no-op 스텁으로 대체해 CI 격리 검증.

검증 대상: bin/codex_run.sh 의 "사본 생성" 로직(실제 codex 호출·네트워크 없이):
  - --target 이 git repo → git worktree 사본(원본 커밋 HEAD 기준), 기존 파일이 사본에 존재.
  - --target 이 비-git → 임시폴더 복제 + git init baseline, 기존 파일이 사본에 존재.
  - --target 생략 → 그린필드(빈 폴더) baseline.
  - 원본 불가침(스텁 codex 가 아무것도 안 해도, 원본 파일이 안 변함).
왜 스텁인가: 실제 codex 는 네트워크·인증·모델이 필요해 CI 에서 재현 불가. 사본 생성 로직 자체는
codex 와 무관하므로, PATH 를 스텁 codex(아무 것도 안 하고 exit 0)로 덮어 로직만 결정적으로 검증한다.
(실제 코딩 위임의 end-to-end 는 baek 이 실측으로 양방향 확인 — 이 테스트는 '사본 생성' 회귀 못박기용.)

pytest 없어도 `python3 test_codex_run_copy.py` 로 직접 실행 가능(폴백 러너 호환).
"""
import os
import subprocess
import tempfile
import shutil
import stat
import textwrap

HERE = os.path.dirname(os.path.abspath(__file__))
CODEX_RUN = os.path.normpath(os.path.join(HERE, "..", "bin", "codex_run.sh"))


def _make_stub_bin(dirpath):
    """codex·scan_danger 우회용 스텁 디렉터리를 만들어 PATH 앞에 둔다.
    codex 스텁: 무엇을 하든 조용히 exit 0 (위임이 '아무 변경도 안 함' = 사본 생성만 검증)."""
    bind = os.path.join(dirpath, "stubbin")
    os.makedirs(bind, exist_ok=True)
    codex = os.path.join(bind, "codex")
    with open(codex, "w", encoding="utf-8") as f:
        f.write("#!/usr/bin/env bash\nexit 0\n")
    os.chmod(codex, 0o755)
    return bind


def _run_codex_run(target=None, extra_env=None):
    """codex_run.sh 를 스텁 환경에서 실행하고 (rc, stdout+stderr, project_root) 반환."""
    tmp = tempfile.mkdtemp(prefix="crun_")
    proot = os.path.join(tmp, "proot")
    os.makedirs(proot, exist_ok=True)
    # CODEX_HOME: auth.json 존재 요건만 충족(스텁 codex 는 안 읽음)
    ch = os.path.join(proot, ".codex_home")
    os.makedirs(ch, exist_ok=True)
    with open(os.path.join(ch, "auth.json"), "w") as f:
        f.write("{}")
    bind = _make_stub_bin(tmp)
    env = dict(os.environ)
    env["PATH"] = bind + os.pathsep + env.get("PATH", "")
    env["PROJECT_ROOT"] = proot
    env["CODEX_HOME"] = ch
    if extra_env:
        env.update(extra_env)
    cmd = ["bash", CODEX_RUN, "do nothing please", ""]
    if target:
        cmd += ["--target", target]
    p = subprocess.run(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       text=True, timeout=60)
    return p.returncode, p.stdout, proot, tmp


def _newest_run_dir(proot):
    runs = os.path.join(proot, "runs")
    if not os.path.isdir(runs):
        return None
    subs = [os.path.join(runs, d) for d in os.listdir(runs)]
    subs = [d for d in subs if os.path.isdir(d)]
    return max(subs, key=os.path.getmtime) if subs else None


def test_target_git_repo_uses_worktree_with_existing_code():
    """git repo target → 사본에 기존 파일이 들어있어야(기존 파일 수정 지원의 전제)."""
    tmp = tempfile.mkdtemp(prefix="crun_git_")
    try:
        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)
        subprocess.run(["git", "init", "-q", repo], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.email", "t@t"], check=True)
        subprocess.run(["git", "-C", repo, "config", "user.name", "t"], check=True)
        with open(os.path.join(repo, "existing.py"), "w") as f:
            f.write("X = 1\n")
        subprocess.run(["git", "-C", repo, "add", "-A"], check=True)
        subprocess.run(["git", "-C", repo, "commit", "-q", "-m", "init"], check=True)

        rc, out, proot, wtmp = _run_codex_run(target=repo)
        try:
            assert "git worktree" in out, f"worktree 모드 아님: {out[:400]}"
            wd = _newest_run_dir(proot)
            assert wd is not None, "run 디렉터리 미생성"
            # ★ 핵심: 사본에 기존 파일이 있어야 '기존 파일 수정'이 가능
            assert os.path.isfile(os.path.join(wd, "existing.py")), "사본에 기존 파일 없음(그린필드 회귀!)"
            # 원본 불가침
            assert open(os.path.join(repo, "existing.py")).read() == "X = 1\n", "원본 변경됨!"
        finally:
            # worktree 정리
            wd = _newest_run_dir(proot)
            if wd:
                subprocess.run(["git", "-C", repo, "worktree", "remove", "--force", wd],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            shutil.rmtree(wtmp, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_target_nongit_uses_clone_with_existing_code():
    """비-git target → 복제 사본에 기존 파일이 들어있어야."""
    tmp = tempfile.mkdtemp(prefix="crun_nongit_")
    try:
        proj = os.path.join(tmp, "proj")
        os.makedirs(proj)
        with open(os.path.join(proj, "data.txt"), "w") as f:
            f.write("original\n")
        rc, out, proot, wtmp = _run_codex_run(target=proj)
        try:
            assert "복제" in out or "clone" in out.lower(), f"복제 모드 아님: {out[:400]}"
            wd = _newest_run_dir(proot)
            assert wd is not None
            assert os.path.isfile(os.path.join(wd, "data.txt")), "복제 사본에 기존 파일 없음"
            assert open(os.path.join(proj, "data.txt")).read() == "original\n", "원본 변경됨!"
        finally:
            shutil.rmtree(wtmp, ignore_errors=True)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_no_target_is_greenfield_empty_baseline():
    """--target 생략 → 그린필드(빈 폴더). 하위호환."""
    rc, out, proot, wtmp = _run_codex_run(target=None)
    try:
        assert "그린필드" in out or "greenfield" in out.lower(), f"그린필드 아님: {out[:400]}"
        wd = _newest_run_dir(proot)
        assert wd is not None
        # 빈 baseline: .git 말고 사용자 파일 없어야
        entries = [e for e in os.listdir(wd) if e != ".git"]
        assert entries == [], f"그린필드인데 파일 있음: {entries}"
    finally:
        shutil.rmtree(wtmp, ignore_errors=True)


if __name__ == "__main__":
    fns = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    import sys
    p = 0; fails = []
    for n, f in fns:
        try:
            f(); p += 1; print(f"  PASS {n}")
        except Exception as e:
            fails.append(n); print(f"  FAIL {n}: {e}")
    print(f"{p}/{len(fns)} 통과")
    sys.exit(1 if fails else 0)
