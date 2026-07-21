"""`/submit` -- scorers finalise a game and apply elo changes.

This is the only place ratings move. Both teams are settled inside one
transaction, so a game can never end up half-scored: previously each player's
elo was written in its own file rewrite, and a crash midway left the winning
team paid and the losing team untouched.
"""

import config
from .. import db
from .. import elo as elo_table
from .. import repository as repo
from .. import utils

VOID = "void"


def _apply_results(game_id, winner, winning_team, losing_team, booster_ids):
    """Write every elo change for a game in one transaction.

    Returns a list of (player_id, before, after, won) so the caller can build
    the results embed without re-reading the database.
    """
    changes = []

    with db.transaction():
        for team, won in ((winning_team, True), (losing_team, False)):
            for player_id in team:
                player = repo.get_player(player_id)
                if player is None:
                    # Unregistered or since removed -- skip rather than abort
                    # the whole submission.
                    continue

                before = player["elo"]

                if won:
                    delta = elo_table.gain(
                        before, booster=player_id in booster_ids
                    )
                else:
                    delta = -elo_table.loss(before)

                repo.update_player_stats(player_id, delta, won)
                after = max(0, before + delta)

                changes.append((player_id, before, after, won))

        repo.set_game_field(game_id, "scored", 1)
        repo.set_game_field(game_id, "winner", winner)

    return changes


async def submit(ctx, game_id=None, winner=None):
    try:
        game_id = int(game_id)
    except (TypeError, ValueError):
        await ctx.send(f"`{game_id}` is not a valid number.")
        return

    if winner not in ("1", "2", VOID):
        await ctx.send(
            f"`{winner}` is not a valid winner! Please do `1` for team 1, "
            f"`2` for team 2, or `'void'` to void said game."
        )
        return

    game = repo.get_game(game_id)
    if game is None:
        await ctx.send(f"There is no game with the ID: `{game_id}`.")
        return

    if game["scored"]:
        await ctx.send(f"Game #`{game_id}` has already been scored.")
        return

    games_channel = ctx.guild.get_channel(config.CHANNEL_GAMES)

    if winner == VOID:
        repo.set_game_field(game_id, "scored", 1)
        repo.set_game_field(game_id, "winner", VOID)

        await ctx.send(f"Successfully voided game#`{game_id}`!")

        if games_channel is not None:
            await games_channel.send(
                embed=utils.embed(
                    f"{config.EMOJI['fight']} **GAME ID**: "
                    f"[ **``{game_id}``** ]\n\n"
                    f"***status:*** [ ***`voided`*** ] {config.EMOJI['bomb']}",
                    color=config.COLOR_VOID,
                )
            )
        return

    loser = "2" if winner == "1" else "1"
    winning_team = repo.get_team(game_id, int(winner))
    losing_team = repo.get_team(game_id, int(loser))

    if not winning_team or not losing_team:
        await ctx.send(f"Game #`{game_id}` has no teams to score.")
        return

    # Booster status is read once up front; it cannot change mid-submission.
    booster_ids = {
        player_id
        for player_id in winning_team
        if (member := ctx.guild.get_member(int(player_id))) is not None
        and utils.is_booster(member)
    }

    changes = _apply_results(
        game_id, winner, winning_team, losing_team, booster_ids
    )

    winning_lines = []
    losing_lines = []

    for player_id, before, after, won in changes:
        icon = config.EMOJI["win"] if won else config.EMOJI["lose"]
        line = f"<@{player_id}> **- ** ``{before}`` **>>** ``{after}`` {icon}\n"
        (winning_lines if won else losing_lines).append(line)

        member = ctx.guild.get_member(int(player_id))
        if member is None:
            continue

        await utils.sync_division_role(member, before, after)

        player = repo.get_player(player_id)
        if player is not None:
            await utils.set_elo_nickname(member, after, player["username"])

    description = (
        f"{config.EMOJI['fight']} **GAME ID:** [ ``{game_id}`` ]\n\n"
        f"{config.EMOJI['crown']}**WINNING TEAM**{config.EMOJI['crown']}\n"
        f"▔▔▔▔▔▔▔▔▔▔\n"
        + "".join(winning_lines)
        + f"\n{config.EMOJI['red']}**LOSING TEAM** {config.EMOJI['red']}\n"
        f"▔▔▔▔▔▔▔▔▔\n"
        + "".join(losing_lines)
        + f"\n***status:***  [ ***`complete`*** ] {config.EMOJI['complete']}"
    )

    await ctx.channel.send(f"Successfully scored game#`{game_id}`.")

    if games_channel is not None:
        await games_channel.send(
            embed=utils.embed(description, color=config.COLOR_GAME)
        )
