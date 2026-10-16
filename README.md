# Shiny Atlas Scanner Service

A research prototype for a **controlled and authorized client/session workflow** supporting Shiny Atlas. This project is separate from the Shiny Atlas frontend and mapper integration.

## Important distinction: Player ID discovery is not mapping

The project must solve two different problems, and must not conflate them:

1. **Trainer Code → internal Player ID resolution.** This is an account-identity/linking workflow. A 12-digit Trainer Code is not the internal Player ID used by the account-specific calculation. It cannot be converted locally by a known public formula.
2. **Map/encounter data collection.** A mapper can supply nearby Pokémon records and, depending on its schema, encounter IDs. It does not automatically reveal the internal Player ID for a Trainer Code.

The scanner/map is not the mechanism for discovering the Trainer ID. The service therefore treats identity resolution as a separate adapter with its own authorization, consent and validation requirements.

## Current status

This repository begins with the service architecture and discovery requirements. It does **not** claim to implement a working Pokémon GO protocol client, bypass account authentication, or resolve a Trainer Code without an authorized source.

A client adapter must remain replaceable and must only use a game-client/device session and account access that the operator is authorized to control. Until an approved source is connected, identity resolution should return an explicit `not_configured` / `unsupported` state rather than fabricated data.

## Proposed architecture

- **API service:** authenticates clients, applies an explicit allowlist, creates jobs, and returns status.
- **Identity-resolution adapter:** separate interface to an authorized identity source. Does not query a mapper to guess an account ID.
- **Session runner/agent:** communicates with an operator-controlled client/device environment; no credential harvesting or login bypass.
- **Mapper adapter (optional and separate):** retrieves location/encounter records, not Player ID identity.
- **Audit/test layer:** fixtures, contract tests, rate limits, job expiry, and secret-free logging.

## Identity resolution acceptance criteria

Before any live integration is marked working, it must:
- identify the authorized source of the internal Player ID;
- verify that the returned identifier matches the expected internal ID format and source contract;
- use an explicit Trainer Code allowlist or equivalent consent check;
- never infer the Player ID from a friend code, coordinates, spawn ID, or encounter ID;
- keep authentication tokens out of browser code, logs, commits, and test fixtures;
- fail closed when no supported source is configured.

## Development

This is currently an architecture and integration scaffold. Keep protocol-specific assumptions and external dependencies documented, and add deterministic mocked tests before enabling live integrations.

## Scope note

The goal is to build an independently understandable workflow, not to depend on a ready-made shiny-prediction product. That does not make private game identifiers derivable from public spawn data. A valid resolution source and authorized session are still required.
