"""Fallback paths against a mock shaped like the REAL llama-server (per its docs,
not run against a real server): no /telemetry, no /memory/compress, no /lora/load.
"""
import json, os, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import hummingbird_nanny as n

ST = {"busy": False, "scales": {0: 0.0, 1: 0.0}, "posted": None}

class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _send(self, body, code=200):
        data = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == "/health": self._send({"status": "ok"})
        elif self.path == "/slots": self._send([{"id": 0, "is_processing": ST["busy"]}])
        elif self.path == "/lora-adapters":
            self._send([{"id": 0, "path": "/models/lora/qwen-general.gguf", "scale": ST["scales"][0]},
                        {"id": 1, "path": "/models/lora/advanced_coding-r16.gguf", "scale": ST["scales"][1]}])
        else: self._send({"error": "not found"}, 404)
    def do_POST(self):
        if self.path == "/lora-adapters":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"[]")
            ST["posted"] = body
            for a in body: ST["scales"][a["id"]] = a["scale"]
            self._send({"success": True})
        else:
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self._send({"error": "not found"}, 404)

class T(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = HTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.base = "http://127.0.0.1:%d" % cls.srv.server_address[1]
    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["HB_NANNY_DB"] = os.path.join(self.tmp.name, "n.db")
        os.environ["HB_VRAM_LIMIT_MB"] = "14000"
        os.environ["HB_SWEEP_COOLDOWN"] = "60"
        os.environ["HB_LLAMA_URL"] = self.base
        ST.update(busy=False, scales={0: 0.0, 1: 0.0}, posted=None)
        self.con = n.db()
        self._orig = n.vram_used_mb
    def tearDown(self):
        n.vram_used_mb = self._orig; self.con.close(); self.tmp.cleanup()

    def test_sweep_without_compress_endpoint_asks_orchestrator(self):
        n.vram_used_mb = lambda: 15200
        acts = n.system_sweep(self.con, self.base)
        self.assertEqual(acts[0]["action"], "compress_context")
        self.assertFalse(acts[0]["executed"])
        self.assertIn("orchestrator must summarise", n.get_system_log(self.con))

    def test_sweep_quiet_when_under_limit(self):
        n.vram_used_mb = lambda: 9000
        self.assertEqual(n.system_sweep(self.con, self.base), [])

    def test_sweep_cooldown(self):
        n.vram_used_mb = lambda: 15200
        self.assertEqual(len(n.system_sweep(self.con, self.base)), 1)
        self.assertEqual(n.system_sweep(self.con, self.base), [])

    def test_lora_swap_via_lora_adapters_scales(self):
        tid = n.add_task(self.con, "vulkan work", [], domain="advanced_coding")
        n.start_task(self.con, tid, execute_adapter_check=True)
        self.assertEqual(ST["scales"], {0: 0.0, 1: 1.0})
        self.assertEqual(n.get_task(self.con, tid)["active_adapter"], "advanced_coding")

    def test_lora_swap_deferred_while_generating(self):
        ST["busy"] = True
        tid = n.add_task(self.con, "vulkan work", [], domain="advanced_coding")
        n.start_task(self.con, tid, execute_adapter_check=True)
        self.assertIsNone(ST["posted"])
        self.assertIsNone(n.get_task(self.con, tid)["active_adapter"])
        self.assertEqual(n.get_task(self.con, tid)["state"], "RUNNING")

    def test_lora_unknown_adapter_does_not_block_task(self):
        tid = n.add_task(self.con, "x", [], domain="no_such_adapter")
        n.start_task(self.con, tid, execute_adapter_check=True)
        self.assertEqual(n.get_task(self.con, tid)["state"], "RUNNING")
        self.assertIsNone(n.get_task(self.con, tid)["active_adapter"])

    def test_dream_idempotent_and_last_step_inherits_checks(self):
        checks = [{"type": "file_exists", "path": "/nope"}]
        pid = n.add_task(self.con, "wrapper", checks)
        a = n.trigger_dream_vector(self.con, pid); b = n.trigger_dream_vector(self.con, pid)
        self.assertEqual(a, b); self.assertEqual(len(a), 3)
        subs = n.get_subtasks(self.con, pid)
        self.assertEqual(json.loads(subs[2]["accept"]), checks)
        self.assertEqual(json.loads(subs[0]["accept"]), [])

    def test_v1_database_is_upgraded(self):
        import sqlite3
        path = os.path.join(self.tmp.name, "old.db")
        c = sqlite3.connect(path)
        c.executescript("CREATE TABLE tasks(id INTEGER PRIMARY KEY, title TEXT, state TEXT DEFAULT 'QUEUED',"
                        "accept TEXT DEFAULT '[]', attempts INTEGER DEFAULT 0, created REAL, started REAL,"
                        "last_activity REAL, updated REAL, note TEXT DEFAULT '');"
                        "CREATE TABLE events(ts REAL, task_id INTEGER, kind TEXT, detail TEXT);"
                        "INSERT INTO tasks(title, created, updated) VALUES('old task', 1, 1);")
        c.commit(); c.close()
        os.environ["HB_NANNY_DB"] = path
        con = n.db()
        row = con.execute("SELECT * FROM tasks").fetchone()
        self.assertEqual(row["title"], "old task"); self.assertIsNone(row["active_adapter"])
        con.close()

if __name__ == "__main__":
    unittest.main(verbosity=2)
