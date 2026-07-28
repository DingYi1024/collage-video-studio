import React from 'react';
import {AbsoluteFill, Audio, Img, interpolate, Sequence, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {directedManifest} from '../lib/manifest';
import {transformAt} from '../lib/motion';
import type {EditorProps, Node} from '../lib/types';
import {PrimitiveView} from './Primitive';

const NodeView: React.FC<{
  node: Node;
  time: number;
  camera: ReturnType<typeof transformAt>;
  canvas: [number, number];
  events: NonNullable<EditorProps['manifest']['events']>;
  worldOffsetPx?: number;
  participantAnchor?: 'screen' | 'world';
}> = ({
  node,
  time,
  camera,
  canvas,
  events,
  worldOffsetPx = 0,
  participantAnchor = 'screen',
}) => {
  const keyframes = node.motion_policy === 'locked-static'
    ? node.keyframes?.slice(0, 1)
    : node.keyframes;
  const own = transformAt(keyframes, time);
  const depth = node.depth ?? 0;
  const x = own.x - camera.x * depth
    + (participantAnchor === 'world' ? worldOffsetPx : 0);
  const y = own.y - camera.y * depth;
  const scale = own.scale * (1 + (camera.scale - 1) * depth);
  const visibilityEvents = node.visibility?.events ?? [];
  let visible = node.visibility?.initial !== 'hidden';
  let visibilityOpacity = visible ? 1 : 0;
  for (const event of visibilityEvents) {
    if (time < event.at_s) break;
    const duration = Math.max(0, event.duration_s ?? 0);
    const target = event.action === 'show' ? 1 : 0;
    const start = event.action === 'show' ? 0 : 1;
    if (duration > 0 && time < event.at_s + duration) {
      visibilityOpacity = interpolate(
        time,
        [event.at_s, event.at_s + duration],
        [start, target],
        {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
      );
      break;
    }
    visible = event.action === 'show';
    visibilityOpacity = visible ? 1 : 0;
  }
  const emphasis = events.find(
    (event) =>
      event.kind === 'emphasis' &&
      event.target_id === node.id &&
      time >= event.from_s &&
      time <= event.to_s,
  );
  const emphasisProgress = emphasis
    ? (time - emphasis.from_s) / Math.max(0.001, emphasis.to_s - emphasis.from_s)
    : 0;
  const emphasisScale = emphasis
    ? 1 + Math.sin(Math.PI * emphasisProgress) * 0.055
    : 1;
  const style: React.CSSProperties = {
    position: 'absolute',
    left: node.layout?.x ?? 0,
    top: node.layout?.y ?? 0,
    width: node.layout?.width ?? '100%',
    height: node.layout?.height ?? '100%',
    zIndex: Math.round((node.z ?? 0) * 100),
    opacity: own.opacity * visibilityOpacity,
    transform: `translate3d(${x}px, ${y}px, 0) rotate(${own.rotation}deg) scale(${scale * own.scaleX * emphasisScale}, ${scale * own.scaleY * emphasisScale})`,
    transformOrigin: 'center center',
  };
  return (
    <div style={style} data-layer-id={node.id}>
      {node.pose_sequence ? (
        <PoseSequence node={node} time={time} />
      ) : node.type === 'image' && node.path && node.looping_strip ? (
        <LoopingStrip
          node={node}
          time={time}
          canvasWidth={canvas[0]}
          worldTravelPx={worldOffsetPx}
        />
      ) : node.type === 'image' && node.path ? (
        <Img
          src={node.path.startsWith('http') ? node.path : staticFile(node.path)}
          style={{
            width: '100%',
            height: '100%',
            objectFit:
              node.layout?.fit === 'stretch'
                ? 'fill'
                : node.layout?.fit ?? 'contain',
          }}
        />
      ) : null}
      {node.motif_field ? <MotifField node={node} time={time} /> : null}
      {node.primitive ? <PrimitiveView primitive={node.primitive} canvas={canvas} /> : null}
      {node.children?.map((child) => {
        const world = node.world;
        const duration = Math.max(
          0.001,
          world?.duration_s ?? Number.POSITIVE_INFINITY,
        );
        const progress = world
          ? Math.max(0, Math.min(1, time / duration))
          : 0;
        const direction = world?.direction === 'right' ? 1 : -1;
        const groupTravel = world
          ? direction * world.distance_viewports * canvas[0] * progress
          : worldOffsetPx;
        const participant = world?.participants.find(
          (item) => item.target_id === child.id,
        );
        return (
          <NodeView
            key={child.id}
            node={child}
            time={time}
            camera={camera}
            canvas={canvas}
            events={events}
            worldOffsetPx={groupTravel}
            participantAnchor={participant?.anchor_space ?? 'screen'}
          />
        );
      })}
    </div>
  );
};

const PoseSequence: React.FC<{node: Node; time: number}> = ({node, time}) => {
  const sequence = node.pose_sequence!;
  const activeFrom = sequence.active_from_s ?? 0;
  const activeUntil = sequence.active_until_s ?? Number.POSITIVE_INFINITY;
  const states = sequence.states;
  if (!states.length) return null;
  if (time >= activeUntil && sequence.hold_state_id) {
    const held = states.find((state) => state.id === sequence.hold_state_id) ?? states.at(-1)!;
    return <Img src={staticFile(held.path)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />;
  }
  const durations = states.map((state) => Math.max(0.001, state.duration_s ?? 0.2));
  const cycle = durations.reduce((sum, value) => sum + value, 0);
  let local = Math.max(0, time - activeFrom);
  if (sequence.playback === 'loop') local %= cycle;
  else if (sequence.playback === 'ping-pong') {
    const span = cycle * 2;
    local %= span;
    if (local > cycle) local = span - local;
  } else {
    local = Math.min(local, cycle - 0.0001);
  }
  let index = 0;
  let cursor = durations[0];
  while (index < states.length - 1 && local >= cursor) {
    index += 1;
    cursor += durations[index];
  }
  return <Img src={staticFile(states[index].path)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />;
};

const LoopingStrip: React.FC<{
  node: Node;
  time: number;
  canvasWidth: number;
  worldTravelPx?: number;
}> = ({node, time, canvasWidth, worldTravelPx = 0}) => {
  const strip = node.looping_strip!;
  const activeFrom = strip.active_from_s ?? 0;
  const activeUntil = strip.active_until_s ?? Number.POSITIVE_INFINITY;
  const effective = strip.frozen ? 0 : Math.max(0, Math.min(time, activeUntil) - activeFrom);
  const tileWidth = Math.max(1, strip.tile_width_px ?? canvasWidth);
  const localTravel = strip.speed_px_s !== undefined
    ? effective * strip.speed_px_s
    : effective * (strip.distance_px ?? 0);
  const travel = worldTravelPx !== 0
    ? worldTravelPx * (strip.speed_factor ?? 1)
    : localTravel;
  const phase = ((strip.start_phase ?? 0) + travel) % tileWidth;
  const wrapped = phase < 0 ? phase + tileWidth : phase;
  const copies = Math.ceil(canvasWidth / tileWidth) + 4;
  const source = node.path!.startsWith('http') ? node.path! : staticFile(node.path!);
  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden'}}>
      {Array.from({length: copies}, (_, index) => index - 2).map((copy) => (
        <Img
          key={copy}
          src={source}
          style={{
            position: 'absolute',
            left: copy * tileWidth + wrapped,
            top: 0,
            width: tileWidth + 1,
            height: strip.render_height_px ?? '100%',
            objectFit: 'cover',
          }}
        />
      ))}
    </div>
  );
};

const MotifField: React.FC<{node: Node; time: number}> = ({node, time}) => {
  const field = node.motif_field!;
  const [x, y, width, height] = field.bounds;
  const count = Math.min(64, Math.max(0, field.count));
  return (
    <>
      {Array.from({length: count}, (_, index) => {
        const random = (salt: number) => {
          const value = Math.sin((field.seed + index * 17 + salt) * 12.9898) * 43758.5453;
          return value - Math.floor(value);
        };
        const cycles = field.cycles ?? 1;
        const progress = (time * 0.08 * cycles + random(2)) % 1;
        const px = x + random(3) * width + Math.sin(progress * Math.PI * 2) * 8;
        const py = field.preset === 'rise-drift'
          ? y + height * (1 - progress)
          : y + random(4) * height + Math.sin(progress * Math.PI * 2) * 10;
        return (
          <span
            key={index}
            style={{
              position: 'absolute',
              left: px,
              top: py,
              width: field.size ?? 12,
              height: field.size ?? 12,
              borderRadius: '50%',
              background: field.color ?? '#f3d76b',
              opacity: 0.55 + random(5) * 0.35,
              transform: `rotate(${progress * 360}deg)`,
            }}
          />
        );
      })}
    </>
  );
};

export const CollageVideo: React.FC<EditorProps> = ({manifest, aspect}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;
  const directed = directedManifest(manifest, aspect);
  const camera = transformAt(directed.camera?.keyframes, time);
  const events = directed.events ?? [];
  return (
    <AbsoluteFill
      style={{
        background: directed.canvas.background ?? '#171411',
        overflow: 'hidden',
        fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif',
      }}
    >
      <NodeView
        node={directed.composition}
        time={time}
        camera={camera}
        canvas={[directed.canvas.width, directed.canvas.height]}
        events={events}
      />
      {events
        .filter((event) => event.sound)
        .map((event) => (
          <Sequence
            key={event.id}
            from={Math.max(0, Math.round(event.from_s * fps))}
            durationInFrames={Math.max(1, Math.round((event.to_s - event.from_s) * fps))}
          >
            <Audio
              src={staticFile(event.sound!.path)}
              volume={event.sound!.volume ?? 1}
            />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
};
