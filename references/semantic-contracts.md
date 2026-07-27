# Semantic and proof contracts

Visual polish cannot repair a wrong identity, topology, mechanism, or chart. Declare these facts
before generation:

```json
{
  "semantic_contracts": [{
    "id": "factory-flow",
    "kind": "mechanism",
    "claim": "Raw cells enter before pack assembly",
    "protected_features": ["left-to-right order"],
    "evidence": [{"kind": "reference", "ref": "source/factory-diagram.png"}]
  }]
}
```

Kinds:

- `identity`: the person, product, or brand remains recognisable.
- `topology`: spatial relationships and ordering remain correct.
- `mechanism`: cause, movement, or assembly is explained correctly.
- `infographic`: labels, units, values, and comparisons remain truthful.

Every contract needs a claim and at least one `source`, `reference`, `registered-source`, `data`,
or `manual` evidence record. Identity and topology should list protected features.

Attach proof moments to the beat that makes the claim:

```json
{
  "duration_s": 4.2,
  "proof_moments": [{
    "id": "assembly-order-visible",
    "offset_s": 2.5,
    "checks": ["input appears left", "pack appears after input"]
  }]
}
```

Compile with `editorial_contract.py`. It emits exact proof timestamps and delivery-frame
numbers, so review samples the claim itself instead of arbitrary thumbnails.

After rendering, extract those exact frames:

```bash
python scripts/proof_review.py final.mp4 reports/editorial-plan.json qa/proof
```

The report deliberately stays `pending-human-review`; a frame extraction tool cannot decide
whether a person is truly recognisable or a mechanism is factually correct.
