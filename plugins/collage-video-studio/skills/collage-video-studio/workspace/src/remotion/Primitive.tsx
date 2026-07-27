import React from 'react';
import type {Primitive} from '../lib/types';

const common = (primitive: Primitive): React.CSSProperties => ({
  position: 'absolute',
  left: primitive.x ?? 0,
  top: primitive.y ?? 0,
  width: primitive.width,
  height: primitive.height,
  boxSizing: 'border-box',
});

const DataSvg: React.FC<{primitive: Primitive}> = ({primitive}) => {
  const data = primitive.svg ?? {};
  return (
    <svg
      style={common(primitive)}
      viewBox={data.viewBox ?? `0 0 ${primitive.width ?? 100} ${primitive.height ?? 100}`}
      preserveAspectRatio="xMidYMid meet"
    >
      {data.paths?.map((path, index) => (
        <path
          key={`path-${index}`}
          d={path.d}
          fill={path.fill ?? 'none'}
          stroke={path.stroke}
          strokeWidth={path.strokeWidth}
        />
      ))}
      {data.circles?.map((circle, index) => (
        <circle key={`circle-${index}`} {...circle} />
      ))}
      {data.text?.map((text, index) => (
        <text
          key={`text-${index}`}
          x={text.x}
          y={text.y}
          fill={text.fill ?? '#fff'}
          fontSize={text.size ?? 18}
        >
          {text.value}
        </text>
      ))}
    </svg>
  );
};

export const PrimitiveView: React.FC<{
  primitive: Primitive;
  canvas: [number, number];
}> = ({primitive, canvas}) => {
  if (primitive.kind === 'group') return null;
  if (primitive.kind === 'rectangle' || primitive.kind === 'ellipse') {
    return (
      <div
        style={{
          ...common(primitive),
          borderRadius:
            primitive.kind === 'ellipse' ? '50%' : (primitive.radius ?? 0),
          background: primitive.fill ?? '#fff',
          border: primitive.stroke
            ? `${primitive.stroke_width ?? 1}px solid ${primitive.stroke}`
            : undefined,
        }}
      />
    );
  }
  if (primitive.kind === 'text') {
    return (
      <div
        style={{
          ...common(primitive),
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent:
            primitive.align === 'center'
              ? 'center'
              : primitive.align === 'right'
                ? 'flex-end'
                : 'flex-start',
          color: primitive.color ?? '#fff',
          background: primitive.background,
          fontSize: primitive.font_size ?? 48,
          fontWeight: primitive.bold ? 800 : 400,
          lineHeight: 1.08,
          whiteSpace: 'pre-wrap',
          overflow: 'hidden',
        }}
      >
        {primitive.text}
      </div>
    );
  }
  if (primitive.kind === 'bar-chart') {
    const values = primitive.values ?? [];
    const maximum = Math.max(1, ...values);
    return (
      <div
        style={{
          ...common(primitive),
          display: 'flex',
          alignItems: 'flex-end',
          gap: primitive.gap ?? 10,
        }}
      >
        {values.map((value, index) => (
          <div
            key={`${value}-${index}`}
            style={{
              flex: 1,
              height: `${(value / maximum) * 100}%`,
              background: primitive.colors?.[index % primitive.colors.length] ?? '#f3d76b',
              borderRadius: primitive.radius ?? 4,
            }}
          />
        ))}
      </div>
    );
  }
  if (primitive.kind === 'map-route' || primitive.kind === 'line') {
    const points = primitive.points ?? [];
    return (
      <svg style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}>
        <polyline
          points={points.map((point) => point.join(',')).join(' ')}
          fill="none"
          stroke={primitive.color ?? '#d75b45'}
          strokeWidth={primitive.stroke_width ?? 6}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        {primitive.kind === 'map-route' &&
          points.map(([cx, cy], index) => (
            <circle key={`${cx}-${cy}-${index}`} cx={cx} cy={cy} r={7} fill="#f3d76b" />
          ))}
      </svg>
    );
  }
  if (primitive.kind === 'timeline') {
    return (
      <div style={{...common(primitive), color: primitive.color ?? '#fff'}}>
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            top: '50%',
            height: primitive.stroke_width ?? 4,
            background: primitive.color ?? '#fff',
          }}
        />
        {primitive.items?.map((item, index) => (
          <div
            key={`${item.label}-${index}`}
            style={{
              position: 'absolute',
              left: `${item.position * 100}%`,
              top: '50%',
              transform: 'translate(-50%, -50%)',
              textAlign: 'center',
              whiteSpace: 'nowrap',
              fontWeight: 700,
            }}
          >
            <span
              style={{
                display: 'block',
                width: 14,
                height: 14,
                margin: '0 auto 8px',
                borderRadius: '50%',
                background: item.color ?? '#fff',
              }}
            />
            {item.label}
          </div>
        ))}
      </div>
    );
  }
  if (primitive.kind === 'annotation') {
    const target = primitive.target ?? [0, 0];
    const initial = primitive.label_box ?? [target[0] + 20, target[1] + 20, 220, 60];
    const [x, y, width, height] = initial;
    return (
      <>
        <svg style={{position: 'absolute', inset: 0, width: '100%', height: '100%'}}>
          <line
            x1={target[0]}
            y1={target[1]}
            x2={x}
            y2={y + height / 2}
            stroke={primitive.color ?? '#f3d76b'}
            strokeWidth={primitive.stroke_width ?? 3}
          />
        </svg>
        <div
          style={{
            position: 'absolute',
            left: x,
            top: y,
            width,
            height,
            display: 'flex',
            alignItems: 'center',
            padding: '8px 12px',
            boxSizing: 'border-box',
            borderRadius: primitive.radius ?? 6,
            background: primitive.background ?? '#302820',
            color: primitive.fill ?? '#fff',
            fontSize: primitive.font_size ?? 22,
            fontWeight: 700,
          }}
        >
          {primitive.text}
        </div>
      </>
    );
  }
  if (primitive.kind === 'data-svg') {
    return <DataSvg primitive={primitive} />;
  }
  return null;
};
