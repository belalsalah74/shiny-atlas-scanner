# Trainer Code → internal Player ID: discovery workstream

## Goal

Find a documented, authorized mechanism to resolve a Trainer Code to the internal game Player ID needed by Shiny Atlas. This is separate from searching for Pokémon spawn or encounter data.

## What is established

- The 12-digit Trainer Code is a friend-facing identifier.
- The prediction implementation expects an internal Player ID plus a numeric encounter ID.
- Public mapper responses can expose spawn records and sometimes encounter IDs, but these are different identifiers.
- No general local formula converting a Trainer Code into an internal Player ID is known.
- The earlier bridge to an existing third-party worker is not a standalone protocol implementation and is not the desired final dependency.

## Candidate paths to evaluate

1. **Official/authorized API or partner access** — verify whether any supported endpoint exposes the identifier and what scopes/permissions are required.
2. **Permissioned provider integration** — request written permission and API documentation from service operators. Use their documented API only.
3. **Controlled client/device experiment** — if authorized access to a test account exposes the identifier in client-visible responses, document the exact data source and verify against a known-good test record. Do not assume that an authenticated session necessarily exposes the ID.
4. **Account-owned export / user-provided identifier** — support manual entry or an explicit user-provided internal ID as a fallback, with validation and clear provenance.

## Research record template

For every candidate source, record:

- URL, contact or official documentation:
- Permission/terms status:
- Required account and client state:
- Input fields:
- Output fields and exact ID semantics:
- Test account used and consent confirmation:
- Independent validation method:
- Rate limits / retention / privacy conditions:
- Result: supported / unavailable / requires permission / rejected:
- Reproducible test fixture with secrets and personal data removed:

## Non-goals

- Do not derive account identifiers from location, spawn IDs or encounter IDs.
- Do not scrape or query private databases without permission.
- Do not collect other players' identifiers without consent.
- Do not harvest credentials or session tokens, bypass login, or impersonate users.
- Do not mark a candidate as functional until a controlled test verifies the returned ID.

## Immediate next task

Establish one permitted source with a test account before writing a live resolver. Until then, the service must return `not_configured` or `unsupported` rather than fabricated results.
