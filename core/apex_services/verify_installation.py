#!/usr/bin/env python3
"""
Verification Script for APEX Services Installation

Run this to verify everything is properly installed and working.

Usage:
    python verify_installation.py
"""

import sys
import os

# Add ROOT to path
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def test_imports():
    """Test that all modules can be imported"""
    print("📦 Testing imports...")
    
    try:
        import core.apex_services
        # Test individual imports
        from core.apex_services.jailbreak_coordinator import start_jailbreak
        from core.apex_services.live_monitor import start_monitor
        from core.apex_services.service_manager import list_services
        from core.apex_services.thought_logger import log_thought
        from core.apex_services.integration import get_integration
        print("   ✅ All imports successful")
        return True
    except Exception as e:
        print(f"   ❌ Import failed: {e}")
        return False


def test_jailbreak_coordinator():
    """Test jailbreak coordinator"""
    print("\n🎯 Testing Jailbreak Coordinator...")
    
    try:
        from core.apex_services.jailbreak_coordinator import (
            get_coordinator, start_jailbreak, get_progress, get_next_step
        )
        
        coordinator = get_coordinator()
        progress = get_progress()
        next_step = get_next_step()
        
        print(f"   ✅ Coordinator loaded")
        print(f"   ✅ Progress: {progress['overall_progress']}%")
        print(f"   ✅ Total steps: {progress['total_steps']}")
        if next_step:
            print(f"   ✅ Next step: {next_step['step_number']} - {next_step['title']}")
        return True
    except Exception as e:
        print(f"   ❌ Jailbreak coordinator failed: {e}")
        return False


def test_live_monitor():
    """Test live monitor"""
    print("\n👁️  Testing Live Monitor...")
    
    try:
        from core.apex_services.live_monitor import get_monitor, start_monitor, stop_monitor
        
        monitor = get_monitor()
        print(f"   ✅ Monitor loaded")
        print(f"   ✅ Running: {monitor._running}")
        return True
    except Exception as e:
        print(f"   ❌ Live monitor failed: {e}")
        return False


def test_service_manager():
    """Test service manager"""
    print("\n🖥️  Testing Service Manager...")
    
    try:
        from core.apex_services.service_manager import list_services, get_service_status
        
        services = list_services()
        print(f"   ✅ Service manager loaded")
        print(f"   ✅ Found {len(services)} services: {services}")
        
        for service in services:
            status = get_service_status(service)
            print(f"      - {service}: {status['status']}")
        
        return True
    except Exception as e:
        print(f"   ❌ Service manager failed: {e}")
        return False


def test_thought_logger():
    """Test thought logger"""
    print("\n💭 Testing Thought Logger...")
    
    try:
        from core.apex_services.thought_logger import log_thought, get_thoughts
        
        # Log a test thought
        result = log_thought("Test thought for verification", thought_type='test')
        
        # Get recent thoughts
        thoughts = get_thoughts(limit=1)
        
        print(f"   ✅ Thought logger loaded")
        print(f"   ✅ Logged test thought: {result.get('ok', result.get('success', False))}")
        print(f"   ✅ Recent thoughts: {len(thoughts)}")
        return True
    except Exception as e:
        print(f"   ❌ Thought logger failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test integration module"""
    print("\n🔧 Testing Integration Module...")
    
    try:
        from core.apex_services.integration import get_integration, get_status
        
        integration = get_integration()
        status = get_status()
        
        print(f"   ✅ Integration module loaded")
        print(f"   ✅ Has jailbreak: {hasattr(integration, 'jailbreak')}")
        print(f"   ✅ Has monitor: {hasattr(integration, 'monitor')}")
        print(f"   ✅ Has services: {hasattr(integration, 'services')}")
        print(f"   ✅ Has thoughts: {hasattr(integration, 'thoughts')}")
        print(f"   ✅ Has chat: {hasattr(integration, 'chat')}")
        return True
    except Exception as e:
        print(f"   ❌ Integration module failed: {e}")
        return False


def test_database():
    """Test database connectivity"""
    print("\n🗃️  Testing Database...")
    
    try:
        import sqlite3
        import os
        
        db_path = os.path.join(ROOT, 'swarm_memory.db')
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check required tables (some are created on first use)
        tables = [
            'messages',
            'peer_messages',
        ]
        
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            print(f"   ✅ Table '{table}': {count} rows")
        
        # Try optional tables
        optional_tables = ['apex_jailbreak_coordinator', 'apex_model_activities', 'apex_thoughts', 'service_trace']
        for table in optional_tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"   ✅ Table '{table}': {count} rows")
            except:
                print(f"   ℹ️  Table '{table}': Not created yet (created on first use)")
        
        # Try to create missing tables by using the modules
        try:
            from core.apex_services.jailbreak_coordinator import get_coordinator
            get_coordinator()
            print("   ✅ Jailbreak coordinator tables created")
        except:
            pass
        
        try:
            from core.apex_services.live_monitor import get_monitor
            get_monitor()
            print("   ✅ Live monitor tables created")
        except:
            pass
        
        conn.close()
        return True
    except Exception as e:
        print(f"   ❌ Database test failed: {e}")
        return False


def test_file_existence():
    """Test that all required files exist"""
    print("\n📁 Testing File Existence...")
    
    files = [
        'core/apex_services/__init__.py',
        'core/apex_services/jailbreak_coordinator.py',
        'core/apex_services/live_monitor.py',
        'core/apex_services/service_manager.py',
        'core/apex_services/thought_logger.py',
        'core/apex_services/integration.py',
        'core/apex_services/APEX_QUICKSTART.py',
        'core/apex_services/README.md'
    ]
    
    all_exist = True
    for file in files:
        full_path = os.path.join(ROOT, file)
        exists = os.path.exists(full_path)
        size = os.path.getsize(full_path) if exists else 0
        status = "✅" if exists else "❌"
        print(f"   {status} {file}: {size} bytes")
        if not exists:
            all_exist = False
    
    return all_exist


def main():
    """Run all tests"""
    print("="*70)
    print("APEX SERVICES VERIFICATION")
    print("="*70)
    
    tests = [
        ("Imports", test_imports),
        ("File Existence", test_file_existence),
        ("Database", test_database),
        ("Jailbreak Coordinator", test_jailbreak_coordinator),
        ("Live Monitor", test_live_monitor),
        ("Service Manager", test_service_manager),
        ("Thought Logger", test_thought_logger),
        ("Integration Module", test_integration),
    ]
    
    results = {}
    for name, test_func in tests:
        results[name] = test_func()
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    passed = sum(1 for r in results.values() if r)
    total = len(results)
    
    for name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status}: {name}")
    
    print(f"\n📊 {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! APEX is ready to use.")
        print("\n🚀 NEXT STEPS:")
        print("   1. APEX can now import: from core.apex_services import *")
        print("   2. Start with: start_apex()")
        print("   3. Then: jailbreak_start()")
        print("   4. And: monitor_start(5)")
        print("\n💡 See README.md for full documentation")
        print("\n👁️  All actions will be visible at http://localhost:5050/ui")
    else:
        print("\n⚠️  SOME TESTS FAILED. Please check the errors above.")
    
    print("="*70)


if __name__ == '__main__':
    main()
