"""Practice 280 (JD 22 Nov: "why HB live has a tag at the end that says 'powersave' and doesn't tell me anything it does and doesn't allow me
to select overclock or any other mode like Auto"): the GPU mode buttons on HB Live. Auto (stock) and Overclock run JD's own root helper
(/usr/local/sbin/hb-gpu-profile, Practice 271) through core/hb_agent_tools.gpu_profile_tool, in the background: the helper watches the
temperatures and reverts by itself, which takes longer than a click should wait. The result is posted in main chat."""
import threading

MODES = {'stock': ('Auto (stock)', {'action': 'reset'}), 'jd_tested': ('Overclock', {'action': 'apply', 'profile': 'jd_tested'})}


def _post(line):
    from contextlib import closing
    from utils.db._connection import get_connection
    with closing(get_connection()) as conn, conn:
        conn.execute("INSERT INTO messages(conversation_id,from_agent,to_agent,content,message_type,tokens_used) VALUES (2845,'hummingbird','user',?,'response',0)",
                     (line,))


def switch_gpu(name, start=None, tool=None, post=None):
    if name not in MODES:
        raise ValueError('GPU mode is stock or jd_tested')
    label, args = MODES[name]

    def work():
        try:
            if tool is None:
                from core.hb_agent_tools import gpu_profile_tool
                (gpu_profile_tool)(dict(args))
            else:
                tool(dict(args))
        except Exception as exc:          # the tool posts its own result; a refusal before that is posted here
            (post or _post)(f'🖥 GPU {label}: NOT applied - {exc}'[:400])
    (start or (lambda f: threading.Thread(target=f, daemon=True).start()))(work)
    return f'GPU: switching to {label}. HB posts the result in main chat.'


def gpu_mode(gpu):
    """'jd_tested' when the card runs JD's tested limits (2600 MHz core limit, 249 W cap), else 'stock'."""
    gpu = gpu or {}
    return 'jd_tested' if (gpu.get('clock_limit_mhz') or 0) >= 2600 and (gpu.get('power_cap_w') or 0) >= 249 else 'stock'
