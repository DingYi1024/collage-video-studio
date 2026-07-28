import React from 'react';
import {
  AbsoluteFill,
  Audio,
  interpolate,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import type {FilmProps, FilmScene} from '../lib/types';
import {CollageVideo} from './CollageVideo';

const TransitionOverlay: React.FC<{
  scene: FilmScene;
  boundaryFrame: number;
  transitionFrames: number;
}> = ({scene, boundaryFrame, transitionFrames}) => {
  const frame = useCurrentFrame();
  if (transitionFrames <= 0) return null;
  const start = boundaryFrame - Math.floor(transitionFrames / 2);
  const end = boundaryFrame + Math.ceil(transitionFrames / 2);
  if (frame < start || frame > end) return null;
  const progress = interpolate(frame, [start, end], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const mechanism = scene.transition?.mechanism ?? 'paper-swipe';
  const direction =
    mechanism.includes('left') || mechanism.includes('reverse') ? -1 : 1;
  const travel = interpolate(progress, [0, 0.5, 1], [direction * 105, 0, -direction * 105]);
  const rotation = mechanism.includes('page')
    ? interpolate(progress, [0, 0.5, 1], [direction * 5, 0, -direction * 5])
    : 0;
  return (
    <AbsoluteFill
      style={{
        zIndex: 10000,
        pointerEvents: 'none',
        transform: `translateX(${travel}%) rotate(${rotation}deg)`,
        transformOrigin: direction > 0 ? 'right center' : 'left center',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: '-4%',
          background:
            'linear-gradient(100deg, #e8ddc3 0%, #f7f0df 52%, #d8c7a5 100%)',
          clipPath:
            'polygon(0 2%, 97% 0, 100% 9%, 97% 17%, 100% 27%, 98% 37%, 100% 49%, 97% 61%, 100% 72%, 98% 83%, 100% 94%, 96% 100%, 0 97%)',
          boxShadow: '0 0 42px rgba(35,25,15,.38)',
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: '8%',
          right: '8%',
          top: '50%',
          height: 3,
          background: '#9c3f32',
          opacity: Math.sin(Math.PI * progress),
        }}
      />
    </AbsoluteFill>
  );
};

export const ProductionFilm: React.FC<FilmProps> = ({film}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const time = frame / fps;
  let cursor = 0;
  const schedule = film.scenes.map((scene) => {
    const from = cursor;
    const frames = Math.max(1, Math.round(scene.duration_s * fps));
    cursor += frames;
    return {scene, from, frames};
  });
  const cue = film.subtitles?.find(
    (item) => time >= item.start_s && time < item.end_s,
  );
  return (
    <AbsoluteFill
      style={{
        background: film.canvas.background ?? '#171411',
        overflow: 'hidden',
        fontFamily: '"Segoe UI", "Microsoft YaHei", sans-serif',
      }}
    >
      {schedule.map(({scene, from, frames}) => (
        <Sequence key={scene.id} from={from} durationInFrames={frames}>
          <CollageVideo manifest={scene.manifest} aspect={scene.aspect} />
        </Sequence>
      ))}
      {schedule.slice(1).map(({scene, from}) => (
        <TransitionOverlay
          key={`transition-${scene.id}`}
          scene={scene}
          boundaryFrame={from}
          transitionFrames={Math.max(
            1,
            Math.round((scene.transition?.duration_s ?? 0.34) * fps),
          )}
        />
      ))}
      {cue ? (
        <div
          style={{
            position: 'absolute',
            zIndex: 20000,
            left: '12%',
            right: '12%',
            bottom: '5.5%',
            display: 'flex',
            justifyContent: 'center',
            pointerEvents: 'none',
          }}
        >
          <div
            style={{
              maxWidth: '100%',
              padding: '10px 18px 12px',
              color: film.style?.subtitle_color ?? '#fffdf5',
              background:
                film.style?.subtitle_background ?? 'rgba(42,30,22,.82)',
              border: '1px solid rgba(255,246,220,.25)',
              borderRadius: 5,
              boxShadow: '0 4px 14px rgba(0,0,0,.26)',
              fontSize: Math.max(26, Math.round(film.canvas.height * 0.034)),
              fontWeight: 650,
              lineHeight: 1.22,
              letterSpacing: '0.02em',
              textAlign: 'center',
              textShadow: '0 2px 3px rgba(0,0,0,.72)',
            }}
          >
            {cue.text}
          </div>
        </div>
      ) : null}
      {film.audio?.narration ? (
        <Audio
          src={staticFile(film.audio.narration.path)}
          volume={film.audio.narration.volume ?? 1}
        />
      ) : null}
      {film.audio?.music ? (
        <Audio
          src={staticFile(film.audio.music.path)}
          volume={(audioFrame) => {
            const audioTime = audioFrame / fps;
            const speaking = film.subtitles?.some(
              (item) =>
                audioTime >= item.start_s - 0.08 &&
                audioTime < item.end_s + 0.14,
            );
            return (film.audio?.music?.volume ?? 0.16) * (speaking ? 0.34 : 1);
          }}
          loop={film.audio.music.loop ?? true}
        />
      ) : null}
      <AbsoluteFill
        style={{
          zIndex: 30000,
          pointerEvents: 'none',
          opacity: 0.075,
          mixBlendMode: 'soft-light',
          backgroundImage:
            'repeating-linear-gradient(0deg, rgba(255,255,255,.18) 0px, rgba(255,255,255,.18) 1px, rgba(20,14,10,.15) 1px, rgba(20,14,10,.15) 3px)',
        }}
      />
    </AbsoluteFill>
  );
};
