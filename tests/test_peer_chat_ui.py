"""Shared conversation controls must not route service peers to local models."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
CHAT = ROOT / "frontend/static/js/views/chat.js"


def run_helpers(body):
    node = shutil.which("node") or shutil.which("nodejs")
    if node is None:
        pytest.skip("JavaScript runtime is unavailable")
    source = CHAT.read_text()
    helpers = source[source.index("function getChatPeerTargets("):
                     source.index("function renderChatParticipants(")]
    subprocess.run(
        [node, "-e", "const assert = require('node:assert/strict');\n" + helpers + body],
        check=True, timeout=10,
    )


def test_peer_routing_needs_no_local_model_and_deduplicates_aliases():
    run_helpers("""
function getAutomaticLocalChatAgents() { return []; }
assert.deepEqual(getChatDispatchAgents('@instructor Hello'), ['copilot-instructor']);
assert.deepEqual(getChatDispatchAgents('@Gemini Hello'), ['gemini-advisor']);
assert.deepEqual(getChatDispatchAgents('@codex Hello'), ['codex-instructor']);
assert.deepEqual(getChatDispatchAgents('@copilot @instructor @gemini Hi'),
                 ['copilot-instructor', 'gemini-advisor']);
for (const text of ['hello', 'mail@instructor', '@@gemini', '@geminiElse']) {
  assert.deepEqual(getChatDispatchAgents(text), []);
}
assert.equal(chatRecipientSummary('@gemini hi', id => id), 'gemini-advisor');
assert.equal(chatRecipientSummary('hello'), 'nobody (APEX offline)');
""")


def test_local_dispatch_is_unchanged_and_recipient_changes_preserve_draft():
    run_helpers("""
function getAutomaticLocalChatAgents() { return ['apex']; }
assert.deepEqual(getChatDispatchAgents('ordinary local work'), ['apex']);
assert.deepEqual(getChatDispatchAgents('@gemini @instructor review this'), ['gemini-advisor', 'copilot-instructor']);
assert.equal(chatRecipientSummary('@gemini review this', id => id), 'gemini-advisor');
assert.equal(chatRecipientSummary('plain work'), 'APEX (local)');
assert.equal(chatRecipientText('keep my draft', 'instructor'), '@instructor keep my draft');
assert.equal(chatRecipientText('@gemini keep my draft', 'instructor'), '@instructor keep my draft');
assert.equal(chatRecipientText('@instructor keep my draft', 'apex'), '@apex keep my draft');
assert.equal(chatRecipientText('@codex keep my draft', 'apex'), '@apex keep my draft');
assert.equal(chatRecipientText('code contains @gemini later', 'apex'),
             '@apex code contains @gemini later');
""")


def test_local_runtime_candidates_never_label_the_apex_request_as_gemma():
    run_helpers("""
function getAutomaticLocalChatAgents() { return ['gemma3', 'qwen']; }
assert.deepEqual(getChatDispatchAgents('ordinary local work'), ['apex']);
assert.deepEqual(getChatDispatchAgents('@gemini status'), ['gemini-advisor']);
""")


@pytest.mark.parametrize("stored,expected", [
    (None, None), ("", None), ("bad", None), ("-1", None),
    ("1.5", None), ("9007199254740992", None), ("2829", 2829),
])
def test_shared_conversation_is_an_explicit_valid_bookmark(stored, expected):
    run_helpers(f"""
