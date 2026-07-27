# Provider lifecycle and recovery

Provider work uses an append-only event ledger. Never erase or rewrite the history of a paid or
externally generated attempt.

Lifecycle:

1. `reserved` records the exact job fingerprint before a request.
2. `completed` records the returned artifact digest.
3. `failed` records a bounded error.
4. `rejected` records why a technically valid output failed editorial review.
5. `recovery-requested` links a correction to the failed or rejected attempt.
6. `superseded` closes an older valid result after an approved replacement.
7. `reused` records deliberate reuse of matching evidence.

`job_runner.py` writes reserve/completed/failed events automatically. The compatibility
`attempts` array remains readable, but `provider_events` is the audit authority. Check it with:

```bash
python scripts/provider_lifecycle.py audit <project>/state.json
python scripts/provider_lifecycle.py event <project>/state.json \
  --attempt-id <id> --event rejected --reason "identity contract failed"
```

An open `reserved` attempt blocks a clean handoff. Resolve it from provider evidence; do not
invent completion.
