"""Run engage-mocks.

    .venv/bin/python -m mocks --riders data/gen/demo_s42/firestore/hireme_riders.ndjson --sink
    FIRESTORE_EMULATOR_HOST=127.0.0.1:8080 .venv/bin/python -m mocks --store firestore \\
        --project demo-hireme-engage-dev --riders-from-firestore --engine-url http://127.0.0.1:8000

--sink mounts a webhook receiver at /sink and points the mocks at it (until the engine API exists).
The webhook secret comes from ENGAGE_WEBHOOK_SECRET; without it a fixed dev value is used.
"""
from __future__ import annotations

import argparse
import logging
import os
import threading
from pathlib import Path

from mocks.clock import Clock, parse_ts
from mocks.common import DEV_WEBHOOK_SECRET, MockConfig
from mocks.faults import PROFILES
from mocks.riders import RiderDirectory
from mocks.store import MemoryStore

log = logging.getLogger("mocks")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8090)
    ap.add_argument("--riders", type=Path, help="hireme_riders.ndjson from a generation")
    ap.add_argument("--riders-from-firestore", action="store_true", help="read hireme_riders from --project")
    ap.add_argument("--store", choices=("memory", "firestore"), default="memory")
    ap.add_argument("--project", help="Firestore project for --store firestore / --riders-from-firestore")
    ap.add_argument("--engine-url", help="base URL that receives webhooks")
    ap.add_argument("--sink", action="store_true", help="mount the dev webhook sink at /sink and use it")
    ap.add_argument("--profile", choices=sorted(PROFILES), default="default")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--scale", type=float, default=1.0, help="virtual seconds per real second")
    ap.add_argument("--start", help="virtual start time, ISO with offset (default: now)")
    ap.add_argument("--data-dir", type=Path, help="generator output for /demo/data (default: the --riders generation)")
    ap.add_argument("--data-project", default="hireme-engage-dev",
                    help="dev project /demo/data reads live (Firestore counts + small BigQuery aggregates)")
    ap.add_argument("--no-cloud-data", action="store_true", help="/demo/data shows the local files only")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    secret = os.environ.get("ENGAGE_WEBHOOK_SECRET") or DEV_WEBHOOK_SECRET
    if secret == DEV_WEBHOOK_SECRET:
        log.warning("ENGAGE_WEBHOOK_SECRET not set: signing webhooks with the fixed dev secret")
    engine_url = f"http://{args.host}:{args.port}/sink" if args.sink else args.engine_url
    cfg = MockConfig(engine_url=engine_url, webhook_secret=secret, profile=args.profile, seed=args.seed,
                     project_id=args.project or "hireme-engage-dev")

    fs_client = None
    if args.store == "firestore" or args.riders_from_firestore:
        from google.cloud import firestore
        from sim.loaders import check_project
        if not args.project:
            ap.error("--project is required with Firestore")
        check_project(args.project)
        if not os.environ.get("FIRESTORE_EMULATOR_HOST"):
            log.warning("FIRESTORE_EMULATOR_HOST not set: using the real %s project (free-tier quotas)", args.project)
        fs_client = firestore.Client(project=args.project)
    if args.riders:
        riders = RiderDirectory.from_ndjson(args.riders)
    elif args.riders_from_firestore:
        riders = RiderDirectory.from_firestore(fs_client)
    else:
        riders = RiderDirectory()
        log.warning("no riders loaded: every push token is UNREGISTERED until POST /mock/admin/riders")
    if args.store == "firestore":
        from mocks.store import FirestoreStore
        store = FirestoreStore(fs_client)
    else:
        store = MemoryStore()

    import uvicorn
    from mocks.app import create_app
    from mocks.sink import create_sink
    from mocks.dataview import DataView
    data_dir = args.data_dir or (args.riders.parent.parent if args.riders else None)
    dataview = DataView(None if args.no_cloud_data else args.data_project, data_dir)
    app = create_app(cfg, store=store, riders=riders, dataview=dataview,
                     clock=Clock(parse_ts(args.start) if args.start else None, args.scale))
    threading.Thread(target=_prewarm, args=(dataview,), daemon=True).start()
    if args.sink:
        app.mount("/sink", create_sink({cfg.webhook_key_id: secret}))
    log.info("riders %d, store %s, webhooks -> %s", len(riders), args.store, engine_url)
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


def _prewarm(dataview) -> None:
    """Load /demo/data once at startup so the page opens instantly in the meeting."""
    try:
        out = dataview.summary()
        log.info("data page ready: source %s%s", out["source"], f" (cloud failed: {out['error']})" if out["error"] else "")
    except Exception as exc:
        log.warning("data page unavailable: %s", exc)


if __name__ == "__main__":
    main()
