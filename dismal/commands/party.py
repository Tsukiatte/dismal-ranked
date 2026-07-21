"""`/party-*` -- two-player parties that queue together.

A party is one invite from a leader to a single other player. It exists from
the moment the invite is sent; if the invitee does not accept within
`PARTY_INVITE_TIMEOUT`, it is disbanded.
"""

import asyncio

import config

from .. import repository as repo
from .. import utils


async def invite(ctx, user):
    if await utils.reject_if_restricted(ctx):
        return

    target_id = utils.parse_user_id(user)

    if target_id == ctx.author.id:
        await ctx.send("You **can not** party yourself!")
        return

    member = await utils.resolve_member(ctx, user)
    if member is None:
        await ctx.send(
            f"`{user}` is not a **valid** user. Please **mention a user** "
            f"or **give a userid**!"
        )
        return

    if not repo.is_registered(ctx.author.id):
        await ctx.send("You are not **registered**!")
        return

    if not repo.is_registered(member.id):
        await ctx.send(
            f"``{utils.display_name(member)}`` is not **registered**!"
        )
        return

    if repo.get_active_party(ctx.author.id) is not None:
        await ctx.send("You are already in a party!")
        return

    party_id = repo.create_party(ctx.author.id, member.id)

    await ctx.send(
        f"{member.mention} has `{config.PARTY_INVITE_TIMEOUT} seconds` to "
        f"**accept** the party invite!"
    )

    await asyncio.sleep(config.PARTY_INVITE_TIMEOUT)

    # No-op if the invite was accepted while we were waiting.
    if repo.expire_unaccepted_party(party_id):
        await ctx.send(
            f"`{utils.display_name(member)}` did **not** accept the party "
            f"invite! Party has been **disbanded**."
        )


async def accept(ctx, user):
    if await utils.reject_if_restricted(ctx):
        return

    member = await utils.resolve_member(ctx, user)
    if member is None:
        await ctx.send(
            f"`{user}` is not a **valid** user. Please **mention a user** "
            f"or **give a userid**!"
        )
        return

    if repo.get_active_party(ctx.author.id) is not None:
        await ctx.send("You are already in a party!")
        return

    party = repo.find_pending_invite(member.id, ctx.author.id)
    if party is None:
        await ctx.send(
            f"You do **not** have an invite to "
            f"`{utils.display_name(member)}`'s party!"
        )
        return

    repo.accept_party_invite(party["id"], ctx.author.id)

    await ctx.send(
        f"Successfully joined `{utils.display_name(member)}`'s party!"
    )


async def leave(ctx):
    if await utils.reject_if_restricted(ctx):
        return

    party = repo.get_active_party(ctx.author.id)
    if party is None:
        await ctx.send("You are not in a party!")
        return

    repo.disband_party(party["id"])
    await ctx.send("Successfully left the party!")


async def show(ctx):
    """List the caller's current party."""
    if await utils.reject_if_restricted(ctx):
        return

    party = repo.get_active_party(ctx.author.id)
    if party is None:
        await ctx.send("You are not in a party!")
        return

    member = f"<@{party['member_id']}>" if party["member_id"] else "none"
    status = "Invite Accepted" if party["accepted"] else "Invite Pending"

    await ctx.send(
        embed=utils.embed(
            f"**Party Leader**: <@{party['leader_id']}>\n"
            f"**Party Member**: {member}\n"
            f"**Party Creation**: <t:{party['created_at']}>\n"
            f"**Party Status**: `{status}`",
            title=f"{utils.display_name(ctx.author)}'s Party",
        )
    )


async def party(ctx, subcommand, user=None):
    """Dispatch for the legacy `=party <subcommand>` prefix form."""
    handlers = {
        "invite": lambda: invite(ctx, user),
        "accept": lambda: accept(ctx, user),
        "leave": lambda: leave(ctx),
        "list": lambda: show(ctx),
    }

    handler = handlers.get(str(subcommand).lower())
    if handler is None:
        await ctx.send(
            "Accepted arguments: `list`, `invite`, `accept`, `leave`."
        )
        return

    await handler()
