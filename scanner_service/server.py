"""Local-only HTTP API for the in-house identity resolver.

The server never calls a remote identity provider. It creates a local game
session via SHINY_ATLAS_SESSION_FACTORY and uses game RPCs directly through it.
Until a session factory is configured, /health returns not_configured and
lookups are refused.
"""
from __future__ import annotations

import hashlib
import hmac
import importlib
import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable
from urllib.parse import urlsplit

from .identity import RaidLobbyIdentityResolver, ResolutionError, normalize_trainer_code
from .raid_discovery import find_usable_raid

LOG = logging.getLogger("shiny_atlas_scanner")
MAX_BODY = 8192


def _load_factory(spec: str) -> Callable[[], Any] | None:
    if not spec or ":" not in spec:
        return None
    module_name, attr = spec.split(":", 1)
    if not module_name or not attr:
        return None
    module = importlib.import_module(module_name)
    factory = getattr(module, attr, None)
    if not callable(factory):
        raise RuntimeError("Configured session factory is not callable")
    return factory


def _allowed_codes() -> set[str]:
    raw = os.environ.get("SHINY_ATLAS_ALLOWED_CODES", "")
    return {item.strip() for item in raw.split(",") if re.fullmatch(r"\d{12}", item.strip())}


def _safe_fingerprint(code: str) -> str:
    # A non-reversible operational correlation value, never a raw code.
    secret = os.environ.get("SHINY_ATLAS_API_TOKEN", "local-only")
    return hmac.new(secret.encode(), code.encode(), hashlib.sha256).hexdigest()[:12]


def _resolve(code: str, consent_ref: str) -> dict[str, Any]:
    factory_spec = os.environ.get("SHINY_ATLAS_SESSION_FACTORY", "")
    if not os.environ.get("SHINY_ATLAS_API_TOKEN"):
        raise RuntimeError("not_configured: SHINY_ATLAS_API_TOKEN is missing")
    if not _allowed_codes():
        raise RuntimeError("not_configured: SHINY_ATLAS_ALLOWED_CODES must explicitly list consenting accounts")
    if code not in _allowed_codes():
        raise PermissionError("Trainer Code is not allowlisted")
    if not consent_ref or len(consent_ref) > 160:
        raise ValueError("consentRef is required and must be at most 160 characters")
    factory = _load_factory(factory_spec)
    if factory is None:
        raise RuntimeError("not_configured: local authenticated game-session adapter is missing")

    session = factory()
    try:
        raid = find_usable_raid(session)
        identity = RaidLobbyIdentityResolver(session).resolve(code, raid)
        LOG.info("resolution_succeeded code_ref=%s consent_ref_present=true", _safe_fingerprint(code))
        return {
            "status": "resolved",
            "trainerName": identity.trainer_name,
            "playerId": identity.player_id,
            "source": "game_session_raid_lobby",
        }
    except Exception as exc:
        LOG.warning("resolution_failed code_ref=%s error_type=%s", _safe_fingerprint(code), type(exc).__name__)
        raise
    finally:
        try:
            session.close()
        except Exception:
            LOG.warning("session_close_failed code_ref=%s", _safe_fingerprint(code))


class Handler(BaseHTTPRequestHandler):
    server_version = "ShinyAtlasScanner/0.1"

    def log_message(self, format: str, *args: object) -> None:
        # Avoid default logging of URL/body or identity inputs.
        return

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        expected = os.environ.get("SHINY_ATLAS_API_TOKEN", "")
        if not expected:
            self._send(503, {"status": "not_configured", "error": "Local API token is missing"})
            return False
        supplied = self.headers.get("Authorization", "")
        if not supplied.startswith("Bearer ") or not hmac.compare_digest(supplied[7:], expected):
            self._send(401, {"status": "denied", "error": "Unauthorized"})
            return False
        return True

    def do_GET(self) -> None:
        if urlsplit(self.path).path != "/health":
            self._send(404, {"status": "not_found"})
            return
        configured = bool(os.environ.get("SHINY_ATLAS_API_TOKEN")) and bool(_allowed_codes()) and bool(os.environ.get("SHINY_ATLAS_SESSION_FACTORY"))
        self._send(200 if configured else 503, {
            "status": "ready" if configured else "not_configured",
            "sessionFactoryConfigured": bool(os.environ.get("SHINY_ATLAS_SESSION_FACTORY")),
            "allowlistConfigured": bool(_allowed_codes()),
            "apiTokenConfigured": bool(os.environ.get("SHINY_ATLAS_API_TOKEN")),
        })

    def do_POST(self) -> None:
        if urlsplit(self.path).path != "/api/resolve":
            self._send(404, {"status": "not_found"})
            return
        if not self._authorized():
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_BODY:
                raise ValueError("Request body size is invalid")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("Expected a JSON object")
            code = normalize_trainer_code(payload.get("trainerCode", ""))
            consent_ref = str(payload.get("consentRef", "")).strip()
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self._send(400, {"status": "invalid_request", "error": str(exc)[:180]})
            return
        if code not in _allowed_codes():
            self._send(403, {"status": "denied", "error": "Trainer Code is not allowlisted for a consenting account"})
            return
        try:
            result = _resolve(code, consent_ref)
            self._send(200, result)
        except PermissionError as exc:
            self._send(403, {"status": "denied", "error": str(exc)})
        except ValueError as exc:
            self._send(400, {"status": "invalid_request", "error": str(exc)[:180]})
        except RuntimeError as exc:
            if str(exc).startswith("not_configured:"):
                self._send(503, {"status": "not_configured", "error": str(exc).split(":", 1)[1].strip()})
            else:
                self._send(503, {"status": "unavailable", "error": "Local game-session adapter unavailable"})
        except ResolutionError as exc:
            self._send(502, {"status": "failed", "error": str(exc)[:180]})
        except Exception as exc:
            LOG.error("unhandled_resolution_error type=%s", type(exc).__name__)
            self._send(502, {"status": "failed", "error": "The local game-session lookup failed"})


def main() -> None:
    logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(message)s")
    host = os.environ.get("SHINY_ATLAS_BIND", "127.0.0.1")
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise SystemExit("Refusing non-loopback bind: configure a private authenticated reverse proxy separately if needed")
    port = int(os.environ.get("SHINY_ATLAS_PORT", "8788"))
    server = ThreadingHTTPServer((host, port), Handler)
    LOG.info("local resolver API listening on %s:%s", host, port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
