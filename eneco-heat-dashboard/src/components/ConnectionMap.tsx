import { useMemo, useState } from 'react';
import type { Connection, DashboardFilters } from '../types';
import { connections, getConnectionsForFilters } from '../data/connections';
import { customers } from '../data/dummyData';
import { formatCurrency, formatPercent, cn } from '../utils/format';
import { Home, Building2, Factory, Building } from 'lucide-react';

interface ConnectionMapProps {
  filters: DashboardFilters;
  onSelectConnection: (connectionId: string) => void;
  onSelectCustomer?: (customerId: string) => void;
  showLossOnly?: boolean;
}

const REGION_LABELS = [
  { x: 28, y: 18, label: 'Amsterdam' },
  { x: 74, y: 38, label: 'Rotterdam' },
  { x: 50, y: 48, label: 'Utrecht' },
  { x: 43, y: 74, label: 'Den Haag' },
  { x: 56, y: 88, label: 'Eindhoven' },
];

function ConnectionIcon({ type, size = 16 }: { type: Connection['type']; size?: number }) {
  switch (type) {
    case 'woning': return <Home size={size} />;
    case 'bedrijfspand': return <Building2 size={size} />;
    case 'industrie': return <Factory size={size} />;
    default: return <Building size={size} />;
  }
}

