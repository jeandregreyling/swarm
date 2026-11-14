import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "scripts"))
import hummingbird_nanny as n

class MockWorkerHandler(BaseHTTPRequestHandler):
    """Mock agent endpoint simulating local LLM node states, VRAM, and LoRA."""
    state = {
        "busy": False,
        "vram_usage_mb": 4096,
        "latency_ms": 120,
        "active_lora": "base",
        "context_size": 2048
    }

    def log_message(self, format, *args): pass

    def do_GET(self):
        if self.path == "/health":
            body = {"status": "ok"}
        elif self.path == "/slots":
            body = [{"id": 0, "is_processing": self.state["busy"]}]
        elif self.path == "/telemetry":
            body = {
                "vram_usage_mb": self.state["vram_usage_mb"],
                "latency_ms": self.state["latency_ms"],
                "context_size": self.state["context_size"]
            }
        elif self.path == "/lora/status":
            body = {"active_adapter": self.state["active_lora"]}
        else:
            self.send_response(404); self.end_headers(); return
        
        self.send_json(body)

    def do_POST(self):
        if self.path == "/memory/compress":
            # Simulate sliding window compression
            self.state["context_size"] = max(512, self.state["context_size"] // 2)
            self.state["vram_usage_mb"] = max(2048, self.state["vram_usage_mb"] - 1024)
            self.state["latency_ms"] = max(50, self.state["latency_ms"] // 2)
            body = {"status": "compressed", "new_size": self.state["context_size"]}
        elif self.path.startswith("/lora/load/"):
            adapter = self.path.split("/")[-1]
            self.state["active_lora"] = adapter
            body = {"status": "loaded", "adapter": adapter}
        else:
            self.send_response(404); self.end_headers(); return
            
        self.send_json(body)

    def send_json(self, body):
        data = json.dumps(body).encode('utf-8')
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

class TestHummingbirdAdvanced(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), MockWorkerHandler)
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        cls.base_url = "http://127.0.0.1:%d" % cls.server.server_address[1]
        os.environ["HB_LLAMA_URL"] = cls.base_url   # start_task() needs to know which server to use

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=2)

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp_dir.name, "hb_state.db")
        os.environ["HB_NANNY_DB"] = self.db_path
        os.environ["HB_STALL_SECONDS"] = "2"
        os.environ["HB_VRAM_LIMIT_MB"] = "14000" # Leave 2GB headroom on 16GB RX 6800
        
        self.con = n.db()
        self.target = os.path.join(self.tmp_dir.name, "out.py")
        self.accept_criteria = [{"type": "file_exists", "path": self.target}]
        
        # Reset mock state
        MockWorkerHandler.state = {
            "busy": False, "vram_usage_mb": 4096, 
            "latency_ms": 120, "active_lora": "base", "context_size": 2048
        }

    def tearDown(self):
        self.con.close()
        self.tmp_dir.cleanup()

    # --- DOES Governance & System Degradation ---

    def test_does_sustain_context_compression(self):
        """Validate DOES automatically triggers context compression upon system degradation."""
        task_id = n.add_task(self.con, "heavy context task", self.accept_criteria)
        n.start_task(self.con, task_id)
        
        # Simulate memory leak / context bloat leading to slowness
        MockWorkerHandler.state["vram_usage_mb"] = 15000  # Breaches 14GB limit
        MockWorkerHandler.state["latency_ms"] = 3500      # Heavy latency
        MockWorkerHandler.state["context_size"] = 32000   # Maxed context window
        
        # Nanny daemon tick should detect threshold breach and execute sweep
        actions = n.system_sweep(self.con, self.base_url)
        
        self.assertIn("compress_context", [a["action"] for a in actions])
        self.assertTrue(MockWorkerHandler.state["vram_usage_mb"] < 15000)
        self.assertTrue(MockWorkerHandler.state["latency_ms"] < 3500)
        
        db_log = n.get_system_log(self.con)
        self.assertIn("DOES_SUSTAIN: Context compressed due to VRAM saturation.", db_log)

    # --- D.R.E.A.M. Orchestration ---

    def test_dream_autonomous_subtask_generation(self):
        """Validate D.R.E.A.M. logic autonomously deriving execution steps without user prompts."""
        parent_task = n.add_task(self.con, "Build local API wrapper", self.accept_criteria)
        
        # Trigger DREAM execution vector
        n.trigger_dream_vector(self.con, parent_task, self.base_url)
        
        # Verify nanny automatically populated child tasks in SQLite
        subtasks = n.get_subtasks(self.con, parent_task)
        self.assertGreater(len(subtasks), 0)
        self.assertEqual(subtasks[0]["status"], "QUEUED")
        self.assertTrue(any("analyze requirements" in st["description"].lower() for st in subtasks))

    # --- Local Model Training & Inference (LoRA) ---

    def test_dynamic_lora_adapter_swap(self):
        """Validate framework hotswaps LoRA weights based on task domain specification."""
        task_id = n.add_task(self.con, "Write C++ Vulkan offload", self.accept_criteria)
        
        # Explicitly set task domain to trigger specific LoRA
        n.set_task_domain(self.con, task_id, "advanced_coding")
        n.start_task(self.con, task_id, execute_adapter_check=True)
        
        # Verify the Nanny instructed the LLM node to load the coding adapter
        self.assertEqual(MockWorkerHandler.state["active_lora"], "advanced_coding")
        
        # Verify tracking in state DB
        task_data = n.get_task(self.con, task_id)
        self.assertEqual(task_data["active_adapter"], "advanced_coding")

    # --- Base Verification Continuity ---

    def test_escalation_ladder(self):
        """Ensure core DOES escalation paths remain intact."""
        task_id = n.add_task(self.con, "build thing", self.accept_criteria)
        n.start_task(self.con, task_id)
        
        r1 = n.claim_done(self.con, task_id); r2 = n.claim_done(self.con, task_id); r3 = n.claim_done(self.con, task_id)
        self.assertEqual([r1["action"], r2["action"], r3["action"]], ["retry_apex", "escalate_fred", "queue_online"])

if __name__ == '__main__':
    unittest.main(verbosity=2)
