"""One-use, session-owned human approval transactions for APEX proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import hashlib
import json
import logging
import os
from pathlib import Path
import secrets
import stat
import subprocess
import tempfile
import threading
import time
import uuid

from core.apex_tools import MAX_DIFF_BYTES, MAX_FILE_BYTES, MAX_WRITE_BYTES, ReadOnlyRepository

LOG = logging.getLogger(__name__)
PROPOSAL_TOOLS = {"propose_write_file", "propose_commit"}
APPROVAL_TIMEOUT = 900


def session_identity(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class ApprovalConflict(RuntimeError):
    pass


@dataclass
class Transaction:
    id: str
    owner: str
    session: str
    csrf: str
    conversation_id: int
    tool: str
    paths: list[str]
    diff: str
    hashes: dict[str, str]
    states: dict[str, tuple[bytes, int]]
    args: dict
    repository: ReadOnlyRepository
    head: str = ""
    index_hash: str = ""
    expires_at: float = field(default_factory=lambda: time.time() + APPROVAL_TIMEOUT)
    ready: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None

    def public(self) -> dict:
        return {
            "transaction_id": self.id, "conversation_id": self.conversation_id,
            "tool": self.tool, "paths": self.paths, "diff": self.diff,
            "hashes": self.hashes, "expires_at": self.expires_at,
            "message": self.args.get("message", ""),
        }


class ApprovalStore:
    """Process-local pending transactions; a restart invalidates every UUID."""
    def __init__(self):
        self._lock = threading.RLock()
        self._pending: dict[str, Transaction] = {}
        self._reserved: set[tuple[str, str]] = set()

    @staticmethod
    def _state(repository, relative, *, commit: bool = False):
        # Reuse the tracked-text and protected-path boundary; never read private pools.
        limit = MAX_FILE_BYTES if commit else MAX_WRITE_BYTES
        repository._text(relative, set(repository._tracked()), allow_untracked=commit, max_bytes=limit)
        path = repository._path(relative)
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
            info = os.fstat(stream.fileno())
            content = stream.read(limit + 1)
        if not stat.S_ISREG(info.st_mode) or len(content) > limit or b"\0" in content:
            raise ValueError("Target is not bounded regular text")
        content.decode("utf-8")
        return content, info.st_mode & 0o777

    @staticmethod
    def _hash(state):
        return hashlib.sha256(state[0] + b"\0mode:" + str(state[1]).encode()).hexdigest()

    @staticmethod
    def _index_hash(repository):
        return hashlib.sha256(repository._git("ls-files", "--stage", "-z").encode()).hexdigest()

    def _finish(self, transaction, status, output):
        transaction.result = {
            "transaction_id": transaction.id, "status": status, "output": output,
        }
        self._pending.pop(transaction.id, None)
        self._reserved.difference_update(
            (str(transaction.repository.root), path) for path in transaction.paths)
        transaction.ready.set()
        LOG.info("Tool approval %s: %s", transaction.id, status)

    def _expire(self):
        for transaction in list(self._pending.values()):
            if transaction.expires_at <= time.time():
                self._finish(transaction, "denied", "Approval expired; no execution occurred")

    def propose(self, repository, tool, args, owner, session, conversation_id) -> Transaction:
        if not owner or not session or tool not in PROPOSAL_TOOLS:
            raise PermissionError("Authenticated operator session is required for proposals")
        if not isinstance(args, dict):
            raise ValueError("Proposal arguments must be an object")
        head = index_hash = ""
        if tool == "propose_write_file":
            if set(args) != {"path", "content"} or not isinstance(args["content"], str):
                raise ValueError("propose_write_file requires path and complete UTF-8 content")
            paths = [args["path"]]
            if len(args["content"].encode()) > MAX_WRITE_BYTES or "\0" in args["content"]:
                raise ValueError("Write payload exceeds limit or contains binary data")
        else:
            if (set(args) != {"paths", "message"} or not isinstance(args["paths"], list)
                    or not 1 <= len(args["paths"]) <= 20
                    or not isinstance(args["message"], str) or not args["message"].strip()
                    or len(args["message"]) > 500 or "\0" in args["message"]):
                raise ValueError("propose_commit requires 1-20 explicit paths and a commit message")
            paths = args["paths"]
        if (any(not isinstance(path, str) or not path or Path(path).as_posix() != path
                or ".." in Path(path).parts or Path(path).is_absolute() for path in paths)
                or len(set(paths)) != len(paths)):
            raise ValueError("Paths must be unique canonical workspace-relative file paths")
        commit = tool == "propose_commit"
        states = {path: self._state(repository, path, commit=commit) for path in paths}
        if tool == "propose_write_file":
            before = states[paths[0]][0].decode("utf-8")
            after = args["content"]
            if before == after:
                raise ValueError("Write proposal has no changes")
            diff = "".join(difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile="a/" + paths[0], tofile="b/" + paths[0]))
            # Show complete file payload when a missing final newline affects diff display.
            diff = json.dumps({"unified_diff": diff, "new_content": after}, ensure_ascii=True, indent=2)
        else:
            head = repository._git("rev-parse", "HEAD").strip()
            index_hash = self._index_hash(repository)
            diff = repository.preview_diff(paths, head)
            if (repository._git("rev-parse", "HEAD").strip() != head
                    or self._index_hash(repository) != index_hash
                    or any(self._hash(self._state(repository, path, commit=True)) != self._hash(state)
                           for path, state in states.items())):
                raise ApprovalConflict("Files, HEAD or staging index changed while preparing preview")
            if not diff:
                raise ValueError("Commit proposal has no changes in its explicit paths")
        if len(diff.encode()) > (MAX_DIFF_BYTES if commit else 512_000):
            raise ValueError("Proposal diff exceeds preview limit")
        with self._lock:
            self._expire()
            reservations = {(str(repository.root), path) for path in paths}
            if self._reserved & reservations or len(self._pending) >= 16:
                raise ApprovalConflict("Target already has a pending proposal or approval queue is full")
            transaction = Transaction(
                str(uuid.uuid4()), owner, session, secrets.token_urlsafe(32), conversation_id,
                tool, list(paths), diff, {path: self._hash(state) for path, state in states.items()},
                states, json.loads(json.dumps(args)), repository, head, index_hash,
            )
            self._pending[transaction.id] = transaction
            self._reserved.update(reservations)
            return transaction

    def list_for(self, owner, session) -> list[dict]:
        with self._lock:
            self._expire()
            return [{**transaction.public(), "csrf_token": transaction.csrf}
                    for transaction in self._pending.values()
                    if transaction.owner == owner and transaction.session == session]

    def cancel(self, transaction, output):
        with self._lock:
            if transaction.id in self._pending:
                self._finish(transaction, "failed", output)

    def wait(self, transaction) -> dict:
        transaction.ready.wait(max(0, transaction.expires_at - time.time()))
        with self._lock:
            if transaction.result is None:
                self._finish(transaction, "denied", "Approval expired; no execution occurred")
            return dict(transaction.result)

    def decide(self, transaction_id, decision, owner, session, csrf, authorize) -> dict:
        if type(decision) is not bool:
            raise ValueError("decision must be a JSON boolean")
        with self._lock:
            self._expire()
            transaction = self._pending.get(transaction_id)
            if transaction is None:
                raise ApprovalConflict("Unknown, expired or already consumed transaction UUID")
            if (transaction.owner != owner or transaction.session != session
                    or not secrets.compare_digest(transaction.csrf, csrf)):
                raise PermissionError("Transaction belongs to another operator session or CSRF token is invalid")
            # Claim before execution; racing approvals cannot execute the same transaction.
            try:
                if not decision:
                    self._finish(transaction, "denied", "User Denied Execution")
                elif not authorize(transaction.tool):
                    self._finish(transaction, "denied", "Operator permission denied execution")
                else:
                    repository = transaction.repository
                    for path in transaction.paths:
                        if self._hash(self._state(repository, path, commit=transaction.tool == "propose_commit")) != transaction.hashes[path]:
                            raise ApprovalConflict("Stale payload: target file changed since proposal")
                    if transaction.tool == "propose_write_file":
                        output = self._write(transaction)
                    else:
                        if (repository._git("rev-parse", "HEAD").strip() != transaction.head
                                or self._index_hash(repository) != transaction.index_hash):
                            raise ApprovalConflict("Stale commit: HEAD or staging index changed")
                        output = self._commit(transaction)
                    self._finish(transaction, "succeeded", output)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                LOG.exception("Tool approval execution failed: %s", transaction.id)
                self._finish(transaction, "failed", str(exc))
            return dict(transaction.result)

    def _write(self, transaction):
        repository = transaction.repository
        relative = transaction.paths[0]
        path = repository._path(relative)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".apex-write-", delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(transaction.args["content"].encode("utf-8"))
                stream.flush()
                os.fchmod(stream.fileno(), transaction.states[relative][1])
                os.fsync(stream.fileno())
            if self._hash(self._state(repository, relative)) != transaction.hashes[relative]:
                raise ApprovalConflict("Stale payload: target changed before atomic replacement")
            os.replace(temp_path, path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
        return f"Approved write completed: {relative}; SHA-256 {self._hash(self._state(repository, relative))}"

    def _commit(self, transaction):
        repository = transaction.repository
        with tempfile.TemporaryDirectory(prefix="apex-commit-") as directory:
            index = str(Path(directory) / "index")
            env = {**os.environ, "GIT_INDEX_FILE": index, "GIT_OPTIONAL_LOCKS": "0"}

            def git(*args):
                return subprocess.check_output(
                    ["git", "--no-pager", "-c", "core.fsmonitor=false", "-C", str(repository.root), *args],
                    env=env, stderr=subprocess.STDOUT, timeout=60, text=True)

            git("read-tree", transaction.head)
            git("add", "--", *transaction.paths)
            selected = git("diff", "--cached", "--name-only", "-z").split("\0")[:-1]
            if set(selected) - set(transaction.paths):
                raise ApprovalConflict("Commit index includes an unapproved file")
            for path in transaction.paths:
                if self._hash(self._state(repository, path, commit=True)) != transaction.hashes[path]:
                    raise ApprovalConflict("Stale commit payload before execution")
            if git("diff", "--cached", "--no-color", "--no-ext-diff", "--no-textconv", "--",
                   *transaction.paths) != transaction.diff:
                raise ApprovalConflict("Staged commit differs from the approved preview")
            if (repository._git("rev-parse", "HEAD").strip() != transaction.head
                    or self._index_hash(repository) != transaction.index_hash):
                raise ApprovalConflict("Stale commit HEAD or index before execution")
            message = transaction.args["message"].strip()
            message += "\n\nCo-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
            git("commit", "-m", message)
            commit = repository._git("rev-parse", "HEAD").strip()
            changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", "-z", commit).split("\0")[:-1]
            if set(changed) - set(transaction.paths):
                raise ApprovalConflict(f"Commit {commit} includes unexpected hook changes; operator review required")
            # Refresh only approved index entries; unrelated staged/worktree changes stay untouched.
            for path in selected:
                entry = git("ls-files", "--stage", "--", path).strip()
                mode, oid, _ = entry.split(None, 2)
                subprocess.run(
                    ["git", "-C", str(repository.root), "update-index", "--add", "--cacheinfo", f"{mode},{oid},{path}"],
                    check=True, capture_output=True, timeout=10)
        return f"Approved commit completed: {commit}; paths: {', '.join(selected)}"


APPROVALS = ApprovalStore()
