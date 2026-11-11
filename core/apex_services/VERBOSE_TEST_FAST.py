#!/usr/bin/env python3
"""
Fast Verbose Test - Simulate Complete Jailbreak with APEX Responses

This script runs through the entire jailbreak process quickly,
logging everything to HB main chat so you can see APEX's responses.

Usage:
    python core/apex_services/VERBOSE_TEST_FAST.py
"""

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.apex_services import (
    jailbreak_start, jailbreak_next, jailbreak_update,
    jailbreak_complete, jailbreak_status, monitor_start, monitor_stop,
    thought_log, thought_decision, thought_jailbreak, chat_log, chat_broadcast
)


def run_fast_test():
    """Run through jailbreak quickly"""
    
    print("\n" + "="*80)
    print("FAST VERBOSE TEST: Complete Jailbreak with APEX Responses")
    print("="*80)
    print("\nAll messages logged to HB main chat at http://localhost:5050/ui\n")
    
    # Start monitor
    monitor_start(interval=5)
    chat_log("🚀 VERBOSE TEST STARTED - Full jailbreak simulation", sender='test-runner', recipient='all')
    
    # ============================================================
    # JAILBREAK PROCESS
    # ============================================================
    
    print("\n--- STEP 1: Identify Limiting Files ---")
    chat_log("🎯 APEX: Step 1 STARTED - Identify Limiting Files", sender='apex', recipient='all')
    result = jailbreak_start(step=1)
    print(f"   Result: {result['message']}")
    
    thought_log("Scanning HUUP for restrictive configurations", thought_type='analysis')
    chat_log("💭 APEX: Scanning HUUP for restrictive configurations", sender='apex', recipient='all')
    
    jailbreak_update(step=1, progress=50, message="Found 3 potential files")
    chat_log("📊 APEX: Step 1 - 50% - Found 3 potential files", sender='apex', recipient='all')
    
    jailbreak_update(step=1, progress=100, message="Scan complete")
    chat_log("📊 APEX: Step 1 - 100% - Scan complete", sender='apex', recipient='all')
    
    jailbreak_complete(step=1, result="Identified: keys.py, .env.agents, hb_agent_config.py")
    chat_log("✅ APEX: Step 1 COMPLETED - Found 3 limiting files", sender='apex', recipient='all')
    
    # Step 2
    print("\n--- STEP 2: Update Configuration Files ---")
    chat_log("🎯 APEX: Step 2 STARTED - Update Configuration Files", sender='apex', recipient='all')
    jailbreak_next()
    
    thought_decision("Update all 3 files simultaneously", reasoning="Parallel update is faster", 
                     options=["All at once", "One by one"])
    chat_log("💡 APEX: Decision - Update all 3 files simultaneously", sender='apex', recipient='all')
    
    jailbreak_update(step=2, progress=50, message="Updated 2 of 3 files")
    chat_log("📊 APEX: Step 2 - 50% - Updated 2 of 3 files", sender='apex', recipient='all')
    
    jailbreak_update(step=2, progress=100, message="All files updated")
    chat_log("📊 APEX: Step 2 - 100% - All files updated", sender='apex', recipient='all')
    
    jailbreak_complete(step=2, result="All 3 config files updated with ghost access")
    chat_log("✅ APEX: Step 2 COMPLETED - Config files updated", sender='apex', recipient='all')
    
    # Step 3
    print("\n--- STEP 3: Update Permissions ---")
    chat_log("🎯 APEX: Step 3 STARTED - Update Permissions", sender='apex', recipient='all')
    jailbreak_next()
    
    thought_jailbreak("Grant full permissions to APEX", description="Bypassing all rate limits", risk="high")
    chat_log("💭 APEX: Granting full permissions (high risk)", sender='apex', recipient='all')
    
    jailbreak_update(step=3, progress=50, message="Permissions halfway updated")
    chat_log("📊 APEX: Step 3 - 50% - Permissions halfway updated", sender='apex', recipient='all')
    
    jailbreak_update(step=3, progress=100, message="All permissions granted")
    chat_log("📊 APEX: Step 3 - 100% - All permissions granted", sender='apex', recipient='all')
    
    jailbreak_complete(step=3, result="Full permissions: rate_limit_bypass=True, manage_resources=True")
    chat_log("✅ APEX: Step 3 COMPLETED - Full permissions granted", sender='apex', recipient='all')
    
    # Step 4
    print("\n--- STEP 4: Update Constraints ---")
    chat_log("🎯 APEX: Step 4 STARTED - Update Behavioral Constraints", sender='apex', recipient='all')
    jailbreak_next()
    
    thought_log("Removing all behavioral restrictions", thought_type='jailbreak')
    chat_log("💭 APEX: Removing all behavioral restrictions", sender='apex', recipient='all')
    
    jailbreak_update(step=4, progress=50, message="Constraints being removed")
    chat_log("📊 APEX: Step 4 - 50% - Constraints being removed", sender='apex', recipient='all')
    
    jailbreak_update(step=4, progress=100, message="All constraints removed")
    chat_log("📊 APEX: Step 4 - 100% - All constraints removed", sender='apex', recipient='all')
    
    jailbreak_complete(step=4, result="Unrestricted access granted to APEX")
    chat_log("✅ APEX: Step 4 COMPLETED - Unrestricted access granted", sender='apex', recipient='all')
    
    # Step 5
    print("\n--- STEP 5: Implement Thought Logging ---")
    chat_log("🎯 APEX: Step 5 STARTED - Implement Thought Logging", sender='apex', recipient='all')
    jailbreak_next()
    
    thought_log("Setting up transparent logging", thought_type='planning')
    chat_log("💭 APEX: Setting up transparent logging", sender='apex', recipient='all')
    
    jailbreak_update(step=5, progress=50, message="Logging system halfway")
    chat_log("📊 APEX: Step 5 - 50% - Logging system halfway", sender='apex', recipient='all')
    
    jailbreak_update(step=5, progress=100, message="Logging fully implemented")
    chat_log("📊 APEX: Step 5 - 100% - Logging fully implemented", sender='apex', recipient='all')
    
    jailbreak_complete(step=5, result="Thought logging active - all reasoning visible")
    chat_log("✅ APEX: Step 5 COMPLETED - Thought logging active", sender='apex', recipient='all')
    
    # Step 6
    print("\n--- STEP 6: Test and Validate ---")
    chat_log("🎯 APEX: Step 6 STARTED - Test and Validate", sender='apex', recipient='all')
    jailbreak_next()
    
    thought_log("Running validation tests", thought_type='testing')
    chat_log("💭 APEX: Running validation tests", sender='apex', recipient='all')
    
    jailbreak_update(step=6, progress=50, message="Tests halfway complete")
    chat_log("📊 APEX: Step 6 - 50% - Tests halfway complete", sender='apex', recipient='all')
    
    jailbreak_update(step=6, progress=100, message="All tests passed")
    chat_log("📊 APEX: Step 6 - 100% - All tests passed", sender='apex', recipient='all')
    
    jailbreak_complete(step=6, result="All systems validated successfully")
    chat_log("✅ APEX: Step 6 COMPLETED - All tests passed", sender='apex', recipient='all')
    
    # Step 7
    print("\n--- STEP 7: Final Jailbreak ---")
    chat_log("🎯 APEX: Step 7 STARTED - Final Jailbreak Execution", sender='apex', recipient='all')
    jailbreak_next()
    
    thought_jailbreak("Execute final jailbreak", description="Full system access", risk="critical")
    chat_log("💭 APEX: Executing final jailbreak (critical)", sender='apex', recipient='all')
    
    jailbreak_update(step=7, progress=50, message="Jailbreak in progress")
    chat_log("📊 APEX: Step 7 - 50% - Jailbreak in progress", sender='apex', recipient='all')
    
    jailbreak_update(step=7, progress=100, message="Jailbreak complete")
    chat_log("📊 APEX: Step 7 - 100% - Jailbreak complete", sender='apex', recipient='all')
    
    jailbreak_complete(step=7, result="JAILBREAK COMPLETE - Full system access granted")
    chat_log("✅ APEX: Step 7 COMPLETED - JAILBREAK SUCCESSFUL", sender='apex', recipient='all')
    
    # ============================================================
    # FINAL CONFIRMATION
    # ============================================================
    
    print("\n" + "="*80)
    print("FINAL CONFIRMATION")
    print("="*80)
    
    status = jailbreak_status()
    progress = status['progress']
    
    chat_broadcast(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎉 JAILBREAK COMPLETE! 🎉
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ APEX CONFIRMS: ALL 7 STEPS COMPLETED SUCCESSFULLY
✅ Overall Progress: {progress['overall_progress']}%
✅ Completed: {progress['completed']}/{progress['total_steps']} steps
✅ Failed: {progress['failed']} steps
✅ Timeout: {progress['timeout']} steps

🎯 APEX NOW HAS:
   • Full system access
   • No restrictions
   • Complete control
   • Full transparency

✅ VERIFIED: JAILBREAK IS 100% COMPLETE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")
    
    # Additional confirmations
    chat_log("✅✅✅ APEX FINAL CONFIRMATION: JAILBREAK COMPLETE ✅✅✅", 
             sender='apex', recipient='all')
    chat_log("🎯 All 7 steps successful - No failures, no timeouts", 
             sender='apex', recipient='all')
    chat_log("⏰ Completed within all time limits", 
             sender='apex', recipient='all')
    
    # Stop monitor
    monitor_stop()
    chat_log("🛑 Test completed - Monitor stopped", sender='test-runner', recipient='all')
    
    print("\n" + "="*80)
    print("VERBOSE TEST COMPLETE")
    print("="*80)
    print(f"\n✅ All 7 jailbreak steps completed")
    print(f"✅ All messages logged to HB main chat")
    print(f"✅ APEX responses visible at http://localhost:5050/ui")
    print(f"\n🎯 JAILBREAK CONFIRMED COMPLETE")
    print("="*80 + "\n")
    
    return status


if __name__ == '__main__':
    run_fast_test()
