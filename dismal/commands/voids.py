"""`/void` and `/unvoid` -- cancelling a game.

Voiding needs agreement: a player opens a request, and the game is only voided
once `VOTES_REQUIRED` of the eight react to it. The reaction handler in
`dismal/events/reactions.py` counts the votes and does the teardown.
"""

import config
from .. import games
from .. import repository as repo
from .. import utils

VOTES_REQUIRED = 5
TEAM_SIZE = 8


async def void(ctx):
    """Open a void request for the game this channel belongs to."""
    if await utils.reject_if_restricted(ctx):
        return

    if not games.is_game_channel(ctx.channel):
        await ctx.send("This is not a ``game channel.``")
        return

    game_id = games.game_id_from_channel(ctx.channel)
    game = repo.get_game(game_id) if game_id is not None else None

    if game is None:
        await ctx.send("This is not a ``game channel.``")
        return

    if game["voids"]:
        await ctx.send("There is already an active ``void request.``")
        return

    message = await ctx.send(
        f"**``void request submitted! {VOTES_REQUIRED}/{TEAM_SIZE} players "
        f"must react before the game is voided.``**"
    )
    await message.add_reaction("✅")

    repo.set_game_field(game_id, "voids", 1)
    repo.set_game_field(game_id, "void_id", str(message.id))
    repo.set_void_message(game_id, message.id)


async def unvoid(ctx, game_id=None):
    """Reverse a void so the game can be scored normally."""
    if (
        getattr(ctx.channel, "category", None) is not None
        and ctx.channel.category.id == config.CATEGORY_GAMES
        and ctx.channel.id != config.CHANNEL_STAFF
    ):
        return

    if await utils.require_staff(ctx, (config.ROLE_SCORER_ID,)):
        return

    if game_id is None:
        await ctx.send("Please provide a **gameid** to **unvoid**")
        return

    try:
        game_id = int(game_id)
    except (TypeError, ValueError):
        await ctx.send(f"`{game_id}` is not a valid gameid!")
        return

    game = repo.get_game(game_id)
    if game is None:
        await ctx.send(f"`{game_id}` is not a valid gameid!")
        return

    if game["winner"] != "void":
        await ctx.send(f"Game **{game_id}** is not currently voided!")
        return

    repo.set_game_field(game_id, "winner", None)
    repo.set_game_field(game_id, "scored", 0)

    await ctx.send(f"Successfully unvoided Game **{game_id}**")
