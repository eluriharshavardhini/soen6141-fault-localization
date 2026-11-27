"""One-command check that a benchmark instance is real: its test fails on the buggy code and
passes on the fixed code, inside a fresh pinned Docker container.

usage:
  python scripts/verify.py <instance_id>     # one instance
  python scripts/verify.py --all             # every instance
  python scripts/verify.py --list            # list instance ids
Requires: git, Docker, and uv on the host (pip install uv). Repositories are cloned into
./repos on first use.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from reproduce import run_one  # noqa: E402

SUBMODULES = {"toml-test": "https://github.com/BurntSushi/toml-test"}


def ensure_repo(repos: Path, inst: dict) -> None:
    dest = repos / inst["repo_dir"]
    if not dest.exists():
        print(f"cloning {inst['repo']} (history since 2025-04) ...", flush=True)
        subprocess.run(["git", "clone", "-q", "--shallow-since=2025-04-01",
                        f"https://github.com/{inst['repo']}", str(dest)], check=True)
    sub = repos.parent / "submods"
    for name, url in SUBMODULES.items():
        if inst["repo_dir"] == "tomlkit" and not (sub / name).exists():
            subprocess.run(["git", "clone", "-q", url, str(sub / name)], check=True)


def verify(inst: dict, repos: Path, work: Path) -> bool:
    ensure_repo(repos, inst)
    print(f"\n=== {inst['instance_id']}  ({inst['date'][:10]})")
    r = run_one({**inst, "src_files": inst["src_files_changed"]}, str(repos), work)
    ok = r["status"] == "kept" and set(inst["fail_to_pass"]) <= set(r.get("f2p", []))
    for t in inst["fail_to_pass"]:
        status = "FAILS on buggy, PASSES on fixed" if t in r.get("f2p", []) else "NOT reproduced"
        print(f"  {status}: {t}")
    print("  RESULT:", "VERIFIED" if ok else f"MISMATCH ({r.get('reason')})")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("instance_id", nargs="?")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    insts = {i["instance_id"]: i for i in map(json.loads, open(ROOT / "data/benchmark/instances.jsonl"))}
    if a.list or not (a.all or a.instance_id):
        print("\n".join(insts))
        return
    todo = list(insts.values()) if a.all else [insts[a.instance_id]]
    repos = ROOT / "repos"
    repos.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        results = [verify(i, repos, Path(work)) for i in todo]
    print(f"\n{sum(results)}/{len(results)} instances verified")
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
