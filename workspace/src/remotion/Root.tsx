import React from 'react';
import {Composition} from 'remotion';
import demoManifest from '../../public/demo.json';
import worldProofManifest from '../../public/world-proof.json';
import type {EditorProps, FilmProps, Manifest} from '../lib/types';
import {directedManifest} from '../lib/manifest';
import {CollageVideo} from './CollageVideo';
import {ProductionFilm} from './ProductionFilm';

const defaults: EditorProps = {
  manifest: demoManifest as unknown as Manifest,
  aspect: '16:9',
};

const worldDefaults: EditorProps = {
  manifest: worldProofManifest as unknown as Manifest,
  aspect: '16:9',
};

const filmDefaults: FilmProps = {
  film: {
    canvas: {
      width: 960,
      height: 540,
      fps: 30,
      duration_s: 6,
      background: '#171411',
    },
    scenes: [
      {
        id: 'editorial-proof',
        duration_s: 6,
        aspect: '16:9',
        manifest: demoManifest as unknown as Manifest,
      },
    ],
  },
};

const metadata = ({props}: {props: EditorProps}) => {
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
};

const filmMetadata = ({props}: {props: FilmProps}) => ({
  width: props.film.canvas.width,
  height: props.film.canvas.height,
  fps: props.film.canvas.fps,
  durationInFrames: Math.max(
    1,
    Math.round(props.film.canvas.duration_s * props.film.canvas.fps),
  ),
});

export const RemotionRoot: React.FC = () => (
  <>
    <Composition
      id="CollageVideo"
      component={CollageVideo}
      defaultProps={defaults}
      width={960}
      height={540}
      fps={30}
      durationInFrames={180}
      calculateMetadata={metadata}
    />
    <Composition
      id="CollageWorldProof"
      component={CollageVideo}
      defaultProps={worldDefaults}
      width={960}
      height={540}
      fps={30}
      durationInFrames={180}
      calculateMetadata={metadata}
    />
    <Composition
      id="ProductionFilm"
      component={ProductionFilm}
      defaultProps={filmDefaults}
      width={960}
      height={540}
      fps={30}
      durationInFrames={180}
      calculateMetadata={filmMetadata}
    />
  </>
);
