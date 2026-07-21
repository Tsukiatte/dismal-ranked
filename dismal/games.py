"""Game channel lifecycle.

Each ranked game owns a text channel (`game-123`) and three voice channels
(`Game#123 | Team 1`, `| Team 2`, `| Team Pick`). Tearing that set down --
move everyone back to the idle channel, delete the four channels, post the
result embed -- was copy-pasted into four command modules with slightly
different error handling in each. It lives here now.
"""

import discord

import config


def game_id_from_channel(channel):
    """Game channels are named `game-123`; pull the id back out."""
    try:
        return int(channel.name.replace("-", "").replace("game", ""))
    except (AttributeError, ValueError):
        return None


def is_game_channel(channel):
    category = getattr(channel, "category", None)
    return category is not None and category.id == config.CATEGORY_QUEUE


def voice_channels(guild, text_channel):
    """The three voice channels belonging to a game's text channel.

    Missing channels come back as None -- they may already have been deleted.
    """
    base = text_channel.name.replace("-", "#").replace("g", "G") + " | Team "

    return [
        discord.utils.get(guild.channels, name=base + suffix)
        for suffix in ("Pick", "1", "2")
    ]


async def close_channels(guild, text_channel):
    """Move everyone to idle, then delete the game's four channels."""
    idle_channel = guild.get_channel(config.CHANNEL_IDLE)
    channels = voice_channels(guild, text_channel)

    if idle_channel is not None:
        for channel in channels:
            if channel is None:
                continue

            for member in list(channel.members):
                try:
                    await member.move_to(idle_channel)
                except discord.HTTPException:
                    # Left voice before we got to them.
                    pass

    for channel in channels + [text_channel]:
        if channel is None:
            continue
        try:
            await channel.delete()
        except discord.HTTPException:
            pass


async def post_result(guild, game_id, status, color=None):
    """Post a game's outcome to the results channel."""
    channel = guild.get_channel(config.CHANNEL_GAMES)
    if channel is None:
        return

    icon = (
        config.EMOJI["bomb"]
        if status == "voided"
        else config.EMOJI["complete"]
    )

    await channel.send(
        embed=discord.Embed(
            title="",
            description=(
                f"{config.EMOJI['fight']} **GAME ID**: [ **``{game_id}``** ]"
                f"\n\n***status:*** [ ***`{status}`*** ] {icon}"
            ),
            color=color or config.COLOR_VOID,
        )
    )
