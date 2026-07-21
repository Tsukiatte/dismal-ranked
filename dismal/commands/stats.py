"""`/info`, `/leaderboard` and `/elo` -- rendered stat cards.

Both cards are drawn with Pillow over a pre-made background and sent as an
attachment, which is why they build a temporary PNG rather than an embed.
Images are written to a temp directory and cleaned up afterwards, instead of
into the working directory as the original did.
"""

import io
import os
import tempfile

import discord
from PIL import Image, ImageDraw, ImageFont

import config

from .. import repository as repo
from .. import utils

ASSETS = "assets"
LEADERBOARD_SIZE = 10

# Avatar slot positions on lbbackground.png, ranks 1-10.
AVATAR_SLOTS = [
    (110, 204), (110, 269), (110, 331), (110, 390), (110, 449),
    (594, 201), (594, 261), (594, 320), (594, 379), (602, 439),
]


def asset(name):
    return os.path.join(ASSETS, name)


def font(size):
    return ImageFont.truetype(asset("Inter.ttf"), size)


def text_width(font_obj, text):
    """Width of `text` in pixels.

    `ImageFont.getsize` was removed in Pillow 10; `getbbox` is the supported
    replacement and works on 9.x too.
    """
    box = font_obj.getbbox(text)
    return box[2] - box[0]


async def _avatar_image(member):
    """Fetch a member's avatar as a 45px circle-ready image.

    Falls back to the default circle asset when the member has no avatar or
    the download fails.
    """
    try:
        data = await member.avatar_url.read()
        image = Image.open(io.BytesIO(data))
    except Exception:
        image = Image.open(asset("circle.png"))

    return image.convert("RGBA").resize((45, 45))


async def leaderboard(ctx):
    if await utils.reject_if_restricted(ctx):
        return

    message = await ctx.send("Fetching statistics...")

    top = repo.get_leaderboard(limit=LEADERBOARD_SIZE)
    if not top:
        await message.edit(content="Nobody is on the leaderboard yet!")
        return

    image = Image.open(asset("lbbackground.png")).convert("RGBA")
    mask = Image.open(asset("circle.png")).convert("L").resize((45, 45))
    draw = ImageDraw.Draw(image)
    label_font = font(37)

    for row in top:
        position = AVATAR_SLOTS[row["rank"] - 1]

        member = ctx.guild.get_member(int(row["discord_id"]))
        if member is not None:
            avatar = await _avatar_image(member)
            image.paste(avatar, position, mask)

        # Draw "[elo] username" as three runs so the brackets, the number and
        # the name can each take their own colour.
        x, y = position[0] + 57, position[1]
        for text, colour in (
            ("[", (221, 160, 221)),
            (str(row["elo"]), (238, 130, 238)),
            ("]", (221, 160, 221)),
            (f" {row['username']}", (255, 255, 255)),
        ):
            draw.text((x, y), text, colour, font=label_font)
            x += text_width(label_font, text)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, "leaderboard.png")
        image.convert("RGB").save(path)
        await message.reply(file=discord.File(path))


async def info(ctx, user=None):
    if await utils.reject_if_restricted(ctx):
        return

    user_id = utils.parse_user_id(user) or ctx.author.id
    player = repo.get_player(user_id)

    if player is None:
        await ctx.send("Invalid user | ``register before running /info.``")
        return

    elo = max(0, player["elo"])
    wins, losses = player["wins"], player["losses"]
    division_name, _, division_colour = config.division(elo)

    image = Image.open(asset("dismal_stats.png")).convert("RGBA")
    draw = ImageDraw.Draw(image)

    name_font = font(42)
    value_font = font(36)

    draw.text((46, 86), player["username"], (255, 255, 255), font=name_font)

    # Each stat is centred on a fixed slot in the background image.
    stats = [
        (208, 271, str(elo), (238, 130, 238)),
        (546, 271, division_name, division_colour),
        (208, 442, str(wins), (50, 205, 50)),
        (546, 442, str(losses), (255, 23, 35)),
        (878, 271, str(wins + losses), (50, 205, 50)),
        (878, 442, str(utils.win_loss_ratio(wins, losses)), (50, 205, 50)),
    ]

    for centre_x, y, text, colour in stats:
        x = centre_x - text_width(value_font, text) / 2
        draw.text((x, y), text, colour, font=value_font)

    # Donors and admins get a badge next to their name.
    if utils.has_role(ctx.author, config.ROLE_DONOR_ID) or (
        ctx.author.guild_permissions.administrator
    ):
        badge = Image.open(asset("booster.png")).convert("RGBA").resize((50, 50))
        name_width = text_width(name_font, player["username"])
        image.paste(badge, (60 + name_width, 86), badge)

    with tempfile.TemporaryDirectory() as directory:
        path = os.path.join(directory, f"{player['username']}.png")
        image.convert("RGB").save(path)
        await ctx.send(file=discord.File(path))


async def divisions(ctx):
    """Post the division chart image."""
    if await utils.reject_if_restricted(ctx):
        return

    await ctx.send(file=discord.File(asset("DismalDivs.png")))
