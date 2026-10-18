import unittest

from scanner_service.identity import RaidGym, RaidLobbyIdentityResolver, ResolutionError, normalize_trainer_code
from scanner_service.proto import bytes_field, double_field, fields, int_field, varint


class FakeSession:
    host = b""
    lat = 51.5
    lon = -0.12

    def __init__(self):
        self.invited = []
        self.calls = []
        self.gym_id = "gym-1"
        self.real_id = "0123456789abcdef01234567"
        self.seen_id = "viewer-scoped-id"

    def rpc(self, method, payload=b""):
        self.calls.append(method)
        if method == 5012:
            player = bytes_field(1, self.seen_id) + bytes_field(2, "Test Trainer")
            reply = int_field(1, 1) + bytes_field(2, player)
            return int_field(1, 1) + bytes_field(2, b"host-2") + bytes_field(3, reply)
        if method == 156:
            raid = int_field(1, 789)
            fort = bytes_field(1, self.gym_id) + bytes_field(20, raid)
            outer = bytes_field(1, fort)
            return bytes_field(1, outer) + int_field(4, 1)
        if method == 163:
            lobby = b"".join(bytes_field(14, value) for value in self.invited)
            return bytes_field(1, lobby) + int_field(4, 1) + int_field(6, 1)
        if method == 159:
            lobby = bytes_field(1, varint(123)) + int_field(10, 1)
            return int_field(1, 1) + bytes_field(2, lobby)
        if method == 1504:
            self.invited.append(self.real_id)
            return int_field(1, 1)
        if method in (160, 815):
            return int_field(1, 1)
        raise AssertionError(f"Unexpected RPC method {method}")

    def redirected_rpc(self, method, payload=b""):
        self.calls.append(("redirected", method))
        return self.rpc(method, payload)

    def close(self):
        pass


class IdentityTests(unittest.TestCase):
    def test_trainer_code_validation(self):
        self.assertEqual(normalize_trainer_code("035 287 579 185"), "035287579185")
        with self.assertRaises(ValueError):
            normalize_trainer_code("12345678901")

    def test_end_to_end_resolves_lobby_id_not_search_id(self):
        session = FakeSession()
        resolver = RaidLobbyIdentityResolver(session, sleep=lambda _: None, invite_polls=1)
        result = resolver.resolve("035287579185", RaidGym("gym-1", 51.5, -0.12))
        self.assertEqual(result.player_id, session.real_id)
        self.assertNotEqual(result.player_id, session.seen_id)
        self.assertEqual(result.trainer_name, "Test Trainer")
        self.assertIn(("redirected", 5012), session.calls)
        self.assertIn(("redirected", 1504), session.calls)
        self.assertIn(163, session.calls)
        self.assertEqual(session.calls[-2:], [("redirected", 160), 160])

    def test_rejects_ambiguous_multiple_new_ids(self):
        class AmbiguousSession(FakeSession):
            def rpc(self, method, payload=b""):
                result = super().rpc(method, payload)
                if method == 1504:
                    self.invited.append("abcdef0123456789")
                return result
        session = AmbiguousSession()
        resolver = RaidLobbyIdentityResolver(session, sleep=lambda _: None, invite_polls=1)
        with self.assertRaises(ResolutionError):
            resolver.resolve("035287579185", RaidGym("gym-1", 51.5, -0.12))

    def test_always_leaves_lobby_after_invite_failure(self):
        class BadInviteSession(FakeSession):
            def rpc(self, method, payload=b""):
                if method == 1504:
                    self.calls.append(method)
                    return int_field(1, 2)
                return super().rpc(method, payload)
        session = BadInviteSession()
        resolver = RaidLobbyIdentityResolver(session, sleep=lambda _: None, invite_polls=1)
        with self.assertRaises(ResolutionError):
            resolver.resolve("035287579185", RaidGym("gym-1", 51.5, -0.12))
        self.assertEqual(session.calls[-1], 160)


if __name__ == "__main__":
    unittest.main()
