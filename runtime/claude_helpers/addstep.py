import sys
sys.path.insert(0, '/home/jd/swarm')
from core.knowledge.projects import add_step
title, test, keyword, owner_note = sys.argv[1:5]
kw = f', "keyword": "{keyword}"' if keyword else ''
desc = (f"HB extra tools: change_set\nPREPARED (Claude Code): this step has a tested change set. Do: change_set show (read why), "
        f"change_set apply, then run_tests with {{\"tests\": [\"{test}\"]{kw}}}, then report in 2-4 lines.\n"
        f"{owner_note}\nDone when: python -m pytest {test} passes\nHB restart after: ui\n")
print(add_step('P-2AB8250A87', title, description=desc, owner='apex'))
