# ALM enforcement wrapper for Flask endpoints
from frontend.services import _alm_gate_or_response

def enforce_alm_gate(data, action_name):
    gate = _alm_gate_or_response(data, action_name)
    if gate:
        return gate
    return None
