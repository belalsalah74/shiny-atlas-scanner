import unittest

from scanner_service.proto import bytes_field, double_field, fields, int_field
from scanner_service.raid_discovery import select_usable_raid
from scanner_service.identity import ResolutionError


def fort(gym_id, lat, lon, *, level, end_ms, started_ms=1_799_999_000_000,
         pokemon_id=1, seed=123, excluded=0, is_gym=0):
    pokemon = int_field(2, pokemon_id)
    raid = (
        int_field(1, seed) + bytes_field(5, pokemon) + int_field(6, level)
        + int_field(3, started_ms) + int_field(4, end_ms)
    )
    return (
        bytes_field(1, gym_id) + double_field(3, lat) + double_field(4, lon)
        + int_field(9, is_gym) + bytes_field(20, raid) + int_field(31, excluded)
    )


class RaidDiscoveryTests(unittest.TestCase):
    def test_chooses_latest_ending_usable_raid(self):
        now = 1_800_000_000
        cell = b"".join([
            bytes_field(3, fort("gym-level-5", 51.0, -0.1, level=5, end_ms=(now+3600)*1000)),
            bytes_field(3, fort("gym-earlier", 51.1, -0.2, level=1, end_ms=(now+1800)*1000)),
            bytes_field(3, fort("gym-latest", 51.2, -0.3, level=3, end_ms=(now+4000)*1000)),
        ])
        reply = fields(bytes_field(1, cell) + int_field(2, 1))
        gym = select_usable_raid(reply, now_seconds=now)
        self.assertEqual(gym.gym_id, "gym-latest")
        self.assertEqual(gym.raid_seed, 123)

    def test_rejects_raids_with_less_than_15_minutes(self):
        now = 1_800_000_000
        cell = bytes_field(3, fort("gym-short", 51.0, -0.1, level=1, end_ms=(now+899)*1000))
        with self.assertRaises(ResolutionError):
            select_usable_raid(fields(bytes_field(1, cell)), now_seconds=now)

    def test_excludes_non_gym_and_ex_eligible_records(self):
        now = 1_800_000_000
        cell = b"".join([
            bytes_field(3, fort("pokestop", 51.0, -0.1, level=1, end_ms=(now+3600)*1000, is_gym=1)),
            bytes_field(3, fort("excluded", 51.0, -0.1, level=1, end_ms=(now+3600)*1000, excluded=1)),
        ])
        with self.assertRaises(ResolutionError):
            select_usable_raid(fields(bytes_field(1, cell)), now_seconds=now)


if __name__ == "__main__":
    unittest.main()
