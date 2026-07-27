export type Aspect = '16:9' | '9:16' | '1:1';

export type Keyframe = {
  t: number;
  x?: number;
  y?: number;
  scale?: number;
  scale_x?: number;
  scale_y?: number;
  rotation?: number;
  opacity?: number;
  ease?: string;
};

export type Primitive = {
  kind:
    | 'group'
    | 'text'
    | 'rectangle'
    | 'ellipse'
    | 'line'
    | 'bar-chart'
    | 'timeline'
    | 'annotation'
    | 'map-route'
    | 'data-svg';
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  text?: string;
  fill?: string;
  color?: string;
  background?: string;
  stroke?: string;
  stroke_width?: number;
  radius?: number;
  font_size?: number;
  min_font_size?: number;
  bold?: boolean;
  align?: 'left' | 'center' | 'right';
  values?: number[];
  labels?: string[];
  colors?: string[];
  gap?: number;
  points?: [number, number][];
  items?: Array<{position: number; label: string; color?: string}>;
  target?: [number, number];
  label_box?: [number, number, number, number];
  avoidance?: {
    padding?: number;
    preferred?: 'top' | 'right' | 'bottom' | 'left';
    exclusions?: Array<[number, number, number, number]>;
  };
  svg?: {
    viewBox?: string;
    paths?: Array<{
      d: string;
      fill?: string;
      stroke?: string;
      strokeWidth?: number;
    }>;
    circles?: Array<{cx: number; cy: number; r: number; fill?: string}>;
    text?: Array<{x: number; y: number; value: string; fill?: string; size?: number}>;
  };
};

export type Node = {
  id: string;
  type: 'group' | 'image' | 'primitive';
  role?: string;
  z?: number;
  depth?: number;
  path?: string;
  primitive?: Primitive;
  keyframes?: Keyframe[];
  visibility?: {
    initial: 'visible' | 'hidden';
    events?: Array<{
      at_s: number;
      duration_s?: number;
      action: 'show' | 'hide';
      transition?: 'cut' | 'fade-rise' | 'fade-scale';
    }>;
  };
  pose_sequence?: {
    family_id: string;
    playback?: 'once' | 'loop' | 'ping-pong';
    transition?: 'cut' | 'crossfade';
    crossfade_s?: number;
    active_from_s?: number;
    active_until_s?: number;
    hold_state_id?: string;
    states: Array<{
      id: string;
      path: string;
      duration_s?: number;
      anchors?: Record<string, [number, number]>;
    }>;
  };
  looping_strip?: {
    axis: 'x';
    distance_px: number;
    active_from_s?: number;
    active_until_s?: number;
    frozen?: boolean;
    start_phase?: number;
  };
  motif_field?: {
    seed: number;
    count: number;
    bounds: [number, number, number, number];
    color?: string;
    size?: number;
    cycles?: number;
    preset?: 'drift' | 'fall-drift' | 'rise-drift' | 'orbit';
  };
  children?: Node[];
};

export type DirectorPlan = {
  width?: number;
  height?: number;
  safe_zones?: Array<{
    id: string;
    policy: 'contain' | 'exclude';
    rect: [number, number, number, number];
  }>;
  node_overrides?: Record<string, Partial<Node>>;
};

export type Manifest = {
  canvas: {
    width: number;
    height: number;
    fps: number;
    duration_s: number;
    background?: string;
  };
  camera?: {keyframes?: Keyframe[]};
  director_plans?: Partial<Record<Aspect, DirectorPlan>>;
  director?: {
    aspect?: Aspect;
    node_overrides?: Record<string, Partial<Node>>;
    annotation_layout?: {
      count: number;
      boxes: Array<[number, number, number, number]>;
      status: 'resolved';
    };
  };
  edit_points?: Array<{
    id: string;
    at_s: number;
    target: string;
    action?: string;
    note?: string;
  }>;
  events?: Array<{
    id: string;
    kind: 'emphasis' | 'visibility' | 'hold';
    target_id: string;
    from_s: number;
    to_s: number;
    visual?: {action?: 'pulse' | 'lift' | 'drop-impact' | 'carve'};
    sound?: {path: string; volume?: number};
    proof_id?: string;
  }>;
  proof_moments?: Array<{
    id: string;
    at_s: number;
    checks?: string[];
  }>;
  scene_transitions?: Array<{
    id: string;
    intent: string;
    mechanism: string;
    before_s: number;
    at_s: number;
    after_s: number;
  }>;
  composition: Node;
};

export type EditorProps = {
  manifest: Manifest;
  aspect: Aspect;
};
