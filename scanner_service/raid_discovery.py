"""Discover a usable raid from the authenticated session's own map response.

No mapper API or external service is queried. The game session must already be
owned/authorized by the operator and must implement rpc(method, payload).
"""
from __future__ import annotations

import time
from typing import Callable

from .identity import RaidGym, ResolutionError
from .proto import bytes_field, double, double_field, fields, one, varint

GET_MAP_OBJECTS = 106
RAID_LEVELS = {1, 3}
MIN_SECONDS_LEFT = 15 * 60


def _pack_varints(values: list[int]) -> bytes:
    return b"".join(varint(value) for value in values)


def map_request(latitude: float, longitude: float, cell_ids: list[int]) -> bytes:
    """Build the map request body used by the live game protocol."""
    if not cell_ids:
        raise ValueError("at least one S2 cell is required")
    return (
        bytes_field(1, _pack_varints(cell_ids))
        + bytes_field(2, _pack_varints([0] * len(cell_ids)))
        + double_field(3, latitude)
        + double_field(4, longitude)
    )


def _gym_forts(reply: dict[int, list]) -> list[dict[int, list]]:
    forts = []
    for cell_raw in reply.get(1, []):
        if not isinstance(cell_raw, bytes):
            continue
        cell = fields(cell_raw)
        for fort_raw in cell.get(3, []):
            if not isinstance(fort_raw, bytes):
                continue
            fort = fields(fort_raw)
            # Map fort type 0 is a gym; type 1 is a PokéStop.
            if one(fort, 9, 0) == 0:
                forts.append(fort)
    return forts


def select_usable_raid(reply: dict[int, list], *, now_seconds: float | None = None) -> RaidGym:
    """Select the usable level-1/3 raid ending last from a parsed map reply."""
    now_ms = int((time.time() if now_seconds is None else now_seconds) * 1000)
    usable: list[tuple[int, RaidGym]] = []
    for fort in _gym_forts(reply):
        gym_id = one(fort, 1)
        lat = double(fort, 3, float("nan"))
        lon = double(fort, 4, float("nan"))
        if not isinstance(gym_id, (str, bytes)) or not gym_id:
            continue
        if isinstance(gym_id, bytes):
            try:
                gym_id = gym_id.decode("utf-8")
            except UnicodeDecodeError:
                continue
        if not lat == lat or not lon == lon or not (-90 <= lat <= 90) or not (-180 <= lon <= 180):
            continue
        if one(fort, 31, 0):
            continue
        raid_raw = one(fort, 20, b"")
        if not isinstance(raid_raw, bytes):
            continue
        raid = fields(raid_raw)
        level = one(raid, 6, 0)
        started = one(raid, 3, 0)
        ends = one(raid, 4, 0)
        pokemon_raw = one(raid, 5, b"")
        pokemon = fields(pokemon_raw) if isinstance(pokemon_raw, bytes) else {}
        pokemon_id = one(pokemon, 2, 0)
        seed = one(raid, 1)
        if level not in RAID_LEVELS or not isinstance(started, int) or not isinstance(ends, int):
            continue
        if started >= now_ms or ends <= now_ms + MIN_SECONDS_LEFT * 1000:
            continue
        if not isinstance(pokemon_id, int) or pokemon_id <= 0:
            continue
        usable.append((ends, RaidGym(str(gym_id), lat, lon, seed if isinstance(seed, int) else None)))
    if not usable:
        raise ResolutionError("No eligible level-1/3 raid with at least 15 minutes remaining was found in the game map")
    usable.sort(key=lambda item: item[0], reverse=True)
    return usable[0][1]


def find_usable_raid(session, *, now: Callable[[], float] = time.time,
                     sleep: Callable[[float], None] = time.sleep, attempts: int = 3) -> RaidGym:
    """Request nearby S2 cells from the game and choose a usable raid.

    s2sphere is used locally for S2 cell math; no mapper or resolver endpoint
    is contacted. The session adapter is responsible for authenticated RPC.
    """
    if attempts < 1 or attempts > 5:
        raise ValueError("attempts must be between 1 and 5")
    try:
        import s2sphere
    except ImportError as exc:
        raise RuntimeError("Install requirements.txt (missing s2sphere)") from exc

    lat, lon = float(session.lat), float(session.lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("session coordinates are invalid")
    centre = s2sphere.CellId.from_lat_lng(
        s2sphere.LatLng.from_degrees(lat, lon)
    ).parent(15)
    first_ring = [centre, *centre.get_all_neighbors(15)]
    ids = {cell.id() for cell in first_ring}
    for cell in first_ring:
        ids.update(neighbour.id() for neighbour in cell.get_all_neighbors(15))
    request = map_request(lat, lon, sorted(ids))

    last_error: Exception | None = None
    for attempt in range(attempts):
        if attempt:
            sleep(2)
        try:
            reply = fields(session.rpc(GET_MAP_OBJECTS, request))
            if one(reply, 2, 0) != 1:
                raise ResolutionError("The game did not return a successful map response")
            return select_usable_raid(reply, now_seconds=now())
        except ResolutionError as exc:
            last_error = exc
            if "No eligible" not in str(exc):
                raise
        except Exception as exc:
            last_error = RuntimeError(f"Game map request failed ({type(exc).__name__})")
    if last_error:
        raise last_error
    raise ResolutionError("Could not discover a usable raid")
