# Aspect direction

Resolve aspect from distribution, staging, and subject motion. Aspect does not repair bad
animation; it only changes the room available for choreography.

## Default policy

`studio.py init` defaults to `--aspect auto` and stores a concrete delivery aspect plus an
`aspect_policy` explanation.

- Explicit user or platform requirements always win.
- Choose `16:9` for spatial stories, side-to-side travel, multiple subjects, environmental
  cause-and-effect, wide paper stages, and landscape establishing shots.
- Choose `9:16` for a single dominant subject, mobile feed delivery, stacked compositions,
  direct-to-camera speech, and short vertical hooks.
- Use `4:5` when a feed-first composition needs more horizontal context than 9:16.
- Match existing footage when restyling; do not crop a performance silently.

## Paper-animation consequences

Landscape gives a paper stage room for foreground occlusion, entrance and exit zones, and stable
left-to-right eyelines. Portrait needs shorter paths, fewer simultaneous hero objects, stronger
vertical depth, and larger safe areas for captions.

Do not choose landscape merely to hide a flashing pose or sliding cutout. Fix registration,
pivots, contact, and shot boundaries first.

## Review

Before style generation, confirm:

1. target platform;
2. dominant subject count;
3. main motion direction;
4. caption and UI safe areas;
5. whether the source already has a fixed aspect.
