# Shiny Atlas Scanner — in-house resolver

This repository contains an independently implemented **local Pokémon GO session resolver**. It does not call CEA, Poliswag, or any remote Trainer Code resolver API. The prediction/map application remains separate.

## Implemented here

- \`scanner_service/proto.py\`: small protobuf wire codec for the observed game message fields.
- \`scanner_service/raid_discovery.py\`: asks the authenticated game session for nearby map cells (\`GET_MAP_OBJECTS\`, method 106) and selects a usable low-tier raid from that response. No mapper endpoint is used.
- \`scanner_service/identity.py\`: searches by Trainer Code, uses the viewer-scoped friend-search ID only to send the raid invitation, then accepts the internal ID only when exactly one new \`invited_player_ids\` value appears in the lobby response. It leaves the lobby and does not start a battle.
- \`scanner_service/server.py\`: loopback-only HTTP interface with bearer auth, explicit allowlist, required consent reference, fail-closed configuration and redacted logs.
- \`tests/\`: deterministic unit tests with a fake session. These verify protocol flow and safety checks but are not proof of live-game compatibility.

## Critical current limitation

**A live authenticated game-session transport adapter is not included yet.** The API expects a locally installed module specified by \`SHINY_ATLAS_SESSION_FACTORY=module:function\`; that factory must connect the local resolver to an authenticated game session owned by the operator and provide \`rpc(method, payload)\`, \`lat\`, \`lon\`, \`host\`, and \`close()\`. Until this adapter is implemented and validated on the target game version, \`/health\` reports \`not_configured\` and live resolution is refused. The code does not invent Player IDs or fall back to an external service.

## Run tests

Python 3.10+:

\`\`\`sh
python -m unittest discover -s tests -v
\`\`\`

## Configure the local API

Install the S2 helper for local cell geometry:

\`\`\`sh
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
\`\`\`

Set an explicit allowlist containing only your own Trainer Code and codes whose owners have consented. Do not set wildcards.

\`\`\`sh
export SHINY_ATLAS_API_TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export SHINY_ATLAS_ALLOWED_CODES="REPLACE_WITH_12_DIGIT_CODE"
export SHINY_ATLAS_SESSION_FACTORY="my_local_adapter:create_session"
python -m scanner_service.server
\`\`\`

Example request:

\`\`\`sh
curl -sS http://127.0.0.1:8788/api/resolve \\
  -H "Authorization: Bearer $SHINY_ATLAS_API_TOKEN" \\
  -H 'Content-Type: application/json' \\
  -d '{"trainerCode":"REPLACE_WITH_12_DIGIT_CODE","consentRef":"my-owned-test-account"}'
\`\`\`

\`consentRef\` is a caller-provided audit label; do not put passwords or tokens in it. The raw Trainer Code and Player ID are not written to logs. Never commit game credentials, refresh tokens, or session captures.

## Workflow

1. The operator allowlists a consenting account.
2. The local adapter connects to the operator-controlled authenticated game client/session.
3. The resolver queries the game map using that session and selects a raid with at least 15 minutes remaining.
4. It runs the one-at-a-time search → invite → lobby ID correlation procedure, with the lobby always left in a \`finally\` cleanup path.
5. The service returns the validated internal Player ID to the caller for local shiny calculation.

Read [\`docs/INTERNAL_RESOLVER_DESIGN.md\`](docs/INTERNAL_RESOLVER_DESIGN.md) for protocol semantics and remaining work.
