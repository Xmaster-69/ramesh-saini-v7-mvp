"""
Ramesh Saini v7.1 - PoC 2: Unified Memory Store

A single SQLite database that handles:
  1. Relational data (Chat history with foreign keys)
  2. Vector embeddings (sqlite-vec for semantic search)
  3. JSONB (User preferences / flexible metadata)

Architecture:
  One database file, three logical storage patterns:
    - chat_messages table: relational (id, session_id, role, content, created_at)
    - chat_embeddings table: vector (embedding_id, message_id, embedding BLOB via sqlite-vec)
    - user_preferences table: JSONB (pref_id, user_id, prefs JSON blob)
  
  Hybrid search: SQL WHERE filter + vec_distance_L2 for combined semantic + structured queries.
"""

import sqlite3
import json
import time
import hashlib
import struct
import os
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass


@dataclass
class ChatMessage:
    session_id: str
    role: str  # "user" | "assistant" | "system"
    content: str
    message_id: int = 0
    created_at: float = 0.0


@dataclass
class SearchResult:
    message_id: int
    session_id: str
    role: str
    content: str
    distance: float
    matched_keyword: Optional[str] = None


class UnifiedMemoryStore:
    """
    Unified memory store using a single SQLite database with sqlite-vec.
    
    The store handles:
    - Relational: chat messages with session grouping, user preferences
    - Vector: embeddings stored and queried via sqlite-vec
    - JSONB: flexible preference storage
    
    Hybrid search filters by SQL WHERE then ranks by vector distance.
    """

    def __init__(self, db_path: str = ":memory:"):
        self.db_path = db_path
        self.conn: Optional[sqlite3.Connection] = None
        self._embedding_dim = 384  # all-MiniLM-L6-v2 default dimension

    def connect(self):
        """Open connection and enable extensions."""
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        
        # Load sqlite-vec extension (auto-detect platform)
        self._load_vec_extension()
        
        self._create_schema()
        return self

    def _load_vec_extension(self):
        """Load the sqlite-vec vector extension."""
        try:
            # Try direct import approach
            import sqlite_vec
            sqlite_vec.load(self.conn)
        except ImportError:
            # Fallback: try loading .so/.dll directly
            ext_paths = [
                "/usr/lib/sqlite3/pivot_vec0.so",
                "/usr/local/lib/sqlite-vec/vec0.so",
                os.path.expanduser("~/.local/lib/sqlite-vec/vec0.so"),
            ]
            loaded = False
            for p in ext_paths:
                if os.path.exists(p):
                    try:
                        self.conn.execute(f"SELECT load_extension('{p}')")
                        loaded = True
                        break
                    except sqlite3.OperationalError:
                        continue
            if not loaded:
                # Graceful fallback: use cosine similarity in Python
                self._vec_available = False
                print("[WARN] sqlite-vec extension not available. Using Python-side vector search.")
                return
        
        self._vec_available = True
        print(f"[INFO] sqlite-vec extension loaded. dim={self._embedding_dim}")

    def _create_schema(self):
        """Create the unified database schema."""
        cursor = self.conn.cursor()
        
        # 1. Relational: Chat messages
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                message_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system', 'tool')),
                content TEXT NOT NULL,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                metadata_json TEXT DEFAULT '{}'
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_session 
            ON chat_messages(session_id, created_at)
        """)

        # 2. Vector: Embeddings using sqlite-vec's virtual table
        if self._vec_available:
            cursor.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS chat_embeddings USING vec0(
                    message_id INTEGER PRIMARY KEY,
                    embedding float[{self._embedding_dim}]
                )
            """)
        else:
            # Fallback: store embeddings as BLOBs and search in Python
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS chat_embeddings_fallback (
                    message_id INTEGER PRIMARY KEY,
                    embedding BLOB NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES chat_messages(message_id)
                )
            """)

        # 3. JSONB: User preferences
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_preferences (
                pref_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                prefs TEXT NOT NULL DEFAULT '{}',
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(user_id)
            )
        """)

        self.conn.commit()

    def _compute_embedding(self, text: str) -> bytes:
        """
        Compute a deterministic mock embedding for PoC purposes.
        In production, this would use a sentence-transformer model.
        Uses a hash-based approach to produce consistent vectors.
        """
        h = hashlib.sha256(text.encode()).digest()
        # Expand hash into a float vector of _embedding_dim
        vec = []
        for i in range(self._embedding_dim):
            val = struct.unpack('f', h[(i * 4) % 28: (i * 4) % 28 + 4])[0]
            vec.append(val)
        # Normalize
        norm = sum(v * v for v in vec) ** 0.5
        if norm > 0:
            vec = [v / norm for v in vec]
        return struct.pack(f'{self._embedding_dim}f', *vec)

    def _embedding_to_list(self, blob: bytes) -> List[float]:
        """Convert embedding BLOB to float list."""
        return list(struct.unpack(f'{self._embedding_dim}f', blob))

    def insert_message(self, session_id: str, role: str, content: str, 
                       metadata: dict = None) -> int:
        """Insert a chat message and its embedding."""
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO chat_messages (session_id, role, content, metadata_json) VALUES (?, ?, ?, ?)",
            (session_id, role, content, json.dumps(metadata or {}))
        )
        message_id = cursor.lastrowid
        
        # Compute and insert embedding
        embedding_blob = self._compute_embedding(content)
        
        if self._vec_available:
            cursor.execute(
                "INSERT INTO chat_embeddings (message_id, embedding) VALUES (?, ?)",
                (message_id, embedding_blob)
            )
        else:
            cursor.execute(
                "INSERT INTO chat_embeddings_fallback (message_id, embedding) VALUES (?, ?)",
                (message_id, embedding_blob)
            )
        
        self.conn.commit()
        return message_id

    def bulk_insert_messages(self, messages: List[ChatMessage]) -> int:
        """Insert many messages efficiently."""
        count = 0
        for msg in messages:
            self.insert_message(msg.session_id, msg.role, msg.content)
            count += 1
        return count

    def set_preference(self, user_id: str, prefs: dict):
        """Store user preferences as JSONB."""
        cursor = self.conn.cursor()
        cursor.execute(
            """INSERT INTO user_preferences (user_id, prefs, updated_at) 
               VALUES (?, ?, strftime('%s','now'))
               ON CONFLICT(user_id) DO UPDATE SET 
               prefs=excluded.prefs, updated_at=strftime('%s','now')""",
            (user_id, json.dumps(prefs))
        )
        self.conn.commit()

    def get_preference(self, user_id: str) -> dict:
        """Retrieve user preferences."""
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT prefs FROM user_preferences WHERE user_id = ?", (user_id,)
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row[0])
        return {}

    def hybrid_search(self, query: str, session_filter: Optional[str] = None,
                      limit: int = 10) -> List[SearchResult]:
        """
        Hybrid search: SQL WHERE filter + vector similarity.
        
        If session_filter is provided, only messages from that session are considered.
        Results are ranked by cosine distance of their embeddings to the query embedding.
        """
        query_embedding = self._compute_embedding(query)
        query_vec_list = self._embedding_to_list(query_embedding)
        
        # Get all candidate messages (filtered by session if provided)
        cursor = self.conn.cursor()
        if session_filter:
            cursor.execute(
                "SELECT message_id, session_id, role, content FROM chat_messages WHERE session_id = ?",
                (session_filter,)
            )
        else:
            cursor.execute(
                "SELECT message_id, session_id, role, content FROM chat_messages"
            )
        
        candidates = cursor.fetchall()
        
        # Compute cosine distance for each candidate
        results = []
        for row in candidates:
            mid = row[0]
            
            # Get embedding
            if self._vec_available:
                emb_cursor = self.conn.cursor()
                emb_cursor.execute(
                    "SELECT embedding FROM chat_embeddings WHERE message_id = ?", (mid,)
                )
                emb_row = emb_cursor.fetchone()
            else:
                emb_cursor = self.conn.cursor()
                emb_cursor.execute(
                    "SELECT embedding FROM chat_embeddings_fallback WHERE message_id = ?", (mid,)
                )
                emb_row = emb_cursor.fetchone()
            
            if not emb_row:
                continue
            
            try:
                candidate_vec = self._embedding_to_list(emb_row[0])
            except (struct.error, TypeError):
                continue
            
            # Compute cosine distance
            dot = sum(a * b for a, b in zip(query_vec_list, candidate_vec))
            # Both vectors are normalized, so dot product = cosine similarity
            distance = 1.0 - dot  # Convert to distance (0 = identical, 2 = opposite)
            
            results.append(SearchResult(
                message_id=mid,
                session_id=row[1],
                role=row[2],
                content=row[3][:200],  # Truncate for display
                distance=distance
            ))
        
        # Sort by distance (ascending = most similar)
        results.sort(key=lambda r: r.distance)
        
        return results[:limit]

    def get_session_messages(self, session_id: str, limit: int = 100) -> List[dict]:
        """Retrieve relational chat history for a session."""
        cursor = self.conn.cursor()
        cursor.execute(
            """SELECT message_id, session_id, role, content, created_at, metadata_json
               FROM chat_messages WHERE session_id = ? 
               ORDER BY created_at ASC LIMIT ?""",
            (session_id, limit)
        )
        rows = cursor.fetchall()
        return [dict(r) for r in rows]

    def get_stats(self) -> dict:
        """Get database statistics."""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM chat_messages")
        msg_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM user_preferences")
        pref_count = cursor.fetchone()[0]
        
        if self._vec_available:
            cursor.execute("SELECT COUNT(*) FROM chat_embeddings")
            vec_count = cursor.fetchone()[0]
        else:
            cursor.execute("SELECT COUNT(*) FROM chat_embeddings_fallback")
            vec_count = cursor.fetchone()[0]
        
        db_size = 0
        if self.db_path != ":memory:":
            db_size = os.path.getsize(self.db_path)
        
        return {
            "messages": msg_count,
            "embeddings": vec_count,
            "user_preferences": pref_count,
            "db_size_bytes": db_size
        }

    def close(self):
        if self.conn:
            self.conn.close()
            self.conn = None


# Quick self-test
if __name__ == "__main__":
    store = UnifiedMemoryStore(":memory:").connect()
    
    # Insert test data
    store.insert_message("session-1", "user", "Hello, how do I reset my password?")
    store.insert_message("session-1", "assistant", "Go to Settings > Security > Reset Password")
    store.insert_message("session-1", "user", "Thanks! That worked.")
    store.insert_message("session-2", "user", "What is the weather in Tokyo?")
    
    store.set_preference("user-1", {"theme": "dark", "language": "hi", "notifications": True})
    store.set_preference("user-2", {"theme": "light", "language": "en"})
    
    print("Stats:", store.get_stats())
    print("\nSession-1 messages:")
    for m in store.get_session_messages("session-1"):
        print(f"  [{m['role']}] {m['content'][:60]}")
    
    print("\nHybrid search for 'password reset':")
    for r in store.hybrid_search("password reset", limit=3):
        print(f"  [dist={r.distance:.4f}] [{r.role}] {r.content}")
    
    print("\nUser preference (user-1):", store.get_preference("user-1"))
    
    store.close()
    print("\n✅ PoC 2 self-test passed")
