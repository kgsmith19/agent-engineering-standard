# Standards route corpus (Stage 52, #143)

Frozen, hand-adjudicated route tasks. Every entry's
`expected_rules` must equal the sorted rule set from
`tools/standards_route.compile(entry.task)`; clean entries
must route ROUTE_MIN..ROUTE_MAX IDs with critical rules at or
above ACK. `standardctl standards-route` validates the set on
every run.

## What the compiler proves

Stage 52 compiles the minimum complete applicable rule set
per task — never the whole registry:

- `duplicate-id` / `missing-id` / `orphan-rule` — index
  integrity (every rule once, named, homed).
- `stale-hash` / `contradictory-triggers` — derived state
  fresh, classes frozen.
- `path-expansion` — bounded focus envelopes.
- `missing-capability` — provider gaps refuse before routing.
- `registry-overload` — accidental whole-registry loads refuse.
- `malicious-task` — hostile input refused before routing.
- `critical-demotion` — critical rules keep at least ACK.
- `minimal-route` — low-risk tasks confirm minimal routes.
