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
  composition: Node;
};

export type EditorProps = {
  manifest: Manifest;
  aspect: Aspect;
};
