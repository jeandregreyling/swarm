#!/usr/bin/env python3
"""ops/install/hive_installer_gui.py — click-through wizard.

Stand-alone double-clickable installer. Stdlib only (Tkinter +
hive_installer_core). The user never sees a terminal.

Run modes:
  python3 hive_installer_gui.py                  # GUI wizard (default)
  python3 hive_installer_gui.py --leader URL     # pre-fill leader
  python3 hive_installer_gui.py --headless ...   # passthrough to core (CI)

Wizard pages: Welcome → Leader → Confirm → Install → Done.
Long-running work runs on worker threads and pushes events into a
queue.Queue; the Tk mainloop drains the queue every 80ms.
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
from pathlib import Path

# Allow being run as a single file *or* as a module from the repo.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from hive_installer_core import (  # type: ignore[import-not-found]
    InstallerError,
    InstallPlan,
    detect_platform,
    plan_install,
    probe_leader,
    run_platform_installer,
    stage_artefacts,
)

PAGE_WELCOME, PAGE_LEADER, PAGE_CONFIRM, PAGE_INSTALL, PAGE_DONE = range(5)


def _import_tk():
    """Import Tkinter lazily so headless test runs don't need a display."""
    import tkinter as tk
    from tkinter import ttk
    return tk, ttk


