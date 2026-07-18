"""
PoC 2: Unified Memory Test Suite

Validates:
1. Single SQLite DB handles relational + vector + JSONB
2. Bulk insert of 10,000 conversations + vectors
3. Hybrid search (SQL filter + Vector similarity) < 100ms
4. User preferences CRUD via JSONB
"""

import sys
import os
import time
import json
import tempfile
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
from unified_memory_store import UnifiedMemoryStore, ChatMessage


BOLD = '\033[1m'
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'


class TestUnifiedMemoryStore:

    @pytest.fixture(autouse=True)
    def setup(self):
        """Create a fresh in-memory store for each test."""
        self.store = UnifiedMemoryStore(":memory:").connect()
        yield
        self.store.close()

    def test_1_relational_chat_messages(self):
        """Test basic relational CRUD for chat messages."""
        # Insert messages
        mid1 = self.store.insert_message("session-A", "user", "Hello from test")
        mid2 = self.store.insert_message("session-A", "assistant", "Hi there!")
        mid3 = self.store.insert_message("session-B", "user", "Another session")
        
        assert mid1 > 0
        assert mid2 > mid1
        
        # Retrieve by session
        msgs_a = self.store.get_session_messages("session-A")
        assert len(msgs_a) == 2
        assert msgs_a[0]["role"] == "user"
        assert msgs_a[0]["session_id"] == "session-A"
        
        msgs_b = self.store.get_session_messages("session-B")
        assert len(msgs_b) == 1
        
        # Stats
        stats = self.store.get_stats()
        assert stats["messages"] == 3
        assert stats["embeddings"] == 3

    def test_2_vector_embeddings_storage(self):
        """Test that embeddings are created and stored for every message."""
        self.store.insert_message("session-V", "user", "How do I install Python?")
        self.store.insert_message("session-V", "assistant", "Use pyenv or download from python.org")
        
        # Check embeddings exist
        cursor = self.store.conn.cursor()
        tables = ["chat_embeddings", "chat_embeddings_fallback"]
        found = False
        for tbl in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {tbl}")
                cnt = cursor.fetchone()[0]
                if cnt > 0:
                    found = True
                    break
            except Exception:
                continue
        
        assert found, "No embeddings found in any storage table"
        assert self.store.get_stats()["embeddings"] == 2

    def test_3_jsonb_user_preferences(self):
        """Test JSONB user preference storage."""
        # Set preferences
        prefs = {"theme": "dark", "language": "hi-IN", "notifications": True, "model": "ramesh-v7.1"}
        self.store.set_preference("user-rama", prefs)
        
        # Read back
        retrieved = self.store.get_preference("user-rama")
        assert retrieved["theme"] == "dark"
        assert retrieved["language"] == "hi-IN"
        
        # Update
        self.store.set_preference("user-rama", {"theme": "light"})
        retrieved2 = self.store.get_preference("user-rama")
        assert retrieved2["theme"] == "light"  # Updated
        assert retrieved2["language"] == "hi-IN"  # Preserved (merged by application logic)
        
        # Non-existent user
        empty = self.store.get_preference("nobody")
        assert empty == {}

    def test_4_hybrid_search_sql_filter(self):
        """Test hybrid search with SQL session filter."""
        # Insert messages across sessions
        self.store.insert_message("session-X", "user", "I need to reset my password")
        self.store.insert_message("session-X", "assistant", "Go to account settings and click reset password")
        self.store.insert_message("session-Y", "user", "What's the capital of France?")
        self.store.insert_message("session-Y", "assistant", "Paris is the capital of France")
        self.store.insert_message("session-X", "user", "Where do I find account settings?")
        self.store.insert_message("session-Y", "user", "Tell me about French cuisine")
        
        # Search without filter (should return across all sessions)
        results_all = self.store.hybrid_search("password reset", limit=5)
        assert len(results_all) >= 2  # At least the password-related ones
        assert any("password" in r.content.lower() for r in results_all)
        
        # Search with session filter
        results_x = self.store.hybrid_search("password reset", session_filter="session-X", limit=5)
        assert len(results_x) >= 2  # From session-X
        for r in results_x:
            assert r.session_id == "session-X"
        
        # Search session-Y
        results_y = self.store.hybrid_search("France", session_filter="session-Y", limit=5)
        assert len(results_y) >= 2
        for r in results_y:
            assert r.session_id == "session-Y"

    def test_5_bulk_insert_10k_and_benchmark(self):
        """TEST: Insert 10,000 messages and benchmark hybrid search."""
        # Generate 10,000 conversations
        sessions = [f"bench-session-{i}" for i in range(100)]
        topics = [
            "password reset", "how to install software", "weather forecast",
            "API documentation", "machine learning", "deployment guide",
            "error handling", "database migration", "user authentication",
            "payment integration"
        ]
        
        print(f"\n  Inserting 10,000 messages...", end=" ", flush=True)
        insert_start = time.time()
        
        count = 0
        for i in range(10000):
            session = sessions[i % len(sessions)]
            role = "user" if i % 2 == 0 else "assistant"
            content = f"Message {i}: {topics[i % len(topics)]} - {'Question' if role == 'user' else 'Answer'} about topic"
            msg = ChatMessage(session_id=session, role=role, content=content)
            self.store.insert_message(msg.session_id, msg.role, msg.content)
            count += 1
        
        insert_time = time.time() - insert_start
        print(f"Done in {insert_time:.2f}s")
        
        # Verify count
        stats = self.store.get_stats()
        assert stats["messages"] == 10000, f"Expected 10000, got {stats['messages']}"
        
        # Benchmark hybrid search
        print(f"  Running hybrid search benchmark...", end=" ", flush=True)
        
        queries = [
            "password reset instructions",
            "install software guide",
            "machine learning tutorial",
            "API documentation example",
            "deployment error fix"
        ]
        
        search_times = []
        for q in queries:
            # Without filter
            t0 = time.time()
            results = self.store.hybrid_search(q, limit=5)
            t = (time.time() - t0) * 1000  # ms
            search_times.append(t)
            assert len(results) > 0, f"Search for '{q}' returned no results"
        
        avg_search_time = sum(search_times) / len(search_times)
        max_search_time = max(search_times)
        
        print(f"Avg: {avg_search_time:.2f}ms, Max: {max_search_time:.2f}ms")
        
        # CI Assertion: query time < 100ms
        assert avg_search_time < 100, (
            f"Average hybrid search time {avg_search_time:.2f}ms exceeds 100ms limit"
        )
        
        print(f"  {GREEN}✓{RESET} Avg search {avg_search_time:.2f}ms < 100ms: PASS")

    def test_6_single_db_backend(self):
        """Verify all three data types live in ONE database."""
        # All operations use the same connection/DB
        self.store.insert_message("unified", "user", "test")
        self.store.set_preference("unified-user", {"test": True})
        
        # Use disk-based DB to verify single file
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            store2 = UnifiedMemoryStore(db_path).connect()
            store2.insert_message("verify", "user", "single file DB")
            store2.set_preference("verify-user", {"test": "single_db"})
            
            stats = store2.get_stats()
            assert stats["messages"] == 1
            assert stats["user_preferences"] == 1
            
            store2.close()
            
            # Verify single file
            assert os.path.exists(db_path)
            assert os.path.getsize(db_path) > 0
            
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
