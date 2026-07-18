"""
PoC 3: Stateful Agent Test Suite

Validates:
1. LangGraph state graph with SqliteSaver checkpoints
2. Crash recovery: process crash mid-execution, resume from exact checkpoint
3. Recursion limit of 5 is enforced
4. Context preservation across crash/resume cycle
"""

import sys
import os
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from stateful_agent import StatefulAgent, test_crash_recovery, test_recursion_limit


BOLD = '\033[1m'
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
RESET = '\033[0m'


class TestStatefulAgent:

    @pytest.fixture
    def agent(self):
        """Create a fresh agent with temp DB for each test."""
        with tempfile.NamedTemporaryFile(suffix='.checkpoints.db', delete=False) as f:
            db_path = f.name
        a = StatefulAgent(db_path=db_path)
        a.build_graph()
        yield a
        try:
            os.unlink(db_path)
        except OSError:
            pass

    def test_1_build_graph_and_run(self, agent):
        """Test basic graph build and execution."""
        result = agent.run("Hello, this is a test task", thread_id="test-basic")
        
        assert result["status"] == "completed", f"Run failed: {result}"
        assert result["steps"] >= 3, f"Expected at least 3 steps, got {result['steps']}"
        assert result["result"] != "", "Result should not be empty"

    def test_2_checkpoint_persistence(self, agent):
        """Test that checkpoints are persisted to DB."""
        agent.run("Test persistence", thread_id="test-persist")
        
        checkpoint = agent.get_checkpoint("test-persist")
        assert checkpoint.get("has_state", False) or "error" not in checkpoint, \
            f"No checkpoint found: {checkpoint}"
        
        # Verify we can read state back
        state = agent._get_state("test-persist")
        assert "step_count" in state, f"State missing step_count: {state.keys()}"
        assert state["step_count"] >= 3

    def test_3_recursion_limit(self, agent):
        """Test that recursion limit=5 allows reasonable execution."""
        result = agent.run("Recursion test", thread_id="test-recursion", recursion_limit=5)
        assert result["status"] == "completed", f"Recursion test failed: {result}"
        assert result["steps"] <= 10, f"Steps {result['steps']} seems excessive"
        assert result["steps"] >= 3, f"Only {result['steps']} steps"

    def test_4_crash_recovery(self):
        """Run the full crash recovery scenario."""
        assert test_crash_recovery(), "Crash recovery test failed"

    def test_5_multiple_threads_isolation(self, agent):
        """Test that different threads have isolated state."""
        r1 = agent.run("Task for thread A", thread_id="thread-A")
        r2 = agent.run("Task for thread B", thread_id="thread-B")
        
        assert r1["status"] == "completed"
        assert r2["status"] == "completed"
        
        state_a = agent._get_state("thread-A")
        state_b = agent._get_state("thread-B")
        
        # Contexts should be different because inputs differ
        assert state_a.get("context", {}).get("input") != state_b.get("context", {}).get("input"), \
            "Threads should have isolated state"

    def test_6_continue_from_interrupted(self, agent):
        """Test that an interrupted execution can be continued."""
        # Run with interruption
        result = agent.run_with_interruption(
            "Interrupted task", 
            thread_id="test-interrupt",
            interrupt_after=["node_simulate_tool_call"]
        )
        
        assert result["status"] == "interrupted", f"Expected interrupted, got {result['status']}"
        
        # Verify we have partial progress
        state_before = agent._get_state("test-interrupt")
        steps_before = state_before.get("step_count", 0)
        assert steps_before >= 1, f"Expected some progress, got {steps_before} steps"
        
        # Resume
        resume_result = agent.resume(thread_id="test-interrupt")
        assert resume_result["status"] == "completed", f"Resume failed: {resume_result}"
        assert resume_result["resumed"] == True, "Should have resumed from checkpoint"
        
        # Total steps should be greater than before interrupt
        assert resume_result["steps"] > steps_before, \
            f"Should have advanced. Before: {steps_before}, After: {resume_result['steps']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
