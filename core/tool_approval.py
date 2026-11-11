"""One-use, session-owned human approval transactions for APEX proposals."""
from __future__ import annotations

from dataclasses import dataclass, field
import difflib
import hashlib
import json
import logging
import ast
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
PROPOSAL_TOOLS = {"propose_write_file", "propose_commit", "propose_patch"}
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
    states: dict[str, tuple[bytes, int] | None]
    args: dict
    repository: ReadOnlyRepository
    head: str = ""
    index_hash: str = ""
    creation_parents: dict[str, tuple[int, int]] = field(default_factory=dict)
    expires_at: float = field(default_factory=lambda: time.time() + APPROVAL_TIMEOUT)
    ready: threading.Event = field(default_factory=threading.Event)
    result: dict | None = None
    execution: dict | None = None

    def public(self) -> dict:
        return {
            "transaction_id": self.id, "conversation_id": self.conversation_id,
            "tool": self.tool, "paths": self.paths, "diff": self.diff,
            "hashes": self.hashes, "expires_at": self.expires_at,
            "message": self.args.get("message", ""),
            "new_paths": [path for path, state in self.states.items() if state is None],
        }


class ApprovalStore:
    """Process-local pending transactions; a restart invalidates every UUID."""
    def __init__(self):
        self._lock = threading.RLock()
        self._pending: dict[str, Transaction] = {}
        self._reserved: set[tuple[str, str]] = set()

    @staticmethod
    def _parent_fd(repository, relative):
        repository._path(relative)
        descriptor = os.open(repository.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in Path(relative).parent.parts:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = child
            return descriptor
        except OSError:
            os.close(descriptor)
            raise

    @staticmethod
    def _state(repository, relative, *, commit: bool = False, patch: bool = False,
               create: bool = False):
        # Reuse the tracked-text and protected-path boundary; never read private pools.
        limit = MAX_FILE_BYTES if commit or patch else MAX_WRITE_BYTES
        if create:
            path = repository._source_path(relative)
            parent = ApprovalStore._parent_fd(repository, relative)
            try:
                try:
                    os.stat(path.name, dir_fd=parent, follow_symlinks=False)
                except FileNotFoundError:
                    ignored = subprocess.run(
                        ["git", "-C", str(repository.root), "check-ignore", "--no-index", "--", relative],
                        capture_output=True, timeout=10)
                    if ignored.returncode == 0:
                        raise PermissionError("Ignored source paths cannot be created")
                    if ignored.returncode != 1:
                        ignored.check_returncode()
                    return None
            finally:
                os.close(parent)
        repository._text(relative, set(repository._tracked()), allow_untracked=commit or create or patch, max_bytes=limit)
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
        if state is None:
            return hashlib.sha256(b"APEX:absent-source-file").hexdigest()
        return hashlib.sha256(state[0] + b"\0mode:" + str(state[1]).encode()).hexdigest()

    @staticmethod
    def _index_hash(repository):
        return hashlib.sha256(repository._git("ls-files", "--stage", "-z").encode()).hexdigest()

    def _finish(self, transaction, status, output):
        transaction.result = {
            "transaction_id": transaction.id, "status": status, "output": output,
        }
        if transaction.execution:
            transaction.result.update({
                'executor': transaction.execution['principal'],
                'requested_by': transaction.execution['requested_by'],
                'run_id': transaction.execution['run_id'],
                'model': transaction.execution['model'],
            })
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
        patch = tool == "propose_patch"
        if tool == "propose_write_file":
            if set(args) != {"path", "content"} or not isinstance(args["content"], str):
                raise ValueError("propose_write_file requires path and complete UTF-8 content")
            paths = [args["path"]]
            if len(args["content"].encode()) > MAX_WRITE_BYTES or "\0" in args["content"]:
                raise ValueError("Write payload exceeds limit or contains binary data")
        elif patch:
            if (set(args) != {"file_path", "exact_old_text", "new_text"}
                    or not isinstance(args["exact_old_text"], str) or not args["exact_old_text"]
                    or not isinstance(args["new_text"], str)
                    or any(len(args[key].encode("utf-8")) > 8000 or "\0" in args[key]
                           for key in ("exact_old_text", "new_text"))):
                raise ValueError("propose_patch requires file_path, nonempty exact_old_text and new_text; text limit 8000 bytes")
            if args["exact_old_text"] == args["new_text"]:
                raise ValueError(
                    "propose_patch new_text is identical to exact_old_text, so it changes nothing. "
                    "Propose only a change the operator or your ALM step explicitly requested. No transaction created."
                )
            paths = [args["file_path"]]
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
        states = {path: self._state(repository, path, commit=commit, patch=patch,
                                    create=tool == "propose_write_file") for path in paths}
        creation_parents = {}
        for path, state in states.items():
            if state is None:
                parent = self._parent_fd(repository, path)
                try:
                    info = os.fstat(parent)
                    creation_parents[path] = (info.st_dev, info.st_ino)
                finally:
                    os.close(parent)
        if tool == "propose_write_file" or patch:
            state = states[paths[0]]
            before = state[0].decode("utf-8") if state is not None else ""
            if patch:
                if (args['exact_old_text'] in args['new_text'] and args['new_text'] in before
                        and before.count(args['exact_old_text'])==1):
                    raise ValueError('This exact insertion is already present in current source; no duplicate write was proposed. Read back the existing result and continue with the next unfinished action.')
                matches = before.count(args["exact_old_text"])
                if matches != 1:
                    raise ValueError(
                        f"Exact patch text matched {matches} locations; provide a larger unique context "
                        "chunk from a fresh raw read. No transaction created."
                    )
                after = before.replace(args["exact_old_text"], args["new_text"], 1)
                if len(after.encode("utf-8")) > MAX_FILE_BYTES:
                    raise ValueError("Patched file exceeds the 1 MiB limit")
            else:
                after = args["content"]
            if before == after and state is not None:
                raise ValueError("Write proposal has no changes")
            if tool=='propose_write_file' and len(before)>4096 and len(after)<len(before)//2:
                raise ValueError('A fragment cannot replace this existing source file. Use an exact scoped patch for an intentional removal; no source changed.')
            if paths[0].endswith('.py'):
                try:updated_tree=ast.parse(after,filename=paths[0])
                except SyntaxError as exc:
                    raise ValueError(f'Python proposal does not parse at line {exc.lineno}: {exc.msg}. No source changed; correct the payload locally.') from None
                if tool=='propose_write_file' and state is not None:
                    try:original_tree=ast.parse(before)
                    except SyntaxError:original_tree=None
                    if original_tree:
                        definitions=lambda tree:{n.name for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef))}
                        removed=definitions(original_tree)-definitions(updated_tree)
                        if removed:raise ValueError('Complete-file write would remove existing definitions: '+', '.join(sorted(removed))+'. Use a reviewed exact patch for an intentional removal; a fragment cannot replace the module.')
            diff = "".join(difflib.unified_diff(
                before.splitlines(keepends=True), after.splitlines(keepends=True),
                fromfile="a/" + paths[0] if state is not None else "/dev/null", tofile="b/" + paths[0]))
            # Show complete file payload when a missing final newline affects diff display.
            diff = json.dumps(
                {"unified_diff": diff, **({"exact_old_text": args["exact_old_text"],
                                          "new_text": args["new_text"]} if patch else {"new_content": after})},
                ensure_ascii=True, indent=2)
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
            from core.agent_identity import CURRENT
            transaction = Transaction(
                str(uuid.uuid4()), owner, session, secrets.token_urlsafe(32), conversation_id,
                tool, list(paths), diff, {path: self._hash(state) for path, state in states.items()},
                states, json.loads(json.dumps(args)), repository, head, index_hash,
                creation_parents=creation_parents,
                execution=dict(CURRENT.get()) if CURRENT.get() else None,
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
        from core.hb_executions import authorized as task_authorized
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
            from core import agent_identity as attribution
            actor = transaction.execution
            before = {path: hashlib.sha256(state[0]).hexdigest() if state is not None else None
                      for path, state in transaction.states.items()}
            audit_started = False

            def audit(status, after=None, result=None):
                return attribution.event(actor, transaction.id, transaction.tool, status,
                    paths=transaction.paths, before=before, after=after, result=result)

            try:
                audit('started', result={'diff': transaction.diff})
                audit_started = actor is not None
                if not decision:
                    audit("denied", result={"reason": "operator_denied"})
                    self._finish(transaction, "denied", "User Denied Execution")
                elif not authorize(transaction.tool) or (actor and not attribution.identity_is_active(actor)) or not task_authorized(actor):
                    audit("denied", result={"reason": "permission_denied"})
                    self._finish(transaction, "denied", "Operator permission denied execution")
                else:
                    repository = transaction.repository
                    from core.hb_process_lock import ProcessLock
                    with ProcessLock('source-write',repository.root):
                        if not authorize(transaction.tool) or (actor and not attribution.identity_is_active(actor)) or not task_authorized(actor):
                            raise PermissionError('Permission revoked before execution')
                        for path in transaction.paths:
                            if self._hash(self._state(repository, path, commit=transaction.tool == "propose_commit",
                                                      patch=transaction.tool == "propose_patch",
                                                      create=transaction.tool == "propose_write_file")) != transaction.hashes[path]:
                                raise ApprovalConflict("Stale payload: target file changed since proposal")
                        if transaction.tool in {"propose_write_file", "propose_patch"}:
                            output = self._write(transaction)
                        else:
                            if (repository._git("rev-parse", "HEAD").strip() != transaction.head
                                    or self._index_hash(repository) != transaction.index_hash):
                                raise ApprovalConflict("Stale commit: HEAD or staging index changed")
                            output = self._commit(transaction)
                        after = attribution.path_hashes(repository, transaction.paths) if actor else None
                        audit("succeeded", after=after)
                        self._finish(transaction, "succeeded", output)
            except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
                LOG.exception("Tool approval execution failed: %s", transaction.id)
                if audit_started:
                    try:
                        audit('failed', result={'error_type': type(exc).__name__})
                    except RuntimeError:
                        LOG.exception('Audit outcome unavailable; durable action intent remains %s', transaction.id)
                self._finish(transaction, "failed", str(exc))
            return dict(transaction.result)

    def _write(self, transaction):
        repository = transaction.repository
        relative = transaction.paths[0]
        path = repository._path(relative)
        patch = transaction.tool == "propose_patch"
        state = transaction.states[relative]
        if state is None:
            return self._create(transaction)
        content = (
            state[0].decode("utf-8").replace(
                transaction.args["exact_old_text"], transaction.args["new_text"], 1)
            if patch else transaction.args["content"]
        )
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".apex-write-", delete=False) as stream:
                temp_path = Path(stream.name)
                stream.write(content.encode("utf-8"))
                stream.flush()
                os.fchmod(stream.fileno(), state[1])
                os.fsync(stream.fileno())
            if self._hash(self._state(repository, relative, patch=patch, create=not patch)) != transaction.hashes[relative]:
                raise ApprovalConflict("Stale payload: target changed before atomic replacement")
            os.replace(temp_path, path)
        finally:
            if temp_path is not None and temp_path.exists():
                temp_path.unlink()
        return f"Approved {'patch' if patch else 'write'} completed: {relative}; SHA-256 {self._hash(self._state(repository, relative, patch=patch, create=not patch))}"

    def _create(self, transaction):
        repository = transaction.repository
        relative = transaction.paths[0]
        parent = self._parent_fd(repository, relative)
        temporary = ".apex-write-" + secrets.token_hex(16)
        created_temp = False
        try:
            info = os.fstat(parent)
            if (info.st_dev, info.st_ino) != transaction.creation_parents[relative]:
                raise ApprovalConflict("Stale payload: creation parent changed")
            descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                                 0o600, dir_fd=parent)
            created_temp = True
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(transaction.args["content"].encode("utf-8"))
                stream.flush()
                os.fchmod(stream.fileno(), 0o644)
                os.fsync(stream.fileno())
            if self._state(repository, relative, create=True) is not None:
                raise ApprovalConflict("Stale payload: creation target now exists")
            current_parent = self._parent_fd(repository, relative)
            try:
                current_info = os.fstat(current_parent)
                if (current_info.st_dev, current_info.st_ino) != transaction.creation_parents[relative]:
                    raise ApprovalConflict("Stale payload: creation parent changed")
            finally:
                os.close(current_parent)
            # Linking the complete inode is atomic and fails if any target appeared.
            os.link(temporary, Path(relative).name, src_dir_fd=parent, dst_dir_fd=parent,
                    follow_symlinks=False)
            os.fsync(parent)
        finally:
            try:
                if created_temp:
                    os.unlink(temporary, dir_fd=parent)
            finally:
                os.close(parent)
        return f"Approved creation completed: {relative}; SHA-256 {self._hash(self._state(repository, relative, commit=True))}"

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
