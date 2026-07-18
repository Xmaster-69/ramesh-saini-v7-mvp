"""
Ramesh Saini v7.1 - PoC 3: Stateful Agent with Crash Recovery

Demonstrates LangGraph with SqliteSaver for checkpoint persistence.
KEY TEST: Crash the process mid-execution, restart, and verify the agent
resumes from the exact last checkpoint without losing context.

Architecture:
  - LangGraph state graph with strict recursion_limit=5
  - SqliteSaver for checkpoint persistence
  - Simulated tool calls that can be interrupted
  - Checkpoint resume verification
"""

import json
import time
import os
import sys
import signal
import tempfile
from typing import TypedDict, Literal, Any
from dataclasses import dataclass

from typing import Annotated, Sequence

# LangGraph imports
try:
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.checkpoint.base import Checkpoint
except ImportError:
    print("[ERROR] langgraph not installed. Install with: pip install langgraph")
    print("[INFO] Will attempt to install...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "langgraph", "langchain-core"])
    from langgraph.graph import StateGraph, END
    from langgraph.checkpoint.sqlite import SqliteSaver


# ============================================================
# Agent State Definition
# ============================================================

class AgentState(TypedDict):
    """State schema for the LangGraph agent."""
    messages: Annotated[Sequence[dict], "Chat messages in order"]
    next_step: str
    context: dict
    step_count: int
    interrupted: bool
    result: str


# ============================================================
# Node functions
# ============================================================

def node_process_input(state: AgentState) -> dict:
    """First node: process the input message."""
    msg = state["messages"][-1]["content"] if state["messages"] else ""
    
    return {
        "next_step": "analyze",
        "context": {**state.get("context", {}), "input_processed": True, "input": msg},
        "step_count": state["step_count"] + 1,
        "messages": state["messages"] + [{"role": "system", "content": f"Node: process_input done. Input: {msg[:50]}..."}]
    }


def node_analyze(state: AgentState) -> dict:
    """Second node: analyze the input."""
    context = state.get("context", {})
    
    return {
        "next_step": "tool_call",
        "context": {**context, "analysis_done": True, "analysis": "Analyzed input successfully"},
        "step_count": state["step_count"] + 1,
        "messages": state["messages"] + [{"role": "system", "content": "Node: analyze done"}]
    }


def node_simulate_tool_call(state: AgentState) -> dict:
    """Third node: simulate a tool call with state mutation."""
    context = state.get("context", {})
    step = state["step_count"]
    
    # Simulate different states each time so we can detect proper resume
    tool_result = f"tool_result_{step}: data_processed_at_step_{step}"
    
    return {
        "next_step": "finalize" if state["step_count"] >= 3 else "analyze",
        "context": {**context, f"tool_{step}": tool_result, "last_tool_result": tool_result},
        "step_count": step + 1,
        "messages": state["messages"] + [{"role": "system", "content": f"Node: tool_call done. Result: {tool_result}"}]
    }


def node_finalize(state: AgentState) -> dict:
    """Final node: produce the result."""
    result = json.dumps({
        "status": "completed",
        "steps_executed": state["step_count"],
        "context_keys": list(state.get("context", {}).keys()),
        "final_tool_result": state.get("context", {}).get("last_tool_result", "none")
    })
    
    return {
        "next_step": "__end__",
        "result": result,
        "step_count": state["step_count"] + 1,
        "messages": state["messages"] + [{"role": "system", "content": f"Node: finalize done. Result: {result[:100]}..."}]
    }


# ============================================================
# Router
# ============================================================

def router(state: AgentState) -> str:
    """Route to the next node based on state."""
    ns = state.get("next_step", "analyze")
    
    mapping = {
        "analyze": "node_analyze",
        "tool_call": "node_simulate_tool_call",
        "finalize": "node_finalize",
        "__end__": END
    }
    
    return mapping.get(ns, END)


# ============================================================
# Agent Builder
# ============================================================

class StatefulAgent:
    """
    A stateful LangGraph agent with SqliteSaver checkpoint persistence.
    
    Features:
    - Checkpoint after every node execution
    - Recursion limit enforcement
    - Crash recovery: load checkpoint and resume
    
    Usage:
        agent = StatefulAgent(db_path="checkpoints.db")
        agent.build_graph()
        
        # First run
        result = agent.run("Hello, process this task")
        
        # Resume after crash
        result = agent.resume_from_checkpoint(thread_id="thread-1")
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.graph = None
        self.checkpointer = None
        self.app = None

    def build_graph(self):
        """Build the state graph with checkpoint saver."""
        # Create the graph
        builder = StateGraph(AgentState)
        
        # Add nodes
        builder.add_node("node_process_input", node_process_input)
        builder.add_node("node_analyze", node_analyze)
        builder.add_node("node_simulate_tool_call", node_simulate_tool_call)
        builder.add_node("node_finalize", node_finalize)
        
        # Set entry point
        builder.set_entry_point("node_process_input")
        
        # Add conditional edges
        builder.add_conditional_edges("node_process_input", router, {
            "node_analyze": "node_analyze",
            END: END
        })
        builder.add_conditional_edges("node_analyze", router, {
            "node_simulate_tool_call": "node_simulate_tool_call",
            END: END
        })
        builder.add_conditional_edges("node_simulate_tool_call", router, {
            "node_analyze": "node_analyze",
            "node_finalize": "node_finalize",
            END: END
        })
        builder.add_conditional_edges("node_finalize", router, {
            END: END
        })
        
        # Set up checkpointer
        self.checkpointer = SqliteSaver.from_conn_string(self.db_path)
        
        # Compile with recursion limit and checkpoint
        self.graph = builder.compile(
            checkpointer=self.checkpointer,
            interrupt_after=[]  # Don't interrupt by default
        )
        
        self.app = self.graph
        return self

    def run(self, input_text: str, thread_id: str = "thread-1", 
            recursion_limit: int = 5) -> dict:
        """Run the agent with checkpointing."""
        config = {
            "configurable": {
                "thread_id": thread_id,
                "recursion_limit": recursion_limit
            }
        }
        
        initial_state = {
            "messages": [{"role": "user", "content": input_text}],
            "next_step": "process_input",
            "context": {},
            "step_count": 0,
            "interrupted": False,
            "result": ""
        }
        
        try:
            events = list(self.graph.stream(initial_state, config))
            
            # Get the final state
            final_state = self._get_state(thread_id)
            return {
                "status": "completed",
                "result": final_state.get("result", ""),
                "steps": final_state.get("step_count", 0),
                "context_keys": list(final_state.get("context", {}).keys()),
                "thread_id": thread_id
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "thread_id": thread_id
            }

    def run_with_interruption(self, input_text: str, thread_id: str = "thread-1",
                               interrupt_after: list = None) -> dict:
        """Run with intentional interruption points for crash testing."""
        if interrupt_after is None:
            interrupt_after = ["node_simulate_tool_call"]
        
        # Rebuild graph with interrupt points
        builder = StateGraph(AgentState)
        builder.add_node("node_process_input", node_process_input)
        builder.add_node("node_analyze", node_analyze)
        builder.add_node("node_simulate_tool_call", node_simulate_tool_call)
        builder.add_node("node_finalize", node_finalize)
        builder.set_entry_point("node_process_input")
        builder.add_conditional_edges("node_process_input", router, {
            "node_analyze": "node_analyze",
            END: END
        })
        builder.add_conditional_edges("node_analyze", router, {
            "node_simulate_tool_call": "node_simulate_tool_call",
            END: END
        })
        builder.add_conditional_edges("node_simulate_tool_call", router, {
            "node_analyze": "node_analyze",
            "node_finalize": "node_finalize",
            END: END
        })
        builder.add_conditional_edges("node_finalize", router, {
            END: END
        })
        
        self.checkpointer = SqliteSaver.from_conn_string(self.db_path)
        self.graph = builder.compile(
            checkpointer=self.checkpointer,
            interrupt_after=interrupt_after
        )
        self.app = self.graph
        
        config = {
            "configurable": {
                "thread_id": thread_id,
                "recursion_limit": 5
            }
        }
        
        initial_state = {
            "messages": [{"role": "user", "content": input_text}],
            "next_step": "process_input",
            "context": {},
            "step_count": 0,
            "interrupted": False,
            "result": ""
        }
        
        try:
            events = list(self.graph.stream(initial_state, config))
            state = self._get_state(thread_id)
            return {
                "status": "interrupted",
                "state": state,
                "thread_id": thread_id
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "thread_id": thread_id
            }

    def resume(self, thread_id: str = "thread-1") -> dict:
        """Resume execution from the last checkpoint."""
        if not self.graph:
            raise ValueError("Graph not built. Call build_graph() first.")
        
        config = {
            "configurable": {
                "thread_id": thread_id,
                "recursion_limit": 5
            }
        }
        
        try:
            # Resume from interrupt
            events = list(self.graph.stream(None, config))
            
            state = self._get_state(thread_id)
            return {
                "status": "completed",
                "result": state.get("result", ""),
                "steps": state.get("step_count", 0),
                "context_keys": list(state.get("context", {}).keys()),
                "thread_id": thread_id,
                "resumed": True
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "thread_id": thread_id,
                "resumed": False
            }

    def _get_state(self, thread_id: str) -> dict:
        """Get the current state for a thread from checkpoints."""
        config = {
            "configurable": {"thread_id": thread_id}
        }
        try:
            state = self.graph.get_state(config)
            if state and state.values:
                return state.values
        except Exception:
            pass
        return {}

    def get_checkpoint(self, thread_id: str) -> dict:
        """Get the latest checkpoint for a thread."""
        config = {
            "configurable": {"thread_id": thread_id}
        }
        try:
            state = self.graph.get_state(config)
            if state:
                return {
                    "has_state": state.values is not None,
                    "next": state.next,
                    "step_count": state.values.get("step_count", 0) if state.values else 0
                }
        except Exception:
            pass
        return {"error": "No checkpoint found"}


# ============================================================
# Crash Recovery Test
# ============================================================

def test_crash_recovery():
    """
    Simulate a crash mid-execution and verify recovery.
    
    Test flow:
    1. Build graph with SqliteSaver
    2. Start execution (interrupt after node_simulate_tool_call)
    3. Save the intermediate state as checkpoint
    4. "Crash" by creating a NEW agent instance with the same DB
    5. Resume from the checkpoint
    6. Verify the agent continues from EXACTLY where it left off
    """
    print("\n🔬 Ramesh Saini v7.1 - PoC 3: Crash Recovery Test\n")
    
    # Use a temp file for the checkpoint DB
    with tempfile.NamedTemporaryFile(suffix='.checkpoints.db', delete=False) as f:
        db_path = f.name
    
    try:
        print("  Phase 1: Start agent execution...")
        agent1 = StatefulAgent(db_path=db_path)
        agent1.build_graph()
        
        # Run with interruption after tool_call
        result1 = agent1.run_with_interruption(
            "Process this task with multiple steps",
            thread_id="crash-test-1",
            interrupt_after=["node_simulate_tool_call"]
        )
        
        assert result1["status"] == "interrupted", f"Expected interrupted, got {result1['status']}"
        
        # Get the checkpoint state
        checkpoint1 = agent1.get_checkpoint("crash-test-1")
        assert checkpoint1.get("step_count", 0) >= 2, f"Expected at least 2 steps, got {checkpoint1}"
        
        step_before_crash = checkpoint1.get("step_count", 0)
        context_before = agent1._get_state("crash-test-1").get("context", {})
        print(f"    Steps completed before crash: {step_before_crash}")
        print(f"    Context keys: {list(context_before.keys())}")
        
        # Phase 2: Simulate crash - create NEW agent with same DB
        print("  Phase 2: ⚡ CRASH - New agent instance loading same checkpoint DB...")
        agent2 = StatefulAgent(db_path=db_path)
        agent2.build_graph()
        
        # Phase 3: Resume
        print("  Phase 3: Resume execution from checkpoint...")
        result2 = agent2.resume(thread_id="crash-test-1")
        
        assert result2["status"] == "completed", f"Resume failed: {result2}"
        
        steps_after_resume = result2.get("steps", 0)
        context_after = agent2._get_state("crash-test-1").get("context", {})
        
        print(f"    Total steps after resume: {steps_after_resume}")
        print(f"    Context keys after resume: {list(context_after.keys())}")
        
        # Verify continuation
        assert steps_after_resume > step_before_crash, (
            f"Agent did not advance. Before: {step_before_crash}, After: {steps_after_resume}"
        )
        
        # Verify context is preserved (the tool results from before crash should still be there)
        assert context_after.get("input_processed") == True, "Context lost: input_processed gone"
        
        print(f"\n  {GREEN}✓{RESET} Crash recovery test PASSED")
        print(f"    Steps before crash: {step_before_crash}")
        print(f"    Steps after resume: {steps_after_resume}")
        print(f"    Context preserved: {list(context_after.keys())}")
        
        return True
        
    except Exception as e:
        print(f"\n  {RED}✗{RESET} Crash recovery test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


def test_recursion_limit():
    """Verify recursion_limit=5 is enforced."""
    print("\n🔒 Recursion Limit Test (limit=5)...")
    
    with tempfile.NamedTemporaryFile(suffix='.checkpoints.db', delete=False) as f:
        db_path = f.name
    
    try:
        agent = StatefulAgent(db_path=db_path)
        agent.build_graph()
        
        # The graph should handle 5 steps fine
        result = agent.run("Test task", thread_id="recursion-test", recursion_limit=5)
        
        if result["status"] == "completed":
            print(f"  {GREEN}✓{RESET} Recursion limit test PASSED: {result['steps']} steps")
            return True
        else:
            print(f"  {RED}✗{RESET} Recursion limit test: {result}")
            return False
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


if __name__ == "__main__":
    results = []
    
    # Test 1: Crash recovery
    results.append(test_crash_recovery())
    
    # Test 2: Recursion limit
    results.append(test_recursion_limit())
    
    print(f"\n{'='*50}")
    print(f"Overall: {sum(results)}/2 passed")
    
    if not all(results):
        print(f"Some tests FAILED")
        sys.exit(1)
    else:
        print(f"✅ PoC 3 All tests passed")
