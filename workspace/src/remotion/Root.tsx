import React from 'react';
import {Composition} from 'remotion';
import demoManifest from '../../public/demo.json';
import type {EditorProps, Manifest} from '../lib/types';
import {directedManifest} from '../lib/manifest';
import {CollageVideo} from './CollageVideo';

const defaults: EditorProps = {
  manifest: demoManifest as unknown as Manifest,
  aspect: '16:9',
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="CollageVideo"
    component={CollageVideo}
    defaultProps={defaults}
    width={960}
    height={540}
    fps={30}
    durationInFrames={180}
    calculateMetadata={({props}) => {
      const directed = directedManifest(props.manifest, props.aspect);
      return {
        width: directed.canvas.width,
        height: directed.canvas.height,
        fps: directed.canvas.fps,
        durationInFrames: Math.max(
          1,
          Math.round(directed.canvas.duration_s * directed.canvas.fps),
        ),
      };
    }}
  />
);
