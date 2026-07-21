"""Data access for every table.

Command modules call these functions instead of reading and rewriting JSON
files. Keeping the SQL in one place means a query can be fixed or indexed
without touching command code, and the multi-table writes (scoring a game)
stay in a single transaction.

Discord IDs are stored as TEXT: they are 64-bit snowflakes, and SQLite's
INTEGER is signed 64-bit, so text avoids any risk of precision surprises and
matches how they arrive from the API.
"""

import time

from . import db

# --- Players ---------------------------------------------------------------


def get_player(user_id):
    """Return a player row, or None if they have never registered."""
    return db.query_one(
        "SELECT * FROM players WHERE discord_id = ?", (str(user_id),)
    )


def is_registered(user_id):
    return get_player(user_id) is not None


def register_player(user_id, username):
    """Create or rename a player. Returns True if this was a new registration.

    Re-registering keeps the player's elo and record; only the display name
    changes.
    """
    existing = get_player(user_id)

    if existing is None:
        db.execute(
            "INSERT INTO players (discord_id, username) VALUES (?, ?)",
            (str(user_id), username),
        )
        return True

    db.execute(
        "UPDATE players SET username = ? WHERE discord_id = ?",
        (username, str(user_id)),
    )
    return False


def unregister_player(user_id):
    db.execute("DELETE FROM players WHERE discord_id = ?", (str(user_id),))


def update_player_stats(user_id, elo_delta, won):
    """Apply an elo change and increment the win or loss counter.

    Elo is floored at zero -- a loss can never push a player negative.
    """
    column = "wins" if won else "losses"
    db.execute(
        f"""
        UPDATE players
           SET elo = MAX(0, elo + ?),
               {column} = {column} + 1
         WHERE discord_id = ?
        """,
        (elo_delta, str(user_id)),
    )


def set_player_field(user_id, field, value):
    """Set a single stat directly. Used by the staff `/edit` command."""
    if field not in ("username", "elo", "wins", "losses"):
        raise ValueError(f"cannot edit field: {field}")

    db.execute(
        f"UPDATE players SET {field} = ? WHERE discord_id = ?",
        (value, str(user_id)),
    )


def get_leaderboard(limit=None, offset=0):
    """Return ranked players, highest elo first."""
    if limit is None:
        return db.query("SELECT * FROM leaderboard")

    return db.query(
        "SELECT * FROM leaderboard LIMIT ? OFFSET ?", (limit, offset)
    )


def get_player_rank(user_id):
    """Return a player's leaderboard position, or None if unregistered."""
    row = db.query_one(
        "SELECT rank FROM leaderboard WHERE discord_id = ?", (str(user_id),)
    )
    return row["rank"] if row else None


def count_players():
    return db.query_one("SELECT COUNT(*) AS n FROM players")["n"]


# --- Games -----------------------------------------------------------------


def create_game(player_ids, captain_ids):
    """Open a new game and return its id."""
    with db.transaction() as conn:
        cursor = conn.execute("INSERT INTO games DEFAULT VALUES")
        game_id = cursor.lastrowid

        conn.executemany(
            """
            INSERT INTO game_players (game_id, player_id, is_captain)
            VALUES (?, ?, ?)
            """,
            [
                (game_id, str(pid), 1 if pid in captain_ids else 0)
                for pid in player_ids
            ],
        )

    return game_id


def get_game(game_id):
    return db.query_one("SELECT * FROM games WHERE id = ?", (game_id,))


def get_game_players(game_id):
    """All players in a game, captains first, then in pick order."""
    return db.query(
        """
        SELECT * FROM game_players
         WHERE game_id = ?
         ORDER BY is_captain DESC, pick_order IS NULL, pick_order
        """,
        (game_id,),
    )


def get_team(game_id, team):
    """Return the player ids on one side of a game."""
    rows = db.query(
        """
        SELECT player_id FROM game_players
         WHERE game_id = ? AND team = ?
         ORDER BY is_captain DESC, pick_order
        """,
        (game_id, team),
    )
    return [row["player_id"] for row in rows]


def get_unpicked_players(game_id):
    """Players still waiting to be picked onto a team."""
    rows = db.query(
        """
        SELECT player_id FROM game_players
         WHERE game_id = ? AND team IS NULL
         ORDER BY rowid
        """,
        (game_id,),
    )
    return [row["player_id"] for row in rows]


def assign_player_to_team(game_id, player_id, team, pick_order):
    db.execute(
        """
        UPDATE game_players
           SET team = ?, pick_order = ?
         WHERE game_id = ? AND player_id = ?
        """,
        (team, pick_order, game_id, str(player_id)),
    )


def set_game_field(game_id, field, value):
    if field not in (
        "winner",
        "scored",
        "proof",
        "picks_done",
        "pick",
        "double_pick",
        "voids",
        "void_id",
    ):
        raise ValueError(f"cannot set game field: {field}")

    db.execute(f"UPDATE games SET {field} = ? WHERE id = ?", (value, game_id))


def get_player_games(user_id, limit=10):
    """A player's most recent games, newest first."""
    return db.query(
        """
        SELECT g.*, gp.team
          FROM games g
          JOIN game_players gp ON gp.game_id = g.id
         WHERE gp.player_id = ?
         ORDER BY g.id DESC
         LIMIT ?
        """,
        (str(user_id), limit),
    )


def current_game_id():
    """Highest game id issued so far (0 when no games exist)."""
    row = db.query_one("SELECT COALESCE(MAX(id), 0) AS id FROM games")
    return row["id"]


# --- Parties ---------------------------------------------------------------


