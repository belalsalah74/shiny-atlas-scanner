# Identity-source investigation — 2026-10-17

## Objective

Find an authorized, reproducible way to resolve a consenting user's 12-digit Trainer Code to the internal Player ID needed by Shiny Atlas. This is **not** a map/spawn-data problem.

## Findings

### CEA (Catch 'Em All)

CEA's official site advertises a specialised **Database access** service for advanced projects and directs interested developers to contact Gohan or LTG on Discord to discuss requirements and feasibility. This is a real lead for requesting permission and asking whether their service supports the specific identity-resolution workflow; the public page does **not** document a Trainer Code → Player ID endpoint or guarantee that CEA can provide it.

Source: https://www.catch-em-all.org/mewtwo/

Next action:
- Contact CEA through its official site/Discord route.
- Describe the project and ask whether an authorized API or research arrangement can resolve a consenting test account's Trainer Code to the internal Player ID.
- Ask for API documentation, access requirements, permitted uses, rate limits, data retention and validation procedure.
- Do not assume their map or database product includes this capability.

### Poliswag

Earlier Shiny Atlas work included a resolver bridge that can queue jobs to a Poliswag linker worker, but it requires infrastructure, authorization/token and an allowlist. The bridge is not itself a resolver. No publicly documented, supported drop-in endpoint has been verified in this investigation.

Next action:
- Contact the Poliswag maintainer through its official community channel.
- Ask whether they offer a documented, permissioned identity-resolution interface and whether an integration is allowed.
- Do not reverse engineer or call private endpoints without permission.

## Technical conclusion

No public evidence found so far establishes a general formula that converts a Trainer Code to the internal Player ID. Treat the values as distinct identifiers. Mapper/spawn/encounter records are not substitutes for identity resolution.

A successful game login also does not, by itself, prove that the internal Player ID is exposed to the client. Before implementing a client-session adapter, capture a controlled test with an account the operator owns, and verify that the identifier is actually present in an authorized client-visible response. Do not collect credentials or session tokens in logs, and do not attempt to bypass authentication.

## Acceptance gate for a live resolver

A candidate source is accepted only when all are true:
1. Written permission or clear published API terms permit the integration.
2. A documented response returns the internal Player ID (not Trainer Code, encounter ID or spawn ID).
3. A consenting test account can be resolved reproducibly.
4. The result is independently validated against a legitimate reference.
5. Secrets are stored outside the repository; responses and logs redact identifiers.
6. If the source is unavailable, the service returns `not_configured` or `unsupported`, never fabricated IDs.

## Contact message draft

Hello, I'm building Shiny Atlas, an independent research project. We need to understand whether you offer an authorized way to resolve a consenting Pokémon GO user's 12-digit Trainer Code to the internal Player ID used by an account-specific calculation. This is separate from map/spawn/encounter data. Do you provide a documented API or approved research access for this use case? If so, could you share the permission process, technical documentation, access requirements, usage limits and data-retention conditions? We will only test with an account we control and will not share credentials or request access to other users' accounts without consent. Thank you.
