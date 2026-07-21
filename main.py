"""Dismal Ranked -- bot entrypoint.

Registers the slash commands, loads the event cogs, starts the background
tasks and the public API, then connects to Discord.

Command bodies live in `dismal/commands/`; this file is only the wiring
between Discord's command definitions and those functions. The option
builders at the top (`user_option`, `text_option`, ...) exist because the
raw `create_option` calls made up most of the original file's length.
"""

import sys

import discord
from discord.ext import commands
from discord_slash import SlashCommand, SlashContext
from discord_slash.utils.manage_commands import create_choice, create_option

import config
from dismal import api, db, tasks
from dismal.commands import (
    admin,
    channels,
    game_info,
    help as help_command,
    moderation,
    party as party_commands,
    pick as pick_command,
    ranked_ban,
    register as register_commands,
    score as score_command,
    stats,
    submit as submit_command,
    voids,
    warns,
)
from dismal.events import EXTENSIONS

# --- Client ----------------------------------------------------------------

intents = discord.Intents.default()
intents.members = True
intents.voice_states = True
intents.reactions = True

client = commands.Bot(command_prefix=config.COMMAND_PREFIX, intents=intents)
client.remove_command("help")

slash = SlashCommand(client, sync_commands=True)


# --- Option builders -------------------------------------------------------
#
# Discord's option types: 3 = string, 4 = integer, 6 = user, 8 = role.

def user_option(description="The user", required=True, name="user"):
    return create_option(
        name=name, description=description, option_type=6, required=required
    )


def text_option(name, description, required=False, choices=None):
    return create_option(
        name=name,
        description=description,
        option_type=3,
        required=required,
        choices=choices,
    )


def number_option(name, description, required=True):
    return create_option(
        name=name, description=description, option_type=4, required=required
    )


def role_option(name="role", description="The role to give"):
    return create_option(
        name=name, description=description, option_type=8, required=True
    )


DURATION_OPTION = text_option("duration", "Example: 1(m/h/d)")
REASON_TEMPLATE = "The reason to {}"


# --- Player commands -------------------------------------------------------


@slash.slash(
    name="help",
    description="Shows the help menu",
    options=[
        text_option(
            "page",
            "Which help page to show",
            choices=[
                create_choice(name=page, value=page)
                for page in ("gameplay", "mod", "scorer", "party")
            ],
        )
    ],
)
async def _help(ctx: SlashContext, page=None):
    await help_command.help(ctx, page)


@slash.slash(
    name="register",
    description="Register to play Dismal Ranked",
    options=[text_option("username", "The name you would like to use")],
)
async def _register(ctx: SlashContext, username=None):
    await register_commands.register(ctx, username)


@slash.slash(name="unregister", description="Unregister from the bot")
async def _unregister(ctx: SlashContext):
    await register_commands.unregister(ctx)


@slash.slash(
    name="info",
    description="Check your or someone else's stats",
    options=[user_option("The user to look up", required=False)],
)
async def _info(ctx: SlashContext, user=None):
    await stats.info(ctx, user)


@slash.slash(name="leaderboard", description="Shows the elo leaderboard")
async def _leaderboard(ctx: SlashContext):
    await stats.leaderboard(ctx)


@slash.slash(name="elo", description="Explains how elo is gained and lost")
async def _elo(ctx: SlashContext):
    await stats.divisions(ctx)


@slash.slash(name="fix", description="Fixes your elo roles")
async def _fix(ctx: SlashContext):
    await admin.fix(ctx)


@slash.slash(name="ping", description="Checks whether the bot is responding")
async def _ping(ctx: SlashContext):
    await admin.ping(ctx)


@slash.slash(name="hwarn", description="Check your warning history")
async def _hwarn(ctx: SlashContext):
    await warns.history(ctx)


# --- Game commands ---------------------------------------------------------


@slash.slash(
    name="game",
    description="Shows the statistics of a game",
    options=[number_option("gameid", "The game to look up")],
)
async def _game(ctx: SlashContext, gameid):
    await game_info.game(ctx, gameid)


@slash.slash(
    name="pick",
    description="Pick a user to be on your team",
    options=[user_option("The user to pick")],
)
async def _pick(ctx: SlashContext, user):
    await pick_command.pick(ctx, user)


@slash.slash(name="score", description="Submit game proof to the scorers")
async def _score(ctx: SlashContext):
    await score_command.score(client, ctx)


@slash.slash(name="void", description="Start a vote to void this game")
async def _void(ctx: SlashContext):
    await voids.void(ctx)


@slash.slash(name="ghost", description="Void a game that stopped responding")
async def _ghost(ctx: SlashContext):
    await game_info.ghost(ctx)


@slash.slash(
    name="submit",
    description="For scorers: submit a game result",
    options=[
        number_option("gameid", "The game to score"),
        text_option(
            "winner",
            "The winner of the game",
            required=True,
            choices=[
                create_choice(name="1", value="1"),
                create_choice(name="2", value="2"),
                create_choice(name="void", value="void"),
            ],
        ),
    ],
)
async def _submit(ctx: SlashContext, gameid, winner):
    await submit_command.submit(ctx, gameid, winner)


@slash.slash(
    name="unvoid",
    description="Unvoid a previously voided game",
    options=[number_option("gameid", "The game to unvoid")],
)
async def _unvoid(ctx: SlashContext, gameid):
    await voids.unvoid(ctx, gameid)


