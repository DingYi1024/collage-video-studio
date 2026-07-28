# Portfolio Production Standard v6

Use this standard for every new topic or photo production. It turns creative quality into
machine-enforced delivery surfaces instead of relying on layer counts or prose.

## Contents

1. Single production runtime
2. Production media provenance
3. Scene and shot diversity
4. Action proof
5. Project-wide composition proof
6. Delivery blockers

## 1. Single production runtime

Render the editable project directly in the project-owned Remotion workspace. Treat Python image
utilities as derivation and proof tools, not as an independent final-film renderer. FFmpeg may
encode, probe, mux, or analyze the Remotion result.

New projects set:

```json
{
  "production": {
    "quality_standard": "portfolio",
    "render_engine": "remotion"
  }
}
```

Do not approve a final whose visual master came from pre-rendered per-shot placeholder clips.

## 2. Production media provenance

Keep the three style-card attempts outside the approved production-image cap. Every production
source artifact declares one of:

- `provider-generated`, with provider and model;
- `user-supplied`;
- `licensed-stock`;
- `commissioned-art`;
- a deterministic derivative with non-empty `source_artifact_ids` that resolve to one of the
  primary classes.

Reject `placeholder: true`, test fixtures, synthetic debug plates, and unprovenanced local output.
Local vector text, data graphics, masks, crops, keyed cutouts, and registered family members are
valid derivatives; they do not replace the required story-specific scene art.

Every layer manifest includes:

```json
{
  "creative": {
    "production_ready": true,
    "shot_scale": "wide",
    "composition_pattern": "asymmetric-depth-stage",
    "environment_id": "scene-workshop",
    "source_artifact_ids": ["image:scene-workshop-source"]
  }
}
```

## 3. Scene and shot diversity

Use context plus detail. A balanced film averages at least 1.5 shots per beat; full-depth averages
at least 2.0. Across the film use wide, medium, and close/detail framing. Change the environment,
camera relationship, focal placement, and foreground occlusion when the story changes.

Do not satisfy a depth promise by dividing a full-frame layout into many transparent full-canvas
files. Every balanced/full-depth shot visibly includes rear, subject, and front/near roles.

The portfolio gate rejects:

- one composition pattern in more than 55% of balanced shots;
- one environment in more than 67% of balanced shots;
- one identical prominent subject asset in more than 60% of balanced shots;
- missing shot-scale, environment, composition-pattern, source, or depth-role declarations.

Full-depth uses stricter 45%, 55%, and 50% limits.

## 4. Action proof

Before bulk production, render one real 3–5 second scene from the same layer package and runtime
used by the final film. Show the MP4 and its six-frame contact sheet. Approval must carry a human
note and bind the manifest, video, and contact-sheet hashes.

Changing any bound input invalidates the action proof.

## 5. Project-wide composition proof

Composition proof covers every registered shot package. It records per-shot quality, semantics,
edit/proof times, evidence frames, creative metadata, and source hashes. A single representative
or final shot is not project proof.

The readiness seal binds:

- approved style proof;
- approved action proof;
- passed project-wide composition proof;
- passed creative-quality report;
- narration timing, subtitles, runtime fingerprint, and all artifacts.

## 6. Delivery blockers

Block delivery when:

- the configured render engine is not Remotion;
- a production source lacks valid provenance;
- a placeholder or test backend output reaches a final surface;
- shot, environment, composition, depth, or pose diversity misses the selected profile;
- any registered shot is absent from project-wide composition proof;
- a kinetic film has low-motion ratio above 40% or a low-motion run above 1.5 seconds;
- the encoded subtitle, narration, action proof, or readiness seal is missing or stale.

Technical validity never overrides failed creative quality. Fix the project or explicitly change
the approved production profile; do not downgrade an error to a warning.
