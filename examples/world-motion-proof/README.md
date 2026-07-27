# Persistent World Motion Proof

This deterministic six-second fixture proves the reusable continuous-world production slice.
It is not a flattened camera pan.

The same semantic composition is separately directed and rendered as:

- [16:9](world-16x9.mp4)
- [9:16](world-9x16.mp4)
- [1:1](world-1x1.mp4)

Each output is 30 FPS and 180 frames. The composition contains far, middle, ground, and near
canonical strips with depth-ordered speeds, one screen-anchored tracked subject, two world-anchored
participants, near-layer occlusion, camera motion, signed travel requirements, and final-order
evidence.

Rebuild and verify the deterministic source surfaces:

```bash
python ../../scripts/generate_world_fixture.py --output .
python ../../scripts/world_motion.py manifest.json \
  --output proof-report.json --evidence-dir evidence
```

Render the three responsive director plans from the bundled Remotion workspace:

```bash
cd ../../workspace
npx remotion render src/remotion/index.ts CollageWorldProof \
  ../examples/world-motion-proof/world-16x9.mp4
npx remotion render src/remotion/index.ts CollageWorldProof \
  ../examples/world-motion-proof/world-9x16.mp4 \
  --props=public/world-9x16-props.json
npx remotion render src/remotion/index.ts CollageWorldProof \
  ../examples/world-motion-proof/world-1x1.mp4 \
  --props=public/world-1x1-props.json
```

The [proof report](proof-report.json) blocks wrong seams, alpha cracks, incomplete aspect
coverage, invalid depth-speed order, insufficient camera-compensated movement, incorrect signed
trajectory, and wrong final participant order.
