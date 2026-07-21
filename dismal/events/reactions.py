"""Void voting.

`/void` posts a message with a ✅ reaction. This cog counts votes on that
message; once enough players agree, the game is voided and its channels are
torn down.

Raw reaction events are used rather than `on_reaction_add` so votes still
register on messages that fall out of the bot's message cache.
"""

import discord
from discord.ext import commands

from .. import games
from .. import repository as repo
from ..commands.voids import VOTES_REQUIRED


class Reactions(commands.Cog):
    def __init__(self, client):
        self.client = client

    def _game_for_message(self, message_id):
        row = repo.get_game_by_void_message(message_id)
        return row["game_id"] if row else None

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        game_id = self._game_for_message(payload.message_id)
        if game_id is None:
            return

        channel = self.client.get_channel(payload.channel_id)
        if channel is None:
            return

        try:
            message = await channel.fetch_message(payload.message_id)
        except discord.HTTPException:
            return

        # The bot's own seed reaction is not a player vote.
        votes = max(0, message.reactions[0].count - 1)
        repo.set_game_field(game_id, "voids", votes)

        if votes < VOTES_REQUIRED:
            return

        repo.set_game_field(game_id, "winner", "void")
        repo.set_game_field(game_id, "scored", 1)

        await channel.send(f"Successfully voided game#`{game_id}`!")
        await games.post_result(channel.guild, game_id, "voided")
        await games.close_channels(channel.guild, channel)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload):
        game_id = self._game_for_message(payload.message_id)
        if game_id is None:
            return

        game = repo.get_game(game_id)
        if game is not None and game["voids"] > 0:
            repo.set_game_field(game_id, "voids", game["voids"] - 1)


def setup(client):
    client.add_cog(Reactions(client))
