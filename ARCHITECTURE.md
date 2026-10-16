# Architecture and implementation plan

## Core data model

Keep these identifiers distinct in code and storage:

| Field | Meaning | Valid source |
|---|---|---|
| `trainer_code` | User-facing 12-digit Trainer Code | User input, explicit consent |
| `player_id` | Internal account identity used by the calculation | Authorized identity-resolution adapter only |
| `encounter_id` | Unique Pokémon encounter identifier | Mapper/client record with documented semantics |
| `spawn_id` | Spawn point/source record key | Mapper feed, if available |

Never use one field as a substitute for another. In particular, `spawn_id` or `encounter_id` cannot be used to derive `player_id`.

## Interfaces

### IdentityResolver

The identity adapter should expose an interface like:

```ts
type ResolveRequest = {
  trainerCode: string;
  requestId: string;
  consentReference: string;
};

type ResolveResult =
  | { status: "resolved"; playerId: string; source: string; verifiedAt: string }
  | { status: "pending"; jobId: string; retryAfterMs: number }
  | { status: "not_configured" }
  | { status: "unsupported"; reason: string }
  | { status: "denied" }
  | { status: "failed"; retryable: boolean; reason: string };
```

The implementation must only be enabled when a documented, authorized source exists. It must not scrape private services, extract another user's private identifiers, bypass authentication, or impersonate an account. A regular Pokémon GO login may not expose the internal Player ID, so do not assume that a successful login is sufficient.

### MapperAdapter

Mapper data is a separate interface. It may return encounter/spawn metadata for a coordinate area. It has no responsibility for Trainer Code lookup.

## Recommended milestones

1. **Service foundation:** config validation, health endpoint, auth middleware, allowlist policy, queue/job model, mock adapters, tests.
2. **Identity-source proof:** document a permitted source and a successful example using a consenting test account. Validate the identifier against an independent authorized reference.
3. **Controlled-session adapter:** connect only after the documented source actually requires a client/device session. Keep credentials and session data in local secrets, not in the API service.
4. **Mapper adapter:** independent module for encounter records, with explicit field provenance.
5. **End-to-end integration:** exercise mocked and approved live test flows; verify error and timeout handling before production use.

## Security requirements

- Use HTTPS outside loopback.
- Store secrets in environment/service secret stores; never commit them.
- Avoid logging trainer codes, player IDs, session cookies or authorization headers.
- Apply per-account and per-token rate limits.
- Add job expiration, replay protection and audit records that do not expose identity values.
- Make ownership/consent explicit before looking up an account.
- Fail closed when the identity provider is absent or cannot verify a result.

## Open question blocking live identity implementation

Which authorized source can return an internal Player ID for a Trainer Code? Possibilities are an officially supported identity/API path, written permission and API credentials from a service operator, or a controlled client workflow whose data access is permitted. Do not hard-code assumptions until one of these paths is demonstrated. A mapper feed alone does not solve this.
