"""Shared helpers used across command modules.

These were originally copy-pasted into most of the thirty-odd command files:
the same mention-stripping loop, the same role check against a stringified
role list, the same "wrong channel" guard. Collecting them here keeps the
command modules to their actual logic.
"""

import discord
from discord.utils import get

import config

# --- User parsing ----------------------------------------------------------


def parse_user_id(value):
    """Extract a numeric user id from a mention, id string, or member object.

    Accepts ``<@123>``, ``<@!123>``, ``"123"``, ``123`` or a Member. Returns an
    int, or None if the value is not a usable id.
    """
    if value is None:
        return None

    if isinstance(value, (discord.Member, discord.User)):
        return value.id

    text = str(value).strip()
    for token in ("<@!", "<@", ">"):
        text = text.replace(token, "")

    try:
        return int(text)
    except ValueError:
        return None


async def resolve_member(ctx, value):
    """Resolve a mention or id to a guild Member, or None if not found."""
    user_id = parse_user_id(value)
    if user_id is None:
        return None

    member = ctx.guild.get_member(user_id)
    if member is not None:
        return member

    # Not in cache -- ask the API before giving up.
    try:
        return await ctx.guild.fetch_member(user_id)
    except discord.HTTPException:
        return None


def display_name(member):
    """`name#discriminator`, the form used throughout the bot's messages."""
    return f"{member.name}#{member.discriminator}"


# --- Permissions -----------------------------------------------------------


def has_role(member, role_id):
    """True if `member` holds the role with `role_id`."""
    return any(role.id == role_id for role in member.roles)


def has_named_role(member, role_name):
    return any(role.name == role_name for role in member.roles)


def is_staff(member, allowed_role_ids):
    """True if `member` holds any of `allowed_role_ids`, or is an admin."""
    if member.guild_permissions.administrator:
        return True

    allowed = set(allowed_role_ids)
    return any(role.id in allowed for role in member.roles)


async def require_staff(ctx, allowed_role_ids):
    """Reject the caller unless they pass `is_staff`.

    Returns True if the command should stop.
    """
    if is_staff(ctx.author, allowed_role_ids):
        return False

    await ctx.send("You don't have permission to run this command!")
    return True


def outranks_staff(member, guild):
    """True if `member` sits above the staff role and so cannot be actioned."""
    staff_role = get(guild.roles, name=config.ROLE_STAFF)
    if staff_role is None:
        return False

    return member.top_role.position > staff_role.position


def is_booster(member):
    return has_role(member, config.ROLE_BOOSTER_ID)


# --- Channel guards --------------------------------------------------------


def in_restricted_category(ctx):
    """True inside game channels, where general commands are turned off."""
    category = getattr(ctx.channel, "category", None)
    return category is not None and category.id == config.CATEGORY_RESTRICTED


async def reject_if_restricted(ctx):
    """Send the "wrong channel" notice and return True if the caller should stop."""
    if not in_restricted_category(ctx):
        return False

    await ctx.send(f"Commands are **limited** to <#{config.CHANNEL_COMMANDS}>.")
    return True


# --- Roles -----------------------------------------------------------------


async def sync_division_role(member, old_elo, new_elo):
    """Move a member between division roles when their elo crosses a bracket.

    No-op when both ratings sit in the same division, which is the common case.
    """
    old_role_id = config.division_role_id(old_elo)
    new_role_id = config.division_role_id(new_elo)

    if old_role_id == new_role_id:
        return

    guild = member.guild
    old_role = get(guild.roles, id=old_role_id)
    new_role = get(guild.roles, id=new_role_id)

    try:
        if old_role is not None:
            await member.remove_roles(old_role)
        if new_role is not None:
            await member.add_roles(new_role)
    except discord.HTTPException:
        # Missing permissions or a deleted role -- not worth failing the
        # surrounding command over.
        pass


async def set_elo_nickname(member, elo, username):
    """Rename a member to `[elo] username`.

    Fails silently: Discord refuses nickname edits on the guild owner and on
    anyone above the bot in the role hierarchy.
    """
    try:
        await member.edit(nick=f"[{elo}] {username}")
    except discord.HTTPException:
        pass


# --- Formatting ------------------------------------------------------------


def parse_duration(text, default=None):
    """Parse a duration like ``30m``, ``2h`` or ``7d`` into seconds.

    Returns `default` if the text is missing or malformed.
    """
    if not text:
        return default

    text = str(text).strip().lower()
    units = {"s": 1, "m": 60, "h": 3600, "d": 86400}

    unit = text[-1]
    if unit not in units:
        return default

    try:
        amount = int(text[:-1])
    except ValueError:
        return default

    if amount <= 0:
        return default

    return amount * units[unit]


def win_loss_ratio(wins, losses):
    """W/L as a rounded float, treating zero losses as one."""
    return round(wins / max(losses, 1), 2)


def embed(description, title="", color=config.COLOR_DEFAULT):
    """Build the standard embed used for bot replies."""
    return discord.Embed(title=title, description=description, color=color)
