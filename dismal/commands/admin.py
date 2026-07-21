"""Administrative commands: `/edit`, `/fix`, `/ping`.

`fix` repairs a player's division role when it has drifted out of sync with
their elo -- usually after a manual `/edit` or a failed role update during
scoring.
"""

import discord
from discord.utils import get

import config
from .. import repository as repo
from .. import utils

EDITABLE_FIELDS = ("elo", "wins", "losses")


async def edit(ctx, user, field, value):
    """Set a player's elo, wins or losses directly."""
    if not ctx.author.guild_permissions.administrator:
        await ctx.send("You don't have permission to run this command!")
        return

    member = await utils.resolve_member(ctx, user)
    if member is None:
        await ctx.send(f"`{user}` is not a valid user!")
        return

    if repo.get_player(member.id) is None:
        await ctx.send(f"`{user}` is not registered!")
        return

    if field not in EDITABLE_FIELDS:
        await ctx.send(
            f"{field} is not a variable you can change! "
            f"(`elo`/`wins`/`losses`)"
        )
        return

    try:
        value = int(value)
    except (TypeError, ValueError):
        await ctx.send(f"The value (`{value}`) cannot be a string!")
        return

    before = repo.get_player(member.id)["elo"]
    repo.set_player_field(member.id, field, value)

    if field == "elo":
        await utils.sync_division_role(member, before, value)
        player = repo.get_player(member.id)
        await utils.set_elo_nickname(member, value, player["username"])

    await ctx.send(
        f"Successfully changed **``{utils.display_name(member)}``**'s "
        f"`{field}` to `{value}`!"
    )


async def fix(ctx):
    """Re-apply the caller's division role based on their current elo."""
    if await utils.reject_if_restricted(ctx):
        return

    player = repo.get_player(ctx.author.id)
    if player is None:
        await ctx.send("You are not registered!")
        return

    member = ctx.author
    correct_role_id = config.division_role_id(player["elo"])

    # Strip every division role, then grant the one that matches.
    stale = [
        get(ctx.guild.roles, id=role_id)
        for _, _, role_id, _ in config.DIVISIONS
        if role_id != correct_role_id and utils.has_role(member, role_id)
    ]
    if utils.has_role(member, config.DIVISION_TOP[1]):
        if config.DIVISION_TOP[1] != correct_role_id:
            stale.append(get(ctx.guild.roles, id=config.DIVISION_TOP[1]))

    try:
        for role in filter(None, stale):
            await member.remove_roles(role)

        correct_role = get(ctx.guild.roles, id=correct_role_id)
        if correct_role is not None and correct_role not in member.roles:
            await member.add_roles(correct_role)
    except discord.HTTPException:
        await ctx.send("Could not update your roles -- missing permissions.")
        return

    await ctx.send("Successfully fixed your roles!")


async def ping(ctx):
    """Liveness check -- replies with the gateway latency."""
    latency_ms = round(ctx.bot.latency * 1000)
    await ctx.send(f"Pong! `{latency_ms}ms`")
