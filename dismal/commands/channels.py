"""Channel management: `/lockdown`, `/unlock`, `/unlockQ`, `/fclose`.

`fclose` force-closes a stuck game; `unlockQ` clears the queue debounce flag
when a crash mid-game-creation leaves the queue refusing new joins.
"""

import config
from .. import games
from .. import repository as repo
from .. import utils

QUEUE_LOCKED = "queue_locked"


async def _set_send_messages(ctx, allowed):
    await ctx.channel.set_permissions(
        ctx.guild.default_role, send_messages=allowed
    )


async def lockdown(ctx):
    if await utils.require_staff(ctx, config.PERM_ADMIN):
        return

    await _set_send_messages(ctx, False)
    await ctx.send(f"Locked down {ctx.channel.mention}!")


async def unlock(ctx):
    if await utils.require_staff(ctx, config.PERM_ADMIN):
        return

    await _set_send_messages(ctx, True)
    await ctx.send(f"Unlocked {ctx.channel.mention}!")


async def unlock_queue(ctx):
    """Clear the debounce flag that stops two games opening at once."""
    if await utils.reject_if_restricted(ctx):
        return

    repo.set_setting(QUEUE_LOCKED, 0)
    await ctx.send("Unlocked queue!")


async def fclose(ctx):
    """Force-close a game channel and everything attached to it."""
    if await utils.require_staff(ctx, config.PERM_ADMIN):
        return

    if not games.is_game_channel(ctx.channel):
        await ctx.send("You can only close `game text channels`!")
        return

    game_id = games.game_id_from_channel(ctx.channel)

    await ctx.send(f"Closing game#`{game_id}`!")
    await games.post_result(ctx.guild, game_id, "voided")
    await games.close_channels(ctx.guild, ctx.channel)
