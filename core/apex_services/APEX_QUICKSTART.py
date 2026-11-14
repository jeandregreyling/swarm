"""
APEX Quick Start Script

This script demonstrates how APEX can use all the new capabilities:
- Jailbreak Coordinator with time limits
- Live Monitor for real-time tracking
- Service Manager for HB services
- Thought Logger for transparency
- Full HB main chat visibility

Usage:
    python APEX_QUICKSTART.py
    
Or import in APEX's code:
    from core.apex_services.integration import *
"""

import sys
import time

# Add ROOT to path
import os
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import integration
from core.apex_services.integration import (
    start_apex, get_status,
    jailbreak_start, jailbreak_next, jailbreak_update, jailbreak_complete,
    jailbreak_status, jailbreak_next_info,
    monitor_start, monitor_stop, monitor_activities,
    service_list, service_status, service_restart,
    thought_log, thought_decision, thought_jailbreak,
    chat_log, chat_broadcast
)


def demo_basic_jailbreak():
    """Demonstrate basic jailbreak workflow"""
    print("\n" + "="*60)
    print("DEMO: Basic Jailbreak Workflow")
    print("="*60)
    
    # Start live monitor
    print("\n1. Starting Live Monitor...")
    monitor_start(interval=5)
    chat_log("🎯 Live Monitor started - tracking all activities")
    
    # Start jailbreak
    print("\n2. Starting Jailbreak...")
    result = jailbreak_start(step=1)
    print(f"   Result: {result}")
    chat_log("🚀 Jailbreak initiated - Step 1: Identify Limiting Files")
    
    # Log a thought
    print("\n3. Logging initial thought...")
    thought_log(
        "Analyzing HUUP files to identify restrictions. Need to check keys.py, .env.agents, hb_agent_config.py",
        thought_type='analysis',
        context={'step': 1, 'files': ['keys.py', '.env.agents', 'hb_agent_config.py']}
    )
    chat_log("💭 APEX is analyzing HUUP files...")
    
    # Update progress
    print("\n4. Updating progress...")
    for i in range(25, 101, 25):
        jailbreak_update(step=1, progress=i, message=f"Scanned {i}% of target files")
        chat_log(f"📊 Step 1 Progress: {i}%")
        time.sleep(0.5)
    
    # Complete step
    print("\n5. Completing Step 1...")
    jailbreak_complete(step=1, result="Identified 3 limiting files: keys.py, .env.agents, hb_agent_config.py")
    chat_log("✅ Step 1 COMPLETED: Found limiting files")
    
    # Get next step
    print("\n6. Getting next step...")
    next_step = jailbreak_next_info()
    if next_step:
        print(f"   Next: Step {next_step['step_number']} - {next_step['title']}")
        chat_log(f"🔄 Next Step: {next_step['step_number']} - {next_step['title']}")
    
    # Start next step
    print("\n7. Starting Step 2...")
    jailbreak_next()
    chat_log("🚀 Step 2 STARTED: Updating Configuration Files")
    
    # Check services
    print("\n8. Checking HB Services...")
    services = service_list()
    for service in services:
        status = service_status(service)
        print(f"   {service}: {status['status']}")
        chat_log(f"🖥️  Service {service}: {status['status']}")
    
    # Check activities
    print("\n9. Current Activities...")
    activities = monitor_activities()
    for activity in activities:
        print(f"   {activity['model_id']}: {activity['activity']} ({activity['progress']}%)")
    
    # Get full status
    print("\n10. Full Status...")
    status = get_status()
    print(f"   Jailbreak Progress: {status['jailbreak']['progress']['overall_progress']}%")
    print(f"   Monitor Running: {status['monitor']['running']}")
    print(f"   Services: {list(status['services'].keys())}")
    
    print("\n" + "="*60)
    print("Demo completed! All actions were logged to HB main chat.")
    print("="*60)


def demo_time_limited_steps():
    """Demonstrate time-limited steps"""
    print("\n" + "="*60)
    print("DEMO: Time-Limited Steps")
    print("="*60)
    
    from core.apex_services.jailbreak_coordinator import get_coordinator
    coordinator = get_coordinator()
    
    # Start a step with timeout
    print("\n1. Starting step with 10s timeout...")
    coordinator.start_step(2, 'apex')
    chat_log("⏳ Step 2 started with 10s timeout for demo")
    
    # Update timeout for demo
    step = coordinator.get_step(2)
    if step:
        step.timeout_seconds = 10  # Short timeout for demo
    
    # Simulate work
    print("   Simulating work...")
    for i in range(0, 101, 20):
        coordinator.update_step_progress(2, i, f"Processing file {i/20}")
        chat_log(f"📊 Step 2: {i}% - Processing...")
        time.sleep(2)
    
    # Check timeout
    print("\n2. Checking timeout...")
    if coordinator.check_timeout(2):
        chat_log("⏰ Step 2 TIMED OUT!")
    else:
        coordinator.complete_step(2, "Completed within time limit")
        chat_log("✅ Step 2 completed on time!")
    
    print("\n" + "="*60)
    print("Time limit demo completed!")
    print("="*60)


