import React from 'react';
import {AbsoluteFill, Img, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {directedManifest} from '../lib/manifest';
import {transformAt} from '../lib/motion';
import type {EditorProps, Node} from '../lib/types';
import {PrimitiveView} from './Primitive';

const NodeView: React.FC<{
  node: Node;
  time: number;
  camera: ReturnType<typeof transformAt>;
  canvas: [number, number];
}> = ({node, time, camera, canvas}) => {
  const own = transformAt(node.keyframes, time);
  const depth = node.depth ?? 0;
  const x = own.x - camera.x * depth;
  const y = own.y - camera.y * depth;
  const scale = own.scale * (1 + (camera.scale - 1) * depth);
  const style: React.CSSProperties = {
    position: 'absolute',
    inset: 0,
    zIndex: Math.round((node.z ?? 0) * 100),
    opacity: own.opacity,
    transform: `translate3d(${x}px, ${y}px, 0) rotate(${own.rotation}deg) scale(${scale * own.scaleX}, ${scale * own.scaleY})`,
    transformOrigin: 'center center',
  };
  return (
    <div style={style} data-layer-id={node.id}>
      {node.type === 'image' && node.path ? (
        <Img src={node.path.startsWith('http') ? node.path : staticFile(node.path)} style={{width: '100%', height: '100%', objectFit: 'contain'}} />
      ) : null}
      {node.primitive ? <PrimitiveView primitive={node.primitive} canvas={canvas} /> : null}
      {node.children?.map((child) => (
        <NodeView
          key={child.id}
          node={child}
          time={time}
          camera={camera}
          canvas={canvas}
        />
      ))}
    </div>
  );
};

export const CollageVideo: React.FC<EditorProps> = ({manifest, aspect}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;
  const directed = directedManifest(manifest, aspect);
  const camera = transformAt(directed.camera?.keyframes, time);
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
      />
    </AbsoluteFill>
  );
};