function revenueColor(revenue: number, maxRevenue: number): string {
  const ratio = revenue / maxRevenue;
  if (ratio > 0.5) return '#00a651';
  if (ratio > 0.1) return '#4ade80';
  if (ratio > 0.01) return '#86efac';
  return '#bbf7d0';
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-gray-200 overflow-hidden">
          {(['alle', 'woning', 'bedrijf', 'industrie'] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTypeFilter(t)}
              className={cn(
                'px-3 py-1.5 text-xs font-medium transition-colors',
                typeFilter === t ? 'bg-eneco-green text-white' : 'bg-white text-gray-600 hover:bg-gray-50',
              )}
            >
              {t === 'alle' ? 'Alles' : t === 'woning' ? 'Woningen' : t === 'bedrijf' ? 'B2B panden' : 'Industrie'}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-4 text-xs text-gray-500">
          <span className="flex items-center gap-1"><Home size={12} /> Woning</span>
          <span className="flex items-center gap-1"><Building2 size={12} /> B2B</span>
          <span className="flex items-center gap-1"><Factory size={12} /> Industrie</span>
          <span className="flex items-center gap-1"><span className="h-2.5 w-2.5 rounded-full bg-red-500" /> Verliesgevend</span>
        </div>
      </div>

      <div className="relative rounded-xl border border-gray-200 bg-gradient-to-br from-slate-50 to-emerald-50/30 overflow-hidden">
        <svg viewBox="0 0 100 100" className="w-full" style={{ minHeight: 420 }}>
          {/* Grid lines */}
          {Array.from({ length: 10 }, (_, i) => (
            <line key={`h${i}`} x1={0} y1={i * 10} x2={100} y2={i * 10} stroke="#e2e8f0" strokeWidth={0.15} />
          ))}
          {Array.from({ length: 10 }, (_, i) => (
            <line key={`v${i}`} x1={i * 10} y1={0} x2={i * 10} y2={100} stroke="#e2e8f0" strokeWidth={0.15} />
          ))}

          {/* Heat network pipes (stylized) */}
          <path d="M 20 35 Q 35 30 50 52 Q 55 60 42 68" fill="none" stroke="#00a651" strokeWidth={0.6} strokeOpacity={0.3} strokeDasharray="2 1" />
          <path d="M 68 55 Q 72 50 78 50" fill="none" stroke="#00a651" strokeWidth={0.6} strokeOpacity={0.3} strokeDasharray="2 1" />
          <path d="M 50 52 Q 54 65 56 80" fill="none" stroke="#00a651" strokeWidth={0.6} strokeOpacity={0.3} strokeDasharray="2 1" />

          {/* Region labels */}
          {REGION_LABELS.map((r) => (
            <text key={r.label} x={r.x} y={r.y} textAnchor="middle" fontSize={2.8} fill="#94a3b8" fontWeight={600}>
              {r.label}
            </text>
          ))}

          {/* Connections */}
          {visibleConnections.map((conn) => {
            const isHovered = hovered === conn.id;
            const size = conn.type === 'industrie' ? 3.2 : conn.type === 'woning' ? 1.8 : 2.4;
            const fill = conn.isLossMaking ? '#ef4444' : revenueColor(conn.revenue, maxRevenue);

            return (
              <g
                key={conn.id}
                transform={`translate(${conn.mapX}, ${conn.mapY})`}
                onMouseEnter={() => setHovered(conn.id)}
                onMouseLeave={() => setHovered(null)}
                onClick={() => onSelectConnection(conn.id)}
                className="cursor-pointer"
              >
                {isHovered && (
                  <circle r={size + 2} fill="none" stroke="#003d2e" strokeWidth={0.4} opacity={0.6} />
                )}
                {conn.isLossMaking && (
                  <circle r={size + 1.2} fill="none" stroke="#ef4444" strokeWidth={0.3} strokeDasharray="1 0.5" />
                )}
                {conn.type === 'woning' ? (
                  <polygon
                    points={`0,${-size} ${size},${size * 0.6} ${-size},${size * 0.6}`}
                    fill={fill}
                    stroke={isHovered ? '#003d2e' : '#fff'}
                    strokeWidth={0.25}
                  />
                ) : conn.type === 'industrie' ? (
                  <rect
                    x={-size} y={-size * 0.8} width={size * 2} height={size * 1.6}
                    fill={fill} stroke={isHovered ? '#003d2e' : '#fff'} strokeWidth={0.25} rx={0.3}
                  />
                ) : (
                  <rect
                    x={-size * 0.7} y={-size} width={size * 1.4} height={size * 2}
                    fill={fill} stroke={isHovered ? '#003d2e' : '#fff'} strokeWidth={0.25} rx={0.2}
                  />
                )}
              </g>
            );
          })}
        </svg>

        {/* Hover tooltip */}
        {selected && (
          <div className="absolute top-4 right-4 w-64 rounded-xl border border-gray-200 bg-white p-4 shadow-lg">
            <div className="flex items-start gap-2">
              <div className={cn('rounded-lg p-2', selected.isLossMaking ? 'bg-red-50 text-red-600' : 'bg-eneco-light text-eneco-green')}>
                <ConnectionIcon type={selected.type} />
              </div>
              <div className="flex-1 min-w-0">
                <p className="font-semibold text-sm text-eneco-dark truncate">{selected.address}</p>
                <p className="text-xs text-gray-500">{customers.find((c) => c.id === selected.customerId)?.name}</p>
              </div>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
              <div><span className="text-gray-500">Omzet</span><p className="font-semibold">{formatCurrency(selected.revenue, true)}</p></div>
              <div><span className="text-gray-500">Kosten</span><p className="font-semibold">{formatCurrency(selected.cost, true)}</p></div>
              <div><span className="text-gray-500">Tarief</span><p className="font-semibold">€{selected.tariffRatePerGJ}/GJ</p></div>
              <div><span className="text-gray-500">Effectief</span><p className={cn('font-semibold', selected.isLossMaking && 'text-red-500')}>€{selected.effectiveCostPerGJ}/GJ</p></div>
            </div>
            {selected.isLossMaking && (
              <div className="mt-2 rounded-lg bg-red-50 px-2 py-1.5 text-xs text-red-700">
                Verlies: {formatCurrency(selected.lossAmount)} · Piek: {formatPercent(selected.peakSharePct)}
              </div>
            )}
            <p className="mt-2 text-[10px] text-gray-400">Klik voor aansluiting-detail</p>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-gray-500">
        <span>{visibleConnections.length} aansluitingen zichtbaar</span>
        <span>Kleur = omzetniveau · Rood = verliesgevend door piekverbruik</span>
      </div>
    </div>
  );
}
