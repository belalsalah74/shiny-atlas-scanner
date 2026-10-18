"""In-house Trainer Code -> internal Player ID resolution workflow.

The resolver speaks through a caller-supplied, already-authenticated game-client
session. It never contacts CEA, Poliswag, or a mapper. The transport must be
implemented by the operator for a client/account they are authorized to use.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import time
from typing import Protocol

from .proto import bytes_field, double_field, fields, int_field, one, packed_ints, text, varint

TRAINER_CODE_RE = re.compile(r"^[0-9]{12}$")
# Observed forms: 16/24+ hex characters or a 15-24 digit decimal identifier.
PLAYER_ID_RE = re.compile(r"^(?:[0-9a-f]{16,32}|[0-9]{15,24})$", re.IGNORECASE)
SEARCH_PLAYER_ACTION = 10000
SEARCH_SOCIAL_METHOD = 5012
GYM_INFO_METHOD = 156
RAID_DETAILS_METHOD = 163
JOIN_RAID_LOBBY_METHOD = 159
LEAVE_RAID_LOBBY_METHOD = 160
CLAIM_FREE_PASS_METHOD = 815
SEND_RAID_INVITATION_METHOD = 1504


class ResolutionError(RuntimeError):
    """The game did not produce a verifiable identity result."""


class TrainerCodeNotFound(ResolutionError):
    pass


class GameSession(Protocol):
    """Adapter contract for an operator-controlled authenticated game session."""
    host: bytes
    lat: float
    lon: float

    def rpc(self, method: int, payload: bytes = b"") -> bytes: ...
    def redirected_rpc(self, method: int, payload: bytes = b"") -> bytes:
        """Run a non-allowlisted RPC through this session's in-process hook."""
        ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class RaidGym:
    gym_id: str
    latitude: float
    longitude: float
    raid_seed: int | None = None


@dataclass(frozen=True)
class ResolvedIdentity:
    trainer_code: str
    trainer_name: str
    player_id: str
    method: str = "raid_lobby_invited_player_ids"


def normalize_trainer_code(raw: str) -> str:
    code = re.sub(r"\s+", "", str(raw or ""))
    if not TRAINER_CODE_RE.fullmatch(code):
        raise ValueError("Trainer Code must be exactly 12 digits")
    return code


def normalize_player_id(raw: str) -> str:
    value = str(raw or "").strip().lower()
    if not PLAYER_ID_RE.fullmatch(value):
        raise ResolutionError("The game returned an internal Player ID in an unrecognized format")
    return value


def _nested(data: bytes | None) -> dict[int, list]:
    return fields(data or b"")


