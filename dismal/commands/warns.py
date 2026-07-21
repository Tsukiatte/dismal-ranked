"""`/warn` and `/hwarn` -- warnings, with an automatic mute on the third.

Warnings roll: hitting three mutes the member and clears the slate, so the
next warning starts a fresh cycle at one.
"""

import discord
from discord.utils import get

import config
from .. import repository as repo
from .. import utils

WARNS_BEFORE_MUTE = 3


async def warn(ctx, user=None, reason="None"):
    if await utils.require_staff(ctx, config.PERM_ADMIN):
        return

    if user is None:
        await ctx.send("Please mention a `user` or give a `userid` to warn!")
        return

    member = await utils.resolve_member(ctx, user)
    if member is None:
        await ctx.send(f"`{user}` is not a valid user!")
        return

    total = repo.add_warn(member.id, ctx.author.id, reason)

    await ctx.send(
        f"`Successfully warned {utils.display_name(member)}` for `{reason}` "
        f"({total}/{WARNS_BEFORE_MUTE})"
    )

    if total < WARNS_BEFORE_MUTE:
        return

    muted_role = get(ctx.guild.roles, name=config.ROLE_MUTED)
    if muted_role is not None:
        try:
            await member.add_roles(muted_role)
        except discord.HTTPException:
            pass

    # Reset so the cycle starts over rather than muting on every later warn.
    repo.clear_warns(member.id)

    await ctx.send(
        f"Auto-Muted `{utils.display_name(member)}` as they have hit "
        f"**{WARNS_BEFORE_MUTE} warnings**"
    )


async def history(ctx):
    """Show the caller their own warning history."""
    warns = repo.get_warns(ctx.author.id)

    if not warns:
        await ctx.send("You have no warnings.")
        return

    lines = [
        f"**{index}.** {row['reason']} — <@{row['moderator_id']}> "
        f"(<t:{row['created_at']}:R>)"
        for index, row in enumerate(warns, start=1)
    ]

    await ctx.send(
        embed=utils.embed(
            "\n".join(lines),
            title=f"{ctx.author.name}'s Warnings ({len(warns)})",
        )
    )
