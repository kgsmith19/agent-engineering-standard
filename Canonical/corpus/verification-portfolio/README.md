# Verification portfolio corpus (Stage 32, #123)

Frozen, hand-adjudicated cheapest-capable selection: every
selection entry's `expected` map and `expected_total_s` must
equal `tools/verification_portfolio.select_portfolio(project)`;
rejection entries must produce their rule.
`standardctl verify-portfolio` validates the set on every run.

## Selection principle

Cheapest portfolio capable of disproving each claim, by
failure shape and kind — never by quota. Per-kind defaults:
parser → property/fuzz; adapter → contract/examples;
ui → one focused e2e; auth/state → matrix plus examples;
R0 docs → no portfolio. Other claims use the Mold default,
cost-capped against the runtime budget (fail loud on overrun).

## The no-noop rule

A no-op command (`true`, `echo ok`, `:`, `exit 0`, empty)
never satisfies a selected technique: it counts as missing.

## Cost table (seconds, Stage 32 estimates)

example 5, contract 15, scenario 20, property 30, matrix 45,
e2e 90, mutation 120, fuzz 180. Total is the deduplicated
technique sum. Stages 40-41 may recalibrate.
