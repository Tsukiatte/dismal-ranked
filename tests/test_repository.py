"""Tests for the storage layer.

Each test runs against a fresh temporary database, so they can run in any
order and leave nothing behind.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class RepositoryTestCase(unittest.TestCase):
    """Base class that points the data layer at a throwaway database."""

    def setUp(self):
        from dismal import db, repository

        self.db = db
        self.repo = repository

        self._directory = tempfile.TemporaryDirectory()
        self.db.configure(os.path.join(self._directory.name, "test.db"))
        self.db.connect()

    def tearDown(self):
        self.db.close()
        self._directory.cleanup()


class TestPlayers(RepositoryTestCase):
    def test_register_creates_player(self):
        is_new = self.repo.register_player(1, "alice")

        self.assertTrue(is_new)
        self.assertEqual(self.repo.get_player(1)["username"], "alice")
        self.assertEqual(self.repo.get_player(1)["elo"], 0)

    def test_reregister_keeps_stats(self):
        self.repo.register_player(1, "alice")
        self.repo.update_player_stats(1, 50, won=True)

        is_new = self.repo.register_player(1, "alice2")

        self.assertFalse(is_new)
        player = self.repo.get_player(1)
        self.assertEqual(player["username"], "alice2")
        self.assertEqual(player["elo"], 50)
        self.assertEqual(player["wins"], 1)

    def test_unknown_player_is_none(self):
        self.assertIsNone(self.repo.get_player(999))
        self.assertFalse(self.repo.is_registered(999))

    def test_elo_floors_at_zero(self):
        self.repo.register_player(1, "alice")
        self.repo.update_player_stats(1, 10, won=True)
        self.repo.update_player_stats(1, -50, won=False)

        player = self.repo.get_player(1)
        self.assertEqual(player["elo"], 0)
        self.assertEqual(player["losses"], 1)

    def test_id_is_stored_as_text(self):
        """Int and str ids must reach the same row."""
        self.repo.register_player(123, "alice")

        self.assertIsNotNone(self.repo.get_player("123"))
        self.assertIsNotNone(self.repo.get_player(123))

    def test_set_player_field_rejects_unknown_column(self):
        self.repo.register_player(1, "alice")

        with self.assertRaises(ValueError):
            self.repo.set_player_field(1, "discord_id; DROP TABLE players", 1)


class TestLeaderboard(RepositoryTestCase):
    def setUp(self):
        super().setUp()
        for user_id, name, elo in ((1, "a", 100), (2, "b", 300), (3, "c", 200)):
            self.repo.register_player(user_id, name)
            self.repo.update_player_stats(user_id, elo, won=True)

    def test_orders_by_elo_descending(self):
        rows = self.repo.get_leaderboard()

        self.assertEqual([row["username"] for row in rows], ["b", "c", "a"])
        self.assertEqual([row["rank"] for row in rows], [1, 2, 3])

    def test_rank_lookup(self):
        self.assertEqual(self.repo.get_player_rank(2), 1)
        self.assertEqual(self.repo.get_player_rank(1), 3)
        self.assertIsNone(self.repo.get_player_rank(999))

    def test_limit_and_offset(self):
        rows = self.repo.get_leaderboard(limit=1, offset=1)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["username"], "c")


class TestGames(RepositoryTestCase):
    def test_create_game_records_captains(self):
        game_id = self.repo.create_game([1, 2, 3, 4], captain_ids=[1, 2])

        players = self.repo.get_game_players(game_id)
        captains = [row["player_id"] for row in players if row["is_captain"]]

        self.assertEqual(len(players), 4)
        self.assertEqual(sorted(captains), ["1", "2"])

    def test_team_assignment(self):
        game_id = self.repo.create_game([1, 2, 3, 4], captain_ids=[1, 2])

        self.repo.assign_player_to_team(game_id, 1, team=1, pick_order=0)
        self.repo.assign_player_to_team(game_id, 3, team=1, pick_order=1)

        self.assertEqual(self.repo.get_team(game_id, 1), ["1", "3"])
        self.assertEqual(sorted(self.repo.get_unpicked_players(game_id)),
                         ["2", "4"])

    def test_set_game_field_rejects_unknown_column(self):
        game_id = self.repo.create_game([1], captain_ids=[])

        with self.assertRaises(ValueError):
            self.repo.set_game_field(game_id, "id", 5)


class TestParties(RepositoryTestCase):
    def test_invite_and_accept(self):
        party_id = self.repo.create_party(1, 2)

        self.assertIsNotNone(self.repo.find_pending_invite(1, 2))

        self.repo.accept_party_invite(party_id, 2)
        party = self.repo.get_party(party_id)

        self.assertTrue(party["accepted"])
        self.assertEqual(party["member_id"], "2")
        self.assertIsNotNone(self.repo.get_active_party(2))

    def test_expire_only_affects_unaccepted(self):
        party_id = self.repo.create_party(1, 2)
        self.repo.accept_party_invite(party_id, 2)

        expired = self.repo.expire_unaccepted_party(party_id)

        self.assertFalse(expired)
        self.assertFalse(self.repo.get_party(party_id)["disbanded"])

    def test_expire_disbands_pending_invite(self):
        party_id = self.repo.create_party(1, 2)

        self.assertTrue(self.repo.expire_unaccepted_party(party_id))
        self.assertTrue(self.repo.get_party(party_id)["disbanded"])

    def test_disbanded_party_is_not_active(self):
        party_id = self.repo.create_party(1, 2)
        self.repo.accept_party_invite(party_id, 2)
        self.repo.disband_party(party_id)

        self.assertIsNone(self.repo.get_active_party(1))
        self.assertIsNone(self.repo.get_active_party(2))


class TestPunishments(RepositoryTestCase):
    def test_active_punishment_is_detected(self):
        self.repo.add_punishment(1, "mute", 3600)

        self.assertTrue(self.repo.has_punishment(1, "mute"))
        self.assertFalse(self.repo.has_punishment(1, "ban"))

    def test_expired_punishment_is_popped_once(self):
        self.repo.add_punishment(1, "mute", -10)

        self.assertEqual(self.repo.pop_expired_punishments("mute"), ["1"])
        self.assertEqual(self.repo.pop_expired_punishments("mute"), [])

    def test_unexpired_punishment_is_not_popped(self):
        self.repo.add_punishment(1, "ban", 3600)

        self.assertEqual(self.repo.pop_expired_punishments("ban"), [])

    def test_reapplying_replaces_expiry(self):
        self.repo.add_punishment(1, "ban", -10)
        self.repo.add_punishment(1, "ban", 3600)

        self.assertEqual(self.repo.pop_expired_punishments("ban"), [])
        self.assertTrue(self.repo.has_punishment(1, "ban"))


class TestWarns(RepositoryTestCase):
    def test_warns_accumulate_then_clear(self):
        self.assertEqual(self.repo.add_warn(1, 99, "spam"), 1)
        self.assertEqual(self.repo.add_warn(1, 99, "spam again"), 2)

        self.repo.clear_warns(1)

        self.assertEqual(self.repo.count_warns(1), 0)

    def test_warns_are_per_user(self):
        self.repo.add_warn(1, 99, "a")
        self.repo.add_warn(2, 99, "b")

        self.assertEqual(self.repo.count_warns(1), 1)
        self.assertEqual(self.repo.count_warns(2), 1)


class TestSettings(RepositoryTestCase):
    def test_set_and_read_back(self):
        self.repo.set_setting("queue_size", 8)

        self.assertEqual(self.repo.get_int_setting("queue_size"), 8)

    def test_default_when_missing(self):
        self.assertEqual(self.repo.get_int_setting("nope", 42), 42)
        self.assertIsNone(self.repo.get_setting("nope"))


class TestTransactions(RepositoryTestCase):
    def test_rollback_undoes_partial_writes(self):
        self.repo.register_player(1, "alice")

        with self.assertRaises(RuntimeError):
            with self.db.transaction():
                self.repo.update_player_stats(1, 100, won=True)
                raise RuntimeError("boom")

        self.assertEqual(self.repo.get_player(1)["elo"], 0)
        self.assertEqual(self.repo.get_player(1)["wins"], 0)


if __name__ == "__main__":
    unittest.main()
