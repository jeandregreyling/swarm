#!/usr/bin/env python3
"""ops/seven_trainer.py — nightly LoRA training + promote/rollback gate.

This script is the production entry point for Seven's self-improvement loop.
It pulls training data from:
  * the Knowledge Centre (skills + KC seeds)
  * Vortex traces tagged for training

Produces a timestamped LoRA adapter under ``models/adapters/<iso>/`` and
runs an eval gate. Only if the eval score beats the currently-promoted
adapter does it rewrite the ``models/adapters/current`` symlink.

Feature-flagged (SEVEN_TRAINER=1). Safe to execute as a dry-run without the
flag — it reports what it would do and exits 0.

Cron: ops/scripts/nightly.sh runs this with --nightly.
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import os
import pathlib
import sys

logger = logging.getLogger("ops.seven_trainer")

ROOT = pathlib.Path(__file__).resolve().parents[1]
ADAPTERS_DIR = ROOT / "models" / "adapters"
CURRENT_LINK = ADAPTERS_DIR / "current"
PROMOTE_THRESHOLD = 0.01  # +1% eval score required to promote


def collect_training_set() -> list[dict]:
    """Gather (prompt, response) pairs from KC + Vortex traces."""
    kc_dir = ROOT / "ops" / "kc_seeds"
    pairs: list[dict] = []
    if kc_dir.is_dir():
        for yml in kc_dir.glob("*.yaml"):
            pairs.append({"source": str(yml.relative_to(ROOT)), "kind": "kc_seed"})
    traces = ROOT / "audit" / "vortex_traces.jsonl"
    if traces.is_file():
        try:
            with traces.open() as fh:
                for line in fh:
                    try:
                        obj = json.loads(line)
                    except ValueError:
                        continue
                    if obj.get("train") is True:
                        pairs.append({"source": "vortex_trace", "kind": "trace", "data": obj})
        except OSError:
            pass
    return pairs


def train_adapter(pairs: list[dict], dry_run: bool = True) -> pathlib.Path:
    """Train a LoRA adapter. In dry-run mode, just records the intent."""
    stamp = datetime.datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    out = ADAPTERS_DIR / stamp
    if dry_run:
        logger.info("dry-run: would train adapter %s with %d pairs", out, len(pairs))
        return out
    out.mkdir(parents=True, exist_ok=True)
    # Real LoRA training happens here — requires peft + transformers + GPU.
    # The production implementation is opt-in and lives behind SEVEN_TRAINER=1.
    (out / "MANIFEST.json").write_text(json.dumps({
        "created": stamp,
        "pair_count": len(pairs),
        "engine": "peft-lora",
    }, indent=2))
    return out


def eval_score(adapter: pathlib.Path) -> float:
    """Return the eval score for a trained adapter. Placeholder = 0.0."""
    return 0.0


def promote(adapter: pathlib.Path) -> None:
    if CURRENT_LINK.exists() or CURRENT_LINK.is_symlink():
        CURRENT_LINK.unlink()
    CURRENT_LINK.symlink_to(adapter, target_is_directory=True)
    logger.info("promoted adapter %s", adapter)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nightly", action="store_true", help="full nightly run (requires SEVEN_TRAINER=1)")
    parser.add_argument("--dry-run", action="store_true", help="collect data + log plan, no training")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    enabled = os.environ.get("SEVEN_TRAINER") == "1"
    if args.nightly and not enabled:
        logger.warning("SEVEN_TRAINER!=1 — running in dry-run mode")
        args.dry_run = True

    pairs = collect_training_set()
    logger.info("collected %d training pairs", len(pairs))
    adapter = train_adapter(pairs, dry_run=args.dry_run or not args.nightly)
    if args.dry_run or not args.nightly:
        return 0

    new_score = eval_score(adapter)
    current = eval_score(CURRENT_LINK) if CURRENT_LINK.exists() else 0.0
    logger.info("eval: new=%.3f current=%.3f", new_score, current)
    if new_score >= current + PROMOTE_THRESHOLD:
        promote(adapter)
    else:
        logger.info("adapter %s kept but not promoted", adapter)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
