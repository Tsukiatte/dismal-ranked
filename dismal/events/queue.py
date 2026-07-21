"""Ranked queue: watches the queue voice channel and starts games.

When the queue channel fills to `queue_size`, this handler:

  1. checks everyone present is registered, ejecting anyone who is not;
  2. seeds the draft -- players sorted by elo, with parties kept together;
  3. creates the game's text and voice channels and grants access;
  4. names two captains and pre-fills any party pairs onto teams;
  5. posts the draft embed and hands over to `/pick`.

A `queue_locked` flag is held for the duration of game creation so a player
joining mid-setup cannot trigger a second game from the same lobby.
"""

import discord
from discord.ext import commands

import config

from .. import repository as repo

CAPTAIN_COUNT = 2
QUEUE_LOCKED = "queue_locked"
# Partial games collapse when the pick channel empties out this far.
ABANDON_THRESHOLD = 3


class Queue(commands.Cog):
    def __init__(self, client):
        self.client = client

    # --- Entry point -------------------------------------------------------

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel is not None:
            await self._check_abandoned_game(before.channel)

        if after.channel is None or after.channel.id != config.CHANNEL_QUEUE:
            return

        await self._on_queue_join(member, after.channel)

    # --- Abandoned games ---------------------------------------------------

    async def _check_abandoned_game(self, channel):
        """Void and tear down a game whose players have all left the draft."""
        category = getattr(channel, "category", None)
        if category is None or category.id != config.CATEGORY_QUEUE:
            return

        if "Pick" not in channel.name or len(channel.members) > ABANDON_THRESHOLD:
            return

        game_id = channel.name.replace("Game#", "").replace(" | Team Pick", "")
        try:
            game_id = int(game_id)
        except ValueError:
            return

        guild = channel.guild
        team1 = discord.utils.get(guild.channels, name=f"Game#{game_id} | Team 1")
        team2 = discord.utils.get(guild.channels, name=f"Game#{game_id} | Team 2")

        # Only collapse if the team channels are empty too -- players may have
        # simply moved on to their teams.
        if len(getattr(team1, "members", [])) > 1:
            return
        if len(getattr(team2, "members", [])) > 1:
            return

        repo.set_game_field(game_id, "winner", "void")
        repo.set_game_field(game_id, "scored", 1)

        text_channel = discord.utils.get(guild.channels, name=f"game-{game_id}")
        for target in (text_channel, team1, team2, channel):
            if target is None:
                continue
            try:
                await target.delete()
            except discord.HTTPException:
                pass

    # --- Queue -------------------------------------------------------------

    async def _on_queue_join(self, member, channel):
        repo.add_to_queue(channel.id, member.id)

        occupants = list(channel.members)
        queue_size = repo.get_int_setting("queue_size", config.DEFAULT_QUEUE_SIZE)

        if len(occupants) < queue_size:
            return

        if repo.get_int_setting(QUEUE_LOCKED, 0):
            return

        if not await self._verify_registered(member.guild, occupants):
            return

        repo.set_setting(QUEUE_LOCKED, 1)
        try:
            await self._start_game(member.guild, occupants[:queue_size])
        finally:
            repo.set_setting(QUEUE_LOCKED, 0)
            repo.clear_queue(channel.id)

    async def _verify_registered(self, guild, occupants):
        """Eject unregistered players from voice. True if everyone is valid."""
        register_channel = guild.get_channel(config.CHANNEL_REGISTER)
        all_registered = True

        for occupant in occupants:
            if repo.is_registered(occupant.id):
                continue

            all_registered = False

            if register_channel is not None:
                await register_channel.send(
                    f"<@{occupant.id}> is not registered. "
                    f"Please use `/register`."
                )
            try:
                await occupant.move_to(None)
            except discord.HTTPException:
                pass

        return all_registered

    # --- Game creation -----------------------------------------------------

    def _draft_order(self, occupants):
        """Players highest elo first, with party members adjacent.

        Returns (ordered_ids, party_pairs). A party pair is a (leader, member)
        tuple that must end up on the same team.
        """
        players = []
        for occupant in occupants:
            player = repo.get_player(occupant.id)
            if player is not None:
                players.append((player["elo"], str(occupant.id)))

        players.sort(reverse=True)
        ordered = [player_id for _, player_id in players]

        pairs = []
        claimed = set()

        for player_id in ordered:
            if player_id in claimed:
                continue

            party = repo.get_active_party(player_id)
            if party is None or not party["accepted"]:
                continue

            leader, partner = party["leader_id"], party["member_id"]
            if leader in ordered and partner in ordered:
                if leader not in claimed and partner not in claimed:
                    pairs.append((leader, partner))
                    claimed.update({leader, partner})

        solo = [player_id for player_id in ordered if player_id not in claimed]
        return solo, pairs

    async def _create_channels(self, guild, game_id):
        """Create the game's four channels, hidden from everyone by default."""
        category = discord.utils.get(guild.channels, id=config.CATEGORY_QUEUE)

        pick_call = await guild.create_voice_channel(
            f"Game#{game_id} | Team Pick", category=category
        )
        team1_call = await guild.create_voice_channel(
            f"Game#{game_id} | Team 1", category=category
        )
        team2_call = await guild.create_voice_channel(
            f"Game#{game_id} | Team 2", category=category
        )
        text_channel = await guild.create_text_channel(
            f"game-{game_id}", category=category
        )

        for voice in (pick_call, team1_call, team2_call):
            await voice.set_permissions(guild.default_role, connect=False)
        await text_channel.set_permissions(
            guild.default_role, view_channel=False
        )

        return pick_call, team1_call, team2_call, text_channel

    async def _admit(self, guild, player_id, pick_call, text_channel):
        """Grant a player access to the game's channels and pull them in."""
        member = guild.get_member(int(player_id))
        if member is None:
            return

        await pick_call.set_permissions(member, connect=True, stream=True)
        await text_channel.set_permissions(
            member, view_channel=True, attach_files=True
        )

        try:
            await member.move_to(pick_call)
        except discord.HTTPException:
            pass

    async def _start_game(self, guild, occupants):
        solo, pairs = self._draft_order(occupants)

        all_players = [pid for pair in pairs for pid in pair] + solo
        if len(all_players) < CAPTAIN_COUNT:
            return

        # Captains are the two highest-rated players not already in a party.
        captains = solo[:CAPTAIN_COUNT]
        game_id = repo.create_game(all_players, captains)

        pick_call, team1_call, team2_call, text_channel = (
            await self._create_channels(guild, game_id)
        )

        # An odd number of parties means one team gets a head start, so that
        # captain picks twice in a row to even it out.
        if len(pairs) % 2 == 1:
            repo.set_game_field(game_id, "double_pick", 1)

        team_lines = {1: [], 2: []}
        remaining_lines = []

        # The first captain takes team 2, the second takes team 1, matching
        # the original seeding so team 1 always picks first.
        for index, captain_id in enumerate(captains):
            team = 2 if index == 0 else 1
            repo.assign_player_to_team(game_id, captain_id, team, 0)
            team_lines[team].append(f"CAPTAIN: <@{captain_id}>\n")

        # Parties are placed whole, alternating teams.
        for index, (leader, partner) in enumerate(pairs):
            team = 1 if index % 2 == 0 else 2
            for offset, player_id in enumerate((leader, partner)):
                repo.assign_player_to_team(
                    game_id, player_id, team, index * 2 + offset + 1
                )
                team_lines[team].append(f"PLAYER: <@{player_id}>\n")

        for player_id in solo[CAPTAIN_COUNT:]:
            player = repo.get_player(player_id)
            ratio = round(player["wins"] / max(player["losses"], 1), 2)
            remaining_lines.append(f"<@{player_id}> [ **W/L** : {ratio} ]\n")

        for player_id in all_players:
            await self._admit(guild, player_id, pick_call, text_channel)

        await self._announce(
            text_channel, game_id, team_lines, remaining_lines
        )

        # With no players left to draft, skip the pick phase entirely.
        if not remaining_lines:
            await self._skip_draft(
                guild, game_id, text_channel, pick_call, team1_call, team2_call
            )

    async def _announce(self, text_channel, game_id, team_lines, remaining):
        embed = discord.Embed(
            title="",
            description=(
                f"{config.EMOJI['pink']} **TEAM [ ``1`` ]** "
                f"{config.EMOJI['pink']}\n▔▔▔▔▔▔▔▔\n"
                + "".join(team_lines[1])
                + f"\n{config.EMOJI['point']} **TEAM [ ``2`` ]** "
                f"{config.EMOJI['point']}\n▔▔▔▔▔▔▔▔\n"
                + "".join(team_lines[2])
                + f"\n{config.EMOJI['arrow']}**REMAINING** "
                f"{config.EMOJI['arrow']}\n▔▔▔▔▔▔▔▔\n"
                + "".join(remaining)
            ),
            color=config.COLOR_GAME,
        )
        embed.set_footer(text="Prefix [ /pick @User ] •")

        await text_channel.send(embed=embed)

        if remaining:
            game = repo.get_game(game_id)
            await text_channel.send(
                f"It is currently Team **{game['pick']}**'s pick!"
            )

    async def _skip_draft(
        self, guild, game_id, text_channel, pick_call, team1_call, team2_call
    ):
        """Parties filled both teams -- move everyone straight to their vc."""
        await text_channel.send(
            "Full teams **detected**. Moving players to team calls."
        )

        for team, voice in ((1, team1_call), (2, team2_call)):
            for player_id in repo.get_team(game_id, team):
                member = guild.get_member(int(player_id))
                if member is None:
                    continue

                await voice.set_permissions(member, connect=True)
                try:
                    await member.move_to(voice)
                except discord.HTTPException:
                    pass

        repo.set_game_field(game_id, "picks_done", 1)

        try:
            await pick_call.delete()
        except discord.HTTPException:
            pass


def setup(client):
    client.add_cog(Queue(client))
