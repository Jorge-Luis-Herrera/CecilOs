#!/usr/bin/env python3
"""
Test script for Phase 1: OpenClaw Enhancement
Tests EnhancedOpenClawPlanner, Vision Enhancement Bridge, and MCP Bridge.
"""

import sys
import os

# Add project paths
sys.path.insert(0, '.')
sys.path.insert(0, 'Cecil-Ear/moonshine/python/src')

def test_imports():
    """Test all Phase 1 component imports."""
    print("🧪 Testing Phase 1 Imports...")
    
    try:
        from cecil_brain.enhanced_openclaw_planner import EnhancedOpenClawPlanner, VisionEnhancementBridge, SkillCacheBridge
        print("✓ EnhancedOpenClawPlanner components imported")
        
        from cecil_brain.mcp_bridge import MCPBridge, MCPTool, MCPToolRegistry
        print("✓ MCPBridge components imported")
        
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False

def test_mcp_bridge():
    """Test MCP Bridge functionality."""
    print("\n🧪 Testing MCP Bridge...")
    
    try:
        from cecil_brain.mcp_bridge import MCPBridge
        
        mcp = MCPBridge()
        print(f"✓ MCPBridge initialized - Available: {mcp.is_available()}")
        
        if mcp.is_available():
            tools = mcp.discover_tools()
            print(f"✓ Discovered {len(tools)} tools")
            
            # Test tool search
            browser_tools = mcp.search_tools("browser")
            print(f"✓ Found {len(browser_tools)} browser-related tools")
            
            # Test stats
            stats = mcp.get_stats()
            print(f"✓ MCP Stats: {stats}")
        else:
            print("⚠ OpenClaw not available - MCP bridge limited")
        
        return True
    except Exception as e:
        print(f"✗ MCP Bridge test failed: {e}")
        return False

def test_vision_enhancement():
    """Test Vision Enhancement Bridge."""
    print("\n🧪 Testing Vision Enhancement Bridge...")
    
    try:
        from cecil_brain.enhanced_openclaw_planner import VisionEnhancementBridge
        from cecil_vision.parser import ScreenParser
        from cecil_vision.capture import ScreenCapture
        
        # Initialize components
        vision_parser = ScreenParser()
        screen_capture = ScreenCapture()
        vision_bridge = VisionEnhancementBridge(vision_parser, screen_capture)
        
        print("✓ Vision Enhancement Bridge initialized")
        
        # Test screen parsing (without actual screenshot)
        context = vision_bridge.parse_screen_for_openclaw()
        print(f"✓ Generated context: {len(context)} characters")
        
        return True
    except Exception as e:
        print(f"✗ Vision Enhancement test failed: {e}")
        return False

def test_skill_cache_bridge():
    """Test Skill Cache Bridge."""
    print("\n🧪 Testing Skill Cache Bridge...")
    
    try:
        from cecil_brain.enhanced_openclaw_planner import SkillCacheBridge
        from cecil_brain.skill_cache import SkillCache
        
        # Initialize components
        skill_cache = SkillCache()
        cache_bridge = SkillCacheBridge(skill_cache)
        
        print("✓ Skill Cache Bridge initialized")
        
        # Test cache query (should return None for non-existent command)
        result = cache_bridge.query_cache_for_openclaw("test command")
        print(f"✓ Cache query result: {result}")
        
        return True
    except Exception as e:
        print(f"✗ Skill Cache Bridge test failed: {e}")
        return False

def test_enhanced_planner():
    """Test Enhanced OpenClaw Planner."""
    print("\n🧪 Testing Enhanced OpenClaw Planner...")
    
    try:
        from cecil_brain.enhanced_openclaw_planner import EnhancedOpenClawPlanner
        from cecil_brain.skill_cache import SkillCache
        from cecil_vision.parser import ScreenParser
        from cecil_vision.capture import ScreenCapture
        
        # Initialize dependencies
        skill_cache = SkillCache()
        vision_parser = ScreenParser()
        screen_capture = ScreenCapture()
        
        # Initialize enhanced planner
        planner = EnhancedOpenClawPlanner(
            skill_cache=skill_cache,
            vision_parser=vision_parser,
            screen_capture=screen_capture
        )
        
        print(f"✓ Enhanced OpenClaw Planner initialized - Available: {planner.available}")
        
        # Test planning (will fail if OpenClaw not available, but should not crash)
        plan = planner.plan_with_enhancement("test command")
        print(f"✓ Planning result: {plan.get('source', 'unknown')}")
        
        # Test stats
        stats = planner.get_stats()
        print(f"✓ Planner stats: {stats}")
        
        return True
    except Exception as e:
        print(f"✗ Enhanced Planner test failed: {e}")
        return False

def main():
    """Run all Phase 1 tests."""
    print("🚀 Starting Phase 1: OpenClaw Enhancement Tests\n")
    
    tests = [
        test_imports,
        test_mcp_bridge,
        test_vision_enhancement,
        test_skill_cache_bridge,
        test_enhanced_planner
    ]
    
    passed = 0
    total = len(tests)
    
    for test in tests:
        if test():
            passed += 1
    
    print(f"\n📊 Test Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 Phase 1 implementation complete and functional!")
        return 0
    else:
        print("⚠ Some tests failed - check implementation")
        return 1

if __name__ == "__main__":
    sys.exit(main())
