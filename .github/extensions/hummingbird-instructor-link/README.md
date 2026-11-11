# Hummingbird attached instructor link

The active implementation is a workspace Copilot SDK extension. It registers
`hummingbird-attached-instructor-link` in the current instructor session; it does
not start a replacement model session or use the old VSIX transport scaffold.

## Chat

In an owner-authenticated HB thread, every operator message goes to APEX first.
Adding `@instructor` or `@gemini` does not bypass APEX; it marks that instructor
as addressed. After APEX commits its answer (or its busy/offline error), each
enabled instructor receives a bounded `[TEAM COPY]` containing the operator's
message and APEX's answer, and coaches APEX in the same thread. The composer
shows `To: APEX (local) · addressed: …`. Only when no local runtime is available
does a mention go directly to the instructor. Peer messages reach the attached
SDK session through `session.send`. The instructor replies with the `post_reply`
canvas action. Gemini messages are relayed through the explicitly shared,
authenticated browser tab by the instructor, and the result is attributed to
`gemini-advisor`.

Both Home Chat and the full Chat window expose **One conversation, one team**:
the operator, APEX (local execution), VS Code Instructor (review) and Gemini
(architectural advice via the instructor relay). Participant buttons insert an
address into the current draft; they do not send, warm a model or grant access.
Explicit peer messages can be sent even when no local model is available.
Service access is read from the owner-only audit endpoint; **Enabled** means
permission, not live presence. **Refresh access** updates those controls.

Select an existing thread and choose **Use this conversation as shared**.
Room controls are under **Shared conversation options and connection details**.
The browser stores that explicit bookmark and both surfaces open the same thread.
**Open shared conversation** returns both surfaces to it; **Unpin** restores
ordinary fresh-thread behavior for the full Chat window. The bookmark is local
to this browser, not a global migration or a new conversation for each participant.
Every message goes to APEX first; mentions only mark the addressed instructor.
The pending label names APEX, not a legacy registry candidate such as Gemma3.
An occupied APEX model returns an explicit busy error after a one-second queue
wait; queue time is included in the turn deadline. Each request retains its own
operator instruction even when another participant updates the shared thread.
The pinned room uses an opaque Chat window so underlying transcripts do not bleed
through and opens maximized rather than at a potentially off-screen saved position.
Unpinning restores the existing window appearance and normal opening behavior.
On short screens its secondary header/runtime controls collapse to retain a
readable transcript; participant buttons remain visible.

The main chat also shows a live, conversation-scoped activity and Studio board.
It displays each participant's latest public message, delivery queue counts,
and the authenticated operator's persisted task rows (including previous
skipped tasks). Task pages contain at most 20 rows and reject mixed revisions;
the saved context checksum is verified without returning private context.
Project/task status is evidence, not execution approval. Bridge contact and
queued delivery are explicitly distinguished from model execution.
Peer messages remain visible while APEX is answering. SSE updates are backed
by a 15-second transcript recovery check; the board refreshes every five
seconds while visible, with explicit failures rather than a false live state.

The attached instructor session and Gemini tab must remain available. This is
an instructor-mediated DOM relay, **not an independent Gemini background
service**. A queued/acknowledged inbox message proves submission to the
instructor, not that Gemini has answered. Read the actual browser response and
the persisted HB reply before claiming an end-to-end pass. Preserve drafts,
check the Gemini origin/conversation, and never relay credentials, private
source, sensitive data or the whole thread.

APEX may request bounded assistance using one or two standalone lines outside
code fences:

```text
[DISPATCH: @instructor] <review or missing-context request>
[DISPATCH: @gemini] <public architectural question>
```

Peer handoffs have a three-second delay and stop dispatching after three agent
turns without operator input. Peer replies do not automatically prompt APEX.
These limits do not grant execution permission; ordinary approval gates remain.

APEX's owner-authenticated Studio tools include `studio_evidence_get` with only
an integer `evidence_id`. It reads the current owner/conversation/project, without
creating storage or accepting paths or SQL. `found` includes stored JSON;
`not_found`, `corrupt` and `truncated` are not completion. Unreadable scope metadata
fails closed as `not_found`. The serialized result is capped at 6,000 bytes.
Full proposal bodies and receipts remain in Studio; only bulky source arguments
are removed from the live model context after a proposal resolves. A capacity
handoff does not undo an approved write or grant a new approval.

