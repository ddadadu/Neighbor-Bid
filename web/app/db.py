import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("DB_PATH", "/data/app.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS guests (
    id          TEXT PRIMARY KEY,              -- UUID
    nickname    TEXT NOT NULL UNIQUE,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    seller_id      TEXT NOT NULL REFERENCES guests(id),
    title          TEXT NOT NULL,
    description    TEXT NOT NULL DEFAULT '',
    image_key      TEXT,                      -- S3 키: items/<uuid>.jpg
    image_url      TEXT,
    start_price    INTEGER NOT NULL,
    current_price  INTEGER NOT NULL,
    top_bidder_id  TEXT REFERENCES guests(id),
    status         TEXT NOT NULL DEFAULT 'OPEN',   -- OPEN / CLOSED / FAILED
    end_at         INTEGER NOT NULL,          -- UTC epoch 초
    created_at     INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bids (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    guest_id    TEXT NOT NULL REFERENCES guests(id),
    amount      INTEGER NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id     INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
    guest_id    TEXT NOT NULL REFERENCES guests(id),
    content     TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_items_status_end ON items(status, end_at);
CREATE INDEX IF NOT EXISTS idx_bids_item_time   ON bids(item_id, created_at);
CREATE INDEX IF NOT EXISTS idx_msgs_item_time   ON messages(item_id, created_at);
"""


def now() -> int:
    """UTC 기준 epoch 초. 모든 시간은 이 값으로 저장·비교한다."""
    return int(time.time())


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row            # row["title"]처럼 이름으로 접근
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """with get_db() as db: ... 블록이 끝나면 커밋(오류 시 롤백) 후 연결을 닫는다."""
    conn = _connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = _connect()
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)
        # 닉네임 반납용 컬럼 (기존 DB에도 추가)
        cols = [r[1] for r in conn.execute("PRAGMA table_info(guests)")]
        if "last_seen" not in cols:
            conn.execute("ALTER TABLE guests ADD COLUMN last_seen INTEGER")
        if "left_at" not in cols:
            conn.execute("ALTER TABLE guests ADD COLUMN left_at INTEGER")
        conn.commit()
    finally:
        conn.close()