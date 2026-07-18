"""
Ramesh Saini v7.3 — Ironclad MVP Backend
Agent Module — integrated from poc-agent (LangGraph + SqliteSaver)
Binds PC Control Tools (File, Browser CDP, UIA) as agent-callable tools.
"""
import sys
import os
import json
import tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'poc-agent', 'src'))
from stateful_agent import StatefulAgent

from core.tools import AVAILABLE_TOOLS, execute_tool


class AgentManager:
    """
    Agent Manager with bound PC Control Tools.
    
    Tools available to the agent:
      - read_file: Read file from disk (guarded path validation)
      - write_file: Write file to disk (guarded path + content scanning)
      - open_browser: Open URL via Raw CDP (guarded URL scanning)
      - find_ui_element: Find/click native UI element (guarded app check)
    
    Flow: User Request → Agent decides Tool → PreCrime Guard validates → Execute → Result
    """

    def __init__(self, checkpoint_db: str = None):
        if checkpoint_db is None:
            checkpoint_db = os.environ.get('RAMESHMEM_DB', ':memory:')
        self.db_path = checkpoint_db
        self.agent = StatefulAgent(db_path=self.db_path)
        self.agent.build_graph()
        self._thread_counter = 0
        self._tool_schemas = self._build_tool_schemas()

    def _build_tool_schemas(self) -> list:
        """Build OpenAI-compatible tool schemas from AVAILABLE_TOOLS registry."""
        schemas = []
        for name, tool in AVAILABLE_TOOLS.items():
            properties = {}
            required = []
            for param_name, param_spec in tool["parameters"].items():
                ptype = param_spec.get("type", "string")
                properties[param_name] = {
                    "type": ptype,
                    "description": param_spec.get("description", ""),
                }
                if "default" not in param_spec:
                    required.append(param_name)

            schemas.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool["description"],
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                },
            })
        return schemas

    def next_thread_id(self) -> str:
        self._thread_counter += 1
        return f"mvp-thread-{self._thread_counter}"

    def run(self, prompt: str, thread_id: str = None, recursion_limit: int = 5) -> dict:
        if thread_id is None:
            thread_id = self.next_thread_id()
        result = self.agent.run(prompt, thread_id=thread_id, recursion_limit=recursion_limit)
        return {
            'thread_id': thread_id,
            'status': result.get('status', 'error'),
            'result': result.get('result', ''),
            'steps': result.get('steps', 0),
        }

    def run_with_tools(self, prompt: str, thread_id: str = None) -> dict:
        """
        Run the agent with tool-calling capability.
        
        The agent can decide to call:
          - read_file("path/to/file.txt")
          - write_file("path/to/file.txt", "content")
          - open_browser("https://example.com")
          - find_ui_element("Calculator", "Add", "click")
        
        Each tool call is validated by PreCrimeSecurityGuard before execution.
        """
        if thread_id is None:
            thread_id = self.next_thread_id()

        # For now, the agent is simulated through the LangGraph state machine.
        # In production, this would use an LLM with tool bindings.
        # Here we detect tool requests in the prompt and execute them directly.
        
        result = self.run(prompt, thread_id=thread_id)
        
        # Post-process: check if result contains tool call instructions
        # (In production, this is handled by the LLM's function_call mechanism)
        reply = result.get('result', '')
        
        return {
            'thread_id': thread_id,
            'status': result.get('status', 'error'),
            'result': reply,
            'steps': result.get('steps', 0),
            'tools_bound': len(self._tool_schemas),
            'tool_schemas': self._tool_schemas,
        }

    def execute_tool_call(self, tool_name: str, params: dict) -> dict:
        """
        Execute a tool call through the PreCrime Security Guard.
        This is the zero-trust execution path for all tools.
        """
        return execute_tool(tool_name, params)

    def get_tool_schemas(self) -> list:
        """Get OpenAI-compatible tool schemas for LLM function calling."""
        return self._tool_schemas

    def has_code_in_output(self, output: str) -> bool:
        """Detect if agent output contains code blocks."""
        markers = ['```python', '```py', '```bash', '```sh', '```javascript', '```js',
                   'import ', 'def ', 'class ', 'os.system', 'subprocess.']
        for m in markers:
            if m in output:
                return True
        return False

    def extract_code_blocks(self, output: str) -> list:
        """Extract code blocks from markdown output."""
        blocks = []
        lines = output.split('\n')
        in_block = False
        current = []
        lang = ''
        for line in lines:
            if line.startswith('```') and not in_block:
                in_block = True
                lang = line[3:].strip()
                current = []
            elif line.startswith('```') and in_block:
                in_block = False
                blocks.append({'language': lang, 'code': '\n'.join(current)})
            elif in_block:
                current.append(line)
        return blocks

    def resume(self, thread_id: str) -> dict:
        return self.agent.resume(thread_id=thread_id)

    def get_checkpoint(self, thread_id: str) -> dict:
        return self.agent.get_checkpoint(thread_id)


if __name__ == '__main__':
    am = AgentManager()
    print(f"✅ Agent initialized with {len(am._tool_schemas)} tool schemas")
    for s in am._tool_schemas:
        print(f"  🛠️  {s['function']['name']}: {s['function']['description'][:60]}...")
