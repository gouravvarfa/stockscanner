"""Where the backend is running, and how much it may keep in memory.

On Render the instance has 512 MB and its disk is wiped on every restart, so the server must hold as
little as possible: finished results live on the user's own device (browser storage / their PC), the
server only keeps a few of them transiently (an Excel download needs the last one). On a local run
there is no such limit, so the larger limits apply. Render sets RENDER=true in every runtime;
STATELESS_SERVER=1 forces the small limits anywhere (handy to test them locally)."""
from __future__ import annotations

import os

ON_RENDER = os.environ.get("RENDER") == "true"
STATELESS_SERVER = ON_RENDER or os.environ.get("STATELESS_SERVER") == "1"


def keep(local: int, stateless: int) -> int:
    """How many of something to keep in memory: `local` on a normal run, `stateless` on Render."""
    return stateless if STATELESS_SERVER else local


def rss_mb() -> int | None:
    """This process's resident memory in MB (Linux /proc only; None elsewhere) - logged during scans so a
    memory problem shows up in the logs before the instance is killed."""
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1]) // 1024
    except OSError:
        return None
    return None
