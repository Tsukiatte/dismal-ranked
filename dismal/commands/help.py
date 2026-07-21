"""`/help` -- paged command reference.

Pages are data rather than five near-identical embed constructions, so adding
a command means editing one list entry.
"""

import discord

from .. import utils

FOOTER_ICON = (
    "https://cdn.discordapp.com/attachments/946753581233610794/"
    "964706777407045632/dismal_pink.png"
)

PAGES = {
    None: (
        "",
        "•  ``help categories``\n▔▔▔▔▔▔▔▔\n"
        "**(game) commands** - ``[help gameplay]``\n"
        "all important basic ranked bot commands.\n\n"
        "**(staff) commands** - ``[help mod]``\n"
        "all important staff commands for moderation.\n\n"
        "**(scorer) commands** - ``[help scorer]``\n"
        "all important scorer commands to approve games.\n\n"
        "**(party) commands** - ``[help party]``\n"
        "all important party commands to utilize the party system.",
    ),
    "gameplay": (
        "   ;;    gameplay",
        "•  ``game commands``\n▔▔▔▔▔▔▔\n"
        "**/register [username]**\nregisters you into the player database.\n\n"
        "**/void**\nvoids the game and doesn't deduct elo. | `5 people must react`.\n\n"
        "**/ghost**\nvoids a ghost game (a game that doesn't respond).\n\n"
        "**/pick [@user]**\npicks a player for your team. | `must be a captain`.\n\n"
        "**/score**\nsubmits proof of winning the game. | `must send 3 screenshots`.\n\n"
        "**/info [@user]**\nchecks your or someone's stats. | `must be registered`.\n\n"
        "**/leaderboard**\nsends an image of the top 10 players by elo.\n\n"
        "**/elo**\nsends an image explaining elo gain and loss.\n\n"
        "**/game [gameid]**\nshows the statistics of a game.\n\n"
        "**/fix**\nfixes your elo roles. | `can be run by anyone`",
    ),
    "mod": (
        "   ;;    mod",
        "•  ``staff commands``\n▔▔▔▔▔▔▔▔\n"
        "**/ban [@user]**\nbans the user. | `head staff / admin`.\n\n"
        "**/unban [userid]**\nunbans the user. | `head staff / admin`.\n\n"
        "**/kick [@user]**\nkicks the user. | `head staff / admin`.\n\n"
        "**/mute [@user]**\nmutes the user. | `staff / head staff`.\n\n"
        "**/unmute [@user]**\nunmutes the user. | `staff / head staff`.\n\n"
        "**/role [@user] [role]**\ngives a role to a user. | `admin`.\n\n"
        "**/purge [amount]**\ndeletes messages. | `staff / head staff`.\n\n"
        "**/fclose**\nvoids a ranked game instantly. | `admin or higher`.\n\n"
        "**/lockdown**\nlocks down a text channel. | `admin or higher`.\n\n"
        "**/unlock**\nunlocks a text channel. | `admin or higher`.\n\n"
        "**/rankedban [@user]**\nremoves a user's ranked queue access.\n\n"
        "**/unrankedban [@user]**\nrestores a user's ranked queue access.",
    ),
    "scorer": (
        "   ;;    scorer",
        "•  ``scorer commands``\n▔▔▔▔▔▔▔▔▔\n"
        "**/submit [gameid] [winner]**\napproves submitted proof. | `must be a scorer`.\n\n"
        "**/submit [gameid] void**\ndenies submitted proof. | `must be a scorer`.\n\n"
        "**/unvoid [gameid]**\nunvoids a voided game. | `must be a scorer`.",
    ),
    "party": (
        "   ;;    party",
        "•  ``party commands``\n▔▔▔▔▔▔▔▔▔\n"
        "**/party-invite [@user]**\ninvites a user to your party. | `allows duo queuing`.\n\n"
        "**/party-accept [@user]**\naccepts a party invite.\n\n"
        "**/party-list**\nshows your current party.\n\n"
        "**/party-leave**\nleaves your party.",
    ),
}

PAGE_ORDER = [None, "gameplay", "mod", "scorer", "party"]


async def help(ctx, page=None):
    if await utils.reject_if_restricted(ctx):
        return

    key = page.lower() if isinstance(page, str) else None

    if key not in PAGES:
        await ctx.send(
            "Accepted arguments: ``None, gameplay, mod, scorer, party``"
        )
        return

    suffix, description = PAGES[key]

    embed = discord.Embed(
        title=f"Help Menu{suffix}",
        description=description,
        color=0xF873F8,
    )
    embed.set_footer(
        text=f"© Dismal Ranked • {PAGE_ORDER.index(key)}/{len(PAGES) - 1}",
        icon_url=FOOTER_ICON,
    )

    await ctx.send(embed=embed)
