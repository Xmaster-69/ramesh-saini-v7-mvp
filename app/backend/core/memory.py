"""
Ramesh Saini v7.1 — Ironclad MVP Backend
Core Memory Module — integrated from poc-memory
"""
import sys, os, json, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..', 'poc-memory', 'src'))
from unified_memory_store import UnifiedMemoryStore


class MemoryManager:
    """Singleton memory store for chat context + vector search + preferences."""

    def __init__(self, db_path=None):
        if db_path is None:
            db_path = os.environ.get('RAMESHMEM_DB', ':memory:')
        self.db_path = db_path
        self.store = UnifiedMemoryStore(db_path).connect()
        self._loaded = False

    def store_message(self, session_id: str, role: str, content: str, metadata: dict = None):
        msg_id = self.store.insert_message(session_id, role, content, metadata or {})
        return msg_id

    def get_context(self, session_id: str, limit: int = 20) -> list:
        msgs = self.store.get_session_messages(session_id, limit=limit)
        return [{'role': m['role'], 'content': m['content']} for m in msgs]

    def hybrid_search(self, query: str, session_id: str = None, limit: int = 5) -> list:
        results = self.store.hybrid_search(query, session_filter=session_id, limit=limit)
        return [{'message_id': r.message_id, 'content': r.content, 'distance': r.distance, 'session_id': r.session_id} for r in results]

    def set_preference(self, user_id: str, prefs: dict):
        self.store.set_preference(user_id, prefs)

    def get_preference(self, user_id: str) -> dict:
        return self.store.get_preference(user_id)

    def close(self):
        if self.store:
            self.store.close()


if __name__ == '__main__':
    mm = MemoryManager()
    mm.store_message('test-session', 'user', 'Hello, Ramesh v7.1 MVP!')
    print(f"Stored. Context: {len(mm.get_context('test-session'))} messages")
    mm.close()