def get_active_party(user_id):
    """The party a user currently leads or belongs to, if any."""
    return db.query_one(
        """
        SELECT * FROM parties
         WHERE disbanded = 0
           AND (leader_id = ? OR member_id = ?)
         LIMIT 1
        """,
        (str(user_id), str(user_id)),
    )


def create_party(leader_id, invitee_id):
    cursor = db.execute(
        """
        INSERT INTO parties (leader_id, invitee_id, created_at)
        VALUES (?, ?, ?)
        """,
        (str(leader_id), str(invitee_id), int(time.time())),
    )
    return cursor.lastrowid


def get_party(party_id):
    return db.query_one("SELECT * FROM parties WHERE id = ?", (party_id,))


def find_pending_invite(leader_id, invitee_id):
    """An open, unaccepted invite from `leader_id` to `invitee_id`."""
    return db.query_one(
        """
        SELECT * FROM parties
         WHERE leader_id = ? AND invitee_id = ?
           AND accepted = 0 AND disbanded = 0
         LIMIT 1
        """,
        (str(leader_id), str(invitee_id)),
    )


def accept_party_invite(party_id, member_id):
    db.execute(
        "UPDATE parties SET accepted = 1, member_id = ? WHERE id = ?",
        (str(member_id), party_id),
    )


def disband_party(party_id):
    db.execute("UPDATE parties SET disbanded = 1 WHERE id = ?", (party_id,))


def expire_unaccepted_party(party_id):
    """Disband a party only if its invite was never accepted.

    Called after the invite timeout; the no-op case is an invite that was
    accepted while the timer was running.
    """
    cursor = db.execute(
        "UPDATE parties SET disbanded = 1 WHERE id = ? AND accepted = 0",
        (party_id,),
    )
    return cursor.rowcount > 0


# --- Warns -----------------------------------------------------------------


def add_warn(user_id, moderator_id, reason="None"):
    """Record a warning and return the user's new warn count."""
    db.execute(
        """
        INSERT INTO warns (user_id, moderator_id, reason)
        VALUES (?, ?, ?)
        """,
        (str(user_id), str(moderator_id), reason),
    )
    return count_warns(user_id)


def get_warns(user_id):
    return db.query(
        "SELECT * FROM warns WHERE user_id = ? ORDER BY created_at",
        (str(user_id),),
    )


def count_warns(user_id):
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM warns WHERE user_id = ?", (str(user_id),)
    )
    return row["n"]


def clear_warns(user_id):
    db.execute("DELETE FROM warns WHERE user_id = ?", (str(user_id),))


# --- Punishments (bans, mutes, ranked bans) --------------------------------


def add_punishment(user_id, kind, duration_seconds):
    """Apply a timed punishment, replacing any existing one of the same kind."""
    db.execute(
        """
        INSERT INTO punishments (user_id, kind, expires_at)
        VALUES (?, ?, ?)
        ON CONFLICT (user_id, kind)
        DO UPDATE SET expires_at = excluded.expires_at
        """,
        (str(user_id), kind, int(time.time()) + duration_seconds),
    )


def remove_punishment(user_id, kind):
    db.execute(
        "DELETE FROM punishments WHERE user_id = ? AND kind = ?",
        (str(user_id), kind),
    )


def has_punishment(user_id, kind):
    row = db.query_one(
        """
        SELECT 1 FROM punishments
         WHERE user_id = ? AND kind = ? AND expires_at > ?
        """,
        (str(user_id), kind, int(time.time())),
    )
    return row is not None


def pop_expired_punishments(kind):
    """Return and delete every punishment of `kind` that has run out.

    Deleting in the same transaction as the read stops the expiry task from
    handing the same user back twice if a sweep runs long.
    """
    now = int(time.time())

    with db.transaction() as conn:
        rows = conn.execute(
            "SELECT user_id FROM punishments WHERE kind = ? AND expires_at <= ?",
            (kind, now),
        ).fetchall()

        if rows:
            conn.execute(
                "DELETE FROM punishments WHERE kind = ? AND expires_at <= ?",
                (kind, now),
            )

    return [row["user_id"] for row in rows]


# --- Queue -----------------------------------------------------------------


def add_to_queue(channel_id, user_id):
    db.execute(
        """
        INSERT OR IGNORE INTO queue_members (channel_id, user_id)
        VALUES (?, ?)
        """,
        (str(channel_id), str(user_id)),
    )


def remove_from_queue(channel_id, user_id):
    db.execute(
        "DELETE FROM queue_members WHERE channel_id = ? AND user_id = ?",
        (str(channel_id), str(user_id)),
    )


def get_queue(channel_id):
    rows = db.query(
        "SELECT user_id FROM queue_members WHERE channel_id = ?",
        (str(channel_id),),
    )
    return [row["user_id"] for row in rows]


def clear_queue(channel_id):
    db.execute(
        "DELETE FROM queue_members WHERE channel_id = ?", (str(channel_id),)
    )


# --- Void messages ---------------------------------------------------------


def set_void_message(game_id, message_id):
    db.execute(
        """
        INSERT INTO void_messages (game_id, message_id) VALUES (?, ?)
        ON CONFLICT (game_id) DO UPDATE SET message_id = excluded.message_id
        """,
        (game_id, str(message_id)),
    )


def get_game_by_void_message(message_id):
    return db.query_one(
        "SELECT game_id FROM void_messages WHERE message_id = ?",
        (str(message_id),),
    )


# --- Settings --------------------------------------------------------------


def get_setting(key, default=None):
    row = db.query_one("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


def set_setting(key, value):
    db.execute(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )


def get_int_setting(key, default=0):
    value = get_setting(key)
    return int(value) if value is not None else default