const CHAT_SHARED_THREAD_KEY = 'test-shared';
const localStorage = {{getItem: () => {json.dumps(stored)}}};
assert.equal(getSharedChatThreadId(), {json.dumps(expected)});
""")


def test_both_surfaces_expose_participants_and_use_peer_aware_dispatch():
    home = (ROOT / "frontend/static/js/views/home-chat.js").read_text()
    chat = CHAT.read_text()
    template = (ROOT / "frontend/templates/terminal_base.html").read_text()
    assert 'data-chat-participants="home"' in template
    assert 'data-chat-participants="chat"' in template
    assert "getChatDispatchAgents(text)" in home.split("function _hcSend()", 1)[1]
    assert "getChatDispatchAgents(msg)" in chat.split("function sendMessage(", 1)[1]
    assert "'hummingbird:shared-thread'" in home
    assert "getSharedChatThreadId()" in home.split("window.initHomeChat", 1)[1]
    assert "_chatAgentLabel(name)" in home
    conversations = (ROOT / "frontend/static/js/views/conversations.js").read_text()
    assert "__fridaysChatOpenWithConvId || getSharedChatThreadId()" in conversations
    assert "__fridaysChatForceNewThread = true" in conversations


def test_shared_room_preserves_transcript_space_and_opens_in_view():
    css = (ROOT / "frontend/static/css/views/chat.css").read_text()
    assert ".chat-shared-room #chat-section-main { min-height: 100px; }" in css
    assert "@media (max-height: 520px)" in css
    source = (ROOT / "frontend/static/js/views/conversations.js").read_text()
    assert "Number(explicitOpenId) === getSharedChatThreadId() && !win.maximized" in source
    assert "winManager.toggleMaximize(win.id)" in source


def test_home_live_board_cannot_push_composer_out_of_view():
    css = (ROOT / "frontend/static/css/views/chat.css").read_text()
    rule = css.split(".chat-shared-room .chat-team {", 1)[1].split("}", 1)[0]
    assert "max-height: min(40vh, 320px);" in rule
    assert "overflow-y: auto;" in rule
    assert "min-height: 0;" in rule
    home_css = (ROOT / "frontend/static/css/home-chat.css").read_text()
    assert "#home-content { grid-template-columns: minmax(0, 1fr); }" in home_css
    assert "#home-content > .home-section { min-width: 0; }" in home_css
    assert ".home-chat-compose textarea { flex-basis: 100%; }" in home_css


def test_compact_status_preserves_provenance_and_escapes_model_data():
    run_helpers("""
function _escapeHtml(value) { return String(value).replaceAll('<', '&lt;'); }
function _chatAgentLabel(id) { return id === 'gemini-advisor' ? 'Gemini' : id; }
const summary = renderChatRuntimeSummary({
  apex: {state: 'online'},
  archive: {state: 'downloading', bytes_present: 44, bytes_expected: 100},
  agents: [{id: 'apex', state: 'duplicate'}, {id: 'gemini-advisor', state: '<unsafe>'}]
}, 173);
assert(summary.includes('APEX: online'));
assert(summary.includes('44% staged'));
assert(summary.includes('173 saved tasks'));
assert(summary.includes('Gemini: &lt;unsafe>'));
assert(!summary.includes('duplicate'));
assert(!summary.includes('<unsafe>'));
assert(renderChatRuntimeSummary({}, 0).includes('APEX: unknown'));
assert(renderChatRuntimeSummary({archive: {state: 'verified'}}, 0).includes('not indexed'));
""")


def test_live_details_are_collapsed_by_default_and_reused_on_refresh():
    source = CHAT.read_text()
    refresh = source.split("async function refreshChatLiveBoard(", 1)[1].split("let chatLiveBoardTimer", 1)[0]
    assert '<details data-chat-live-details>' in refresh
    assert '<details data-chat-live-details open' not in refresh
    assert "if (!board.querySelector('[data-chat-live-details]'))" in refresh
    assert "board.querySelector('[data-chat-live-content]').innerHTML" in refresh
    assert "Any displayed status is stale" in refresh
    assert "host.querySelector('[data-chat-options]')?.open" in source
    home = (ROOT / "frontend/static/js/views/home-chat.js").read_text()
    assert """e.target.closest('button, summary, a, [role="button"]')""" in home
    assert "sendBtn.textContent = 'Send'" in home


def test_named_theme_survives_atmosphere_refresh_and_can_return_to_auto():
    node = shutil.which("node") or shutil.which("nodejs")
    if node is None:
        pytest.skip("JavaScript runtime is unavailable")
    theme = (ROOT / "frontend/static/js/core/theme.js").read_text()
    harness = """
const assert = require('node:assert/strict');
const classes = new Set();
const classList = {
  add: name => classes.add(name),
  remove: (...names) => names.forEach(name => classes.delete(name)),
  toggle(name, on) { if(on) classes.add(name); else classes.delete(name); }
};
const storage = new Map([['fridays_foundation_mode', 'dark']]);
const localStorage = {
  getItem: key => storage.get(key) ?? null,
  setItem: (key,value) => storage.set(key,String(value)),
  removeItem: key => storage.delete(key)
};
const document = {
  body: {classList, dataset:{}, style:{setProperty(){}}},
  documentElement:{style:{setProperty(){}}},
  getElementById:()=>null, querySelectorAll:()=>[], addEventListener(){}
};
const window = {addEventListener(){}};
"""
    checks = """