class InstallerApp:
    def __init__(self, *, prefill_leader: str = "", prefill_node_id: str = ""):
        tk, ttk = _import_tk()
        self.tk = tk
        self.ttk = ttk

        self.root = tk.Tk()
        self.root.title("Swarm Hive — Add this device")
        self.root.geometry("560x420")
        self.root.minsize(520, 380)

        self.events: "queue.Queue[tuple]" = queue.Queue()
        self.page = PAGE_WELCOME
        self.leader = prefill_leader.strip()
        self.node_id = prefill_node_id.strip()
        self.platform = detect_platform()
        self.probe_result = None
        self.plan: InstallPlan | None = None
        self.install_log: list[str] = []
        self.install_ok: bool | None = None

        # Layout: header | body | footer (Back / Next / Cancel)
        self.header = ttk.Label(self.root, text="", font=("TkDefaultFont", 14, "bold"))
        self.header.pack(fill="x", padx=14, pady=(14, 4))

        self.subheader = ttk.Label(self.root, text="", foreground="#666")
        self.subheader.pack(fill="x", padx=14, pady=(0, 8))

        self.body = ttk.Frame(self.root)
        self.body.pack(fill="both", expand=True, padx=14, pady=4)

        footer = ttk.Frame(self.root)
        footer.pack(fill="x", padx=14, pady=10)

        self.btn_back = ttk.Button(footer, text="Back", command=self.on_back)
        self.btn_next = ttk.Button(footer, text="Next", command=self.on_next)
        self.btn_cancel = ttk.Button(footer, text="Cancel", command=self.on_cancel)
        self.btn_back.pack(side="left")
        self.btn_cancel.pack(side="right")
        self.btn_next.pack(side="right", padx=6)

        self._render()
        self.root.after(80, self._drain_events)

    # ---- event loop bridge ------------------------------------------------

    def _drain_events(self) -> None:
        try:
            while True:
                evt = self.events.get_nowait()
                self._handle_event(evt)
        except queue.Empty:
            pass
        self.root.after(80, self._drain_events)

    def _handle_event(self, evt: tuple) -> None:
        kind = evt[0]
        if kind == "probe_done":
            self.probe_result = evt[1]
            self._render()
        elif kind == "install_log":
            self.install_log.append(evt[1])
            self._append_log(evt[1])
        elif kind == "install_done":
            self.install_ok = evt[1]
            self.page = PAGE_DONE
            self._render()
        elif kind == "stage_progress":
            stage, read, total = evt[1], evt[2], evt[3]
            pct = "" if not total else f" {read*100//total}%"
            self._append_log(f"[download] {stage}{pct} ({read} bytes)")

    # ---- page rendering ---------------------------------------------------

    def _clear_body(self) -> None:
        for w in self.body.winfo_children():
            w.destroy()

    def _render(self) -> None:
        self._clear_body()
        if self.page == PAGE_WELCOME:    self._render_welcome()
        elif self.page == PAGE_LEADER:   self._render_leader()
        elif self.page == PAGE_CONFIRM:  self._render_confirm()
        elif self.page == PAGE_INSTALL:  self._render_install()
        elif self.page == PAGE_DONE:     self._render_done()

        self.btn_back.state(["!disabled"] if self.page in (PAGE_LEADER, PAGE_CONFIRM) else ["disabled"])
        if self.page == PAGE_DONE:
            self.btn_next.configure(text="Finish")
        elif self.page == PAGE_INSTALL:
            self.btn_next.configure(text="Installing…")
            self.btn_next.state(["disabled"])
        elif self.page == PAGE_CONFIRM:
            self.btn_next.configure(text="Install")
            self.btn_next.state(["!disabled"])
        else:
            self.btn_next.configure(text="Next")
            self.btn_next.state(["!disabled"])

    def _render_welcome(self) -> None:
        self.header.configure(text="Welcome")
        self.subheader.configure(
            text="This wizard will join this device to your Swarm Hive. It takes about 30 seconds.",
        )
        body = self.ttk.Frame(self.body)
        body.pack(fill="both", expand=True)
        self.ttk.Label(body, justify="left", text=(
            f"• Detected platform: {self.platform}\n"
            "• You will be asked for the leader's URL.\n"
            "• The agent will run as a background service so it survives reboot.\n"
            "• You can remove the device later from the leader's Monitor view."
        )).pack(anchor="w", pady=4)

    def _render_leader(self) -> None:
        self.header.configure(text="Leader URL")
        self.subheader.configure(text="Where is the Hive leader?")
        body = self.ttk.Frame(self.body)
        body.pack(fill="both", expand=True)

        self.ttk.Label(body, text="Leader URL (e.g. http://10.0.0.5:5050)").pack(anchor="w")
        self._leader_var = self.tk.StringVar(value=self.leader or "http://")
        entry = self.ttk.Entry(body, textvariable=self._leader_var, width=48)
        entry.pack(fill="x", pady=4)
        entry.focus_set()

        self.ttk.Label(body, text="Optional node id (leave blank for auto)").pack(anchor="w", pady=(8, 0))
        self._node_var = self.tk.StringVar(value=self.node_id)
        self.ttk.Entry(body, textvariable=self._node_var, width=48).pack(fill="x", pady=4)

        self._probe_status = self.ttk.Label(body, text="", foreground="#666")
        self._probe_status.pack(anchor="w", pady=(8, 0))

        def _test():
            self.leader = (self._leader_var.get() or "").strip()
            self.node_id = (self._node_var.get() or "").strip()
            self._probe_status.configure(text="Testing…", foreground="#666")
            self.probe_result = None
            threading.Thread(
                target=self._probe_worker, args=(self.leader,), daemon=True,
            ).start()

        self.ttk.Button(body, text="Test connection", command=_test).pack(anchor="w", pady=4)

        if self.probe_result is not None:
            if self.probe_result.ok:
                msg = f"OK — {self.probe_result.leader} ({self.probe_result.node_count} nodes)"
                self._probe_status.configure(text=msg, foreground="#2a7")
            else:
                self._probe_status.configure(
                    text=f"Failed: {self.probe_result.reason}", foreground="#c33",
                )

    def _probe_worker(self, leader: str) -> None:
        result = probe_leader(leader)
        self.events.put(("probe_done", result))

    def _render_confirm(self) -> None:
        self.header.configure(text="Confirm")
        self.subheader.configure(text="Review the install plan before proceeding.")
        body = self.ttk.Frame(self.body)
        body.pack(fill="both", expand=True)
        plan = self.plan
        rows = [
            ("Leader",      plan.leader if plan else self.leader),
            ("Platform",    plan.platform if plan else self.platform),
            ("Node id",     (plan.node_id if plan else self.node_id) or "(auto-derived)"),
            ("Stage dir",   str(plan.stage_dir) if plan else "(pending)"),
            ("Installer",   plan.installer_filename if plan else "(pending)"),
        ]
        for k, v in rows:
            row = self.ttk.Frame(body); row.pack(fill="x", pady=2)
            self.ttk.Label(row, text=k, width=14, anchor="w").pack(side="left")
            self.ttk.Label(row, text=v, anchor="w").pack(side="left", fill="x", expand=True)
        self.ttk.Label(
            body,
            foreground="#666", justify="left",
            text=(
                "\nClicking Install will:\n"
                "  1. Download the agent + platform installer from the leader.\n"
                "  2. Register a background service so it starts on boot.\n"
                "  3. Send the first telemetry sample.\n"
            ),
        ).pack(anchor="w", pady=(8, 0))

    def _render_install(self) -> None:
        self.header.configure(text="Installing")
        self.subheader.configure(text="Hold tight — this takes about 20 seconds.")
        body = self.ttk.Frame(self.body)
        body.pack(fill="both", expand=True)
        self._log_box = self.tk.Text(body, height=14, wrap="none", font=("TkFixedFont", 9))
        self._log_box.pack(fill="both", expand=True)
        for line in self.install_log:
            self._log_box.insert("end", line + "\n")
        self._log_box.configure(state="disabled")

    def _append_log(self, line: str) -> None:
        if self.page != PAGE_INSTALL:
            return
        if not hasattr(self, "_log_box"):
            return
        self._log_box.configure(state="normal")
        self._log_box.insert("end", line + "\n")
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _render_done(self) -> None:
        ok = self.install_ok is True
        self.header.configure(text="Done" if ok else "Install failed")
        self.subheader.configure(
            text=("Your device is now part of the Hive."
                  if ok else
                  "The installer reported an error. See the log below."),
        )
        body = self.ttk.Frame(self.body)
        body.pack(fill="both", expand=True)
        if ok and self.plan:
            self.ttk.Label(
                body, foreground="#2a7", justify="left",
                text=(
                    f"Open the leader's Monitor view to see this device:\n"
                    f"  {self.plan.leader}/monitor"
                ),
            ).pack(anchor="w", pady=(0, 8))
        # Always show the log
        log_box = self.tk.Text(body, height=12, wrap="none", font=("TkFixedFont", 9))
        log_box.pack(fill="both", expand=True)
        for line in self.install_log:
            log_box.insert("end", line + "\n")
        log_box.configure(state="disabled")

    # ---- navigation -------------------------------------------------------

    def on_back(self) -> None:
        if self.page in (PAGE_LEADER, PAGE_CONFIRM):
            self.page -= 1
            self._render()

    def on_cancel(self) -> None:
        self.root.destroy()

    def on_next(self) -> None:
        if self.page == PAGE_WELCOME:
            self.page = PAGE_LEADER
            self._render()
            return
        if self.page == PAGE_LEADER:
            self.leader = (self._leader_var.get() or "").strip()
            self.node_id = (self._node_var.get() or "").strip()
            if self.probe_result is None or not self.probe_result.ok:
                # Force a probe before allowing advance.
                self._probe_status.configure(text="Click ‘Test connection’ first.", foreground="#c33")
                return
            try:
                self.plan = plan_install(self.probe_result.leader, node_id=self.node_id or None)
            except InstallerError as e:
                self._probe_status.configure(text=f"Cannot plan: {e}", foreground="#c33")
                return
            self.page = PAGE_CONFIRM
            self._render()
            return
        if self.page == PAGE_CONFIRM:
            self.page = PAGE_INSTALL
            self._render()
            threading.Thread(target=self._install_worker, daemon=True).start()
            return
        if self.page == PAGE_DONE:
            self.root.destroy()
            return

    def _install_worker(self) -> None:
        try:
            assert self.plan is not None
            def _stage_progress(stage, read, total):
                self.events.put(("stage_progress", stage, read, total))
            agent, installer = stage_artefacts(self.plan, progress=_stage_progress)
            self.events.put(("install_log", f"[stage] agent at {agent}"))
            self.events.put(("install_log", f"[stage] installer at {installer}"))
            def _on_log(line):
                self.events.put(("install_log", line))
            result = run_platform_installer(self.plan, installer, on_log=_on_log)
            self.events.put(("install_log", f"[result] {result.detail}"))
            self.events.put(("install_done", result.ok))
        except InstallerError as e:
            self.events.put(("install_log", f"[error] {e}"))
            self.events.put(("install_done", False))
        except Exception as e:  # last-ditch — surface in UI rather than silently dying
            self.events.put(("install_log", f"[fatal] {type(e).__name__}: {e}"))
            self.events.put(("install_done", False))

    def run(self) -> None:
        self.root.mainloop()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Swarm Hive click-through installer")
    p.add_argument("--leader", default="", help="Pre-fill the leader URL")
    p.add_argument("--node-id", default="", help="Pre-fill the node id")
    args = p.parse_args(argv)
    try:
        app = InstallerApp(prefill_leader=args.leader, prefill_node_id=args.node_id)
    except Exception as e:
        # Tk not available (e.g. headless server with no display).
        sys.stderr.write(
            f"GUI installer cannot start ({type(e).__name__}: {e}).\n"
            "Falling back to terminal: rerun bootstrap.sh / bootstrap.ps1 instead.\n"
        )
        return 2
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
