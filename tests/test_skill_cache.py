#!/usr/bin/env python3
"""
Test suite for Skill Cache (Layer 0.5) integration.

Tests:
  1. Basic skill creation and caching
  2. Cache hit/miss detection
  3. Success/failure metrics tracking
  4. Semantic step conversion (intent → action)
  5. Cache persistence (SQLite)
"""

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from cecil_brain.skill_cache import (
    SkillCache,
    CachedSkill,
    SemanticStep,
)

def test_skill_creation():
    """Test 1: Create and save a basic skill."""
    print("=" * 60)
    print("TEST 1: Skill Creation & Caching")
    print("=" * 60)
    
    cache = SkillCache()
    print(f"✓ Cache initialized (count: {cache.count})")
    
    # Create a semantic skill: "Abre Firefox"
    skill = CachedSkill(
        id="skill_001_open_firefox",
        command="abre firefox",
        command_embedding=[0.1] * 384,  # Dummy embedding
        steps=[
            SemanticStep(
                intent="launch_app",
                target="firefox",
            ),
        ],
        app_context="desktop",
        success_count=0,
        failure_count=0,
        last_executed=None,
        last_validated=None,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        composite=False,
    )
    
    cache.save(skill)
    print(f"✓ Skill 'abre firefox' saved")
    print(f"  - ID: {skill.id}")
    print(f"  - Steps: {len(skill.steps)}")
    print(f"  - Success rate: {skill.success_rate:.0%}")
    print(f"  - Cache count: {cache.count}")
    return cache


def test_cache_query(cache: SkillCache):
    """Test 2: Query cache and verify matching."""
    print("\n" + "=" * 60)
    print("TEST 2: Cache Query & Matching (Keyword-based)")
    print("=" * 60)
    print("NOTE: Current implementation uses keyword matching (no embeddings yet).")
    print("      Threshold parameter reserved for future embedding-based similarity.")
    
    # List all skills in cache
    all_skills = cache.list_skills()
    print(f"\nCache contents: {len(all_skills)} skills")
    for skill in all_skills:
        print(f"  - {skill.id}: '{skill.command}' (success_rate: {skill.success_rate:.0%})")
    
    # Query with any threshold (keyword-based matching ignores threshold for now)
    result = cache.query("abre firefox", threshold=0.85)
    
    if result:
        print(f"\n✓ Cache HIT: '{result.command}'")
        print(f"  - Keywords matched: 'abre' and 'firefox'")
        print(f"  - Success rate: {result.success_rate:.0%}")
    else:
        print(f"\n✗ Cache MISS: No matching keywords found")
    
    # Query with non-matching command
    result2 = cache.query("something completely different", threshold=0.85)
    if result2 is None:
        print(f"✓ Cache MISS (expected): No keywords match")
    
    return result


def test_metrics_tracking(cache: SkillCache, skill_id: str):
    """Test 3: Record success and failure metrics."""
    print("\n" + "=" * 60)
    print("TEST 3: Metrics Tracking (Success/Failure)")
    print("=" * 60)
    
    skill_before = cache.query("abre firefox", threshold=0.0)
    print(f"Before: success_count={skill_before.success_count}, failure_count={skill_before.failure_count}")
    
    # Simulate 3 successful executions
    for i in range(3):
        cache.record_success(skill_id)
        print(f"  → Recorded success #{i+1}")
    
    skill_after = cache.query("abre firefox", threshold=0.0)
    print(f"After:  success_count={skill_after.success_count}, failure_count={skill_after.failure_count}")
    print(f"  ✓ Success rate: {skill_after.success_rate:.0%}")
    
    # Simulate 1 failure
    cache.record_failure(skill_id)
    print(f"  → Recorded failure #1")
    
    skill_final = cache.query("abre firefox", threshold=0.0)
    print(f"Final:  success_count={skill_final.success_count}, failure_count={skill_final.failure_count}")
    print(f"  ✓ Success rate: {skill_final.success_rate:.0%}")


def test_semantic_steps():
    """Test 4: Semantic step types and conversion."""
    print("\n" + "=" * 60)
    print("TEST 4: Semantic Step Types")
    print("=" * 60)
    
    steps = [
        SemanticStep(intent="launch_app", target="firefox"),
        SemanticStep(intent="type_text", text="github.com"),
        SemanticStep(intent="key_press", key="Return"),
        SemanticStep(intent="pause", text="2.0"),
        SemanticStep(intent="click_button", target="Search", fallback="ctrl+f"),
    ]
    
    for i, step in enumerate(steps, 1):
        print(f"\nStep {i}: {step.intent}")
        if step.target:
            print(f"  - Target: {step.target}")
        if step.text:
            print(f"  - Text/delay: {step.text}")
        if step.key:
            print(f"  - Key: {step.key}")
        if step.fallback:
            print(f"  - Fallback: {step.fallback}")


def test_cache_persistence():
    """Test 5: Verify cache persists across instances."""
    print("\n" + "=" * 60)
    print("TEST 5: Cache Persistence (SQLite)")
    print("=" * 60)
    
    # Create cache 1, add skill
    cache1 = SkillCache()
    print(f"Cache 1 created: {cache1.count} skills")
    
    skill = CachedSkill(
        id="skill_002_persistent",
        command="test persistence",
        command_embedding=[0.5] * 384,
        steps=[SemanticStep(intent="key_press", key="Escape")],
        app_context="test",
        success_count=2,
        failure_count=0,
        last_executed=None,
        last_validated=None,
        created_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        composite=False,
    )
    cache1.save(skill)
    print(f"✓ Skill saved in Cache 1: {cache1.count} skills")
    
    # Create cache 2 (new instance), verify skill is still there
    cache2 = SkillCache()
    print(f"\nCache 2 created (new instance): {cache2.count} skills")
    
    retrieved = cache2.query("test persistence", threshold=0.0)
    if retrieved:
        print(f"✓ Skill PERSISTED across instances!")
        print(f"  - Command: {retrieved.command}")
        print(f"  - Success count: {retrieved.success_count}")
    else:
        print(f"✗ Skill NOT persisted")


if __name__ == "__main__":
    print("\n🧪 CecilOs Skill Cache Test Suite")
    print("Layer 0.5 — Semantic Plan Caching\n")
    
    # Run tests
    cache = test_skill_creation()
    skill = test_cache_query(cache)
    
    if skill:
        test_metrics_tracking(cache, skill.id)
    
    test_semantic_steps()
    test_cache_persistence()
    
    print("\n" + "=" * 60)
    print("✓ All tests completed!")
    print("=" * 60)
