"""`/score` -- players submit proof screenshots for scorer review.

The command waits for the caller's next message in the channel, checks it
carries exactly `REQUIRED_SCREENSHOTS` images, forwards them to the scoring
channel, and closes the game's channels. A scorer then runs `/submit` to
apply the result.
"""

import asyncio
import io

import discord

import config

from .. import games
from .. import repository as repo

REQUIRED_SCREENSHOTS = 3
IMAGE_EXTENSIONS = (".png", ".jpeg", ".jpg", ".gif")
UPLOAD_TIMEOUT = 120  # seconds to wait for the proof message


def is_image(attachment):
    return attachment.filename.lower().endswith(IMAGE_EXTENSIONS)


async def score(client, ctx):
    if not games.is_game_channel(ctx.channel):
        await ctx.send("This is not a ``game channel.``")
        return

    game_id = games.game_id_from_channel(ctx.channel)
    game = repo.get_game(game_id) if game_id is not None else None

    if game is None:
        await ctx.send("This is not a ``game channel.``")
        return

    if game["proof"]:
        await ctx.send(
            f"There is already submitted proof for game#`{game_id}`."
        )
        return

    await ctx.send(
        f"Please send a message with {REQUIRED_SCREENSHOTS} images as "
        f"attachments!"
    )

    def check(message):
        return (
            message.channel == ctx.channel and message.author == ctx.author
        )

    try:
        message = await client.wait_for(
            "message", check=check, timeout=UPLOAD_TIMEOUT
        )
    except asyncio.TimeoutError:
        await ctx.send("Timed out waiting for proof. Run `/score` again.")
        return

    images = [a for a in message.attachments if is_image(a)]

    if len(images) != REQUIRED_SCREENSHOTS:
        await ctx.send(
            f"Please provide exactly ``{REQUIRED_SCREENSHOTS} screenshots.``"
        )
        return

    # Read attachments into memory rather than writing them to disk and
    # deleting them afterwards, as the original did.
    files = []
    for index, attachment in enumerate(images, start=1):
        data = await attachment.read()
        files.append(
            discord.File(io.BytesIO(data), filename=f"game{game_id}-{index}.png")
        )

    repo.set_game_field(game_id, "proof", 1)

    scoring_channel = ctx.guild.get_channel(config.CHANNEL_SCORING)

    if scoring_channel is not None:
        team_one = "\n".join(
            f"<@{pid}>" for pid in repo.get_team(game_id, 1)
        )
        team_two = "\n".join(
            f"<@{pid}>" for pid in repo.get_team(game_id, 2)
        )

        await scoring_channel.send(
            f"game{game_id} results! Scored by (<@{ctx.author.id}>) "
            f"<@&{config.ROLE_SCORER_PING_ID}>",
            files=files,
        )
        await scoring_channel.send(
            f"TEAM ONE\n===========\n{team_one}\n\n"
            f"TEAM TWO\n===========\n{team_two}"
        )

    await ctx.send(
        f"`Game#{game_id}` has been scored. ``closing channels!``"
    )

    await games.close_channels(ctx.guild, ctx.channel)
