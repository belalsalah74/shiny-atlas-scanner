# Internal resolver design and current gap

## Goal

Resolve a consenting Trainer Code into the internal Player ID required by Shiny Atlas without a CEA/Poliswag resolver endpoint and without treating mapper IDs as account IDs.

## Flow implemented in code

1. Validate exact 12-digit Trainer Code, explicit allowlist and consent reference.
2. Use the locally provided, already-authenticated \`GameSession\` adapter.
3. Request nearby S2 map cells over the same game session (\`GET_MAP_OBJECTS\`, RPC 106) and select a usable level-1 or level-3 raid ending at least 15 minutes in the future.
4. Search Trainer Code through social RPC 5012, action 10000. The result is viewer-scoped; it is not the final Player ID.
5. Read raid state, claim only the free daily pass when offered, join a private lobby, invite the search result, and poll raid details.
6. Accept only one unique new value from \`invited_player_ids\`; validate format; leave the lobby. The flow never starts a battle and does not request a paid pass.
7. Return the resolved ID to the local caller. Logs use a keyed, short HMAC fingerprint rather than raw identity values.

## Still required for real end-to-end operation

The local **authenticated game-session transport adapter** remains the missing piece. It must implement the session interface for the operator's current client/device and target game version. The resolver API will not start without that factory configured. The mock session tests confirm our request-building and parsing logic only; they cannot prove current server compatibility. An adapter must be tested against a test account whose internal Player ID is independently known before this can be called working.

This is not solved by querying a mapper: map \`spawn_id\`/\`encounter_id\` identify spawn records, not the trainer account. Nor is the friend-search ID correct for the shiny formula.

## Protocol reference

The observed request/response flow can be compared with the public reverse-engineering reference in \`rubendgpedrosa/Poliswag/scripts/shiny_linker\` (not used as a runtime dependency):

- \`proto.py\`: protobuf wire fields
- \`lobby.py\`: friend search, raid lobby and \`invited_player_ids\` correlation
- \`remote.py\`: game map request and raid selection
- \`phone.py\` / \`native-method-redirect.js\`: an ARM64 rooted-client hook approach tied to a scanner's own session transport

The code in this repository is independently written and limited to the documented message sequence. Do not copy tokens, sessions or account information into source control. Only use accounts you own or have explicit permission to resolve.
