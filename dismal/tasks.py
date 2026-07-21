"""Background tasks.

The original bot ran three loops: a leaderboard rebuild every 60 seconds, a
JSON file backup every second, and a punishment expiry sweep every 10.

The first two are gone. The leaderboard is a SQL view, so it is always current
with no rebuild, and SQLite's write-ahead log removes the need to copy files
around -- that loop was doing six full file copies per second.

What remains is the expiry sweep, which lifts bans, mutes and ranked bans once
their timers run out.
"""

import discord
from discord.ext import tasks
from discord.utils import get

import config

from . import repository as repo

EXPIRY_INTERVAL = 10  # seconds


def setup(client):
    """Attach and start the background tasks for `client`."""

    @tasks.loop(seconds=EXPIRY_INTERVAL)
    async def expire_punishments():
        guild = client.get_guild(config.GUILD_ID)
        if guild is None:
            return

        await _lift_bans(guild)
        await _lift_role(guild, "mute", config.ROLE_MUTED)
        await _lift_role(guild, "rankban", config.ROLE_RANKED_BANNED)

    @expire_punishments.before_loop
    async def before_expiry():
        await client.wait_until_ready()

    expire_punishments.start()
    return expire_punishments


async def _lift_bans(guild):
    """Unban anyone whose timed ban has run out."""
    expired = repo.pop_expired_punishments("ban")
    if not expired:
        return

    try:
        bans = await guild.bans()
    except discord.HTTPException:
        return

    by_id = {str(entry.user.id): entry.user for entry in bans}

    for user_id in expired:
        user = by_id.get(user_id)
        if user is None:
            continue

        try:
            await guild.unban(user)
        except discord.HTTPException:
            pass


async def _lift_role(guild, kind, role_name):
    """Remove a punishment role from anyone whose timer has run out."""
    expired = repo.pop_expired_punishments(kind)
    if not expired:
        return

    role = get(guild.roles, name=role_name)
    if role is None:
        return

    for user_id in expired:
        member = guild.get_member(int(user_id))
        if member is None:
            continue

        try:
            await member.remove_roles(role)
        except discord.HTTPException:
            pass

        # A ranked ban ending restores ladder access.
        if kind == "rankban":
            ranked_role = get(guild.roles, name=config.ROLE_RANKED)
            if ranked_role is not None:
                try:
                    await member.add_roles(ranked_role)
                except discord.HTTPException:
                    pass
