"""One-off migration from the original JSON files into SQLite.

The bot used to keep its state in ``databases/*.json``. This script reads that
directory and writes the equivalent rows into the SQLite database, so an
existing deployment keeps its player ratings and game history.

    python scripts/migrate_json.py path/to/databases

It is idempotent: rows are inserted with ON CONFLICT ... DO UPDATE, so running
it twice is harmless. It never deletes anything from the JSON side.
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dismal import db  # noqa: E402


def load(source, name):
    """Read one JSON file, returning an empty dict if it is missing or blank."""
    path = source / f"{name}.json"

    if not path.exists():
        print(f"  skip {name}.json (not found)")
        return {}

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {}

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        print(f"  warn {name}.json is not valid JSON ({error}); skipping")
        return {}


def migrate_players(conn, source):
    players = load(source, "playerstats")
    rows = []

    for discord_id, stats in players.items():
        if not isinstance(stats, dict):
            continue
        rows.append(
            (
                str(discord_id),
                stats.get("username", "unknown"),
                stats.get("elo", 0),
                stats.get("wins", 0),
                stats.get("losses", 0),
            )
        )

    conn.executemany(
        """
        INSERT INTO players (discord_id, username, elo, wins, losses)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (discord_id) DO UPDATE SET
            username = excluded.username,
            elo      = excluded.elo,
            wins     = excluded.wins,
            losses   = excluded.losses
        """,
        rows,
    )
    print(f"  players: {len(rows)}")


def migrate_games(conn, source):
    games = load(source, "gamelogs")
    game_rows = []
    player_rows = []

    for raw_id, game in games.items():
        try:
            game_id = int(raw_id)
        except (TypeError, ValueError):
            continue
        if not isinstance(game, dict):
            continue

        game_rows.append(
            (
                game_id,
                game.get("winner") or None,
                int(bool(game.get("scored"))),
                int(bool(game.get("proof"))),
                int(bool(game.get("picksdone"))),
                game.get("pick", 1),
                int(bool(game.get("doublepick"))),
                game.get("voids", 0),
                game.get("voidid") or None,
            )
        )

        team1 = game.get("team1") or []
        team2 = game.get("team2") or []
        captains = game.get("captains") or []
        picked = game.get("picked") or []

        for player_id in game.get("allplayers") or []:
            if player_id in team1:
                team = 1
            elif player_id in team2:
                team = 2
            else:
                team = None

            pick_order = (
                picked.index(player_id) + 1 if player_id in picked else None
            )

            player_rows.append(
                (
                    game_id,
                    str(player_id),
                    team,
                    int(player_id in captains),
                    pick_order,
                )
            )

    conn.executemany(
        """
        INSERT INTO games
            (id, winner, scored, proof, picks_done, pick, double_pick,
             voids, void_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO NOTHING
        """,
        game_rows,
    )

    conn.executemany(
        """
        INSERT INTO game_players
            (game_id, player_id, team, is_captain, pick_order)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (game_id, player_id) DO NOTHING
        """,
        player_rows,
    )
    print(f"  games: {len(game_rows)} ({len(player_rows)} participations)")


def migrate_parties(conn, source):
    parties = load(source, "party")
    rows = []

    for key, party in parties.items():
        if key == "currentid" or not isinstance(party, dict):
            continue

        member = party.get("member")
        if member == "none":
            member = None

        accepted = party.get("invite") == "accepted"
        invitee = None if accepted else party.get("invite")

        rows.append(
            (
                int(key),
                party.get("leader"),
                invitee,
                member,
                int(accepted),
                int(bool(party.get("disbanded"))),
                party.get("timestamp", int(time.time())),
            )
        )

    conn.executemany(
        """
        INSERT INTO parties
            (id, leader_id, invitee_id, member_id, accepted, disbanded,
             created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (id) DO NOTHING
        """,
        rows,
    )
    print(f"  parties: {len(rows)}")


def migrate_warns(conn, source):
    warnlist = load(source, "warnlist")
    rows = []

    for user_id, record in warnlist.items():
        if not isinstance(record, dict):
            continue

        # Warns were stored as numbered keys alongside a "warns" counter:
        #   {"warns": 3, "1": [reason, moderator_id], ...}
        for key, entry in record.items():
            if key == "warns" or not isinstance(entry, list) or not entry:
                continue

            reason = entry[0] if len(entry) > 0 else "None"
            moderator = entry[1] if len(entry) > 1 else user_id

            rows.append((str(user_id), str(reason), str(moderator)))

    conn.executemany(
        """
        INSERT INTO warns (user_id, reason, moderator_id) VALUES (?, ?, ?)
        """,
        rows,
    )
    print(f"  warns: {len(rows)}")


def migrate_punishments(conn, source):
    total = 0

    for name, kind in (
        ("banlist", "ban"),
        ("mutelist", "mute"),
        ("rankbanlist", "rankban"),
    ):
        entries = load(source, name)
        rows = []

        for user_id, expires_at in entries.items():
            if not isinstance(expires_at, (int, float)):
                continue
            rows.append((str(user_id), kind, int(expires_at)))

        conn.executemany(
            """
            INSERT INTO punishments (user_id, kind, expires_at)
            VALUES (?, ?, ?)
            ON CONFLICT (user_id, kind)
            DO UPDATE SET expires_at = excluded.expires_at
            """,
            rows,
        )
        total += len(rows)

    print(f"  punishments: {total}")


def migrate_void_messages(conn, source):
    voids = load(source, "voidids")
    rows = []

    for raw_id, message_id in voids.items():
        try:
            rows.append((int(raw_id), str(message_id)))
        except (TypeError, ValueError):
            continue

    # Only keep rows whose game actually migrated -- the foreign key would
    # otherwise reject them.
    known = {row["id"] for row in conn.execute("SELECT id FROM games")}
    rows = [row for row in rows if row[0] in known]

    conn.executemany(
        """
        INSERT INTO void_messages (game_id, message_id) VALUES (?, ?)
        ON CONFLICT (game_id) DO UPDATE SET message_id = excluded.message_id
        """,
        rows,
    )
    print(f"  void messages: {len(rows)}")


def migrate_settings(conn, source):
    game = load(source, "game")
    maximum = load(source, "max")

    settings = []
    if isinstance(game, dict) and "game" in game:
        settings.append(("current_game_id", str(game["game"])))
    if isinstance(maximum, dict) and "max" in maximum:
        settings.append(("queue_size", str(maximum["max"])))

    conn.executemany(
        """
        INSERT INTO settings (key, value) VALUES (?, ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value
        """,
        settings,
    )
    print(f"  settings: {len(settings)}")


def main():
    source = Path(sys.argv[1] if len(sys.argv) > 1 else "databases")

    if not source.is_dir():
        print(f"error: {source} is not a directory")
        return 1

    print(f"Migrating from {source.resolve()}")

    with db.transaction() as conn:
        migrate_players(conn, source)
        migrate_games(conn, source)
        migrate_parties(conn, source)
        migrate_warns(conn, source)
        migrate_punishments(conn, source)
        migrate_void_messages(conn, source)
        migrate_settings(conn, source)

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
