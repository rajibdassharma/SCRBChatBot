"""Resource governor for the batch analysis jobs.

WHY THIS EXISTS
---------------
On 2026-08-04 the development laptop bugchecked three times in twenty
minutes while profiling the statement corpus:

    0x0000010E  VIDEO_MEMORY_MANAGEMENT_INTERNAL   15:43 . 15:53 . 16:02

The jobs never touched the GPU -- pdfplumber and Pillow are pure CPU.
But the machine has hybrid graphics, and the Intel Arc iGPU allocates
its video memory FROM SYSTEM RAM. Twenty parallel workers, each holding
a fully-parsed PDF, exhausted the pool the display driver was drawing
from. The bug is the driver's; the trigger was ours.

So these jobs no longer get to decide their own concurrency. Everything
here exists to keep a batch run invisible to the person using the
machine:

  1. Workers are budgeted from FREE MEMORY, not from core count. Cores
     are why we used 20; memory is why 20 was wrong.
  2. A fixed reserve is held back for the OS and the shared iGPU pool
     and never allocated to workers.
  3. Workers run at below-normal priority, so the compositor and the
     editor keep their timeslice.
  4. Workers are recycled after a fixed number of files, which bounds
     any per-file leak instead of trusting there is none.
  5. The parent re-checks free memory between chunks and stalls -- or
     shrinks the pool -- when the machine gets tight.

No third-party dependency. psutil would do most of this, but it is not
in requirements.txt and the production target is Ubuntu, so the probes
below are written against the OS directly for both platforms.
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import sys
import time

IS_WIN = sys.platform.startswith("win")

def _env_float(name: str, default: float) -> float:
    """Read a positive float from the environment, else the default.

    Deliberately forgiving: a typo in a unit file must not stop the
    nightly job. A bad value falls back to the default and the job
    runs at laptop-safe settings, which is never dangerous -- only
    slow.
    """
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        val = float(raw)
    except ValueError:
        return default
    return val if val > 0 else default


#: Held back for the OS, the desktop compositor and -- the reason this
#: number is generous rather than token -- the Intel Arc iGPU's shared
#: video memory. This is the reserve whose exhaustion bugchecked the
#: machine, so it is not a knob worth shaving ON THIS MACHINE.
#:
#: It IS a knob on a different machine, which is why it reads the
#: environment. 10 GB describes a 32 GB laptop with hybrid graphics.
#: The production target is a headless 4 vCPU / 8 GB Ubuntu VM with no
#: iGPU and no compositor: nothing there is drawing video memory from
#: system RAM, and reserving 10 GB of 8 would make every plan come out
#: negative and pin the job at one worker forever.
#:
#: The default stays at the safe end so an unset variable can only cost
#: speed, never stability. Production sets
#: CFDSR_ANALYSIS_RESERVE_GB=2.0 in the service unit.
RESERVE_GB = _env_float("CFDSR_ANALYSIS_RESERVE_GB", 10.0)

#: Budget per worker.
#:
#: 0.5 GB, and that is a MEASUREMENT, not a loosening. The original 1.5
#: was a guess made before extract._release() existed, when a worker
#: held every parsed page of its document at once. With page caches now
#: flushed as the reader advances, the observed peak is 0.15 GB — and
#: that was on a 1,128-page statement, the worst case in the corpus.
#: 0.5 keeps better than 3x headroom over the worst thing measured.
#:
#: The RESERVE_GB guard above is untouched. That is the one protecting
#: the shared iGPU pool, and it is not a knob to trade for speed.
PER_WORKER_GB = 0.5

#: Never exceed this regardless of how much memory is free. Past a
#: point these jobs are I/O bound and extra workers only add pressure.
#:
#: Also capped by core count -- as a CEILING, never as the basis. The
#: distinction is the whole lesson of this module: choosing workers
#: FROM cores is what put 20 of them on this machine and bugchecked
#: it. Using cores only to lower a memory-derived number is safe, and
#: it matters on the 4 vCPU production VM, where 8 processes would
#: thrash for no throughput. Locally (22 cores) this changes nothing.
MAX_WORKERS = min(8, os.cpu_count() or 8)

#: Recycle a worker after this many files. Bounds leaks without paying
#: process-spawn cost on every file.
TASKS_PER_CHILD = 20

#: Deadline for one chunk of work, as seconds PER FILE in the chunk.
#:
#: Named constants rather than literals inside governed_map because a
#: timeout that cannot be measured or adjusted is a guess that outlives
#: its evidence. 60s is ~55x the observed 1.1s average and still clears
#: the corpus's worst case -- a 1,421-page statement -- comfortably.
CHUNK_TIMEOUT_PER_FILE_S = _env_float("CFDSR_ANALYSIS_CHUNK_TIMEOUT_S", 60.0)

#: Floor for that deadline, so a small final chunk is not given an
#: unreasonably tight one.
CHUNK_TIMEOUT_FLOOR_S = _env_float("CFDSR_ANALYSIS_CHUNK_FLOOR_S", 600.0)

#: Pause and re-check when free memory falls below this.
#:
#: DERIVED from the reserve rather than set independently, because the
#: two are not free to disagree. A low-water mark above the reserve
#: describes a machine that must pause for memory it was never going
#: to be given: on an 8 GB VM the old fixed 6.0 would have stalled
#: every chunk check, waited out the full timeout, halved the pool,
#: and crawled -- while the box was in fact perfectly healthy.
#:
#: 0.6x keeps the original relationship (6.0 of 10.0) intact, so the
#: laptop's behaviour is unchanged and any future reserve change
#: carries its low-water mark along instead of leaving this stale.
LOW_WATER_GB = _env_float("CFDSR_ANALYSIS_LOW_WATER_GB", RESERVE_GB * 0.6)


# --------------------------------------------------------------------
# memory probes
# --------------------------------------------------------------------

def available_bytes() -> int:
    """Physical memory actually available to allocate, or 0 if unknown.

    'Available' rather than 'free' deliberately: on both platforms free
    excludes reclaimable cache, and budgeting against it would leave
    most of the machine idle.
    """
    if IS_WIN:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD),
                ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return int(st.ullAvailPhys)
        return 0
    try:
        with open("/proc/meminfo", encoding="ascii") as fh:
            for line in fh:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) * 1024
    except OSError:
        pass
    return 0


def total_bytes() -> int:
    if IS_WIN:
        import ctypes
        from ctypes import wintypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
            return int(st.ullTotalPhys)
        return 0
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError):
        return 0


def rss_bytes() -> int:
    """Resident set of THIS process. Used by workers to self-police."""
    if IS_WIN:
        import ctypes
        from ctypes import wintypes

        class PMC(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        c = PMC()
        c.cb = ctypes.sizeof(PMC)
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE
        h = k32.GetCurrentProcess()
        # Try kernel32's K32GetProcessMemoryInfo first and psapi second.
        # Modern Windows forwards the psapi export, but which one is
        # resolvable varies; calling the unresolved one returns 0 and
        # the probe silently reports "0.00 GB", which is worse than no
        # probe at all — it reads as "using no memory".
        for lib, name in ((k32, "K32GetProcessMemoryInfo"),
                          (getattr(ctypes.windll, "psapi", None),
                           "GetProcessMemoryInfo")):
            fn = getattr(lib, name, None) if lib else None
            if fn is None:
                continue
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            if fn(h, ctypes.byref(c), c.cb):
                return int(c.WorkingSetSize)
        return 0
    try:
        with open("/proc/self/statm", encoding="ascii") as fh:
            return int(fh.read().split()[1]) * os.sysconf("SC_PAGE_SIZE")
    except (OSError, ValueError, IndexError):
        return 0


def gb(n: int | float) -> float:
    return n / (1024 ** 3)


# --------------------------------------------------------------------
# scheduling
# --------------------------------------------------------------------

def plan_workers(requested: int = 0, per_worker_gb: float = PER_WORKER_GB,
                 reserve_gb: float = RESERVE_GB,
                 cap: int = MAX_WORKERS) -> int:
    """How many workers this machine can afford RIGHT NOW.

    `requested` is an upper bound the caller may ask for, never a
    guarantee — a --workers flag cannot override the memory budget,
    because a flag is what caused the crash this module exists to
    prevent.
    """
    avail = available_bytes()
    cores = os.cpu_count() or 4
    # Leave two cores for the OS and whatever the person is doing.
    by_cpu = max(1, cores - 2)
    by_mem = int(max(0.0, gb(avail) - reserve_gb) // per_worker_gb) if avail else 1
    n = max(1, min(by_cpu, by_mem or 1, cap))
    if requested > 0:
        n = min(n, requested)
    return n


def lower_priority() -> None:
    """Run below normal, so a batch job never outranks the desktop.

    Called in each worker at startup. On Windows this is the difference
    between a responsive machine and a frozen one during a long run.
    """
    try:
        if IS_WIN:
            import ctypes
            from ctypes import wintypes
            BELOW_NORMAL_PRIORITY_CLASS = 0x00004000
            k32 = ctypes.windll.kernel32
            # restype MUST be set. GetCurrentProcess returns the
            # pseudo-handle (HANDLE)-1; with ctypes' default int restype
            # that is truncated to 32 bits on a 64-bit build, so
            # SetPriorityClass receives a bad handle, returns 0, and —
            # because it signals failure by return value rather than by
            # raising — the `except` below never fires. The call looked
            # like it worked for the whole of a run at Normal priority.
            k32.GetCurrentProcess.restype = wintypes.HANDLE
            k32.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k32.SetPriorityClass.restype = wintypes.BOOL
            if not k32.SetPriorityClass(k32.GetCurrentProcess(),
                                        BELOW_NORMAL_PRIORITY_CLASS):
                raise OSError(ctypes.get_last_error())
        else:
            os.nice(10)
    except Exception:                                  # noqa: BLE001
        # Deliberately non-fatal: running at normal priority is a
        # comfort problem, not a correctness one, and must not abort a
        # multi-hour job.
        pass


def _init_worker() -> None:
    lower_priority()


def wait_for_memory(low_water_gb: float = LOW_WATER_GB, timeout: float = 120.0,
                    log=None) -> bool:
    """Block until memory recovers, or give up after `timeout`.

    Returns True if there is room. The caller decides what to do with
    False; the driver shrinks its pool rather than pressing on.
    """
    t0 = time.time()
    while time.time() - t0 < timeout:
        a = gb(available_bytes())
        if a <= 0 or a >= low_water_gb:
            return True
        if log:
            log(f"  memory low ({a:.1f} GB free) — pausing {low_water_gb} GB needed")
        time.sleep(3.0)
    return False


def governed_map(fn, items, requested_workers: int = 0, chunk: int = 0,
                 per_worker_gb: float = PER_WORKER_GB, log=None):
    """Parallel map that yields (item, result) and keeps the box alive.

    Differs from ProcessPoolExecutor().map in the ways that matter here:

      - Concurrency comes from plan_workers(), i.e. from free memory.
      - Work is submitted in bounded chunks instead of all at once, so
        the pending-futures list cannot itself become the memory
        problem on a 16,000-item run.
      - Free memory is re-checked between chunks; if it has fallen, the
        pool is rebuilt smaller rather than pushed harder.
      - Workers start at below-normal priority and are recycled every
        TASKS_PER_CHILD items.
      - A worker that dies takes only its own item down: the item is
        yielded with None and the run continues.
    """
    items = list(items)
    if not items:
        return
    workers = plan_workers(requested_workers, per_worker_gb)
    chunk = chunk or max(workers * 8, 32)
    if log:
        log(f"  {workers} workers, chunks of {chunk} "
            f"({gb(available_bytes()):.1f} GB free, {RESERVE_GB:.0f} GB reserved)")

    # The ceiling is what was ASKED FOR, not what the opening plan
    # happened to grant. Anchoring it to the grant meant a job that
    # started while the machine was briefly busy stayed throttled for
    # its whole life: the long-statement pass opened at 1 worker under
    # transient pressure, and closing a couple of applications freed
    # 3.7 GB that it could never then use. Recovery has to be able to
    # reach the request, or "re-plan upward" only ever means "back to
    # the bad number we started with".
    ceiling = requested_workers if requested_workers > 0 else MAX_WORKERS
    i = 0
    while i < len(items):
        if not wait_for_memory(log=log):
            new = max(1, workers // 2)
            if log and new != workers:
                log(f"  memory still tight — reducing {workers} -> {new} workers")
            workers = new
        else:
            # Re-plan upward as well as down. A multi-hour run opens
            # while the machine happens to be busy and would otherwise
            # stay throttled for the whole job even after the user
            # closes whatever was holding the memory. Bounded by the
            # opening plan so this can only recover lost capacity, never
            # exceed what was judged safe at the start.
            re_planned = min(ceiling, plan_workers(ceiling, per_worker_gb))
            if re_planned > workers:
                if log:
                    log(f"  memory recovered — {workers} -> {re_planned} workers")
                workers = re_planned
        batch = items[i:i + chunk]
        # A CHUNK MUST BE ABLE TO GIVE UP.
        #
        # as_completed() had no timeout, and on 2026-08-10 a run wedged
        # for 13 minutes: 0% CPU, no disk I/O, zero worker children, an
        # idle DB connection, no progress. A worker had died without its
        # future ever resolving, so as_completed waited for a result
        # that was never coming.
        #
        # `with ProcessPoolExecutor(...)` could not have rescued it,
        # which is why the pool is managed by hand below: __exit__ calls
        # shutdown(wait=True) and would have blocked on the same dead
        # worker. Both the wait and the teardown need an escape.
        #
        # The budget covers the whole chunk, because that is what
        # as_completed measures. See CHUNK_TIMEOUT_PER_FILE_S.
        budget = max(CHUNK_TIMEOUT_FLOOR_S,
                     CHUNK_TIMEOUT_PER_FILE_S * len(batch))
        timed_out = False
        ex = cf.ProcessPoolExecutor(
            max_workers=workers,
            initializer=_init_worker,
            max_tasks_per_child=TASKS_PER_CHILD,
        )
        try:
            futs = {ex.submit(fn, it): it for it in batch}
            pending = set(futs)
            try:
                for fut in cf.as_completed(futs, timeout=budget):
                    pending.discard(fut)
                    it = futs[fut]
                    try:
                        yield it, fut.result()
                    except Exception:                  # noqa: BLE001
                        # A crashed worker must not abort a 16k-file run.
                        yield it, None
            except TimeoutError:
                timed_out = True
                if log:
                    log(f"  chunk stalled after {budget:.0f}s — abandoning "
                        f"{len(pending)} file(s) and rebuilding the pool")
                # Yielded as failures rather than dropped. The caller
                # records a failure, and `failed` is retried on the next
                # run, so a stall costs a retry and never a file.
                for fut in pending:
                    fut.cancel()
                    yield futs[fut], None
        finally:
            # wait=False ONLY after a timeout. In the normal case the
            # workers must still be joined, so their memory is actually
            # back before the next chunk is planned — that join is the
            # whole reason the pool is rebuilt per chunk.
            ex.shutdown(wait=not timed_out, cancel_futures=True)
        # Pool torn down per chunk on purpose: it is the only way to
        # guarantee every worker's memory actually goes back, and the
        # spawn cost is amortised over `chunk` files.
        i += chunk
