"""Standalone scheduler loop for Fridays.

The email listener can still call ``check_due()`` for backward compatibility,
but production scheduling should run through this small process so inbox IO,
agent recovery work, and scheduled task ownership do not share one long-lived
SQLite writer.
"""
from __future__ import annotations

import argparse
import logging
import signal
import time

from fridays.scheduler import check_due


_STOP = False


def _handle_stop(signum, frame):  # pragma: no cover - signal glue
    global _STOP
    _STOP = True


def run_loop(interval_seconds: int = 60) -> None:
    logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s %(name)s: %(message)s')
    log = logging.getLogger('seven.scheduler_daemon')
    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)
    interval = max(5, min(int(interval_seconds or 60), 300))
    log.info('scheduler daemon started interval=%ss', interval)
    while not _STOP:
        started = time.time()
        try:
            check_due()
        except Exception as exc:
            log.exception('check_due failed: %s', exc)
        elapsed = time.time() - started
        sleep_for = max(1.0, interval - elapsed)
        deadline = time.time() + sleep_for
        while not _STOP and time.time() < deadline:
            time.sleep(min(1.0, deadline - time.time()))
    log.info('scheduler daemon stopped')


def main() -> None:
    parser = argparse.ArgumentParser(description='Run Fridays scheduled tasks outside the email listener.')
    parser.add_argument('--interval-seconds', type=int, default=60)
    args = parser.parse_args()
    run_loop(args.interval_seconds)


if __name__ == '__main__':
    main()
