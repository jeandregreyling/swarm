import sys
sys.path.insert(0, '/home/jd/swarm')
from contextlib import closing
from utils.db._connection import get_connection
from core import hb_commands
with closing(get_connection()) as c:
    print(hb_commands.handle(c, 2845, '/clip top ' + sys.argv[1], 'Claude Code')); c.commit()