APEX coaching runs through Studio ALM. Instructors create a step with owner
`apex` whose description lists numbered lines with an exact tool and its arguments,
a done-check and a stop rule. They also add test cases to that step. APEX reads the step with
`alm_step_get {"step_id":"S-…"}`. Steps not owned by or routed to APEX return
`not_assigned`. `run_tests` runs bounded pytest (150 s). Its first field,
`verdict`, is one line APEX quotes instead of interpreting raw fields: `PASS`,
`NOT A PASS` (no tests ran, pytest exit 5, recorded as an ALM fail), `FAIL` or
`UNKNOWN` (busy or timed out). Called with
`case_id`, it records an `apex:pytest` ALM run and rolls up the case status. Invalid
arguments create no run; a busy or timed-out runner records an aborted run.
`tests` takes files only: a pytest node ID (`file::function`) is rejected with
the exact `{"tests":[file],"keyword":function}` form to send instead. A keyword
under three characters is rejected with the resend for that ALM case (no
keyword, plus the `C-` id of the case titled with that letter); if the call
already carries that case's `case_id`, the letter is dropped instead, the whole
file runs for the case, and the result carries a `note` saying so. A placeholder
keyword such as `<real_test_name>` is told to run `grep_repo` alone first and
copy a name from its receipt, and a quote-only keyword is told that keywords are
plain text. Every such rejection ends `NOT RUN: no pytest started, so there is
no exit code, verdict or ALM run`. Only the owner approves or closes a step.

APEX's repository tools (`grep_repo`, `read_file`, `list_files`, `run_tests`)
see only git-tracked files. A new file is invisible to APEX until it is
committed or registered with `git add -N <path>` (reversible with
`git reset -- <path>`). `grep_repo` searches up to 2,000 files within 8 s. If it
stops early, the receipt says INCOMPLETE and shows where it stopped. A complete
search ends with `[complete: N git-tracked text files searched; untracked files
are invisible]`.

APEX's system prompt ends with `ATTACHED TOOLS THIS TURN (complete list)`,
generated from the backend's mode: the five read tools are always included, and
Studio, ALM, test and proposal tools are added for authenticated Hummingbird
turns. Shell, installs and service control are never attached. Before a final
answer is delivered, the backend checks every Studio or ALM-style ID in it
(`S-`, `C-`, `B-`, `R-` with 10 hex digits, and 16- or 32-hex run IDs) against
the messages and receipts of the turn. An ID that appears nowhere triggers one
`BACKEND GROUNDING ERROR` retry. If the retry still contains invented IDs,
the answer is delivered with a visible warning instead of being presented as fact.
A line that names exactly one tool but cites another tool's receipt id gets one
`BACKEND RECEIPT CHECK` retry listing the right receipt ids, then a visible
warning if it is still wrong. On a turn that names an ALM step, the same check
rejects receipt ids that no tool call of this turn produced (for example ones
copied from an earlier answer), so a retest must run its tools again.
If the operator's message names an ALM step (`S-…`) and the turn ends without an
`alm_step_get` receipt for it, the backend sends one `BACKEND STEP CHECK`
correction; if the step is still unread, the answer carries a visible warning.
`alm_step_get` returns the step description as a numbered `checklist`, one
sentence per item, so each part of a multi-part step stays visible. It reports runs as `earlier_runs` with a note that they are history,
not results of the current turn, so a retest needs a new `run_tests` call.

