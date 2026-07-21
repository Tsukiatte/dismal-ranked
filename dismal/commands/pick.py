"""`/pick` -- captains draft players into teams.

Captains alternate picks. When only one player is left the draft ends: that
player is auto-assigned to the team that did not just pick, everyone is moved
into their team voice channel, and the shared pick channel is deleted.
"""

import discord

import config
from .. import repository as repo
from .. import utils


def game_id_from_channel(channel):
    """Game channels are named `game-123`; pull the id back out."""
    try:
        return int(channel.name.replace("-", "").replace("game", ""))
    except ValueError:
        return None


def _team_channel_names(channel):
    """The three voice channels belonging to a game text channel."""
    base = channel.name.replace("-", "#").replace("g", "G") + " | Team "
    return base + "1", base + "2", base + "Pick"


async def _finish_draft(ctx, game_id, last_team):
    """Assign the final player, move everyone to voice, close the pick channel."""
    remaining = repo.get_unpicked_players(game_id)
    next_team = 2 if last_team == 1 else 1

    for player_id in remaining:
        repo.assign_player_to_team(game_id, player_id, next_team, None)

    repo.set_game_field(game_id, "picks_done", 1)

    name1, name2, pick_name = _team_channel_names(ctx.channel)
    voice1 = discord.utils.get(ctx.guild.channels, name=name1)
    voice2 = discord.utils.get(ctx.guild.channels, name=name2)
    pick_channel = discord.utils.get(ctx.guild.channels, name=pick_name)

    for team, voice_channel in ((1, voice1), (2, voice2)):
        if voice_channel is None:
            continue

        for player_id in repo.get_team(game_id, team):
            member = ctx.guild.get_member(int(player_id))
            if member is None:
                continue

            await voice_channel.set_permissions(member, connect=True)
            try:
                await member.move_to(voice_channel)
            except discord.HTTPException:
                # Not connected to voice -- they can join on their own.
                pass

    if pick_channel is not None:
        try:
            await pick_channel.delete()
        except discord.HTTPException:
            pass


async def pick(ctx, user):
    if await utils.reject_if_restricted(ctx):
        return

    category = getattr(ctx.channel, "category", None)
    if category is None or category.id != config.CATEGORY_QUEUE:
        await ctx.send("This is not a ``game channel.``")
        return

    game_id = game_id_from_channel(ctx.channel)
    if game_id is None:
        await ctx.send("This is not a ``game channel.``")
        return

    game = repo.get_game(game_id)
    if game is None:
        await ctx.send("This is not a ``game channel.``")
        return

    if game["picks_done"]:
        await ctx.send("Picking stage is ``over.``")
        return

    players = {row["player_id"]: row for row in repo.get_game_players(game_id)}
    captain = players.get(str(ctx.author.id))

    if captain is None or not captain["is_captain"]:
        await ctx.send("You are not a ``captain.``")
        return

    if captain["team"] != game["pick"]:
        await ctx.send("It's not your pick ``right now.``")
        return

    target = await utils.resolve_member(ctx, user)
    if target is None:
        await ctx.send(
            "You didn't provide a valid ``[User ID]`` or ``[@A-User]`` "
            "to **pick.**"
        )
        return

    entry = players.get(str(target.id))
    if entry is None or entry["team"] is not None:
        await ctx.send("You can't pick this ``user.``")
        return

    pick_order = sum(
        1 for row in players.values() if row["team"] is not None
    ) + 1
    repo.assign_player_to_team(game_id, target.id, captain["team"], pick_order)

    # One player left after this pick -- auto-assign and close the draft.
    if len(repo.get_unpicked_players(game_id)) == 1:
        await _finish_draft(ctx, game_id, captain["team"])
        await ctx.channel.send(
            f"Successfully picked <@{target.id}>. "
            f"Moving players to their team vcs."
        )
        return

    # A double pick lets the same captain go again instead of alternating.
    if game["double_pick"]:
        repo.set_game_field(game_id, "double_pick", 0)
        next_pick = captain["team"]
    else:
        next_pick = 2 if captain["team"] == 1 else 1
        repo.set_game_field(game_id, "pick", next_pick)

    await ctx.channel.send(
        f"Successfully picked <@{target.id}>. "
        f"**``Team {next_pick}'s pick!``**"
    )