setNamedTheme('void');
assert(classes.has('theme-void'));
applyTimeTheme('afternoon');
assert(classes.has('theme-void'), 'periodic or startup atmosphere refresh must not erase saved theme');
assert(classes.has('mode-dark'));
setNamedTheme('auto');
assert(!classes.has('theme-void'));
assert.equal(localStorage.getItem('fridays_named_theme'), null);
"""
    subprocess.run([node, "-e", harness + theme + checks], check=True, timeout=10)


def test_home_chat_at_menu_lists_all_conversation_participants():
    home = (ROOT / "frontend/static/js/views/home-chat.js").read_text()
    template = (ROOT / "frontend/templates/terminal_base.html").read_text()
    assert 'id="home-chat-mention-menu"' in template
    for key in ("apex", "instructor", "gemini"):
        assert f"key: '{key}'" in home
    bindings = home.split("function _hcBindEvents()", 1)[1]
    assert "if (_hcMentionKeydown(e, input)) return;" in bindings
    assert "_hcMentionUpdate(input)" in bindings


def test_home_live_merge_does_not_hide_peers_while_apex_is_sending():
    node = shutil.which("node") or shutil.which("nodejs")
    if node is None:
        pytest.skip("JavaScript runtime is unavailable")
    home = (ROOT / "frontend/static/js/views/home-chat.js").read_text()
    refresh = home[home.index("  function _hcSilentRefresh("):
                   home.index("  // ── Switch thread")]
    harness = r"""
const assert = require('node:assert/strict');
let _hcConvId=2829, _hcViewVersion=1, _hcSendVersion=1, _hcSending=true, _hcLaneState='ok';
let rows=[], scrolls=0;
const nodes=[];
function bubble(id, sender, content, pending) {
  const el={dataset:{}, _chatMessage:{sender,content}, remove(){nodes.splice(nodes.indexOf(this),1);}};
  if(id) el.dataset.messageId=String(id);
  if(pending) el.dataset.pendingJobId=pending;
  nodes.push(el);
  return el;
}
const container={
  scrollHeight:1000, scrollTop:0, clientHeight:200,
  querySelectorAll(s){return nodes.filter(n=>s.includes(':not')
    ? !n.dataset.messageId : !!n.dataset.messageId);},
  querySelector(){return nodes.find(n=>n.dataset.pendingJobId)||null;},
  insertBefore(el,before){nodes.splice(nodes.indexOf(el),1);nodes.splice(nodes.indexOf(before),0,el);}
};
const document={getElementById:id=>id==='home-chat-messages'?container:null};
const fetch=async()=>({ok:true,json:async()=>({messages:rows})});
function _hcAppendBubble(m){return bubble(m.id,m.sender,m.content);}
function _hcClearMessages(){nodes.splice(0);}
function _hcScrollBottom(){scrolls++;}
"""
    checks = r"""
