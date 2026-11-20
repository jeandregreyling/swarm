#!/bin/bash
# Full-suite gate: run everything, compare with the saved baseline, print only NEW failures (and fixed ones).
cd /home/jd/swarm
OUT=$(mktemp); timeout 3000 .venv/bin/python -m pytest -q -o addopts="" -p no:cacheprovider tests/ --maxfail=400 2>&1 | grep -E "^(FAILED|ERROR) |passed|failed" > $OUT
grep -E "^(FAILED|ERROR) tests/" $OUT | awk '{print $2}' | sort > $OUT.now
echo "SUMMARY: $(tail -1 $OUT)"
echo "NEW: $(comm -13 runtime/claude_helpers/baseline_failures.txt $OUT.now | tr '\n' ' ')"
echo "FIXED: $(comm -23 runtime/claude_helpers/baseline_failures.txt $OUT.now | tr '\n' ' ')"
