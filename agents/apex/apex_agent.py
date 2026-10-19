"""agents/apex/apex_agent.py: Apex, the local worker. Same engine as Fred, own name, memory and sandpit."""
from agents.fred.fred_agent import chat as _worker_chat

AGENT_NAME = 'apex'


def chat(message, conversation_history=None, stage_cb=None):
    return _worker_chat(message, conversation_history, stage_cb, agent_name=AGENT_NAME)
