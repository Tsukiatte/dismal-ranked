"""Bot configuration.

Every Discord snowflake the bot depends on lives here rather than being spelled
out inline across thirty modules. Moving the bot to another guild means editing
this file (or setting the matching environment variables) and nothing else.

Only the token is secret; it is read from the environment and has no default.
"""

import os

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv is optional; the environment may already be populated
    # (systemd, Docker, a hosting platform's secret store).
    pass

# --- Credentials -----------------------------------------------------------

TOKEN = os.getenv("DISCORD_TOKEN")

# --- Storage ---------------------------------------------------------------

DATABASE_PATH = os.getenv("DATABASE_PATH", "data/dismal.db")

# --- Guild -----------------------------------------------------------------

GUILD_ID = int(os.getenv("GUILD_ID", 902869390024908821))

COMMAND_PREFIX = "="

# Presence shown under the bot's name in the member list.
STREAM_NAME = "Season 1 | /help"
STREAM_URL = "https://www.twitch.tv/nokil1"

# --- Channels --------------------------------------------------------------

CHANNEL_REGISTER = 1010961203515895808
CHANNEL_COMMANDS = 1010961216178487356
# Where completed game results are posted.
CHANNEL_GAMES = 1010961247883239535
# Voice channel players are returned to when a game's channels are torn down.
CHANNEL_IDLE = 1010963156618719392
# Where submitted proof screenshots go for scorer review.
CHANNEL_SCORING = 1010964098948812981
CHANNEL_STAFF = 955871984888184852
# Voice channel players join to enter the ranked queue.
CHANNEL_QUEUE = 1010963391390687252

# --- Categories ------------------------------------------------------------

CATEGORY_QUEUE = 1010961001417543782
CATEGORY_GAMES = 927729208719990887
# Commands are refused inside this category to keep game channels clean.
CATEGORY_RESTRICTED = 962993321901449247

# --- Roles -----------------------------------------------------------------

ROLE_RANKED = "+ Ranked"
ROLE_MUTED = "+ Muted"
ROLE_RANKED_BANNED = "+ Ranked Banned"
ROLE_BRONZE = "+ Bronze"

# Note the double space -- this is the literal role name in the guild.
ROLE_STAFF = "+  Staff"

# Nitro boosters earn slightly more elo per win.
ROLE_BOOSTER_ID = 906243887998304326
# Shown as a badge on the /info stats card.
ROLE_DONOR_ID = 1008058037065490463

# --- Permissions -----------------------------------------------------------
#
# Staff tiers, lowest to highest. Each command checks against one of these
# tuples; administrators always pass.

ROLE_TRIAL_MOD_ID = 1002971954459971734
ROLE_MOD_ID = 903698626252001371
ROLE_ADMIN_ID = 1011311489661030451

ROLE_RANKED_BANNED_ID = 1010964120478175332
# Scorers review proof screenshots and run /submit and /unvoid.
ROLE_SCORER_ID = 1010961534299680880
# Pinged in the scoring channel when new proof arrives.
ROLE_SCORER_PING_ID = 1008058136663429221

# Mute, unmute and purge.
PERM_MODERATE = (ROLE_TRIAL_MOD_ID, ROLE_MOD_ID, ROLE_ADMIN_ID)
# Kick, ban and unban.
PERM_BAN = (ROLE_MOD_ID, ROLE_ADMIN_ID)
# Warn, role assignment and stat edits.
PERM_ADMIN = (ROLE_ADMIN_ID,)

# Divisions, ordered low to high: (max_elo, name, role_id, display_colour).
# A player belongs to the first bracket their elo fits into; anyone above the
# last bracket is in DIVISION_TOP.
DIVISIONS = [
    (100, "BRONZE", 1010963519090471034, (255, 99, 71)),
    (200, "SILVER", 1010616815736598549, (170, 170, 170)),
    (300, "GOLD", 1010963755783421982, (255, 170, 0)),
    (400, "PLATINUM", 1010963794459115530, (30, 144, 255)),
    (500, "DIAMOND", 1010963922293112914, (85, 255, 255)),
    (600, "EMERALD", 1010963999556386836, (0, 170, 0)),
]
DIVISION_TOP = ("RUBY", 1010964063079125072, (170, 0, 0))

# --- Queue -----------------------------------------------------------------

DEFAULT_QUEUE_SIZE = 8
PARTY_INVITE_TIMEOUT = 60  # seconds an invite stays open
MAX_USERNAME_LENGTH = 15

# --- Emoji -----------------------------------------------------------------

EMOJI = {
    "arrow": "<:arrow:1013519793808224306>",
    "bomb": "<a:bombie:1013519805183164507>",
    "complete": "<a:dc:1013519809314570240>",
    "crown": "<:dgc:1013519812997169222>",
    "fight": "<:fight:1013519819821289514>",
    "lose": "<:lose:1013519822186872882>",
    "pink": "<:dismalpinkish:1014943069726052413>",
    "point": "<:dcp1:1013519811181019216>",
    "purple": "<:dp:1014608762411163701>",
    "red": "<:dismalredish:1013519814955896963>",
    "win": "<:win:1013519831909273642>",
}

# --- Embed colours ---------------------------------------------------------

COLOR_DEFAULT = 0x6495ED
COLOR_GAME = 0xFF7AFA
COLOR_VOID = 0xF872F8


def division(elo):
    """Return (name, role_id, colour) for a rating."""
    for threshold, name, role_id, colour in DIVISIONS:
        if elo <= threshold:
            return name, role_id, colour
    return DIVISION_TOP


def division_role_id(elo):
    """Return the division role a player with `elo` should hold."""
    return division(elo)[1]


def division_name(elo):
    return division(elo)[0]


def division_colour(elo):
    return division(elo)[2]
