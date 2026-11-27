"""Dynamic validation (rules R1-R6 of protocol/SCREENING_PROTOCOL.md).

usage: python scripts/reproduce.py <repos_dir> <candidates.jsonl> <out_dir> [--jobs N]

For each candidate: export buggy tree B (+ test files from F) and fixed tree F, then in a
pinned Docker image install dependencies resolved as of the fix date (uv --exclude-newer),
run the touched test files twice on F and twice on B, and classify the outcome.
Results are appended to <out_dir>/repro_results.jsonl (resumable).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import io
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mine import is_test  # noqa: E402
from oracle import git  # noqa: E402

BASE_IMAGE = "python@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b"  # python:3.12-slim
ATTEMPT_CAP = 60

# repo_dir -> install config. "pythonpath": put this dir first on sys.path instead of installing.
REPO_ENV = {
    "sqlglot": {"deps": ["pytest", "duckdb", "pandas", "python-dateutil", "pytz"], "pythonpath": "."},
    "black": {"deps": ["pytest", "aiohttp"], "editable": ".[d]", "default_tests": ["tests/test_format.py"]},
    "astroid": {"deps": ["pytest", "attrs", "python-dateutil", "regex", "six", "typing-extensions",
                         "urllib3<2", "setuptools<82"], "editable": "."},
    "scrapy": {"deps": ["pytest", "attrs", "pexpect", "psutil", "pyftpdlib", "pygments", "pytest-timeout",
                        "sybil", "testfixtures"], "editable": "."},
    "tomlkit": {"deps": ["pytest", "PyYAML"], "editable": ".", "submodules": {"tests/toml-test": "toml-test"}},
    "marshmallow": {"deps": ["pytest", "simplejson"], "editable": "."},
    "click": {"deps": ["pytest"], "editable": "."},
}

RUNNER = r"""
set -e
command -v uv >/dev/null || pip install -q uv==0.11.32
cd /w/fixed
export SETUPTOOLS_SCM_PRETEND_VERSION=99.0.0 PIP_DISABLE_PIP_VERSION_CHECK=1
{install_fixed}
uv pip freeze --system > /w/out/freeze.txt
for i in 1 2; do (cd /w/fixed && {py_fixed} timeout 900 python -m pytest -p no:cacheprovider -q -rN --junitxml=/w/out/fixed_$i.xml {tests} > /w/out/fixed_$i.log 2>&1 || true); done
{install_buggy}
for i in 1 2; do (cd /w/buggy && {py_buggy} timeout 900 python -m pytest -p no:cacheprovider -q -rN --junitxml=/w/out/buggy_$i.xml {tests} > /w/out/buggy_$i.log 2>&1 || true); done
"""


def export(repo: str, rev: str, dest: Path) -> None:
    data = subprocess.run(["git", "-C", repo, "archive", "--format=tar", rev], check=True,
                          capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tf:
        tf.extractall(dest, filter="data")


def overlay_tests(repo: str, fix: str, buggy_dir: Path) -> list[str]:
    rows = git(repo, "diff", "--name-status", "--no-renames", f"{fix}^", fix).splitlines()
    touched = []
    for row in rows:
        status, path = row.split("\t", 1)
        if not is_test(path):
            continue
        target = buggy_dir / path
        if status == "D":
            target.unlink(missing_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(subprocess.run(["git", "-C", repo, "show", f"{fix}:{path}"], check=True,
                                          capture_output=True).stdout)
        touched.append(path)
    return touched


def parse_junit(path: Path) -> dict[str, dict]:
    """nodeid-ish key -> {outcome, message}"""
    res: dict[str, dict] = {}
    if not path.exists():
        return res
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError:
        return res
    for tc in root.iter("testcase"):
        key = f"{tc.get('classname')}::{tc.get('name')}"
        outcome, msg = "passed", ""
        for child in tc:
            if child.tag in ("failure", "error"):
                outcome = child.tag
                msg = (child.get("message") or "") + "\n" + (child.text or "")
            elif child.tag == "skipped":
                outcome = "skipped"
        res[key] = {"outcome": outcome, "message": msg[:6000]}
    return res


def collection_errored(log: Path) -> bool:
    txt = log.read_text(errors="replace") if log.exists() else ""
    return bool(re.search(r"ERROR collecting|errors? during collection|no tests ran", txt))


ADDED_NAME = re.compile(r"^\+\s*(?:def|class|async def)\s+(\w+)|^\+\s*(\w+)\s*[:=]", re.M)


def added_names(repo: str, fix: str, src_files: list[str]) -> set[str]:
    diff = git(repo, "diff", f"{fix}^", fix, "--", *src_files)
    return {a or b for a, b in ADDED_NAME.findall(diff)}


def classify(cand: dict, out: Path, repo: str) -> dict:
    f1, f2 = parse_junit(out / "fixed_1.xml"), parse_junit(out / "fixed_2.xml")
    b1, b2 = parse_junit(out / "buggy_1.xml"), parse_junit(out / "buggy_2.xml")
    res = {"n_tests_fixed": len(f1)}
    if not f1:
        return {**res, "status": "dropped", "reason": "env" if not collection_errored(out / "fixed_1.log") else "fixed_collection_error"}
    if collection_errored(out / "buggy_1.log") or not b1:
        return {**res, "status": "dropped", "reason": "collection_error"}
    bad = ("failure", "error")
    f2p = [k for k, v in f1.items() if v["outcome"] == "passed" and b1.get(k, {}).get("outcome") in bad]
    flaky = [k for k in set(f1) | set(b1)
             if f1.get(k, {}).get("outcome") != f2.get(k, {}).get("outcome")
             or b1.get(k, {}).get("outcome") != b2.get(k, {}).get("outcome")]
    res.update({"f2p": f2p, "flaky_tests": flaky})
    if not f2p:
        return {**res, "status": "dropped", "reason": "no_f2p"}
    if any(k in flaky for k in f2p):
        return {**res, "status": "dropped", "reason": "flaky"}
    names = added_names(repo, cand["fix_commit"], cand["src_files"])
    msgs = [b1[k]["message"] for k in f2p]
    for m in msgs:
        if re.search(r"\b(ImportError|ModuleNotFoundError|NameError)\b", m.split("\n")[0]):
            return {**res, "status": "dropped", "reason": "collection_error"}
        a = re.search(r"has no attribute '(\w+)'", m)
        if a and a.group(1) in names:
            return {**res, "status": "dropped", "reason": "collection_error"}
    ran = [k for k, v in b1.items() if v["outcome"] != "skipped"]
    failing_b = [k for k in ran if b1[k]["outcome"] in bad]
    if ran and len(failing_b) / len(ran) > 0.5 and len(ran) >= 4:
        return {**res, "status": "dropped", "reason": "transplant_broken"}
    res["buggy_failures"] = {k: b1[k]["message"] for k in f2p}
    return {**res, "status": "kept"}


def run_one(cand: dict, repos_dir: str, work: Path) -> dict:
    name = cand["repo_dir"]
    repo = str(Path(repos_dir) / name)
    cfg = REPO_ENV[name]
    wd = work / cand["fix_commit"][:12]
    shutil.rmtree(wd, ignore_errors=True)
    (wd / "out").mkdir(parents=True)
    export(repo, cand["fix_commit"], wd / "fixed")
    export(repo, cand["buggy_commit"], wd / "buggy")
    touched = overlay_tests(repo, cand["fix_commit"], wd / "buggy")
    # git-archive omits submodules: export each pinned submodule commit from a local clone
    for sub_path, sub_clone in cfg.get("submodules", {}).items():
        for t, rev in (("fixed", cand["fix_commit"]), ("buggy", cand["buggy_commit"])):
            row = git(repo, "ls-tree", rev, sub_path).split()
            if row and row[1] == "commit":
                dest = wd / t / sub_path
                shutil.rmtree(dest, ignore_errors=True)
                dest.mkdir(parents=True)
                export(str(Path(repos_dir).parent / "submods" / sub_clone), row[2], dest)
    tests = [p for p in touched if p.endswith(".py") and Path(p).name not in ("conftest.py", "__init__.py")
             and (Path(p).name.startswith("test") or Path(p).name.endswith("_test.py"))]
    if not tests:
        tests = cfg.get("default_tests", [])
    if not tests:
        return {"status": "dropped", "reason": "no_runnable_test"}
    # dependency pin: newest releases available one day after the fix commit
    pin = (datetime.fromisoformat(cand["date"]) + timedelta(days=1)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    dep_list = list(cfg["deps"])
    # scrapy: older trees get --reactor from pytest-twisted, newer ones define it in conftest.py
    if name == "scrapy":
        conftest = wd / "fixed" / "conftest.py"
        if not (conftest.exists() and re.search(r'addoption\(\s*"--reactor"', conftest.read_text())):
            dep_list.append("pytest-twisted")
    deps = " ".join(f"'{d}'" for d in dep_list)
    if "pythonpath" in cfg:
        install_fixed = f"uv pip install --system --exclude-newer {pin} {deps}"
        install_buggy = "true"
        py_fixed, py_buggy = "PYTHONPATH=/w/fixed", "PYTHONPATH=/w/buggy"
    else:
        install_fixed = f"uv pip install --system --exclude-newer {pin} {deps} -e '/w/fixed{cfg['editable'][1:]}'"
        install_buggy = f"cd /w/buggy && uv pip install --system --no-deps --exclude-newer {pin} -e '/w/buggy{cfg['editable'][1:]}'"
        py_fixed = py_buggy = ""
    script = RUNNER.format(install_fixed=install_fixed, install_buggy=install_buggy, py_fixed=py_fixed,
                           py_buggy=py_buggy, tests=" ".join(tests))
    (wd / "out" / "run.sh").write_text(script)
    env_args = []
    if os.environ.get("HTTPS_PROXY"):  # only needed behind an egress proxy
        env_args = ["-e", f"HTTPS_PROXY={os.environ['HTTPS_PROXY']}"]
        ca = os.environ.get("FLB_CA_BUNDLE", "/root/.ccr/ca-bundle.crt")
        if Path(ca).exists():
            env_args += ["-e", "SSL_CERT_FILE=/ca.crt", "-e", "PIP_CERT=/ca.crt", "-e", "UV_SYSTEM_CERTS=1",
                         "-v", f"{ca}:/ca.crt:ro"]
    if sys.platform.startswith("linux") and shutil.which("uv"):  # reuse host uv binary (faster)
        env_args += ["-v", f"{shutil.which('uv')}:/usr/local/bin/uv:ro"]
    cache = Path(os.environ.get("FLB_UV_CACHE", Path.home() / ".cache" / "fl-bench-uv"))
    cache.mkdir(parents=True, exist_ok=True)
    cmd = ["docker", "run", "--rm", "--network", "host", *env_args,
           "-e", "UV_CACHE_DIR=/uvcache", "-e", "UV_LINK_MODE=copy", "-v", f"{cache}:/uvcache",
           "-v", f"{wd}:/w", BASE_IMAGE, "bash", "/w/out/run.sh"]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    (wd / "out" / "docker.log").write_text(proc.stdout + proc.stderr)
    res = classify(cand, wd / "out", repo)
    res["tests_run"] = tests
    res["dep_pin"] = pin
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("repos_dir")
    ap.add_argument("candidates")
    ap.add_argument("out_dir")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--work", default="/home/user/work")
    ap.add_argument("--only", default=None, help="comma-separated repo_dir filter")
    a = ap.parse_args()
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    resf = out / "repro_results.jsonl"
    done = set()
    if resf.exists():
        done = {json.loads(l)["fix_commit"] for l in resf.read_text().splitlines() if l.strip()}
    cands = [json.loads(l) for l in open(a.candidates)]
    per_repo: dict[str, int] = {}
    todo = []
    for c in cands:  # already sorted oldest first
        if c["repo_dir"] not in REPO_ENV or (a.only and c["repo_dir"] not in a.only.split(",")):
            continue
        per_repo[c["repo_dir"]] = per_repo.get(c["repo_dir"], 0) + 1
        if per_repo[c["repo_dir"]] > ATTEMPT_CAP or c["fix_commit"] in done:
            continue
        todo.append(c)
    print(f"{len(todo)} to run", flush=True)

    def job(c):
        try:
            r = run_one(c, a.repos_dir, Path(a.work))
        except Exception as e:  # noqa: BLE001
            r = {"status": "dropped", "reason": "env", "error": repr(e)[:500]}
        r = {"repo": c["repo"], "fix_commit": c["fix_commit"], **r}
        with open(resf, "a") as fh:
            fh.write(json.dumps(r) + "\n")
        print(c["repo_dir"], c["fix_commit"][:10], r["status"], r.get("reason", ""), flush=True)

    with ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(job, todo))


if __name__ == "__main__":
    main()
