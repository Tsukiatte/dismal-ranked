"""Elo gain and loss tables.

The ladder is deliberately compressive: low-rated players gain a lot and lose
little, and that reverses as they climb. A new player reaches mid-table in a
handful of wins, while holding a top rating means winning most games.

Nitro boosters gain slightly more per win; losses are unaffected.
"""

# (max_elo, gain, loss, booster_gain) -- the first bracket a rating fits into
# is the one that applies.
BRACKETS = [
    (100, 25, 10, 30),
    (300, 20, 15, 25),
    (600, 15, 20, 20),
]

# Applied above the last bracket.
TOP_BRACKET = (10, 25, 15)


def _bracket(elo):
    for max_elo, gain, loss, booster_gain in BRACKETS:
        if elo <= max_elo:
            return gain, loss, booster_gain
    return TOP_BRACKET


def gain(elo, booster=False):
    """Elo awarded for a win at the given rating."""
    win, _, booster_win = _bracket(elo)
    return booster_win if booster else win


def loss(elo):
    """Elo deducted for a loss at the given rating.

    The caller floors the result at zero; a player cannot go negative.
    """
    _, lose, _ = _bracket(elo)
    return lose
