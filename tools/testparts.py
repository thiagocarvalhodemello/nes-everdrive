"""
Test sections that can run on their own (tools/run_tests.py runs them in parallel).

Each section of a test is a block with its own temporary SD card:
    for root in part(1):
        ...
runs the block when the test was started without --part, or with --part listing 1
(e.g. "python tools/test_search.py --part 2,4"). Sections must not share variables.
"""
import sys, tempfile


def selected():
    """set of section numbers from --part, or None (all)"""
    if "--part" not in sys.argv:
        return None
    return {int(x) for x in sys.argv[sys.argv.index("--part") + 1].split(",")}


def part(k):
    want = selected()
    if want is None or k in want:
        with tempfile.TemporaryDirectory() as root:
            yield root
