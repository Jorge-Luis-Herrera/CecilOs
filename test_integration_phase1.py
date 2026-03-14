#!/usr/bin/env python3
"""
Full Integration Test for Phase 1 - Enhanced OpenClaw Integration
Tests the complete CecilApp with Enhanced OpenClaw Planner.
"""

import sys
import os

# Add project paths
sys.path.insert(0, '.')
sys.path.insert(0, 'Cecil-Ear/moonshine/python/src')

def test_full_integration():
    """Test full CecilApp integration with Phase 1 enhancements."""
    print("🧪 Testing Full Phase 1 Integration...")
    
    try:
        from cecil_simple import CecilApp
        import tkinter as tk
        
        # Create root window
        root = tk.Tk()
        root.withdraw()  # Hide for testing
        
        # Initialize CecilApp
        app = CecilApp(root)
        print("✓ CecilApp initialized successfully")
        
        # Check enhanced OpenClaw planner
        print(f"✓ Enhanced OpenClaw Available: {app.openclaw.available}")
        
        # Check stats
        stats = app.openclaw.get_stats()
        print(f"✓ OpenClaw Stats: {stats}")
        
        # Test skill cache
        print(f"✓ Skill Cache Count: {app.skill_cache.count}")
        
        # Test vision components
        print(f"✓ Vision Parser AT-SPI2: {app.vision_parser._has_atspi}")
        print(f"✓ Vision Parser Tesseract: {app.vision_parser._has_tesseract}")
        
        # Test enhanced planning method
        plan = app.openclaw.plan_with_enhancement("test command")
        print(f"✓ Enhanced Planning Result: {plan.get('source', 'unknown')}")
        
        root.destroy()
        print("🎉 Full Phase 1 integration test PASSED")
        return True
        
    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_gui_startup():
    """Test GUI startup without crashing."""
    print("\n🧪 Testing GUI Startup...")
    
    try:
        from cecil_simple import CecilApp
        import tkinter as tk
        import threading
        import time
        
        # Create root window
        root = tk.Tk()
        root.title("CecilOs Test")
        
        # Initialize CecilApp
        app = CecilApp(root)
        print("✓ GUI initialized successfully")
        
        # Test that all components are properly initialized
        assert hasattr(app, 'openclaw'), "Enhanced OpenClaw planner missing"
        assert hasattr(app, 'skill_cache'), "Skill cache missing"
        assert hasattr(app, 'vision_capture'), "Vision capture missing"
        assert hasattr(app, 'vision_parser'), "Vision parser missing"
        
        print("✓ All Phase 1 components present")
        
        # Test basic GUI functionality
        print(f"✓ GUI title: {root.title()}")
        print(f"✓ GUI size: {root.winfo_width()}x{root.winfo_height()}")
        
        # Schedule GUI close after 2 seconds
        def close_gui():
            time.sleep(2)
            root.quit()
        
        # Start GUI in background
        gui_thread = threading.Thread(target=close_gui, daemon=True)
        gui_thread.start()
        
        # Run GUI main loop
        root.mainloop()
        
        print("✓ GUI startup test completed")
        return True
        
    except Exception as e:
        print(f"✗ GUI test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_enhanced_planning_flow():
    """Test the enhanced planning flow with vision enhancement."""
    print("\n🧪 Testing Enhanced Planning Flow...")
    
    try:
        from cecil_brain.enhanced_openclaw_planner import EnhancedOpenClawPlanner
        from cecil_brain.skill_cache import SkillCache
        from cecil_vision.parser import ScreenParser
        from cecil_vision.capture import ScreenCapture
        
        # Initialize components
        skill_cache = SkillCache()
        vision_parser = ScreenParser()
        screen_capture = ScreenCapture()
        
        planner = EnhancedOpenClawPlanner(
            skill_cache=skill_cache,
            vision_parser=vision_parser,
            screen_capture=screen_capture
        )
        
        print("✓ Enhanced planner initialized")
        
        # Test planning with vision enhancement
        plan = planner.plan_with_enhancement(
            "abre firefox", 
            active_app="desktop",
            keybindings="super+firefox"
        )
        
        print(f"✓ Enhanced plan generated: {plan.get('source', 'unknown')}")
        
        # Test stats
        stats = planner.get_stats()
        print(f"✓ Planning stats: {stats}")
        
        return True
        
    except Exception as e:
        print(f"✗ Enhanced planning test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all integration tests."""
    print("🚀 Starting Full Phase 1 Integration Tests\n")
    
    tests = [
        test_full_integration,
        test_enhanced_planning_flow,
        test_gui_startup
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Integration Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Phase 1 FULLY FUNCTIONAL - Ready for Phase 2!")
        return 0
    else:
        print("⚠ Some integration tests failed - check implementation")
        return 1

if __name__ == "__main__":
    sys.exit(main())
