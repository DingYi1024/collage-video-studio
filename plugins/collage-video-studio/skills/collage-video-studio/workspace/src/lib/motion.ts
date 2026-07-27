import {Easing, interpolate} from 'remotion';
import type {Keyframe} from './types';

export type Transform = {
  x: number;
  y: number;
  scale: number;
  scaleX: number;
  scaleY: number;
  rotation: number;
  opacity: number;
};

const defaults: Transform = {
  x: 0,
  y: 0,
  scale: 1,
  scaleX: 1,
  scaleY: 1,
  rotation: 0,
  opacity: 1,
};

const easing = (name?: string) => {
  if (name === 'linear') return Easing.linear;
  if (name === 'ease-out-cubic') return Easing.out(Easing.cubic);
  if (name === 'ease-in-cubic') return Easing.in(Easing.cubic);
  if (name === 'ease-out-back') return Easing.out(Easing.back(1.4));
  return Easing.inOut(Easing.cubic);
};

const property = (
  frames: Keyframe[],
  time: number,
  key: keyof Omit<Keyframe, 't' | 'ease'>,
  fallback: number,
) => {
  if (frames.length === 0) return fallback;
  if (frames.length === 1) return Number(frames[0][key] ?? fallback);
  const ordered = [...frames].sort((a, b) => a.t - b.t);
  let before = ordered[0];
  let after = ordered.at(-1) ?? before;
  for (let index = 1; index < ordered.length; index += 1) {
    if (time <= ordered[index].t) {
      before = ordered[index - 1];
      after = ordered[index];
      break;
    }
  }
  return interpolate(
    time,
    [before.t, Math.max(before.t + 0.0001, after.t)],
    [Number(before[key] ?? fallback), Number(after[key] ?? fallback)],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: easing(after.ease),
    },
  );
};

export const transformAt = (frames: Keyframe[] | undefined, time: number): Transform => {
  const list = frames ?? [];
  return {
    x: property(list, time, 'x', defaults.x),
    y: property(list, time, 'y', defaults.y),
    scale: property(list, time, 'scale', defaults.scale),
    scaleX: property(list, time, 'scale_x', defaults.scaleX),
    scaleY: property(list, time, 'scale_y', defaults.scaleY),
    rotation: property(list, time, 'rotation', defaults.rotation),
    opacity: property(list, time, 'opacity', defaults.opacity),
  };
};
