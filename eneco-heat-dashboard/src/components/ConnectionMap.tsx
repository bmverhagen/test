import { useMemo, useState } from 'react';
import type { DashboardFilters } from '../types';
import { connections, getConnectionsForFilters } from '../data/connections';
import { customers } from '../data/dummyData';
import { formatCurrency, formatPercent, cn } from '../utils/format';
import { Home, Building2, Factory, Building, MapPin } from 'lucide-react';

interface ConnectionMapProps {
  filters: DashboardFilters;
  onSelectConnection: (connectionId: string) => void;
  showLossOnly?: boolean;
}

const REGION_LABELS = [
  { x: 28, y: 16, label: 'Amsterdam', connections: 7 },
  { x: 74, y: 36, label: 'Rotterdam', connections: 4 },
  { x: 50, y: 46, label: 'Utrecht', connections: 3 },
  { x: 43, y: 72, label: 'Den Haag', connections: 2 },
  { x: 56, y: 86, label: 'Eindhoven', connections: 7 },
];

const PIPES = [
  'M 20 35 Q 35 28 50 52 Q 55 62 42 68',
  'M 68 55 Q 72 48 78 50',
  'M 50 52 Q 54 66 56 80',
  'M 35 28 Q 50 38 68 55',
];

function revenueColor(revenue: number, maxRevenue: number): string {
  const ratio = revenue / maxRevenue;
  if (ratio > 0.5) return '#00c965';
  if (ratio > 0.1) return '#00a651';
  if (ratio > 0.01) return '#4ade80';
  return '#86efac';
}

