"""Tests for the rating tables and division brackets."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config  # noqa: E402
from dismal import elo  # noqa: E402


class TestEloTable(unittest.TestCase):
    def test_low_ratings_gain_more_than_they_lose(self):
        self.assertGreater(elo.gain(0), elo.loss(0))
        self.assertGreater(elo.gain(100), elo.loss(100))

    def test_high_ratings_lose_more_than_they_gain(self):
        self.assertLess(elo.gain(700), elo.loss(700))

    def test_gain_decreases_as_rating_climbs(self):
        gains = [elo.gain(rating) for rating in (50, 200, 500, 900)]

        self.assertEqual(gains, sorted(gains, reverse=True))

    def test_loss_increases_as_rating_climbs(self):
        losses = [elo.loss(rating) for rating in (50, 200, 500, 900)]

        self.assertEqual(losses, sorted(losses))

    def test_boosters_gain_more(self):
        for rating in (0, 150, 400, 800):
            self.assertGreater(
                elo.gain(rating, booster=True), elo.gain(rating)
            )

    def test_bracket_boundaries_are_inclusive(self):
        """A rating exactly on a threshold stays in the lower bracket."""
        self.assertEqual(elo.gain(100), 25)
        self.assertEqual(elo.gain(101), 20)


class TestDivisions(unittest.TestCase):
    def test_names_ascend_with_rating(self):
        names = [config.division_name(r) for r in (0, 150, 250, 350, 450, 550, 900)]

        self.assertEqual(
            names,
            ["BRONZE", "SILVER", "GOLD", "PLATINUM", "DIAMOND", "EMERALD",
             "RUBY"],
        )

    def test_every_division_has_a_distinct_role(self):
        role_ids = [role_id for _, _, role_id, _ in config.DIVISIONS]
        role_ids.append(config.DIVISION_TOP[1])

        self.assertEqual(len(role_ids), len(set(role_ids)))

    def test_role_matches_bracket(self):
        self.assertEqual(
            config.division_role_id(50), config.DIVISIONS[0][2]
        )
        self.assertEqual(
            config.division_role_id(10_000), config.DIVISION_TOP[1]
        )

    def test_colour_is_rgb_triple(self):
        for rating in (0, 500, 900):
            colour = config.division_colour(rating)

            self.assertEqual(len(colour), 3)
            self.assertTrue(all(0 <= channel <= 255 for channel in colour))


if __name__ == "__main__":
    unittest.main()
