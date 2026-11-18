"""Practice 165 (owner 18 Nov 2026): the routing block before a main-chat APEX turn used 'closing' without importing it, so HB's review and
model choice never ran in main chat ("APEX model routing failed ... NameError: name 'closing' is not defined")."""


def test_practice_165_routing_block_imports_closing():
    src = open('frontend/blueprints/chat.py').read()
    block = src[src.index('# Practice 153: HB puts the model'):src.index("_LOG.exception('APEX model routing failed")]
    assert 'from contextlib import closing' in block and 'hb_apex_swap.route_for' in block
