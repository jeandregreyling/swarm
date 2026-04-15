"""
{{TOOL_NAME}} — Custom Swarm Skill ({{DESCRIPTION}})
Built by {{AGENT}} on {{DATE}}

Register in REGISTRY and _HANDLERS in fridays/skills.py to activate.
"""


def handle(args, agent, **_):
    """
    SKILL {{TOOL_NAME}} <args>
    {{DESCRIPTION}}
    """
    text = (args or '').strip()
    if not text:
        return False, 'Usage: SKILL {{TOOL_NAME}} <args>'

    # TODO: implement skill logic here
    result = f'{{TOOL_NAME}} processed: {text}'
    return True, result
