"""SQLite storage layer.

Replaces the flat JSON files the bot originally used. Every table lives in a
single database file (``DATABASE_PATH``), so a game submission that touches
player elo, game state and party rows either lands completely or not at all.

The connection is opened once and shared. SQLite handles the bot's write volume
comfortably: the ranked queue peaks at a few writes per second.

``WAL`` journalling lets the read-heavy leaderboard queries run without
blocking writers.
"""

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from config import DATABASE_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS players (
    discord_id TEXT PRIMARY KEY,
    username   TEXT NOT NULL,
    elo        INTEGER NOT NULL DEFAULT 0,
    wins       INTEGER NOT NULL DEFAULT 0,
    losses     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS games (
    id           INTEGER PRIMARY KEY,
    winner       TEXT,
    scored       INTEGER NOT NULL DEFAULT 0,
    proof        INTEGER NOT NULL DEFAULT 0,
    picks_done   INTEGER NOT NULL DEFAULT 0,
    pick         INTEGER NOT NULL DEFAULT 1,
    double_pick  INTEGER NOT NULL DEFAULT 0,
    voids        INTEGER NOT NULL DEFAULT 0,
    void_id      TEXT,
    created_at   INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
);

-- One row per player per game. `team` is NULL until captains finish picking.
CREATE TABLE IF NOT EXISTS game_players (
    game_id     INTEGER NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id   TEXT    NOT NULL,
    team        INTEGER,
    is_captain  INTEGER NOT NULL DEFAULT 0,
    pick_order  INTEGER,
    PRIMARY KEY (game_id, player_id)
);

CREATE INDEX IF NOT EXISTS idx_game_players_player ON game_players(player_id);

CREATE TABLE IF NOT EXISTS parties (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    leader_id  TEXT NOT NULL,
    invitee_id TEXT,
    member_id  TEXT,
    accepted   INTEGER NOT NULL DEFAULT 0,
    disbanded  INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_parties_active
    ON parties(disbanded, leader_id, member_id);

CREATE TABLE IF NOT EXISTS warns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT NOT NULL,
    reason       TEXT NOT NULL DEFAULT 'None',
    moderator_id TEXT NOT NULL,
    created_at   INTEGER NOT NULL DEFAULT (strftime('%s', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_warns_user ON warns(user_id);

-- Replaces banlist.json / mutelist.json / rankbanlist.json. `kind` keeps the
-- three timed punishments in one table so the expiry sweep is a single query.
CREATE TABLE IF NOT EXISTS punishments (
    user_id    TEXT    NOT NULL,
    kind       TEXT    NOT NULL CHECK (kind IN ('ban', 'mute', 'rankban')),
    expires_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, kind)
);

CREATE INDEX IF NOT EXISTS idx_punishments_expiry ON punishments(kind, expires_at);

CREATE TABLE IF NOT EXISTS queue_members (
    channel_id TEXT NOT NULL,
    user_id    TEXT NOT NULL,
    PRIMARY KEY (channel_id, user_id)
);

CREATE TABLE IF NOT EXISTS void_messages (
    game_id    INTEGER PRIMARY KEY REFERENCES games(id) ON DELETE CASCADE,
    message_id TEXT NOT NULL
);

-- Small key/value bag for the counters that used to live in game.json and
-- max.json (current game id, queue size cap, ...).
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- The leaderboard was a JSON file rebuilt by a background task every 60s.
-- As a view it is always current and costs nothing to maintain.
CREATE VIEW IF NOT EXISTS leaderboard AS
    SELECT
        ROW_NUMBER() OVER (ORDER BY elo DESC, wins DESC, discord_id) AS rank,
        discord_id,
        username,
        elo,
        wins,
        losses
    FROM players;
"""

_connection = None
_path = DATABASE_PATH
_lock = threading.Lock()


def configure(path):
    """Point the layer at a different database file.

    Closes any open connection first, so the next `connect()` opens the new
    file. Tests use this to run against a temporary database.
    """
    global _path

    close()
    _path = path


def connect():
    """Return the shared connection, creating and initialising it on first use."""
    global _connection

    with _lock:
        if _connection is None:
            Path(_path).parent.mkdir(parents=True, exist_ok=True)

            _connection = sqlite3.connect(
                _path,
                check_same_thread=False,
                isolation_level=None,  # explicit transactions via transaction()
            )
            _connection.row_factory = sqlite3.Row
            _connection.execute("PRAGMA journal_mode = WAL")
            _connection.execute("PRAGMA foreign_keys = ON")
            _connection.execute("PRAGMA synchronous = NORMAL")
            _connection.executescript(SCHEMA)

    return _connection


def query(sql, params=()):
    """Run a SELECT and return all rows."""
    return connect().execute(sql, params).fetchall()


def query_one(sql, params=()):
    """Run a SELECT and return the first row, or None."""
    return connect().execute(sql, params).fetchone()


def execute(sql, params=()):
    """Run a single INSERT/UPDATE/DELETE."""
    return connect().execute(sql, params)


@contextmanager
def transaction():
    """Group several writes so they commit or roll back together.

    Used by anything that has to stay consistent across tables -- scoring a
    game updates `games`, every player's elo, and their win/loss counts.
    """
    conn = connect()
    conn.execute("BEGIN")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK")
        raise
    else:
        conn.execute("COMMIT")


def close():
    """Close the shared connection (used on shutdown and in tests)."""
    global _connection

    with _lock:
        if _connection is not None:
            _connection.close()
            _connection = None
