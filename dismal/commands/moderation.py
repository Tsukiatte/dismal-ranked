"""Moderation commands: kick, ban, unban, mute, unmute, role, purge.

Timed bans and mutes write an expiry into the `punishments` table; the
background task in `dismal/tasks.py` lifts them when they run out.

Every command here shares the same shape -- permission check, resolve the
target, refuse if the target outranks staff, act -- so that sequence lives in
`_prepare_target` rather than being repeated seven times.
"""

import asyncio

import discord
from discord.utils import get

import config

from .. import repository as repo
from .. import utils

NO_REASON = "``None``"


async def _prepare_target(ctx, user, permissions, action):
    """Run the shared guard sequence and return the target Member, or None.

    Sends the appropriate error message itself, so callers only need to check
    for None.
    """
    if await utils.require_staff(ctx, permissions):
        return None

    if user is None:
        await ctx.send(f"Mention a user to ``{action}.``")
        return None

    member = await utils.resolve_member(ctx, user)
    if member is None:
        await ctx.send(f"Invalid user! ``mention a user to {action}.``")
        return None

    if utils.outranks_staff(member, ctx.guild):
        await ctx.send(
            f"You cannot {action} a user with a role higher than "
            f"`{config.ROLE_STAFF}`!"
        )
        return None

    return member


async def kick(ctx, user=None, reason=None):
    member = await _prepare_target(ctx, user, config.PERM_BAN, "kick")
    if member is None:
        return

    reason = reason or NO_REASON

    try:
        await member.kick(reason=reason)
    except discord.HTTPException:
        await ctx.send("Mention a ``valid user``.")
        return

    await ctx.send(
        f"**{utils.display_name(member)}** has been kicked for: "
        f"**{reason}**. {config.EMOJI['purple']}"
    )


async def ban(ctx, user=None, duration=None, reason=None):
    member = await _prepare_target(ctx, user, config.PERM_BAN, "ban")
    if member is None:
        return

    reason = reason or NO_REASON
    seconds = utils.parse_duration(duration)

    if duration is not None and seconds is None:
        await ctx.send(f"`{duration}` is not a valid duration!")
        return

    try:
        await member.ban(reason=reason)
    except discord.HTTPException:
        await ctx.send("Mention a ``valid user``.")
        return

    # Recorded only for timed bans; a permanent ban has no expiry row.
    if seconds is not None:
        repo.add_punishment(member.id, "ban", seconds)

    suffix = f" for `{duration}`" if seconds is not None else ""
    await ctx.send(
        f"**{utils.display_name(member)}** has been banned{suffix} for: "
        f"**{reason}**. {config.EMOJI['purple']}"
    )


async def unban(ctx, userid=None):
    if await utils.require_staff(ctx, config.PERM_BAN):
        return

    user_id = utils.parse_user_id(userid)
    if user_id is None:
        await ctx.send("Give a userid to ``unban.``")
        return

    for ban_entry in await ctx.guild.bans():
        if ban_entry.user.id == user_id:
            await ctx.guild.unban(ban_entry.user)
            repo.remove_punishment(user_id, "ban")
            await ctx.send(
                f"<@{user_id}> has been unbanned. {config.EMOJI['purple']}"
            )
            return

    await ctx.send("The provided userid is not ``banned.``")


async def mute(ctx, user=None, duration=None, reason=None):
    member = await _prepare_target(ctx, user, config.PERM_MODERATE, "mute")
    if member is None:
        return

    reason = reason or NO_REASON
    seconds = utils.parse_duration(duration)

    if duration is not None and seconds is None:
        await ctx.send(f"`{duration}` is not a valid duration!")
        return

    muted_role = get(ctx.guild.roles, name=config.ROLE_MUTED)
    if muted_role is None:
        await ctx.send(f"The `{config.ROLE_MUTED}` role is missing.")
        return

    try:
        await member.add_roles(muted_role)
    except discord.HTTPException:
        await ctx.send("Mention a ``valid user.``")
        return

    if seconds is not None:
        repo.add_punishment(member.id, "mute", seconds)

    suffix = f" for `{duration}`" if seconds is not None else ""
    await ctx.send(
        f"**{utils.display_name(member)}** has been muted{suffix} for: "
        f"**{reason}**. {config.EMOJI['purple']}"
    )


async def unmute(ctx, user=None):
    member = await _prepare_target(ctx, user, config.PERM_MODERATE, "unmute")
    if member is None:
        return

    muted_role = get(ctx.guild.roles, name=config.ROLE_MUTED)
    if muted_role is not None:
        try:
            await member.remove_roles(muted_role)
        except discord.HTTPException:
            await ctx.send("Mention a ``valid user.``")
            return

    repo.remove_punishment(member.id, "mute")

    await ctx.send(
        f"**{utils.display_name(member)}** has been unmuted "
        f"{config.EMOJI['purple']}"
    )


async def role(ctx, user, role_name):
    """Toggle a role on a member -- adds it, or removes it if already held."""
    member = await _prepare_target(ctx, user, config.PERM_ADMIN, "manage")
    if member is None:
        return

    target_role = get(ctx.guild.roles, name=str(role_name))
    if target_role is None:
        await ctx.send(f"``{role_name}`` is not a ``valid role name.``")
        return

    staff_role = get(ctx.guild.roles, name=config.ROLE_STAFF)
    if staff_role is not None and target_role.position > staff_role.position:
        await ctx.send(
            f"You cannot give a role higher than `{config.ROLE_STAFF}`!"
        )
        return

    try:
        if target_role in member.roles:
            await member.remove_roles(target_role)
            verb, preposition = "removed", "from"
        else:
            await member.add_roles(target_role)
            verb, preposition = "added", "to"
    except discord.HTTPException:
        await ctx.send(
            f"Could not give ``{role_name}`` to "
            f"``{utils.display_name(member)}``"
        )
        return

    await ctx.send(
        f"**``{verb}``** [ **{target_role.name}** ] "
        f"**``{preposition} {utils.display_name(member)}``**. "
        f"{config.EMOJI['purple']}"
    )


async def purge(ctx, amount=0, user=None):
    if await utils.require_staff(ctx, config.PERM_MODERATE):
        return

    if amount <= 0:
        await ctx.send(
            f"Please give an amount of messages to purge! "
            f"{config.EMOJI['purple']}"
        )
        return

    check = None
    target = None

    if user is not None:
        target = await utils.resolve_member(ctx, user)
        if target is None:
            await ctx.send("User is not in the ``server.``")
            return

        def check(message):
            return message.author.id == target.id

    deleted = await ctx.channel.purge(limit=amount, check=check)

    suffix = f" sent by <@{target.id}>" if target is not None else ""
    sent = await ctx.send(
        f"Successfully purged {len(deleted)} message(s){suffix}! "
        f"{config.EMOJI['purple']}"
    )

    await asyncio.sleep(3)
    try:
        await sent.delete()
    except discord.HTTPException:
        pass
