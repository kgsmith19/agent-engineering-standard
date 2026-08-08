# Evidence & Learning

## Goal

Measure whether the system creates useful software faster, cheaper, and more reliably.

## 1. Machine evidence

Prefer machine-generated evidence over agent-written claims.

Record enough to reconstruct important runs, including:

- commit/base SHA
- issue/spec/slice
- risk profile
- checks run/results
- important capabilities granted
- protected-control changes
- artifact/deployment identity when relevant

Do not create verbose run reports unless a human needs them.

## 2. Primary optimization target

Optimize:

**accepted useful outcomes per human active minute and total cost**

subject to quality/security/reliability floors.

Do not optimize for LOC, PR count, agent count, test count, raw coverage, or token volume.

## 3. Minimum useful metrics

Track:

- human active minutes
- agent cost
- retries/interventions
- first-pass verification success
- escaped defects/reverts
- change/release failures
- product success signal

Add other metrics only when they change decisions.

## 4. Learn from failures

Repeated failures should produce improvements to:

- prompts/instructions
- tools
- context retrieval
- tests/evaluators
- architecture constraints
- model routing
- retry policy

Do not solve recurring failures by repeatedly telling the agent to try harder.

## 5. Close the loop

Telemetry may propose new ideas or maintenance work.

A proposal must still pass the normal Shape / Research → Outcome / Bet process before becoming product work.
