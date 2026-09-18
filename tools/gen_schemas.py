"""Generate Canonical/schemas/*.schema.json + inventory from the owner
v5 artifact inventory (single source of truth outside the repo).
Stdlib only, byte-deterministic. Run: python tools/gen_schemas.py
"""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INV_SRC = Path(
    r'C:\Users\kyleg\OneDrive\Desktop\agent-engineering-v5-final-sdvfd-package'
    r'\agent-engineering-v5-artifact-schema-inventory.md')
OUTDIR = ROOT / 'Canonical' / 'schemas'
VERSION = '5.0.0'

REQUIRED_BY_SCHEMA = {
    'milestone-outcome.schema.json': ['milestone', 'outcome'],
    'thin-spec.schema.json': ['outcome', 'behavior_claims'],
    'slice.schema.json': ['slice', 'contract'],
    'thinness.schema.json': ['score', 'axes'],
    'disposition.schema.json': ['disposition'],
    'ready.schema.json': ['issue', 'ready'],
    'verification-mold.schema.json': ['mold', 'tests'],
    'mold-qualification.schema.json': ['qualification'],
    'task-capsule.schema.json': ['capsule', 'task'],
    'context-budget.schema.json': ['budget', 'capsule'],
    'extension-catalog.schema.json': ['catalog'],
    'extension-profile.schema.json': ['profile'],
    'provider-capability.schema.json': ['provider', 'capabilities'],
    'extensions-lock.schema.json': ['locks'],
    'standards-route.schema.json': ['route'],
    'standards-receipt.schema.json': ['receipt'],
    'work-state.schema.json': ['issue', 'branch', 'head'],
    'continuity-event.schema.json': ['event', 'at'],
    'state-snapshot.schema.json': ['snapshot', 'at'],
    'checkpoint.schema.json': ['checkpoint'],
    'writer-lease.schema.json': ['lease', 'holder'],
    'tool-execution.schema.json': ['tool', 'result'],
    'external-effect.schema.json': ['effect'],
    'failure.schema.json': ['failure', 'class'],
    'evidence-manifest.schema.json': ['evidence', 'artifacts'],
    'review-finding.schema.json': ['finding', 'severity'],
    'release-mold.schema.json': ['release', 'evidence'],
    'process-experiment.schema.json': ['experiment', 'metric'],
    'standard-lock.schema.json': ['standard', 'commit'],
}


def parse_inventory():
    text = INV_SRC.read_text(encoding='utf-8')
    rows = re.findall(
        r'^\| ([^|]+) \| ([^|]+) \| [`]([^`]+)[`] \|', text, re.M)
    assert len(rows) == 29, 'want 29 artifacts, got %d' % len(rows)
    return [(a.strip(), b.strip(), s.strip()) for a, b, s in rows]


def build_schema(artifact, authority, filename):
    name = filename.replace('.schema.json', '')
    return {
        '$schema': 'https://json-schema.org/draft/2020-12/schema',
        'name': name,
        'version': VERSION,
        'artifact': artifact,
        'durable_authority': authority,
        'description': '%s (Agent Engineering Standard v5 artifact)' % artifact,
        'type': 'object',
        'required': REQUIRED_BY_SCHEMA[filename],
        'properties': {key: {'type': 'string'} for key in
                       REQUIRED_BY_SCHEMA[filename]},
        'additionalProperties': True,
    }


def main():
    rows = parse_inventory()
    OUTDIR.mkdir(parents=True, exist_ok=True)
    inventory = []
    for artifact, authority, filename in rows:
        schema = build_schema(artifact, authority, filename)
        (OUTDIR / filename).write_text(
            json.dumps(schema, indent=2, ensure_ascii=False) + '\n',
            encoding='utf-8', newline='\n')
        inventory.append({
            'artifact': artifact,
            'durable_authority': authority,
            'schema': 'Canonical/schemas/' + filename,
            'version': VERSION,
        })
    (OUTDIR / 'INVENTORY.json').write_text(
        json.dumps(inventory, indent=2, ensure_ascii=False) + '\n',
        encoding='utf-8', newline='\n')
    print('gen_schemas: wrote %d schemas + INVENTORY.json' % len(rows))


if __name__ == '__main__':
    main()
