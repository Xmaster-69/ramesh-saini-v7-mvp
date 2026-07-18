"""
Ramesh Saini v7.1 — Ironclad MVP Backend
Agent Module — integrated from poc-agent (LangGraph + SqliteSaver)
"""
import sys, os, json, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'poc-agent', 'src'))
from stateful_agent import StatefulAgent


class AgentManager:
    """
    Wraps the LangGraph StatefulAgent for use in the MVP chat pipeline.
    Provides:
      - run_with_code_detection: runs agent, detects if output contains code
      - get_state / resume: crash recovery
    """

    def __init__(self, checkpoint_db: str = None):
        if checkpoint_db is None:
            checkpoint_db = os.environ.get('RAMESHMEM_DB', ':memory:')
        self.db_path = checkpoint_db
        self.agent = StatefulAgent(db_path=self.db_path)
        self.agent.build_graph()
        self._thread_counter = 0

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
    result = am.run("Say hello in Python", recursion_limit=3)
    print(f"Agent: {result['status']}, steps={result['steps']}")
    print(f"Output: {result['result'][:100]}")
