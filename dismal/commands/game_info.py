"""`/game` and `/ghost` -- inspecting and clearing individual games."""

import asyncio

import discord

from .. import games, utils
from .. import repository as repo

STATUS_PICKING = ("Picking Teams", 0x1F51FF)
STATUS_PLAYING = ("Scrimming", 0xFFF01F)
STATUS_SCORING = ("Scoring Game", 0xE96AA3)
STATUS_FINISHED = ("Finished", 0x5DC76F)


def game_status(row):
    """Return (label, colour) describing where a game is in its lifecycle."""
    if row["scored"] or row["winner"] == "void":
        return STATUS_FINISHED
    if not row["picks_done"]:
        return STATUS_PICKING
    if row["proof"]:
        return STATUS_SCORING
    return STATUS_PLAYING


def format_team(player_ids):
    """Number a team's players, marking the captain with crossed swords."""
    lines = []
    for index, player_id in enumerate(player_ids, start=1):
        suffix = " :crossed_swords:" if index == 1 else ""
        lines.append(f"**[{index}]** <@{player_id}>{suffix}\n")

    return "".join(lines) or "—"


async def game(ctx, game_id=None):
    if await utils.reject_if_restricted(ctx):
        return

    if game_id is None:
        await ctx.send("Correct usage: `/game <gameid>`")
        return

    try:
        game_id = int(game_id)
    except (TypeError, ValueError):
        await ctx.send(f"**{game_id}** is not a valid gameid!")
        return

    row = repo.get_game(game_id)
    if row is None:
        await ctx.send(f"**{game_id}** is not a valid gameid!")
        return

    status, colour = game_status(row)

    embed = discord.Embed(
        title=f"`Game {game_id}`",
        description=f"**Status: {status}**",
        color=colour,
    )
    embed.add_field(
        name="`Team 1`", value=format_team(repo.get_team(game_id, 1)),
        inline=False,
    )
    embed.add_field(
        name="`Team 2`", value=format_team(repo.get_team(game_id, 2)),
        inline=False,
    )
    embed.add_field(
        name="`Additional statistics`",
        value=f"Winner: {row['winner'] or 'none'}",
        inline=False,
    )

    await ctx.send(embed=embed)


async def ghost(ctx):
    """Clear a 'ghost' game -- channels that exist with no matching record."""
    if not games.is_game_channel(ctx.channel):
        await ctx.send("This is not a ``game channel.``")
        return

    game_id = games.game_id_from_channel(ctx.channel)

    if game_id is not None and repo.get_game(game_id) is not None:
        await ctx.send("This is not a ghost game!")
        return

    await ctx.send("Voiding ghost game!")
    await asyncio.sleep(1)

    await games.close_channels(ctx.guild, ctx.channel)

    if game_id is not None:
        await games.post_result(ctx.guild, game_id, "voided")
