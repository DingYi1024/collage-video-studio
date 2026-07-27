import type {Aspect, Manifest, Node, Primitive} from './types';
import {placeAnnotation, type Rect} from './layout';

const mergeNode = (node: Node, override: Partial<Node> | undefined): Node => {
  if (!override) return structuredClone(node);
  return {
    ...structuredClone(node),
    ...structuredClone(override),
    primitive: (
      node.primitive || override.primitive
        ? {...structuredClone(node.primitive), ...structuredClone(override.primitive)}
        : undefined
    ) as Primitive | undefined,
  };
};

export const directedManifest = (source: Manifest, aspect: Aspect): Manifest => {
  const result = structuredClone(source);
  const plan = source.director_plans?.[aspect];
  if (!plan) throw new Error(`Missing director plan for ${aspect}`);
  result.canvas.width = plan.width ?? result.canvas.width;
  result.canvas.height = plan.height ?? result.canvas.height;
  result.director = {
    aspect,
    node_overrides: structuredClone(plan.node_overrides ?? {}),
  };
  const overrides = plan.node_overrides ?? {};
  const visit = (node: Node): Node => {
    const merged = mergeNode(node, overrides[node.id]);
    merged.children = merged.children?.map(visit);
    return merged;
  };
  result.composition = visit(result.composition);
  const occupied: Rect[] = [];
  const resolveAnnotations = (node: Node) => {
    if (node.primitive?.kind === 'annotation') {
      const primitive = node.primitive;
      const target = primitive.target ?? [0, 0];
      const box = primitive.label_box ?? [target[0] + 20, target[1] + 20, 220, 60];
      const placed = placeAnnotation({
        target,
        size: [box[2], box[3]],
        canvas: [result.canvas.width, result.canvas.height],
        preferred: primitive.avoidance?.preferred,
        padding: primitive.avoidance?.padding,
        exclusions: primitive.avoidance?.exclusions,
        occupied,
      });
      primitive.label_box = placed;
      occupied.push(placed);
    }
    node.children?.forEach(resolveAnnotations);
  };
  resolveAnnotations(result.composition);
  result.director.annotation_layout = {
    count: occupied.length,
    boxes: occupied,
    status: 'resolved',
  };
  return result;
};

export const flattenNodes = (root: Node): Node[] => {
  const output: Node[] = [];
  const visit = (node: Node) => {
    output.push(node);
    node.children?.forEach(visit);
  };
  visit(root);
  return output;
};

export const updateNode = (root: Node, id: string, patch: Partial<Node>): Node => {
  if (root.id === id) {
    return {
      ...root,
      ...patch,
      primitive: patch.primitive
        ? {...root.primitive, ...patch.primitive}
        : root.primitive,
    };
  }
  return {
    ...root,
    children: root.children?.map((child) => updateNode(child, id, patch)),
  };
};
