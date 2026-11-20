"""Claude Code's own work in HB's activity log (HB Live L1): it shows in main chat's Claude Code lane like any other worker.

  python hbrun.py start "<title>" [--task T-..] [--step S-..]   -> prints the run id
  python hbrun.py step R-... "<line>"
  python hbrun.py finish R-... [ok|error] ["<line>"]
"""
import sys
import time
sys.path.insert(0, '/home/jd/swarm')
from core import hb_activity_log as live

args = sys.argv[1:]
if not args:
    sys.exit(__doc__)
if args[0] == 'start':
    title = args[1]
    task = args[args.index('--task') + 1] if '--task' in args else None
    step = args[args.index('--step') + 1] if '--step' in args else None
    r = live.begin('claude', 'claude-code', title, model='claude-code', device='online', task_id=task, step_id=step, purpose='Claude Code')
    print(r.run_id)
elif args[0] == 'step':
    live.write({'run_id': args[1], 'lane': 'claude-code', 'actor': 'claude', 'kind': 'step', 'text': args[2]})
elif args[0] == 'finish':
    ok = len(args) < 3 or args[2] != 'error'
    live.write({'run_id': args[1], 'lane': 'claude-code', 'actor': 'claude', 'kind': 'finish' if ok else 'error',
                'text': args[3] if len(args) > 3 else ('done' if ok else 'failed')})
