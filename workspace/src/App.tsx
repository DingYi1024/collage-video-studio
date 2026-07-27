import React, {useMemo, useRef, useState} from 'react';
import {Player, type PlayerRef} from '@remotion/player';
import demoManifest from '../public/demo.json';
import {directedManifest, flattenNodes, updateNode} from './lib/manifest';
import type {Aspect, Manifest, Node} from './lib/types';
import {CollageVideo} from './remotion/CollageVideo';

const aspects: Aspect[] = ['16:9', '9:16', '1:1'];

const numberValue = (value: string) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

export const App: React.FC = () => {
  const [manifest, setManifest] = useState<Manifest>(
    demoManifest as unknown as Manifest,
  );
  const [aspect, setAspect] = useState<Aspect>('16:9');
  const [selectedId, setSelectedId] = useState<string>('title');
  const player = useRef<PlayerRef>(null);
  const directed = useMemo(() => directedManifest(manifest, aspect), [manifest, aspect]);
  const nodes = useMemo(() => flattenNodes(directed.composition), [directed]);
  const selected = nodes.find((node) => node.id === selectedId) ?? nodes[0];
  const fps = directed.canvas.fps;
  const durationInFrames = Math.max(1, Math.round(directed.canvas.duration_s * fps));

  const patchSelected = (patch: Partial<Node>) => {
    setManifest((current) => ({
      ...current,
      composition: updateNode(current.composition, selected.id, patch),
      director_plans: {
        ...current.director_plans,
        [aspect]: {
          ...current.director_plans?.[aspect],
          node_overrides: {
            ...current.director_plans?.[aspect]?.node_overrides,
            [selected.id]: {
              ...current.director_plans?.[aspect]?.node_overrides?.[selected.id],
              ...patch,
              primitive: patch.primitive
                ? {
                    ...current.director_plans?.[aspect]?.node_overrides?.[selected.id]
                      ?.primitive,
                    ...patch.primitive,
                  }
                : undefined,
            },
          },
        },
      },
    }));
  };

  const openManifest = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setManifest(JSON.parse(await file.text()) as Manifest);
  };

  const saveManifest = async () => {
    const content = JSON.stringify(manifest, null, 2);
    const browser = window as typeof window & {
      showSaveFilePicker?: (options: unknown) => Promise<{
        createWritable: () => Promise<{
          write: (value: string) => Promise<void>;
          close: () => Promise<void>;
        }>;
      }>;
    };
    if (browser.showSaveFilePicker) {
      const handle = await browser.showSaveFilePicker({
        suggestedName: 'composition.json',
        types: [{description: 'Composition JSON', accept: {'application/json': ['.json']}}],
      });
      const writer = await handle.createWritable();
      await writer.write(content);
      await writer.close();
      return;
    }
    const url = URL.createObjectURL(new Blob([content], {type: 'application/json'}));
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = 'composition.json';
    anchor.click();
    URL.revokeObjectURL(url);
  };

  return (
    <main className="app-shell">
      <header className="topbar">
        <div>
          <div className="eyebrow">COLLAGE VIDEO STUDIO</div>
          <h1>Responsive editorial workspace</h1>
        </div>
        <div className="toolbar">
          <label className="button secondary">
            Open JSON
            <input type="file" accept=".json,application/json" onChange={openManifest} hidden />
          </label>
          <button className="button" onClick={saveManifest}>Save JSON</button>
        </div>
      </header>

      <section className="workspace">
        <aside className="panel layers-panel">
          <div className="panel-title">Layers</div>
          {nodes.map((node) => (
            <button
              key={node.id}
              className={`layer-row ${node.id === selected.id ? 'active' : ''}`}
              onClick={() => setSelectedId(node.id)}
            >
              <span>{node.id}</span>
              <small>{node.type} · z {node.z ?? 0}</small>
            </button>
          ))}
        </aside>

        <section className="stage-column">
          <div className="aspect-tabs">
            {aspects.map((value) => (
              <button
                key={value}
                className={aspect === value ? 'active' : ''}
                onClick={() => setAspect(value)}
              >
                {value}
              </button>
            ))}
          </div>
          <div className="player-wrap">
            <Player
              ref={player}
              component={CollageVideo}
              inputProps={{manifest, aspect}}
              durationInFrames={durationInFrames}
              fps={fps}
              compositionWidth={directed.canvas.width}
              compositionHeight={directed.canvas.height}
              controls
              loop
              style={{width: '100%', height: '100%'}}
            />
          </div>
          <div className="edit-points">
            <span>Edit points</span>
            {manifest.edit_points?.map((point) => (
              <button
                key={point.id}
                onClick={() => player.current?.seekTo(Math.round(point.at_s * fps))}
                title={point.note}
              >
                {point.id} · {point.at_s.toFixed(2)}s
              </button>
            ))}
          </div>
        </section>

        <aside className="panel inspector">
          <div className="panel-title">Inspector</div>
          <div className="selected-name">{selected.id}</div>
          <label>
            Depth
            <input
              type="number"
              min="-1"
              max="1"
              step="0.05"
              value={selected.depth ?? 0}
              onChange={(event) => patchSelected({depth: numberValue(event.target.value)})}
            />
          </label>
          {selected.primitive ? (
            <>
              {(['x', 'y', 'width', 'height'] as const).map((key) => (
                <label key={key}>
                  {key}
                  <input
                    type="number"
                    value={selected.primitive?.[key] ?? 0}
                    onChange={(event) =>
                      patchSelected({
                        primitive: {
                          kind: selected.primitive!.kind,
                          [key]: numberValue(event.target.value),
                        } as Node['primitive'],
                      })
                    }
                  />
                </label>
              ))}
              {selected.primitive.kind === 'text' ? (
                <label>
                  Text
                  <textarea
                    value={selected.primitive.text ?? ''}
                    onChange={(event) =>
                      patchSelected({
                        primitive: {
                          kind: selected.primitive!.kind,
                          text: event.target.value,
                        } as Node['primitive'],
                      })
                    }
                  />
                </label>
              ) : null}
            </>
          ) : null}
          <div className="evidence">
            <strong>Director evidence</strong>
            <span>{nodes.length} editable nodes</span>
            <span>{durationInFrames} exact frames</span>
            <span>{directed.canvas.width}×{directed.canvas.height}</span>
          </div>
        </aside>
      </section>
    </main>
  );
};
