"""Where the backend is running, and how much it may keep in memory.

On Render the instance has 512 MB and its disk is wiped on every restart, so the server must hold as
little as possible: finished results live on the user's own device (browser storage / their PC), the
server only keeps a few of them transiently (an Excel download needs the last one). On a local run
there is no such limit, so the larger limits apply. Render sets RENDER=true in every runtime;
STATELESS_SERVER=1 forces the small limits anywhere (handy to test them locally)."""
from __future__ import annotations

import asyncio
import ctypes
import gc
import logging
import os
import sys
import time

logger = logging.getLogger("scanner.runtime")

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

# ---- Memory on Render (2026-11-20) ------------------------------------------------------------------------
# Render killed the instance at "used over 512MB" during an A Group scan. On Linux, glibc gives every thread its
# own malloc arena and keeps freed memory inside them, so a long multi-threaded pandas workload grows its RSS
# without leaking anything (the same scan stays flat on Windows). Two fixes: at most 2 arenas, and giving freed
# memory back to the OS (malloc_trim) regularly. Both are no-ops off Linux.
_libc = None
if sys.platform.startswith("linux"):
    try:
        _libc = ctypes.CDLL("libc.so.6")
    except OSError:
        _libc = None

M_ARENA_MAX = -8
SOFT_LIMIT_MB = 380  # above this: free what we can (gc + malloc_trim)
HARD_LIMIT_MB = 440  # above this: a scan waits before fetching the next stock, instead of the instance dying


def tune_malloc() -> bool:
    """Limit glibc to 2 malloc arenas. Call once at startup, before worker threads start."""
    if _libc is None:
        return False
    try:
        return bool(_libc.mallopt(M_ARENA_MAX, 2))
    except (AttributeError, OSError):
        return False


def trim_memory() -> int | None:
    """Collect garbage and hand freed heap pages back to the OS. Returns the RSS in MB afterwards (None off Linux)."""
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except (AttributeError, OSError):
            pass
    return rss_mb()


async def memory_guard(label: str = "") -> None:
    """Before starting more work on Render: trim when memory is high, and wait (up to ~90 s) while it stays near the
    limit, so in-flight stocks can finish and free their memory. Never raises; does nothing on a local run."""
    if not STATELESS_SERVER:
        return
    mem = rss_mb()
    if mem is None or mem < SOFT_LIMIT_MB:
        return
    mem = trim_memory()
    waited = 0.0
    while mem is not None and mem >= HARD_LIMIT_MB and waited < 90:
        if waited == 0:
            logger.warning("memory %d MB is near the 512 MB limit - %s waits for it to come down", mem, label or "work")
        await asyncio.sleep(2)
        waited += 2
        mem = trim_memory()
    if waited:
        logger.info("memory back to %s MB after waiting %.0f s (%s)", mem, waited, label or "work")


_last_trim = 0.0


def trim_now_and_then(min_interval_s: float = 20.0) -> None:
    """Cheap to call often (e.g. after every stock): trims at most every `min_interval_s` seconds on Render."""
    global _last_trim
    if not STATELESS_SERVER:
        return
    now = time.monotonic()
    if now - _last_trim >= min_interval_s:
        _last_trim = now
        trim_memory()
