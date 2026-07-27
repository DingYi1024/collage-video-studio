export type Rect = [number, number, number, number];

export const intersects = (a: Rect, b: Rect, padding = 0) =>
  a[0] < b[0] + b[2] + padding &&
  a[0] + a[2] + padding > b[0] &&
  a[1] < b[1] + b[3] + padding &&
  a[1] + a[3] + padding > b[1];

const clamp = (value: number, low: number, high: number) =>
  Math.min(high, Math.max(low, value));

export const placeAnnotation = ({
  target,
  size,
  canvas,
  preferred = 'right',
  exclusions = [],
  occupied = [],
  padding = 12,
}: {
  target: [number, number];
  size: [number, number];
  canvas: [number, number];
  preferred?: 'top' | 'right' | 'bottom' | 'left';
  exclusions?: Rect[];
  occupied?: Rect[];
  padding?: number;
}): Rect => {
  const [tx, ty] = target;
  const [width, height] = size;
  const candidates: Record<string, Rect> = {
    right: [tx + padding, ty - height / 2, width, height],
    left: [tx - width - padding, ty - height / 2, width, height],
    top: [tx - width / 2, ty - height - padding, width, height],
    bottom: [tx - width / 2, ty + padding, width, height],
  };
  const order = [preferred, 'right', 'left', 'top', 'bottom'];
  const unique = [...new Set(order)];
  for (const direction of unique) {
    const raw = candidates[direction];
    const candidate: Rect = [
      clamp(raw[0], padding, canvas[0] - width - padding),
      clamp(raw[1], padding, canvas[1] - height - padding),
      width,
      height,
    ];
    if (![...exclusions, ...occupied].some((other) => intersects(candidate, other, padding))) {
      return candidate;
    }
  }
  // Deterministic vertical scan is the final fallback.
  for (let y = padding; y <= canvas[1] - height - padding; y += padding) {
    const candidate: Rect = [
      clamp(tx + padding, padding, canvas[0] - width - padding),
      y,
      width,
      height,
    ];
    if (![...exclusions, ...occupied].some((other) => intersects(candidate, other, padding))) {
      return candidate;
    }
  }
  const fallback: Rect = [
    clamp(tx + padding, padding, canvas[0] - width - padding),
    clamp(ty + padding, padding, canvas[1] - height - padding),
    width,
    height,
  ];
  if ([...exclusions, ...occupied].some((other) => intersects(fallback, other, padding))) {
    throw new Error('No collision-free annotation placement exists');
  }
  return fallback;
};