class RaidLobbyIdentityResolver:
    """Resolve one consenting Trainer Code using one-at-a-time raid invites.

    The friend-search ID is viewer-scoped, so it is never returned as the final
    Player ID. The final ID must appear as a new value in lobby field 14
    (invited_player_ids) after inviting that search result.
    """
    def __init__(self, session: GameSession, *, sleep=time.sleep, invite_polls: int = 6,
                 poll_interval_seconds: float = 2.0):
        if invite_polls < 1 or invite_polls > 10:
            raise ValueError("invite_polls must be between 1 and 10")
        self.session = session
        self.sleep = sleep
        self.invite_polls = invite_polls
        self.poll_interval_seconds = poll_interval_seconds
        self.raid: RaidGym | None = None
        self.lobby_id: list[int] | None = None
        self.raid_seed: int | None = None
        self._known_invited: list[str] = []

    def resolve(self, raw_code: str, raid: RaidGym) -> ResolvedIdentity:
        code = normalize_trainer_code(raw_code)
        self.raid = raid
        self._ensure_raid()
        try:
            trainer_name, viewer_scoped_id = self._search(code)
            self._open_lobby()
            player_id = self._invite_and_read_id(viewer_scoped_id)
            return ResolvedIdentity(code, trainer_name, player_id)
        finally:
            self._leave_lobby()

    def _native(self, method: int, payload: bytes = b"") -> dict[int, list]:
        # The stock client/scanner path directly allows only map/gym/details
        # reads. Social search, invite, lobby join/leave and free-ticket claim
        # must go through our local nonce-checked in-process RPC redirector.
        if method in (106, GYM_INFO_METHOD, RAID_DETAILS_METHOD):
            reply = self.session.rpc(method, payload)
        else:
            reply = self.session.redirected_rpc(method, payload)
        return fields(reply)

    def _search(self, code: str) -> tuple[str, str]:
        payload = (
            int_field(1, SEARCH_PLAYER_ACTION)
            + bytes_field(2, self.session.host)
            + bytes_field(3, bytes_field(1, code))
        )
        proxy = self._native(SEARCH_SOCIAL_METHOD, payload)
        status = one(proxy, 1, 0)
        packed_reply = one(proxy, 3)
        if status not in (1, 2) or not isinstance(packed_reply, bytes):
            raise ResolutionError(f"Game social-search RPC failed (status={status})")
        host = one(proxy, 2, self.session.host)
        if isinstance(host, bytes):
            self.session.host = host
        reply = fields(packed_reply)
        result = one(reply, 1, 0)
        player_raw = one(reply, 2, b"")
        player = fields(player_raw) if isinstance(player_raw, bytes) else {}
        # Field 1 is only the ID visible to the querying account. It is used
        # as the invitation target, not as the calculation's internal ID.
        viewer_id = text(player, 1)
        trainer_name = text(player, 2)
        if result != 1 or not viewer_id or not trainer_name:
            raise TrainerCodeNotFound(f"Trainer Code was not found by the game (result={result})")
        return trainer_name, viewer_id

    def _ensure_raid(self) -> None:
        assert self.raid is not None
        gym_reply = self._native(
            GYM_INFO_METHOD,
            bytes_field(1, self.raid.gym_id)
            + double_field(2, self.raid.latitude)
            + double_field(3, self.raid.longitude)
            + double_field(4, self.raid.latitude)
            + double_field(5, self.raid.longitude),
        )
        outer = _nested(one(gym_reply, 1, b""))
        fort = _nested(one(outer, 1, b""))
        raid_info = _nested(one(fort, 20, b""))
        seed = one(raid_info, 1)
        if one(gym_reply, 4, 0) != 1 or text(fort, 1) != self.raid.gym_id or not isinstance(seed, int) or not seed:
            raise ResolutionError("The selected gym no longer has a readable raid")
        self.raid_seed = seed

    def _details(self) -> dict[int, list]:
        assert self.raid is not None and self.raid_seed is not None
        payload = (
            int_field(1, self.raid_seed)
            + bytes_field(2, self.raid.gym_id)
            + double_field(4, self.raid.latitude)
            + double_field(5, self.raid.longitude)
            + double_field(6, self.raid.latitude)
            + double_field(7, self.raid.longitude)
        )
        if self.lobby_id:
            payload += bytes_field(3, b"".join(varint(part) for part in self.lobby_id))
        return self._native(RAID_DETAILS_METHOD, payload)

    @staticmethod
    def _invited_players(lobby: dict[int, list]) -> list[str]:
        values = []
        for raw in lobby.get(14, []):
            if isinstance(raw, bytes):
                try:
                    values.append(raw.decode("utf-8"))
                except UnicodeDecodeError:
                    continue
        return values

    def _open_lobby(self) -> None:
        assert self.raid is not None and self.raid_seed is not None
        lat, lon = self.raid.latitude, self.raid.longitude
        details = self._details()
        if one(details, 4, 0) != 1:
            raise ResolutionError(f"Raid-details request failed (status={one(details, 4, 0)})")
        # Claim only the free daily pass when the response indicates one is
        # available. Never request a paid pass.
        if not one(details, 6, 0) and one(details, 7, 0):
            award = self._native(
                CLAIM_FREE_PASS_METHOD,
                bytes_field(1, self.raid.gym_id)
                + double_field(2, lat)
                + double_field(3, lon),
            )
            if one(award, 1, 0) not in (1, 3):
                raise ResolutionError(f"The game rejected the free-pass claim (status={one(award, 1, 0)})")
        here = double_field(5, lat) + double_field(6, lon) + double_field(7, lat) + double_field(8, lon)
        reply = self._native(
            JOIN_RAID_LOBBY_METHOD,
            int_field(1, self.raid_seed)
            + bytes_field(2, self.raid.gym_id)
            + int_field(4, 1)
            + here,
        )
        lobby = _nested(one(reply, 2, b""))
        lobby_id = packed_ints(lobby, 1)
        if one(reply, 1, 0) != 1 or not lobby_id or not one(lobby, 10, 0):
            raise ResolutionError(f"Could not join private raid lobby (status={one(reply, 1, 0)})")
        self.lobby_id = lobby_id
        self._known_invited = self._invited_players(lobby)

    def _invite_and_read_id(self, viewer_scoped_id: str) -> str:
        assert self.raid is not None and self.raid_seed is not None and self.lobby_id
        lat, lon = self.raid.latitude, self.raid.longitude
        payload = (
            bytes_field(1, viewer_scoped_id)
            + bytes_field(2, self.raid.gym_id)
            + bytes_field(3, b"".join(varint(part) for part in self.lobby_id))
            + double_field(4, lat)
            + double_field(5, lon)
            + int_field(6, 1)
        )
        reply = self._native(SEND_RAID_INVITATION_METHOD, payload)
        status = one(reply, 1, 0)
        if status in (4, 5, 6, 7):
            raise ResolutionError(f"The raid lobby no longer accepts invites (status={status})")
        if status != 1 or reply.get(3):
            raise ResolutionError(f"The game rejected the raid invitation (status={status})")

        for _ in range(self.invite_polls):
            details = self._details()
            lobby = _nested(one(details, 1, b""))
            invited = self._invited_players(lobby)
            fresh = [value for value in invited if value not in self._known_invited]
            if len(fresh) > 1:
                raise ResolutionError("More than one new invited_player_id appeared; cannot attribute an ID safely")
            if fresh:
                found = normalize_player_id(fresh[0])
                self._known_invited.append(fresh[0])
                return found
            self.sleep(self.poll_interval_seconds)
        raise ResolutionError("The game did not expose a new invited_player_id before timeout")

    def _leave_lobby(self) -> None:
        if not self.lobby_id or self.raid is None or self.raid_seed is None:
            return
        lobby_id = self.lobby_id
        self.lobby_id = None
        try:
            self._native(
                LEAVE_RAID_LOBBY_METHOD,
                int_field(1, self.raid_seed)
                + bytes_field(2, self.raid.gym_id)
                + bytes_field(3, b"".join(varint(part) for part in lobby_id)),
            )
        except Exception:
            # Preserve the original resolution error, but don't continue toward
            # battle. The adapter should report sanitized local transport errors.
            pass
