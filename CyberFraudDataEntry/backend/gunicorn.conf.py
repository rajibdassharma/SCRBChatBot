"""Gunicorn configuration for the CyberFraud Data Entry backend.

Loaded by deploy/cyberfraud-backend.service:

    ExecStart=/opt/cyberfraud/backend/venv/bin/gunicorn cyber_fraud:app -c gunicorn.conf.py

WHY THIS FILE EXISTS IN GIT NOW
-------------------------------
It did not until 2026-08-23. It lived only on the production server,
hand-written at some point and never committed, so it was invisible to
every clone. Standing up a new machine got as far as starting the service
and then failed with::

    gunicorn: Error: 'gunicorn.conf.py' doesn't exist

which also means a genuine recovery OF PRODUCTION would have hit the same
wall, at the point where the server was already gone. Anything the
service needs to start has to be in the repository.
"""

import os

# ── Binding ─────────────────────────────────────────────────────────────
# Localhost only. nginx terminates TLS and proxies to 127.0.0.1:8000; the
# backend is never exposed directly. See deploy/nginx.conf.
bind = "127.0.0.1:8000"

# ── Workers ─────────────────────────────────────────────────────────────
# UvicornWorker, because the app is ASGI (FastAPI) and every route is
# async. A sync worker here would serve requests but serialise them.
worker_class = "uvicorn.workers.UvicornWorker"

# Sized from the machine rather than hard-coded: production has 2 vCPUs,
# the DGX Spark has 20. These are async workers, so a handful saturates
# even a large box — the ceiling is deliberate, and each worker holds its
# own MySQL pool (10 + 5 overflow), so more workers means more connections
# against MySQL's max_connections.
workers = int(os.environ.get("CFDSR_GUNICORN_WORKERS", "0")) or min(
    4, max(2, os.cpu_count() or 2)
)

# NEVER preload. database.py builds the async engine at import time, so
# preloading would create it in the parent and fork it into every worker,
# handing them a shared connection pool and an event loop that belongs to
# a process that no longer exists. Symptoms are intermittent and ugly.
preload_app = False

# ── Timeouts ────────────────────────────────────────────────────────────
# 120s rather than the default 30: the PDF and Excel reports render
# synchronously inside the request, and a 45-PS landscape sheet is not
# fast. Below this, exports fail as worker timeouts under load.
timeout = 120
graceful_timeout = 30
keepalive = 5

# ── Logging ─────────────────────────────────────────────────────────────
# Files, not stdout, because Operations.md documents these paths and the
# systemd unit grants write access to exactly this directory
# (ReadWritePaths=/var/log/cyberfraud). If you change these, change
# ProtectSystem/ReadWritePaths in the unit too or the service will not
# start.
_LOG_DIR = os.environ.get("CFDSR_LOG_DIR", "/var/log/cyberfraud")
# Joined with "/" rather than os.path.join: this file is only ever read
# on Linux, and os.path.join produces backslashes if anyone evaluates it
# on Windows while checking the config.
accesslog = f"{_LOG_DIR}/access.log"
errorlog = f"{_LOG_DIR}/error.log"
loglevel = os.environ.get("CFDSR_LOG_LEVEL", "info")

# Send worker tracebacks to errorlog rather than losing them.
capture_output = True

# Default access format plus request time, which is what you want when
# someone reports "the dashboard is slow".
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(L)ss'

# ── systemd ─────────────────────────────────────────────────────────────
# The unit is Type=notify, so gunicorn must tell systemd when it is ready.
# Gunicorn does that automatically when NOTIFY_SOCKET is in the
# environment; nothing to configure here. Do not set daemon = True — under
# Type=notify that makes systemd wait for a readiness signal that never
# comes, and the start times out.
daemon = False

proc_name = "cyberfraud-backend"