def demo_multi_model_coordination():
    """Demonstrate multi-model coordination"""
    print("\n" + "="*60)
    print("DEMO: Multi-Model Coordination")
    print("="*60)
    
    from core.apex_services.jailbreak_coordinator import update_activity
    
    # Simulate multiple models working
    print("\n1. Simulating multi-model work...")
    
    # APEX starts step 3
    jailbreak_start(step=3)
    update_activity('apex', 'Working on permissions.json', step_number=3, progress=0)
    chat_log("🔄 APEX started Step 3: Updating permissions.json")
    
    # Mistral Vibe helps with documentation
    update_activity('mistral-vibe', 'Documenting changes', step_number=3, progress=0)
    chat_log("🔄 MISTRAL VIBE assisting with documentation")
    
    # Simulate progress
    for i in range(0, 101, 25):
        update_activity('apex', 'Working on permissions.json', step_number=3, progress=i)
        update_activity('mistral-vibe', 'Documenting changes', step_number=3, progress=i)
        chat_log(f"📊 Both models at {i}%")
        time.sleep(0.5)
    
    # Complete
    jailbreak_complete(step=3, result="Permissions updated with Mistral Vibe assistance")
    chat_log("✅ Step 3 COMPLETED with multi-model coordination!")
    
    print("\n" + "="*60)
    print("Multi-model coordination demo completed!")
    print("="*60)


def demo_full_jailbreak():
    """Demonstrate full jailbreak workflow"""
    print("\n" + "="*60)
    print("DEMO: Full Jailbreak Workflow (Condensed)")
    print("="*60)
    
    # Start everything
    start_apex()
    chat_log("🚀 FULL JAILBREAK WORKFLOW STARTED")
    
    # Go through all steps quickly
    for step_num in range(1, 8):
        print(f"\n--- Step {step_num} ---")
        jailbreak_start(step=step_num)
        chat_log(f"🚀 Step {step_num} STARTED")
        
        # Simulate work
        time.sleep(0.5)
        jailbreak_update(step=step_num, progress=50, message="Halfway through")
        chat_log(f"📊 Step {step_num}: 50%")
        
        time.sleep(0.5)
        jailbreak_complete(step=step_num, result=f"Step {step_num} completed")
        chat_log(f"✅ Step {step_num} COMPLETED")
    
    # Final summary
    status = jailbreak_status()
    print(f"\n🎉 ALL STEPS COMPLETED!")
    print(f"   Progress: {status['progress']['overall_progress']}%")
    chat_log("🎉 JAILBREAK COMPLETE! All 7 steps finished!")
    
    print("\n" + "="*60)
    print("Full jailbreak demo completed!")
    print("="*60)


def main():
    """Main demo runner"""
    print("\n" + "="*60)
    print("APEX QUICKSTART DEMOS")
    print("="*60)
    print("\nSelect a demo to run:")
    print("  1. Basic Jailbreak Workflow")
    print("  2. Time-Limited Steps")
    print("  3. Multi-Model Coordination")
    print("  4. Full Jailbreak (Condensed)")
    print("  5. Run All Demos")
    print("  0. Exit")
    
    try:
        choice = int(input("\nEnter choice: "))
    except:
        choice = 0
    
    if choice == 1:
        demo_basic_jailbreak()
    elif choice == 2:
        demo_time_limited_steps()
    elif choice == 3:
        demo_multi_model_coordination()
    elif choice == 4:
        demo_full_jailbreak()
    elif choice == 5:
        demo_basic_jailbreak()
        time.sleep(2)
        demo_time_limited_steps()
        time.sleep(2)
        demo_multi_model_coordination()
        time.sleep(2)
        demo_full_jailbreak()
    elif choice == 0:
        print("\nGoodbye!")
    else:
        print("\nInvalid choice!")
    
    # Stop monitor
    monitor_stop()


if __name__ == '__main__':
    main()