APEX's llama-server slot holds 8,192 tokens, and tool rounds keep a 2,048-token
output reserve (the largest observed round used about 1,550 completion tokens).
When a correction rejects an answer, that answer stays in context marked
`rejected_answer`: the receipts it read count as consumed and compact to
excerpts, but its text never grounds IDs or test names. A `grep_repo` receipt too
large for the window keeps its leading matches with a `CONTEXT CUT` note that
asks for a narrower path, instead of being withheld entirely. If receipts fill the
window after real tool work, the backend
sends one `BACKEND CONTEXT LIMIT` notice. APEX then gets one tool-free round
under a 1,024-token reserve to report from the receipts it already has, instead
of handing off with no answer. The same tool-free round, announced by
`BACKEND ROUND LIMIT`, follows a turn that used all six tool rounds, and
`BACKEND TIME LIMIT` follows tool work once the rest of the 360-second turn
budget is under twice the longest round so far (at least 120 seconds), because
CPU-bound rounds can each take over a minute and the answer round must fit. If it asks
for more tools in that round, or the request itself does not fit, the turn is
saved as a Studio handoff as before. Each Studio turn trace lists the backend
corrections sent before each round ("Backend corrections sent before: round 6
BACKEND STEP CHECK"), so a retry is visible without reading service logs.
When a `run_tests` receipt must be withheld to fit, it keeps its `verdict`,
`alm_run_id`, `alm_run_status` and `alm_case_id` and only drops the pytest
output. Any other withheld read keeps its real `status` and says its output was
withheld, so a successful read is never shown to APEX as failed. Within a turn,
a `run_tests` keyword shaped like `test_…` that appears in no earlier message
or receipt is rejected as a guess before pytest starts (calls in one batch
cannot see each other's receipts). A test path that is not tracked becomes a
fixable failed receipt instead of a denial. Both errors list the test files and
`def test_…` names this turn's read receipts show. Repeating a call that was
already rejected returns `REPEATED CALL` with the earlier receipt id. On a turn
that names an ALM step, an answer that stops to ask the operator for input
(for example "can't proceed… please provide the path") while no receipt shows a
failure or denial gets one `BACKEND STEP CHECK` telling APEX to do the step's
next instruction with a tool. After a blocking receipt the request is delivered,
except when every `run_tests` call this turn was rejected before pytest started
(`NOT RUN`): that answer gets one `BACKEND STEP CHECK` naming the rejected
receipt and asking for the corrected call that its error lists. A failure later
fixed by a successful call of the same tool no longer counts as a blocker, and
deflections such as "defined elsewhere" or "search X to locate it" also get the
correction. A `grep_repo` phrase search with at most two matches, or a guessed
underscore name with none, suggests searching one word alone, because the real
code name differs. Using an ALM case title as the `run_tests` keyword is
refused before pytest with the fix. On a step turn, an answer that omits a
recorded `run_tests` ALM run (or says no test ran) gets one answer-only receipt
check with no further tools; this can fire once even after the round or context
limit. If the answer still omits it, the backend appends the run's receipt,
verdict and ALM run id as a labelled note. When the step's checklist names a
search ("search the core path", "search the tests path for the word bounded")
and no successful `grep_repo` call used that path and word, the answer gets one
`BACKEND STEP CHECK` listing the missing searches by checklist item; if no tool
round remains, the answer is delivered with a labelled note naming them.

APEX has one model slot. A message sent while APEX is mid-turn is queued in
arrival order (up to 1,260 s: one pending approval plus one turn) instead of
failing as "model busy". The chat shows
`queued`, and the queued turn includes the earlier answer in its context.
Every finished, blocked or offline turn writes a readable `trace` note to the
thread's Studio project and to any ALM project whose step or case it touched:
each tool call with arguments, status and receipt id, model rounds and the answer.
Read the notes in Studio or at
`GET /api/knowledge/projects/<project_id>/blackboard?status=all`. A trace shows
what ran; it is not approval. Proposals that change nothing, and proposals for
advice, status or system-check requests, are refused without a transaction.

## Access and memory

The Agents window lists service participants and their auditable memory pools.
Disable prevents authentication and new delivery for that principal, including
Gemini replies relayed by the instructor. Already delivered external requests
cannot be recalled, but their replies cannot be posted while the author is
disabled. A handoff to a disabled participant is refused and audited without
discarding the sending peer's own reply.

Service credentials are limited to the dedicated peer identity, inbox, message,
thread and memory endpoints. They are rejected on legacy execution and
owner-management routes, even alongside an owner cookie. Credentials are stored
outside the repository; never print them or enter an owner cookie as a peer token.

## Verification

From the repository root:

```sh
.venv/bin/python -m pytest tests/test_peer_bridge.py tests/test_chat_continuity.py tests/test_peer_chat_ui.py tests/test_unified_local_chat.py tests/test_home_chat_continuity.py tests/test_apex_alm.py tests/test_apex_read_tools.py tests/test_apex_test_runner.py tests/test_apex_turn_queue.py tests/test_apex_guidance_examples.py tests/test_apex_grounding.py tests/test_apex_final_answer.py tests/test_apex_guessed_calls.py tests/test_apex_studio.py tests/test_apex_context.py tests/test_tool_approval.py -q -p no:cacheprovider
node --test .github/extensions/hummingbird-instructor-link/relay.test.mjs .github/extensions/hummingbird-instructor-link/peer.test.mjs
```

After changing extension code, reload extensions, discover the canvas, then open
it and call `connection_status`. Reopening the same instance preserves its live
panel. The `read_thread`, `remember` and `recall` actions use scoped HB endpoints.
Validate an actual correlated HB request, Gemini response and displayed HB reply;
unit tests alone cannot establish browser connectivity.