# --- Party commands --------------------------------------------------------


@slash.slash(
    name="party-invite",
    description="Invite a user to your party",
    options=[user_option("The user to invite")],
)
async def _party_invite(ctx: SlashContext, user):
    await party_commands.invite(ctx, user)


@slash.slash(
    name="party-accept",
    description="Accept a user's party invite",
    options=[user_option("The user whose invite to accept")],
)
async def _party_accept(ctx: SlashContext, user):
    await party_commands.accept(ctx, user)


@slash.slash(name="party-list", description="Lists your party members")
async def _party_list(ctx: SlashContext):
    await party_commands.show(ctx)


@slash.slash(name="party-leave", description="Leave your party")
async def _party_leave(ctx: SlashContext):
    await party_commands.leave(ctx)


# --- Moderation commands ---------------------------------------------------


@slash.slash(
    name="kick",
    description="Kicks a user",
    options=[
        user_option("The user to kick"),
        text_option("reason", REASON_TEMPLATE.format("kick")),
    ],
)
async def _kick(ctx: SlashContext, user, reason=None):
    await moderation.kick(ctx, user, reason)


@slash.slash(
    name="ban",
    description="Bans a user",
    options=[
        user_option("The user to ban"),
        DURATION_OPTION,
        text_option("reason", REASON_TEMPLATE.format("ban")),
    ],
)
async def _ban(ctx: SlashContext, user, duration=None, reason=None):
    await moderation.ban(ctx, user, duration, reason)


@slash.slash(
    name="unban",
    description="Unbans a user",
    options=[text_option("user", "The userid to unban", required=True)],
)
async def _unban(ctx: SlashContext, user):
    await moderation.unban(ctx, user)


@slash.slash(
    name="mute",
    description="Mutes a user",
    options=[
        user_option("The user to mute"),
        DURATION_OPTION,
        text_option("reason", REASON_TEMPLATE.format("mute")),
    ],
)
async def _mute(ctx: SlashContext, user, duration=None, reason=None):
    await moderation.mute(ctx, user, duration, reason)


@slash.slash(
    name="unmute",
    description="Unmutes a user",
    options=[user_option("The user to unmute")],
)
async def _unmute(ctx: SlashContext, user):
    await moderation.unmute(ctx, user)


@slash.slash(
    name="warn",
    description="Warns a user",
    options=[
        user_option("The user to warn"),
        text_option("reason", REASON_TEMPLATE.format("warn")),
    ],
)
async def _warn(ctx: SlashContext, user, reason="None"):
    await warns.warn(ctx, user, reason)


@slash.slash(
    name="role",
    description="Gives or removes a role",
    options=[user_option("The user to give a role to"), role_option()],
)
async def _role(ctx: SlashContext, user, role):
    await moderation.role(ctx, user, role)


@slash.slash(
    name="purge",
    description="Purges messages from a channel",
    options=[
        number_option("amount", "Amount of messages to purge"),
        user_option("Only purge this user's messages", required=False),
    ],
)
async def _purge(ctx: SlashContext, amount, user=None):
    await moderation.purge(ctx, amount, user)


@slash.slash(
    name="edit",
    description="Edit a player's stats",
    options=[
        user_option("The user to edit"),
        text_option(
            "field",
            "The stat to change",
            required=True,
            choices=[
                create_choice(name=field, value=field)
                for field in admin.EDITABLE_FIELDS
            ],
        ),
        number_option("value", "The new value"),
    ],
)
async def _edit(ctx: SlashContext, user, field, value):
    await admin.edit(ctx, user, field, value)


@slash.slash(
    name="rankedban",
    description="Bar a user from ranked play",
    options=[user_option("The user to ranked-ban"), DURATION_OPTION],
)
async def _rankedban(ctx: SlashContext, user, duration=None):
    await ranked_ban.rankban(ctx, user, duration)


@slash.slash(
    name="unrankedban",
    description="Restore a user's ranked access",
    options=[user_option("The user to un-ranked-ban")],
)
async def _unrankedban(ctx: SlashContext, user):
    await ranked_ban.unrankban(ctx, user)


# --- Channel commands ------------------------------------------------------


@slash.slash(name="lockdown", description="Locks down a channel")
async def _lockdown(ctx: SlashContext):
    await channels.lockdown(ctx)


@slash.slash(name="unlock", description="Unlocks a channel")
async def _unlock(ctx: SlashContext):
    await channels.unlock(ctx)


@slash.slash(
    name="unlockQ", description="Is the queue broken? Try using this command!"
)
async def _unlock_queue(ctx: SlashContext):
    await channels.unlock_queue(ctx)


@slash.slash(name="fclose", description="Force-closes a game channel")
async def _fclose(ctx: SlashContext):
    await channels.fclose(ctx)


# --- Lifecycle -------------------------------------------------------------


@client.event
async def on_ready():
    print(f"Logged in as {client.user}")

    await client.change_presence(
        activity=discord.Streaming(
            name=config.STREAM_NAME, url=config.STREAM_URL
        )
    )


def main():
    if not config.TOKEN:
        sys.exit(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and fill it "
            "in, or export the variable before starting the bot."
        )

    db.connect()

    for extension in EXTENSIONS:
        client.load_extension(extension)

    tasks.setup(client)
    api.start(client)

    try:
        client.run(config.TOKEN)
    finally:
        db.close()


if __name__ == "__main__":
    main()
