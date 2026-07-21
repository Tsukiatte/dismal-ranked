"""`/rankedban` and `/unrankedban` -- barring a player from ranked play.

A ranked ban swaps the player's `+ Ranked` role for `+ Ranked Banned`, so they
keep server access but drop out of the queue. Passing a duration schedules the
lift; without one the ban stands until removed by hand.
"""

import discord
from discord.utils import get

import config
from .. import repository as repo
from .. import utils


async def _swap_roles(member, add_name, remove_name):
    """Add one role and drop another, ignoring roles that don't exist."""
    add_role = get(member.guild.roles, name=add_name)
    remove_role = get(member.guild.roles, name=remove_name)

    try:
        if add_role is not None:
            await member.add_roles(add_role)
        if remove_role is not None:
            await member.remove_roles(remove_role)
    except discord.HTTPException:
        pass


async def rankban(ctx, user=None, duration=None):
    """Toggle a ranked ban: banning an already-banned player lifts it."""
    if await utils.require_staff(ctx, config.PERM_ADMIN):
        return

    if user is None:
        await ctx.send(
            "Please mention a `user` or give a `userid` to rank ban!"
        )
        return

    member = await utils.resolve_member(ctx, user)
    if member is None:
        await ctx.send(f"`{user}` is not a valid user!")
        return

    name = utils.display_name(member)

    if utils.has_role(member, config.ROLE_RANKED_BANNED_ID):
        await _swap_roles(member, config.ROLE_RANKED, config.ROLE_RANKED_BANNED)
        repo.remove_punishment(member.id, "rankban")
        await ctx.send(f"Un-Ranked Banned `{name}`!")
        return

    seconds = utils.parse_duration(duration)
    if duration is not None and seconds is None:
        await ctx.send(f"`{duration}` is not a valid duration!")
        return

    await _swap_roles(member, config.ROLE_RANKED_BANNED, config.ROLE_RANKED)

    if seconds is not None:
        repo.add_punishment(member.id, "rankban", seconds)

    suffix = f" for `{duration}`" if seconds is not None else ""
    await ctx.send(f"Ranked banned `{name}`{suffix}!")


async def unrankban(ctx, user=None):
    if await utils.require_staff(ctx, config.PERM_ADMIN):
        return

    if user is None:
        await ctx.send(
            "Please mention a `user` or give a `userid` to un rank-ban!"
        )
        return

    member = await utils.resolve_member(ctx, user)
    if member is None:
        await ctx.send(f"`{user}` is not a valid user!")
        return

    await _swap_roles(member, config.ROLE_RANKED, config.ROLE_RANKED_BANNED)
    repo.remove_punishment(member.id, "rankban")

    await ctx.send(f"Un Ranked-banned `{utils.display_name(member)}`!")