export function ConnectionMap({ filters, onSelectConnection, showLossOnly = false }: ConnectionMapProps) {
  const [hovered, setHovered] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState<'alle' | 'woning' | 'bedrijf' | 'industrie'>('alle');

  const visibleConnections = useMemo(() => {
    let list = getConnectionsForFilters(filters);
    if (showLossOnly) list = list.filter((c) => c.isLossMaking);
    if (typeFilter === 'woning') list = list.filter((c) => c.type === 'woning');
    if (typeFilter === 'bedrijf') list = list.filter((c) => c.type === 'bedrijfspand' || c.type === 'gebouw');
    if (typeFilter === 'industrie') list = list.filter((c) => c.type === 'industrie');
    return list;
  }, [filters, showLossOnly, typeFilter]);

  const maxRevenue = Math.max(...visibleConnections.map((c) => c.revenue), 1);
  const selected = hovered ? connections.find((c) => c.id === hovered) : null;
  const totalRevenue = visibleConnections.reduce((s, c) => s + c.revenue, 0);

  return (
    <div className="space-y-4">
      {/* Controls */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex rounded-xl border border-eneco-green/15 overflow-hidden shadow-sm">
          {(['alle', 'woning', 'bedrijf', 'industrie'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={cn(
                'px-4 py-2 text-xs font-semibold transition-all duration-200',
                typeFilter === t
                  ? 'bg-gradient-to-r from-eneco-green to-eneco-green-bright text-white shadow-inner'
                  : 'bg-white text-gray-600 hover:bg-eneco-light/40',
              )}
            >
              {t === 'alle' ? 'Alles' : t === 'woning' ? '🏠 Woningen' : t === 'bedrijf' ? '🏢 B2B' : '🏭 Industrie'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-3 rounded-xl bg-eneco-dark px-4 py-2 text-xs text-white/80">
          <MapPin size={13} className="text-eneco-mint" />
          <span><strong className="text-white">{visibleConnections.length}</strong> aansluitingen</span>
          <span className="text-white/30">|</span>
          <span><strong className="text-eneco-mint">{formatCurrency(totalRevenue, true)}</strong> omzet</span>
        </div>
      </div>

      {/* Map canvas */}
      <div className="relative overflow-hidden rounded-2xl border border-eneco-green/20 shadow-eneco" style={{ minHeight: 460 }}>
        {/* Dark map background */}
        <div className="absolute inset-0 bg-gradient-to-br from-[#001a12] via-[#002419] to-[#003d2e]" />

        <svg viewBox="0 0 100 100" className="relative w-full" style={{ minHeight: 460 }}>
          <defs>
            <radialGradient id="mapGlow" cx="50%" cy="50%" r="60%">
              <stop offset="0%" stopColor="rgba(0,166,81,0.15)" />
              <stop offset="100%" stopColor="rgba(0,0,0,0)" />
            </radialGradient>
            <radialGradient id="cityGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="rgba(0,200,101,0.25)" />
              <stop offset="100%" stopColor="rgba(0,0,0,0)" />
            </radialGradient>
            <linearGradient id="pipeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#00a651" stopOpacity="0.2" />
              <stop offset="50%" stopColor="#00c965" stopOpacity="0.8" />
              <stop offset="100%" stopColor="#00a651" stopOpacity="0.2" />
            </linearGradient>
            <filter id="glow">
              <feGaussianBlur stdDeviation="0.8" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
            <filter id="pinGlow">
              <feGaussianBlur stdDeviation="1.2" result="blur" />
              <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
            </filter>
          </defs>

          {/* Ambient glow */}
          <rect width="100" height="100" fill="url(#mapGlow)" />

          {/* Subtle grid */}
          {Array.from({ length: 20 }, (_, i) => (
            <line key={`h${i}`} x1={0} y1={i * 5} x2={100} y2={i * 5} stroke="rgba(0,166,81,0.06)" strokeWidth={0.08} />
          ))}
          {Array.from({ length: 20 }, (_, i) => (
            <line key={`v${i}`} x1={i * 5} y1={0} x2={i * 5} y2={100} stroke="rgba(0,166,81,0.06)" strokeWidth={0.08} />
          ))}

          {/* City glow zones */}
          {REGION_LABELS.map((r) => (
            <ellipse key={r.label} cx={r.x} cy={r.y + 4} rx={12} ry={8} fill="url(#cityGlow)" />
          ))}

          {/* Animated heat pipes */}
          {PIPES.map((d, i) => (
            <g key={i}>
              <path d={d} fill="none" stroke="rgba(0,166,81,0.15)" strokeWidth={1.2} />
              <path d={d} fill="none" stroke="url(#pipeGrad)" strokeWidth={0.7} className="pipe-animated" filter="url(#glow)" />
            </g>
          ))}

          {/* City labels */}
          {REGION_LABELS.map((r) => (
            <g key={r.label}>
              <rect x={r.x - 9} y={r.y - 3.5} width={18} height={5} rx={2.5} fill="rgba(0,166,81,0.2)" stroke="rgba(0,200,101,0.3)" strokeWidth={0.15} />
              <text x={r.x} y={r.y} textAnchor="middle" fontSize={2.2} fill="#b8f0d0" fontWeight={700} fontFamily="Plus Jakarta Sans, sans-serif">
                {r.label}
              </text>
            </g>
          ))}

          {/* Connections */}
          {visibleConnections.map((conn) => {
            const isHovered = hovered === conn.id;
            const size = conn.type === 'industrie' ? 3.5 : conn.type === 'woning' ? 2 : 2.6;
            const fill = conn.isLossMaking ? '#e30613' : revenueColor(conn.revenue, maxRevenue);

            return (
              <g
                key={conn.id}
                transform={`translate(${conn.mapX}, ${conn.mapY})`}
                onMouseEnter={() => setHovered(conn.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => onSelectConnection(conn.id)}
                style={{ cursor: 'pointer' }}
                filter={isHovered ? 'url(#pinGlow)' : undefined}
              >
                {/* Pulse ring for loss-making */}
                {conn.isLossMaking && (
                  <circle r={size + 2} fill="none" stroke="#e30613" strokeWidth={0.25} opacity={0.6}>
                    <animate attributeName="r" values={`${size + 1};${size + 3};${size + 1}`} dur="2s" repeatCount="indefinite" />
                    <animate attributeName="opacity" values="0.6;0.2;0.6" dur="2s" repeatCount="indefinite" />
                  </circle>
                )}

                {/* Hover ring */}
                {isHovered && (
                  <circle r={size + 1.5} fill="none" stroke="#b8f0d0" strokeWidth={0.35} />
                )}

                {/* Shadow */}
                <ellipse cx={0.3} cy={size * 0.8} rx={size * 0.8} ry={size * 0.3} fill="rgba(0,0,0,0.4)" />

                {conn.type === 'woning' ? (
                  <polygon
                    points={`0,${-size} ${size * 0.9},${size * 0.5} ${-size * 0.9},${size * 0.5}`}
                    fill={fill}
                    stroke={isHovered ? '#b8f0d0' : 'rgba(255,255,255,0.6)'}
                    strokeWidth={0.3}
                  />
                ) : conn.type === 'industrie' ? (
                  <>
                    <rect x={-size} y={-size * 0.7} width={size * 2} height={size * 1.4} fill={fill} stroke={isHovered ? '#b8f0d0' : 'rgba(255,255,255,0.5)'} strokeWidth={0.3} rx={0.4} />
                    <rect x={-size * 0.3} y={-size * 1.2} width={size * 0.6} height={size * 0.5} fill={fill} opacity={0.7} rx={0.2} />
                  </>
                ) : (
                  <rect
                    x={-size * 0.65} y={-size} width={size * 1.3} height={size * 2}
                    fill={fill} stroke={isHovered ? '#b8f0d0' : 'rgba(255,255,255,0.5)'} strokeWidth={0.3} rx={0.3}
                  />
                )}
              </g>
            );
          })}
        </svg>

        {/* Legend */}
        <div className="absolute bottom-4 left-4 flex items-center gap-3 rounded-xl bg-black/40 backdrop-blur-md px-4 py-2.5 ring-1 ring-white/10">
          <div className="flex items-center gap-1.5 text-[10px] text-white/70">
            <div className="h-2.5 w-8 rounded-full bg-gradient-to-r from-[#86efac] via-[#00a651] to-[#00c965]" />
            Omzet laag → hoog
          </div>
          <div className="h-3 w-px bg-white/20" />
          <div className="flex items-center gap-1 text-[10px] text-white/70">
            <span className="h-2.5 w-2.5 rounded-full bg-eneco-red animate-pulse" />
            Piekverlies
          </div>
        </div>

        {/* Hover tooltip */}
        {selected && (
          <div className="absolute top-4 right-4 w-72 glass-panel rounded-2xl p-5 animate-fade-up">
            <div className="flex items-start gap-3">
              <div className={cn(
                'flex h-11 w-11 items-center justify-center rounded-xl',
                selected.isLossMaking
                  ? 'bg-gradient-to-br from-red-500 to-eneco-red text-white shadow-lg shadow-red-500/30'
                  : 'bg-gradient-to-br from-eneco-green to-eneco-green-bright text-white shadow-lg shadow-eneco-green/30',
              )}>
                {selected.type === 'woning' ? <Home size={18} /> :
                 selected.type === 'industrie' ? <Factory size={18} /> :
                 selected.type === 'bedrijfspand' ? <Building2 size={18} /> : <Building size={18} />}
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-bold text-eneco-dark truncate">{selected.address}</p>
                <p className="text-xs text-gray-500 mt-0.5">{customers.find((c) => c.id === selected.customerId)?.name}</p>
              </div>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3">
              {[
                { label: 'Omzet YTD', value: formatCurrency(selected.revenue, true), color: 'text-eneco-green' },
                { label: 'Kosten YTD', value: formatCurrency(selected.cost, true), color: 'text-gray-700' },
                { label: 'Contracttarief', value: `€${selected.tariffRatePerGJ}/GJ`, color: 'text-eneco-teal' },
                { label: 'Effectief', value: `€${selected.effectiveCostPerGJ}/GJ`, color: selected.isLossMaking ? 'text-eneco-red' : 'text-gray-700' },
              ].map((item) => (
                <div key={item.label} className="rounded-xl bg-gray-50 px-3 py-2">
                  <p className="text-[10px] font-medium text-gray-400 uppercase tracking-wide">{item.label}</p>
                  <p className={cn('mt-0.5 text-sm font-bold', item.color)}>{item.value}</p>
                </div>
              ))}
            </div>
            {selected.isLossMaking && (
              <div className="mt-3 rounded-xl bg-gradient-to-r from-red-50 to-orange-50 px-3 py-2.5 ring-1 ring-eneco-red/20">
                <p className="text-xs font-bold text-eneco-red">⚠ Piekverbruiker</p>
                <p className="text-xs text-red-700 mt-0.5">
                  Verlies {formatCurrency(selected.lossAmount)} · Piek {formatPercent(selected.peakSharePct)}
                </p>
              </div>
            )}
            <p className="mt-3 text-center text-[10px] font-medium text-eneco-green">Klik voor detail →</p>
          </div>
        )}
      </div>
    </div>
  );
}
