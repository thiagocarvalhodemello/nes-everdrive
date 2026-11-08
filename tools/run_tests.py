"""
Runs the emulator regression tests in parallel and prints a summary. Tests split in
sections (tools/testparts.py) run one process per section.

  python tools/run_tests.py            # all tests
  python tools/run_tests.py favorites  # only the tests whose name contains "favorites"

Exit code 0 only when every test passed. The full output of a failed test is printed.
"""
import os, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor

TOOLS = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TOOLS)
# test file -> number of sections (0 = not split)
TESTS = {"test_search.py": 5, "test_favorites.py": 4, "test_game_art.py": 2, "test_theme_safety.py": 0}


def jobs(tests):
    for t in tests:
        n = TESTS[t]
        yield from ([(t, None)] if n == 0 else [(t, k) for k in range(1, n + 1)])


def run(job):
    name, k = job
    t0 = time.time()
    cmd = [sys.executable, os.path.join(TOOLS, name)] + ([] if k is None else ["--part", str(k)])
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace")
    label = name if k is None else f"{name} #{k}"
    return label, p.returncode, time.time() - t0, p.stdout + p.stderr


def main(args):
    tests = [t for t in TESTS if not args or any(a in t for a in args)]
    t0 = time.time()
    js = list(jobs(tests))
    with ThreadPoolExecutor(min(len(js), os.cpu_count() or 4)) as ex:
        results = list(ex.map(run, js))
    failed = [r for r in results if r[1] != 0]
    for name, rc, dt, out in failed:
        print(f"===== {name} (exit {rc}) =====\n{out}")
    for name, rc, dt, out in results:
        fails = sum(l.lstrip().startswith("[FAIL]") for l in out.splitlines())
        print(f"  {'OK  ' if rc == 0 else 'FAIL'}  {name:24s} {dt:6.1f} s" + (f"  ({fails} checks failed)" if fails else ""))
    print(f"{'PASSED' if not failed else f'FAILED ({len(failed)})'} in {time.time() - t0:.1f} s")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
