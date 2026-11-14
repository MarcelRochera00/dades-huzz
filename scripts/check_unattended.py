"""Check that this laptop can run the serving loop unattended: keep-awake works, and the watchdog restarts a
loop that exits or hangs. Touches nothing in RawTree, so it is safe while another loop serves.

    uv run python scripts/check_unattended.py
"""

import sys

from dades_huzz.serving.watchdog import self_check

if __name__ == "__main__":
    ok = self_check()
    print(
        "ALL PASS"
        if ok
        else "SOMETHING FAILED: tell lane A (Marcel) and paste this output"
    )
    sys.exit(0 if ok else 1)
