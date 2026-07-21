"""`/register` and `/unregister` -- joining and leaving the ranked ladder."""

import asyncio

from discord.utils import get

import config
from .. import repository as repo
from .. import utils

# Usernames are shown on the leaderboard image, so they are restricted to
# characters that render predictably in the font used there.
ALLOWED_EXTRA_CHARS = {"_", " "}


def is_valid_username(username):
    """Letters, digits, spaces and underscores only."""
    return all(
        char.isalnum() or char in ALLOWED_EXTRA_CHARS for char in username
    )


async def register(ctx, username=None):
    if ctx.channel.id != config.CHANNEL_REGISTER:
        message = await ctx.send(
            f"You can only register in <#{config.CHANNEL_REGISTER}>"
        )
        await asyncio.sleep(2)
        await message.delete()
        return

    if username is None:
        username = ctx.author.name

    if len(username) > config.MAX_USERNAME_LENGTH:
        await ctx.send(
            f"Username must be less than "
            f"``{config.MAX_USERNAME_LENGTH} characters long.``"
        )
        return

    if not is_valid_username(username):
        await ctx.send("Symbols aren't ``allowed.``")
        return

    is_new = repo.register_player(ctx.author.id, username)

    if is_new:
        await ctx.send(f"Successfully registered as `{username}`!")
    else:
        await ctx.send(f"Re-registered as `{username}`!")

    member = ctx.guild.get_member(ctx.author.id)
    if member is None:
        return

    for role_name in (config.ROLE_RANKED, "+ Bronze"):
        role = get(ctx.guild.roles, name=role_name)
        if role is not None:
            await member.add_roles(role)

    player = repo.get_player(ctx.author.id)
    await utils.set_elo_nickname(member, player["elo"], player["username"])


async def unregister(ctx):
    if not repo.is_registered(ctx.author.id):
        await ctx.send("You are not **registered**!")
        return

    repo.unregister_player(ctx.author.id)

    member = ctx.guild.get_member(ctx.author.id)
    if member is not None:
        role = get(ctx.guild.roles, name=config.ROLE_RANKED)
        if role is not None:
            await member.remove_roles(role)

    await ctx.send("Successfully **unregistered**.")
