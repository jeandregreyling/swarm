import json, os, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer

tmp = tempfile.mkdtemp()
os.environ["HB_NANNY_DB"] = os.path.join(tmp, "n.db")
os.environ["HB_STALL_SECONDS"] = "2"
os.environ["HB_MAX_RUNTIME"] = "3600"
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import hummingbird_nanny as n

STATE = {"busy": False}
class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path == "/health":
            body = {"status": "ok"}
        elif self.path == "/slots":
            body = [{"id": 0, "is_processing": STATE["busy"]}]
        else:
            self.send_response(404); self.end_headers(); return
        data = json.dumps(body).encode()
        self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(data)
srv = HTTPServer(("127.0.0.1", 0), H)   # free port: avoids clashes with other suites
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = "http://127.0.0.1:%d" % srv.server_address[1]

con = n.db()
target = os.path.join(tmp, "out.py")
accept = [
    {"type": "file_exists", "path": target},
    {"type": "modified_since_start", "path": target},
    {"type": "py_compile", "path": target},
    {"type": "not_matches", "path": target, "regex": "TODO|placeholder"},
    {"type": "cmd", "cmd": f"python3 {target}", "timeout": 20},
]

# 1. false 'done' claims climb the ladder
t1 = n.add_task(con, "build thing", accept)
n.start_task(con, t1)
r1 = n.claim_done(con, t1); r2 = n.claim_done(con, t1); r3 = n.claim_done(con, t1)
assert [r1["action"], r2["action"], r3["action"]] == ["retry_apex", "escalate_fred", "queue_online"], (r1, r2, r3)
assert n.get_task(con, t1)["state"] == "ESCALATED"
print("ok  1: false claims -> retry_apex, escalate_fred, queue_online")

# 2. placeholder text is rejected, real file is verified
t2 = n.add_task(con, "build thing 2", accept); n.start_task(con, t2)
time.sleep(0.05)
open(target, "w").write("# TODO finish\nprint('hi')\n")
r = n.claim_done(con, t2)
assert not r["verified"] and any("forbidden" in f for f in r["failures"]), r
n.start_task(con, t2)
open(target, "w").write("print('hi')\n")
r = n.claim_done(con, t2)
assert r["verified"] and n.get_task(con, t2)["state"] == "VERIFIED", r
print("ok  2: placeholder rejected, real file verified")

# 3. no acceptance checks -> cannot verify
t3 = n.add_task(con, "vague task", []); n.start_task(con, t3)
r = n.claim_done(con, t3)
assert not r["verified"], r
print("ok  3: task without acceptance checks cannot be verified")

# 4. busy model keeps task alive, idle model triggers stall escalation
t4 = n.add_task(con, "long job", accept); n.start_task(con, t4)
STATE["busy"] = True
for _ in range(3):
    time.sleep(1.2)
    assert n.tick(con, BASE) == []
assert n.get_task(con, t4)["state"] == "RUNNING"
print("ok  4a: busy slot keeps the task alive past the stall window")
STATE["busy"] = False
time.sleep(2.5)
acts = n.tick(con, BASE)
assert acts and acts[0]["task"] == t4 and "stalled" in acts[0]["reason"], acts
print("ok  4b: idle model past the stall window -> escalation:", acts[0]["action"])

# 5. dead server reported
srv.shutdown(); srv.server_close()
h, b = n.server_state(BASE)
assert h is False and b is None
print("ok  5: dead server reads as unhealthy")
