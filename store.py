import json
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from agent import chunks

DB_PATH = Path(__file__).resolve().parent / "data" / "ragbee.db"
CONFIG_PATH = Path(__file__).resolve().parent / "data" / "config.json"
ABOUT_PATH = Path(__file__).resolve().parent / "data" / "about.md"
ABOUT_COLLECTION_NAME = "About RAGbee"


def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(DB_PATH))
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    return c


_REQUIRED = {"collections", "chunks", "threads", "messages", "meta"}


def init_db():
    if DB_PATH.exists():
        with _conn() as c:
            existing = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        if not _REQUIRED.issubset(existing):
            print(f"[ragbee] Database missing tables {sorted(_REQUIRED - existing)}; recreating.")
            DB_PATH.unlink()
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS collections (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY,
                collection_id TEXT NOT NULL,
                source TEXT NOT NULL,
                text TEXT NOT NULL,
                embedding TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS threads (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                collection_id TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE SET NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (thread_id) REFERENCES threads(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );
        """)


def _now():
    return datetime.utcnow().isoformat() + "Z"


def _row(row):
    return dict(row) if row else None


# ── Collections ─────────────────────────────────────────────
def list_collections():
    with _conn() as c:
        rows = c.execute("""
            SELECT c.id, c.name, c.created_at,
                   COUNT(ch.id) AS chunk_count
            FROM collections c
            LEFT JOIN chunks ch ON ch.collection_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def create_collection(name):
    cid = uuid.uuid4().hex
    with _conn() as c:
        c.execute("INSERT INTO collections (id, name, created_at) VALUES (?, ?, ?)",
                  (cid, name, _now()))
    return cid


def delete_collection(cid):
    with _conn() as c:
        c.execute("DELETE FROM collections WHERE id = ?", (cid,))


def get_collection(cid):
    with _conn() as c:
        return _row(c.execute("SELECT * FROM collections WHERE id = ?", (cid,)).fetchone())


# ── Chunks ──────────────────────────────────────────────────
def list_chunks(collection_id):
    with _conn() as c:
        rows = c.execute(
            "SELECT id, collection_id, source, text, embedding, created_at "
            "FROM chunks WHERE collection_id = ? ORDER BY created_at",
            (collection_id,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["embedding"] = json.loads(d["embedding"])
        out.append(d)
    return out


def add_chunk(collection_id, source, text, embedding):
    ckid = uuid.uuid4().hex
    with _conn() as c:
        c.execute(
            "INSERT INTO chunks (id, collection_id, source, text, embedding, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (ckid, collection_id, source, text, json.dumps(embedding), _now()),
        )
    return ckid


def delete_chunk(ckid):
    with _conn() as c:
        c.execute("DELETE FROM chunks WHERE id = ?", (ckid,))


# ── Threads ─────────────────────────────────────────────────
def list_threads():
    with _conn() as c:
        rows = c.execute("""
            SELECT t.id, t.title, t.collection_id, t.created_at,
                   col.name AS collection_name
            FROM threads t
            LEFT JOIN collections col ON col.id = t.collection_id
            ORDER BY t.created_at DESC
        """).fetchall()
    return [dict(r) for r in rows]


def create_thread(title="New thread", collection_id=None):
    tid = uuid.uuid4().hex
    with _conn() as c:
        c.execute(
            "INSERT INTO threads (id, title, collection_id, created_at) VALUES (?, ?, ?, ?)",
            (tid, title, collection_id, _now()),
        )
    return tid


def get_thread(tid):
    with _conn() as c:
        return _row(c.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone())


def update_thread(tid, **fields):
    if not fields:
        return
    cols = ", ".join(f"{k} = ?" for k in fields)
    vals = list(fields.values()) + [tid]
    with _conn() as c:
        c.execute(f"UPDATE threads SET {cols} WHERE id = ?", vals)


def delete_thread(tid):
    with _conn() as c:
        c.execute("DELETE FROM threads WHERE id = ?", (tid,))


# ── Messages ────────────────────────────────────────────────
def list_messages(thread_id):
    with _conn() as c:
        rows = c.execute(
            "SELECT role, content FROM messages WHERE thread_id = ? ORDER BY created_at",
            (thread_id,),
        ).fetchall()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def add_message(thread_id, role, content):
    mid = uuid.uuid4().hex
    with _conn() as c:
        c.execute(
            "INSERT INTO messages (id, thread_id, role, content, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (mid, thread_id, role, content, _now()),
        )
    return mid


# ── Settings ────────────────────────────────────────────────
def _empty_slot():
    return {"provider": None, "api_key": "", "model": None}


def get_config():
    defaults = {"chat": _empty_slot(), "embedding": _empty_slot()}
    if not CONFIG_PATH.exists():
        return defaults
    cfg = json.loads(CONFIG_PATH.read_text())

    if "openrouter_api_key" in cfg and "chat" not in cfg:
        key = cfg.pop("openrouter_api_key")
        cfg = {
            "chat": {"provider": "openrouter", "api_key": key, "model": cfg.get("chat_model")},
            "embedding": {"provider": "openrouter", "api_key": key, "model": cfg.get("embedding_model")},
        }
    elif "provider" in cfg and "chat" not in cfg:
        key = cfg.pop("api_key", "")
        chat_model = cfg.pop("chat_model", None)
        emb_model = cfg.pop("embedding_model", None)
        prov = cfg.pop("provider")
        cfg = {
            "chat": {"provider": prov, "api_key": key, "model": chat_model},
            "embedding": {"provider": prov, "api_key": key, "model": emb_model},
        }

    for slot in ("chat", "embedding"):
        cfg.setdefault(slot, _empty_slot())
        for k, v in _empty_slot().items():
            cfg[slot].setdefault(k, v)
    return cfg


def set_config(d):
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(d, indent=2))


def mask_key(key):
    if not key or len(key) < 8:
        return ""
    return key[:6] + "..." + key[-4:]


# ── Self-knowledge: seeded "About RAGbee" collection ────────
def _meta_get(key):
    with _conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None


def _meta_set(key, value):
    with _conn() as c:
        c.execute("INSERT INTO meta (key, value) VALUES (?, ?) "
                  "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                  (key, value))


def get_about_collection_id():
    """Return the id of the seeded 'About RAGbee' collection, or None if it
    hasn't been created yet (call seed_about first)."""
    cid = _meta_get("about_collection_id")
    if not cid:
        return None
    return cid if get_collection(cid) else None


def seed_about_collection():
    """Create the 'About RAGbee' collection at startup so it's visible
    immediately, even before any embedding provider is configured. Chunks
    are added later by `seed_about_chunks` once an embedding provider is
    available. Idempotent."""
    if _meta_get("about_collection_id"):
        return
    if not ABOUT_PATH.exists():
        return
    cid = create_collection(ABOUT_COLLECTION_NAME)
    _meta_set("about_collection_id", cid)


def seed_about_chunks(embed_fn):
    """Embed and store the about.md chunks. Called from any endpoint that
    has an embedding provider available. Idempotent: a no-op once chunks
    are seeded. Self-healing: creates the collection if it doesn't exist.
    `embed_fn(text) -> list[float]` is the embedding function."""
    if _meta_get("about_chunks_seeded") == "1":
        return
    if not ABOUT_PATH.exists():
        return
    cid = _meta_get("about_collection_id")
    if not cid or not get_collection(cid):
        cid = create_collection(ABOUT_COLLECTION_NAME)
        _meta_set("about_collection_id", cid)
        _meta_set("about_chunks_seeded", "")
    text = ABOUT_PATH.read_text()
    if not text.strip():
        return
    for part in chunks(text):
        add_chunk(cid, ABOUT_PATH.name, part, embed_fn(part))
    _meta_set("about_chunks_seeded", "1")


ABOUT_THREAD_NAME = "Meet RAGbee"
ABOUT_THREAD_EXCHANGES = [
    ("user", "What is RAGbee?"),
    ("assistant",
     "RAGbee is a local personal knowledge base with a chat agent. You build "
     "collections of files and notes, then talk to the agent about them. "
     "It runs entirely on your machine and uses your own API keys."),
    ("user", "What can I do here?"),
    ("assistant",
     "Create collections under 📚 Collections, add files or notes to them, "
     "then start a thread under 💬 Threads and ask questions. The agent "
     "retrieves relevant chunks from the collection and answers with "
     "citations. Switch the chat input to 📝 Ingest mode to save a quick "
     "note straight into the active collection."),
    ("user", "Can you tell me more about yourself?"),
    ("assistant",
     "Sure — try asking me anything about how RAGbee works, the available "
     "commands, troubleshooting, or how to extend it. Once you've set your "
     "API key in ⚙ Settings, my answers will cite the chunks I retrieved from."),
]


def seed_about_thread():
    """Create a starter thread with a couple of example Q&A turns so a new
    user sees a working conversation immediately. Tied to the About collection.
    Idempotent: a no-op if the meta flag is set. If a stale demo thread from
    a prior version exists, its messages are refreshed."""
    if not _meta_get("about_collection_id"):
        return
    cid = _meta_get("about_collection_id")
    if not get_collection(cid):
        return
    existing_tid = _meta_get("about_thread_id")
    if existing_tid and get_thread(existing_tid):
        if _meta_get("about_thread_seeded") == "1":
            return
        with _conn() as c:
            c.execute("DELETE FROM messages WHERE thread_id = ?", (existing_tid,))
        tid = existing_tid
    else:
        tid = create_thread(ABOUT_THREAD_NAME, collection_id=cid)
        _meta_set("about_thread_id", tid)
    for role, content in ABOUT_THREAD_EXCHANGES:
        add_message(tid, role, content)
    _meta_set("about_thread_seeded", "1")