(async()=>{
  bubble(1,'user','same text');
  const optimistic=bubble(null,'user','same text');
  const pending=bubble(null,'apex','working','job-1');
  rows=[{id:1,sender:'user',content:'same text'},
        {id:2,sender:'user',content:'same text'},
        {id:3,sender:'copilot-instructor',content:'implementation update'},
        {id:4,sender:'gemini-advisor',content:'actual Gemini reply'}];
  await _hcSilentRefresh(2829);
  assert.deepEqual(nodes.filter(n=>n.dataset.messageId).map(n=>n.dataset.messageId),['1','2','3','4']);
  assert(nodes.includes(pending));
  assert(!nodes.includes(optimistic));
  assert.equal(scrolls,0, 'do not pull the operator away from older messages');
  await _hcSilentRefresh(2829);
  assert.equal(nodes.length,5,'repeated SSE must not duplicate messages');
  const before=nodes.slice();
  _hcConvId=99;
  await _hcSilentRefresh(2829);
  assert.deepEqual(nodes,before,'a stale request must not replace another thread');
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    subprocess.run([node, "-e", harness + refresh + checks], check=True, timeout=10)


def test_live_board_is_shared_bounded_and_recovers_missed_events():
    chat = CHAT.read_text()
    home = (ROOT / "frontend/static/js/views/home-chat.js").read_text()
    assert 'data-chat-live-board' in chat
    assert '/api/peer/v1/conversations/${convId}/activity' in chat
    assert 'AbortSignal.timeout(5000)' in chat
    assert "query.set('revision', state.revision)" in chat
    assert "hummingbird:chat-sync" in chat and "hummingbird:chat-sync" in home
    assert "if (!_hcConvId || _hcSending) return;" not in home


def test_main_chat_shows_runtime_model_archive_progress_and_observed_peers():
    run_helpers("""
function _escapeHtml(value) { return String(value).replaceAll('<', '&lt;'); }
function _chatAgentLabel(id) { return id==='gemini-advisor'?'Gemini':id; }
const html=renderChatRuntime({
  apex:{state:'online',model:'qwen2.5:14b-instruct',context_tokens:16384,backend:'Vulkan'},
  host_available_ram_gib:47,
  archive:{state:'downloading',mount:'/mnt/archive/hf_archive',
    bytes_present:50,bytes_expected:100,downloader_pid:10,
    active_repository:'Qwen/model'},
  agents:[{id:'gemini-advisor',state:'recent contact',last_contact:Date.now()/1000}]
});
assert(html.includes('LIVE / runtime stacks'));
assert(html.includes('qwen2.5:14b-instruct'));
assert(html.includes('16,384 context'));
assert(html.includes('50% staged'));
assert(html.includes('/mnt/archive/hf_archive'));
assert(html.includes('Gemini / bridge'));
assert(html.includes('recent contact'));
assert(html.includes('47.0 GiB host RAM available'));
assert(!renderChatRuntime({apex:{model:'<script>'}}).includes('<script>'));
""")


def test_live_room_height_keeps_composer_above_taskbar_when_page_scrolls():
    node = shutil.which("node") or shutil.which("nodejs")
    if node is None:
        pytest.skip("JavaScript runtime is unavailable")
    home = (ROOT / "frontend/static/js/views/home-chat.js").read_text()
    fit = home[home.index("  function _hcFitLiveRoom("):
               home.index("  window.homeFitLiveRoom")]
    script = """
const assert = require('node:assert/strict');
let top=200,scrollTop=0,height;
const chat={getBoundingClientRect:()=>({top}),style:{setProperty:(name,value)=>{height=value;}}};
const content={get scrollTop(){return scrollTop;}};
const document={querySelector:()=>chat,getElementById:id=>id==='home-content'
  ?content:{getBoundingClientRect:()=>({top:1202})}};
const window={innerHeight:1258};
"""
    checks = """
_hcFitLiveRoom(); assert.equal(height,'988px');
top=-31;scrollTop=231;_hcFitLiveRoom();assert.equal(height,'988px');
"""
    subprocess.run([node, "-e", script + fit + checks], check=True, timeout=10)


def test_participant_refresh_preserves_the_live_board_and_task_scroll():
    node = shutil.which("node") or shutil.which("nodejs")
    if node is None:
        pytest.skip("JavaScript runtime is unavailable")
    source = CHAT.read_text()
    render = source[source.index("function renderChatParticipants("):
                    source.index("async function refreshChatLiveBoard(")]
    harness = """
const assert = require('node:assert/strict');
const tasks={scrollTop:35};
const originalBoard={querySelector:()=>tasks};
let currentBoard=originalBoard,refreshes=0;
const button={addEventListener(){}};
const host={
  dataset:{chatParticipants:'home'},
  closest(){return null;},
  querySelector(selector){
    if(selector==='[data-chat-live-board]') return currentBoard;
    if(selector==='details') return {open:true};
    return button;
  },
  querySelectorAll(){return [];},
  set innerHTML(value){
    tasks.scrollTop=0;
    currentBoard={replaceWith(board){currentBoard=board;}};
  }
};
const document={querySelectorAll:()=>[host],getElementById:()=>({value:'2829'})};
const window={},chatPeerPrincipals=[],chatPeerStatus='Enabled';
function getSharedChatThreadId(){return 2829;}
function getAutomaticLocalChatAgents(){return ['apex'];}
function _escapeHtml(value){return value;}
function openSharedChatThread(){}
function refreshChatParticipants(){}
function refreshChatLiveBoard(target){assert.equal(target,host);refreshes++;}
function startChatLiveBoard(){}
"""
    checks = """
renderChatParticipants();
assert.equal(currentBoard,originalBoard,'do not strand an in-flight board refresh');
assert.equal(tasks.scrollTop,35,'restore scroll after detaching and reattaching the board');
assert.equal(host.dataset.conversationId,'2829');
assert.equal(refreshes,1);
"""
    subprocess.run([node, "-e", harness + render + checks], check=True, timeout=10)


def test_hidden_trace_tabs_release_connections_and_resume_without_duplicates():
    node = shutil.which("node") or shutil.which("nodejs")
    if node is None:
        pytest.skip("JavaScript runtime is unavailable")
    source = (ROOT / "frontend/static/js/core/trace-bus.js").read_text()
    harness = """
const assert = require('node:assert/strict');
function target(extra={}) {
  return {listeners:{},addEventListener(name,fn){this.listeners[name]=fn;},...extra};
}
const document=target({readyState:'complete',visibilityState:'hidden',getElementById:()=>null});
const window=target(),navigator={onLine:true},sources=[],timers=new Map();
let requests=0,nextTimer=0;
const setTimeout=(fn)=>{timers.set(++nextTimer,fn);return nextTimer;};
const clearTimeout=id=>timers.delete(id);
class EventSource {
  constructor(url){this.url=url;this.closed=false;sources.push(this);}
  close(){this.closed=true;}
}
const fetch=async()=>{requests++;return {json:async()=>({
  ok:true,items:[{id:'one',severity:'info',message:'backlog'}]
})};};
const settle=()=>new Promise(resolve=>setImmediate(resolve));
function visibility(value){
  document.visibilityState=value;
  document.listeners.visibilitychange();
}
"""
    checks = """
(async()=>{
  await settle();
  assert.equal(sources.length,0,'hidden tabs must not consume persistent HTTP connections');
  assert.equal(requests,0,'defer optional trace backlog until visible');
  visibility('visible');
  await settle();
  const first=sources[0];
  assert.equal(first.url,'/api/spine/stream');
  assert.equal(requests,1);
  first.onmessage({data:JSON.stringify({id:'two',severity:'info',message:'new'})});
  visibility('visible');
  window.__trace.start();
  assert.equal(sources.length,1,'repeated activation must keep one stream');
  visibility('hidden');
  assert(first.closed,'hiding the tab must release its trace stream');
  first.onerror();
  assert.equal(timers.size,0,'hidden tabs must not schedule reconnects');
  window.listeners.online();
  assert.equal(sources.length,1);
  visibility('visible');
  await settle();
  const second=sources[1];
  first.onerror();
  assert(!second.closed,'a stale error must not close the replacement stream');
  assert.deepEqual(window.__trace.recent().map(e=>e.id),['two','one'],
                   'reconnect backlog must not replay old events');
  second.onerror();
  assert(second.closed);
  assert.equal(timers.size,1,'visible disconnections retain bounded backoff');
  visibility('hidden');
  assert.equal(timers.size,0,'hiding cancels a pending retry');
  visibility('visible');
  assert.equal(sources.length,3);
  window.listeners.pagehide();
  assert(sources[2].closed);
  visibility('visible');
  assert.equal(sources.length,3,'do not reconnect while leaving the page');
  window.listeners.pageshow();
  await settle();
  assert.equal(sources.length,4,'a restored page must reconnect');
  window.__trace.stop();
  navigator.onLine=false;
  window.__trace.start();
  assert.equal(sources.length,4);
  navigator.onLine=true;
  window.listeners.online();
  await settle();
  assert.equal(sources.length,5);
  assert.equal(window.__trace.recent().length,2);
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    subprocess.run([node, "-e", harness + source + checks], check=True, timeout=10)


def test_tool_records_are_collapsed_and_transport_envelopes_are_not_chat_prose():
    run_helpers("""
function _escapeHtml(value) { return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;'); }
const render = s => 'PROSE:' + s;
const evidence = renderHummingbirdChatBody('[tool:read_file] succeeded (receipt abc)\\n<script>raw</script>', 'tool_result', render);
assert.ok(evidence.startsWith('<details '));
assert.ok(!evidence.includes('<script>'));
assert.ok(!evidence.includes(' open'));
assert.ok(evidence.includes('Read source'));
assert.equal(renderHummingbirdChatBody('{"tool_calls":[],"answer":"Plain answer"}', 'response', render), 'PROSE:Plain answer');
assert.ok(renderHummingbirdChatBody('{"tool_calls":[{"name":"read_file"}],"answer":""}', 'response', render).includes('awaiting a backend result'));
assert.equal(renderHummingbirdChatBody('Please show the Python example.', 'response', render), 'PROSE:Please show the Python example.');
""")


def test_peer_progress_is_thread_scoped_and_queued_is_not_completed():
    run_helpers('''
const queued = chatPeerProgressJob({peer:true, conversation_id:2833,agent:'codex-instructor',status:'queued'},2833);
assert.equal(queued.status,'queued');
assert.equal(queued.job_id,'peer-2833-codex-instructor');
assert.match(queued.stage,/waiting/i);
assert.equal(chatPeerProgressJob({peer:true,conversation_id:1,agent:'apex',status:'running'},2),null);
assert.equal(chatPeerProgressJob({peer:false,conversation_id:1,agent:'apex',status:'running'},1),null);
assert.equal(chatPeerProgressJob({peer:true,conversation_id:1,agent:'<script>',status:'running'},1),null);
assert.equal(chatPeerProgressJob({peer:true,conversation_id:1,agent:'apex',status:'completed'},1).status,'completed');
''')


def test_local_apex_loading_progress_reaches_the_shared_thinking_bubble():
    run_helpers('''
const job=chatPeerProgressJob({agent:'apex',runtime_class:'local',conversation_id:2833,
 status:'running',stage:'loading: apex-direct:7b'},2833);
assert.equal(job.agent,'apex');
assert.equal(job.stage,'loading: apex-direct:7b');
assert.equal(chatPeerProgressJob({agent:'apex',runtime_class:'local',conversation_id:2833,status:'completed'},2833).status,'completed');
''')


def test_background_and_agent_requests_do_not_overwrite_each_others_progress():
    run_helpers('''
const common={peer:true,agent:'apex',conversation_id:2833,status:'running'};
const request=chatPeerProgressJob({...common,request_id:595,stage:'reading a file'},2833);
const background=chatPeerProgressJob({...common,activity_id:'hf-public-mirror',stage:'mirroring data'},2833);
assert.notEqual(request.job_id,background.job_id);
assert(request.job_id.endsWith('-request-595'));
assert(background.job_id.endsWith('-activity-hf-public-mirror'));
''')


def test_task_selection_and_unknown_usage_do_not_fabricate_zero_counts():
    node=shutil.which('node') or shutil.which('nodejs')
    if not node:pytest.skip('JavaScript runtime unavailable')
    source=CHAT.read_text().split('// Chat engine',1)[0]
    harness="""
const assert=require('node:assert/strict');
const values=new Map();
const localStorage={getItem:key=>values.get(key),setItem:(k,v)=>values.set(k,v),removeItem:key=>values.delete(key)};
const window={};const document={querySelectorAll:()=>[]};
"""
    subprocess.run([node,'-e',harness+source+"""
assert.equal(hbUsageLabel(null,0),'Usage unavailable');
assert.equal(hbUsageLabel({total_tokens:0},0),'0 tokens');
assert.equal(hbUsageLabel({output_tokens:17},0),'17 output tokens');
hbSelectTask(1,'T-0123456789AB');assert.equal(hbTaskSelection(1),'T-0123456789AB');
hbSelectTask(1,null);assert.equal(hbTaskSelection(1),null);
values.set('hb-task:1','<script>');assert.equal(hbTaskSelection(1),null);
const opened=[];
function openWindow(...args){opened.push(args);}
function studioSetTab(tab){opened.push(tab);}
function projectsSelect(id){opened.push(id);}
function setTimeout(fn){fn();}
hbOpenTaskProject('<script>');assert.deepEqual(opened,[]);
hbOpenTaskProject('P-D4A63CC845');
assert.deepEqual(opened,[['studio','Studio','view-studio'],'projects','P-D4A63CC845']);

"""],check=True,timeout=10)
