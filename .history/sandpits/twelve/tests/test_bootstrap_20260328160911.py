#!/usr/bin/env python3
"""
Agent Twelve Bootstrap Tests
Verify that Agent Twelve is properly registered and all infrastructure exists.
Test run: DECISION-001
"""

import sqlite3
import os
from datetime import datetime
from pathlib import Path

def test_agent_twelve_registered():
    """Test: Agent Twelve exists in agents registry"""
    conn = sqlite3.connect('/home/seven/swarm/swarm_memory.db')
    c = conn.cursor()
    c.execute("SELECT id, name, model, role FROM agents WHERE name='twelve'")
    result = c.fetchone()
    conn.close()
    
    assert result is not None, "Agent Twelve not found in registry"
    assert result[1] == 'twelve', f"Expected name 'twelve', got '{result[1]}'"
    assert result[2] == 'claude-haiku', f"Expected model 'claude-haiku', got '{result[2]}'"
    print(f"✓ Agent Twelve registered (id={result[0]})")
    return True

def test_memory_twelve_table():
    """Test: memory_twelve table exists and is writable"""
    conn = sqlite3.connect('/home/seven/swarm/swarm_memory.db')
    c = conn.cursor()
    
    # Verify table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='memory_twelve'")
    result = c.fetchone()
    assert result is not None, "memory_twelve table not found"
    
    # Verify it's writable
    c.execute("""
        INSERT INTO memory_twelve (agent, content, importance, type, tags)
        VALUES (?, ?, ?, ?, ?)
    """, ('twelve', 'Bootstrap test entry', 9, 'system', 'bootstrap'))
    conn.commit()
    
    # Verify read back
    c.execute("SELECT COUNT(*) FROM memory_twelve WHERE agent='twelve'")
    count = c.fetchone()[0]
    assert count >= 1, f"Expected at least 1 entry, got {count}"
    
    conn.close()
    print(f"✓ memory_twelve table exists and is writable ({count} entries)")
    return True

def test_decisions_table():
    """Test: decisions table exists and schema is correct"""
    conn = sqlite3.connect('/home/seven/swarm/swarm_memory.db')
    c = conn.cursor()
    
    # Verify table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='decisions'")
    result = c.fetchone()
    assert result is not None, "decisions table not found"
    
    # Verify schema
    c.execute("PRAGMA table_info(decisions)")
    columns = {col[1]: col[2] for col in c.fetchall()}
    required = ['decision_id', 'timestamp', 'agent', 'component', 'proposal_file', 
                'decision', 'reasoning', 'test_status', 'commit_hash']
    for col in required:
        assert col in columns, f"Missing column: {col}"
    
    # Test insertion
    c.execute("""
        INSERT INTO decisions (agent, component, proposal_file, decision, reasoning, test_status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, ('twelve', 'bootstrap', 'DECISION-001-create-agent-twelve.md', 
          'Create Agent Twelve', 'Bootstrap test', 'PENDING'))
    conn.commit()
    
    c.execute("SELECT decision_id FROM decisions WHERE agent='twelve' ORDER BY decision_id DESC LIMIT 1")
    decision_id = c.fetchone()[0]
    
    conn.close()
    print(f"✓ decisions table exists and writable (test decision_id={decision_id})")
    return True

def test_time_machine_table():
    """Test: time_machine table exists"""
    conn = sqlite3.connect('/home/seven/swarm/swarm_memory.db')
    c = conn.cursor()
    
    # Verify table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='time_machine'")
    result = c.fetchone()
    assert result is not None, "time_machine table not found"
    
    # Verify schema
    c.execute("PRAGMA table_info(time_machine)")
    columns = {col[1]: col[2] for col in c.fetchall()}
    required = ['checkpoint_id', 'timestamp', 'agent', 'file_path', 
                'before_code', 'after_code', 'decision_id', 'commit_hash']
    for col in required:
        assert col in columns, f"Missing column: {col}"
    
    conn.close()
    print(f"✓ time_machine table exists with correct schema")
    return True

def test_daily_checkpoint_table():
    """Test: daily_checkpoint table exists"""
    conn = sqlite3.connect('/home/seven/swarm/swarm_memory.db')
    c = conn.cursor()
    
    # Verify table exists
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='daily_checkpoint'")
    result = c.fetchone()
    assert result is not None, "daily_checkpoint table not found"
    
    conn.close()
    print(f"✓ daily_checkpoint table exists")
    return True

def test_sandpit_structure():
    """Test: sandpits/twelve/ directory structure is complete"""
    basepath = Path('/home/seven/swarm/sandpits/twelve')
    required_dirs = ['proposals', 'logs', 'tests', 'working', 'archive']
    
    assert basepath.exists(), f"sandpits/twelve not found at {basepath}"
    
    for dirname in required_dirs:
        dirpath = basepath / dirname
        assert dirpath.exists() and dirpath.is_dir(), f"Missing directory: {dirpath}"
    
    print(f"✓ sandpits/twelve/ structure complete ({len(required_dirs)} directories)")
    return True

def test_proposal_file_exists():
    """Test: DECISION-001 proposal file exists"""
    proposal_path = Path('/home/seven/swarm/sandpits/twelve/proposals/DECISION-001-create-agent-twelve.md')
    assert proposal_path.exists(), f"Proposal file not found at {proposal_path}"
    
    content = proposal_path.read_text()
    assert 'DECISION-001' in content, "Proposal doesn't contain DECISION-001 marker"
    assert 'Agent Twelve' in content, "Proposal doesn't mention Agent Twelve"
    
    print(f"✓ DECISION-001 proposal file exists and is valid")
    return True

def run_all_tests():
    """Run all bootstrap tests"""
    tests = [
        test_agent_twelve_registered,
        test_memory_twelve_table,
        test_decisions_table,
        test_time_machine_table,
        test_daily_checkpoint_table,
        test_sandpit_structure,
        test_proposal_file_exists,
    ]
    
    print("\n" + "="*60)
    print("AGENT TWELVE BOOTSTRAP TESTS")
    print("="*60 + "\n")
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__}: {type(e).__name__}: {e}")
            failed += 1
    
    print("\n" + "="*60)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("="*60 + "\n")
    
    return failed == 0

if __name__ == '__main__':
    success = run_all_tests()
    exit(0 if success else 1)
