"""
copilot_agent.py — GitHub Copilot / Claude Integration
═══════════════════════════════════════════════════════════════════════════════
Nine is the Ghost Layer architectural agent. Direct interface to VS Code and
system-level decision making. Claude reasoning, full context awareness, code
generation, debugging, refactoring. Part of the Ghost Layer.

When Gemma routes a request to Ghost/Architecture/Code, Nine steps in.
═══════════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time

# Add paths for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
_SWARM_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

# Import from utils
from utils.database import (log_message, save_agent_memory, get_agent_memory,
                            search_memory, promote_to_verified, save_gemma_verdict)
from utils.config import NINE_SYSTEM_PROMPT

# Import from lib/system
from lib.system.logging_bridge import log_action, log_agent_thinking, batch_commit
from lib.system.system_clock import get_system_clock

# Nine (Copilot) is always available via CLI/local - uses claude-like reasoning
MODEL = 'neural:latest'  # Placeholder for Copilot/Claude when available
TEMP = 0.4  # Balanced reasoning


def nine_consult(prompt, context=''):
    """
    Direct consultation with Nine (Claude/Copilot).
    Used for architecture decisions, code generation, system analysis.
    Logs to memory and propagates to Ghost.
    
    Args:
        prompt (str): The question or request for Nine
        context (str): Optional context (conversation history, file paths, etc)
    
    Returns:
        str: Nine's verdict/response
    """
    start_time = time.time()
    timestamp = get_system_clock().timestamp_compact()
    
    full_prompt = prompt
    if context:
        full_prompt = f"{context}\n\n---\n\n{prompt}"
    
    # Log the consultation
    log_action('copilot', 'consult_start', f'Nine consulting on: {prompt[:80]}...', 'info')
    print(f'\n[{timestamp}] [Nine/Copilot] analyzing...')
    
    # Save to memory for audit trail
    memory_key = f'copilot_consult_{int(time.time())}'
    save_agent_memory('copilot', memory_key, {
        'prompt': prompt,
        'context_len': len(context),
        'timestamp': timestamp,
        'status': 'consulting'
    })
    
    try:
        # For now, this is a stub that respects the Copilot integration pattern
        # When actual Claude/Copilot API is available, response comes from there
        response = _ask_nine(full_prompt)
        
        elapsed_ms = int((time.time() - start_time) * 1000)
        log_agent_thinking('copilot', 'responded', elapsed_ms)
        
        # Promote if high-value insight
        if any(keyword in response.lower() for keyword in ['architecture', 'design', 'refactor', 'pattern']):
            promote_to_verified('copilot', memory_key, response)
        
        # Log completion
        save_agent_memory('copilot', memory_key, {
            'prompt': prompt,
            'response_len': len(response),
            'timestamp': timestamp,
            'status': 'completed',
            'elapsed_ms': elapsed_ms
        })
        
        batch_commit(f'[Nine/Copilot] completed consult (${elapsed_ms}ms)')
        return response
        
    except Exception as e:
        log_action('copilot', 'consult_error', str(e), 'error')
        raise


def _ask_nine(prompt):
    """
    Internal: Call Nine directly. Stub for Copilot/Claude API integration.
    When actual API is set up, this routes to the external agent.
    """
    # TODO: Route to actual Copilot/Claude API when available
    # For now, return architectural reasoning placeholder
    return (
        f"[Nine/Copilot Analysis]\n"
        f"Prompt analyzed: {prompt[:100]}...\n"
        f"\n"
        f"Status: Copilot API integration pending. This agent is active in Fridays\n"
        f"and ready to receive:- Architecture questions\n"
        f"- Code generation requests\n"
        f"- Debugging assistance\n"
        f"- System design reviews\n"
        f"- Refactoring guidance\n"
        f"\n"
        f"Once Copilot API is connected, this will provide full Claude reasoning"
        f" with VS Code context awareness.\n"
    )


def nine_debug(context, error_msg=''):
    """
    Nine debugs a code issue given context and optional error message.
    """
    prompt = f"Debug this issue:\nContext: {context}\n"
    if error_msg:
        prompt += f"Error: {error_msg}\n"
    return nine_consult(prompt)


def nine_refactor(code_block, goal=''):
    """
    Nine suggests refactoring for a code block.
    """
    prompt = f"Refactor this code:\n```\n{code_block}\n```\n"
    if goal:
        prompt += f"Goal: {goal}\n"
    return nine_consult(prompt)


def nine_arch_review(system_description):
    """
    Nine reviews architecture and suggests improvements.
    """
    prompt = f"Review this architecture design:\n{system_description}\nSuggest improvements."
    return nine_consult(prompt)


# Export for orchestrator
def ask_nine(prompt, retries=1):
    """Orchestrator interface for Nine."""
    try:
        return nine_consult(prompt)
    except Exception as e:
        if retries > 0:
            time.sleep(2)
            return ask_nine(prompt, retries - 1)
        raise


if __name__ == '__main__':
    # Test: python3 agents/specialists/copilot_agent.py
    test_prompt = "What is the architecture of Seven's Swarm?"
    result = nine_consult(test_prompt)
    print(result)
