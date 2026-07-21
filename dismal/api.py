"""Read-only public REST API.

Served from a background thread alongside the bot so the community site can
show live ratings. Ranking used to mean loading every player into memory and
sorting in Python on each request; it is now an indexed query against the
`leaderboard` view.

Endpoints:
    GET /v1/players/<username>   a single player's stats
    GET /v1/players?limit=&sort= the top N players
"""

from threading import Thread

from flask import Flask, jsonify, request

import config
from . import db
from . import repository as repo

MAX_LIMIT = 30
DEFAULT_AVATAR = "https://dismal.co/cdn/default_avatar.png"

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

# Set by start(); used to look up avatars for the leaderboard endpoint.
_client = None


@app.after_request
def add_cors_header(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def serialise(row, rank=None):
    """Shape a player row into the public JSON representation."""
    name, _, colour = config.division(row["elo"])

    return {
        "id": row["discord_id"],
        "username": row["username"],
        "elo": row["elo"],
        "rank": {"name": name, "colour": list(colour)},
        "wins": row["wins"],
        "losses": row["losses"],
        "wlr": "{0:.2f}".format(row["wins"] / max(row["losses"], 1)),
    }


@app.route("/", methods=["GET"])
@app.route("/v1", methods=["GET"])
def get_index():
    return jsonify(
        {
            "message": "Welcome to the Dismal API! For more information and "
            "full documentation, view https://dismal.co/api"
        }
    )


@app.route("/v1/players/<username>", methods=["GET"])
def get_player(username):
    row = db.query_one(
        "SELECT * FROM players WHERE username = ? COLLATE NOCASE", (username,)
    )

    if row is None:
        return jsonify({"error": "Player isn't registered with Dismal."}), 404

    return jsonify(serialise(row))


@app.route("/v1/players", methods=["GET"])
def get_players():
    limit = request.args.get("limit")
    sort = request.args.get("sort")

    if not limit:
        return (
            jsonify({"error": 'Query "limit" required but not specified.'}),
            400,
        )

    try:
        limit = int(limit)
    except ValueError:
        return jsonify({"error": 'Query "limit" expected type number.'}), 400

    if not 1 <= limit <= MAX_LIMIT:
        return (
            jsonify(
                {
                    "error": f'Query "limit" must be less than {MAX_LIMIT} '
                    f"and more than 1."
                }
            ),
            400,
        )

    if not sort:
        return (
            jsonify({"error": 'Query "sort" required but not specified.'}),
            400,
        )

    if sort != "elo":
        return jsonify({"error": 'Query "sort" invalid.'}), 400

    leaderboard = []

    for row in repo.get_leaderboard(limit=limit):
        avatar = DEFAULT_AVATAR

        if _client is not None:
            user = _client.get_user(int(row["discord_id"]))
            if user is not None and user.avatar_url:
                avatar = str(user.avatar_url)

        leaderboard.append(
            {
                "pos": row["rank"],
                "id": row["discord_id"],
                "username": row["username"],
                "avatar": avatar,
                "elo": row["elo"],
            }
        )

    return jsonify(leaderboard)


@app.errorhandler(404)
def page_not_found(error):
    return jsonify({"error": "Endpoint not found."}), 404


def start(client, port=3000):
    """Run the API on a daemon thread so it dies with the bot."""
    global _client
    _client = client

    thread = Thread(
        target=lambda: app.run(
            host="0.0.0.0", port=port, debug=False, use_reloader=False
        ),
        daemon=True,
    )
    thread.start()
    return thread
