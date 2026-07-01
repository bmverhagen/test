import { useMemo } from 'react';
import type { DashboardFilters, Segment } from '../types';
import { profitCenters, customers, getMarginBridge } from '../data/dummyData';
import { connections } from '../data/connections';
import { formatCurrency, formatPercent } from '../utils/format';
import { drillToSegment } from '../utils/drill';
import { KpiCard } from '../components/KpiCard';
import { Card, StatPill } from '../components/ui';
import { MarginBridgeChart } from '../components/MarginBridgeChart';
import { FilterBar } from '../components/FilterBar';
import { DrillBreadcrumb } from '../components/DrillBreadcrumb';
import { DrillDownTable } from '../components/DrillDownTable';
import { chartTooltipStyle, chartAxisStyle, SEGMENT_COLORS, ENECO_COLORS } from '../theme/chartTheme';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, PieChart, Pie, Cell,
} from 'recharts';
import { TrendingUp, DollarSign, Flame, Percent } from 'lucide-react';

interface OverviewViewProps {
  filters: DashboardFilters;
  onFilterChange: (f: DashboardFilters) => void;
}

export function OverviewView({ filters, onFilterChange }: OverviewViewProps) {
  const bridge = useMemo(() => getMarginBridge({
    segment: filters.segment,
    profitCenterId: filters.profitCenterId,
    customerId: filters.customerId,
    connectionId: filters.connectionId,
  }), [filters]);

  const totals = useMemo(() => {
    if (filters.connectionId !== 'alle') {
      const conn = connections.find((c) => c.id === filters.connectionId);
      if (conn) return { revenue: conn.revenue, cost: conn.cost, margin: conn.revenue - conn.cost, volume: conn.volumeGJ, sprucing: 0, heatLoss: 0 };
    }
    if (filters.customerId !== 'alle') {
      const c = customers.find((x) => x.id === filters.customerId);
      if (c) {
        const rev = filters.revenueType === 'fixed' ? c.revenueFixed : filters.revenueType === 'variable' ? c.revenueVariable : c.revenue;
        const cost = filters.costType === 'fixed' ? c.costFixed : filters.costType === 'variable' ? c.costVariable : c.cost;
        return { revenue: rev, cost, margin: rev - cost - c.sprucingCost + c.heatLossRevenue, volume: c.volumeGJ, sprucing: c.sprucingCost, heatLoss: c.heatLossRevenue };
      }
    }
    let items = profitCenters;
    if (filters.segment !== 'alle') items = items.filter((pc) => pc.segment === filters.segment);
    if (filters.profitCenterId !== 'alle') items = items.filter((pc) => pc.id === filters.profitCenterId);
    const revenue = items.reduce((s, i) => s + (filters.revenueType === 'fixed' ? i.revenueFixed : filters.revenueType === 'variable' ? i.revenueVariable : i.revenue), 0);
    const cost = items.reduce((s, i) => s + (filters.costType === 'fixed' ? i.costFixed : filters.costType === 'variable' ? i.costVariable : i.cost), 0);
    const sprucing = items.reduce((s, i) => s + i.sprucingCost, 0);
    const heatLoss = items.reduce((s, i) => s + i.heatLossRevenue, 0);
    return { revenue, cost, margin: revenue - cost - sprucing + heatLoss, volume: items.reduce((s, i) => s + i.volumeGJ, 0), sprucing, heatLoss };
  }, [filters]);

  const segmentData = useMemo(() => {
    return (['residentieel', 'zakelijk', 'industrie', 'overheid'] as const).map((seg) => {
      const pcs = profitCenters.filter((pc) => pc.segment === seg);
      const rev = pcs.reduce((s, i) => s + i.revenue, 0);
      const cost = pcs.reduce((s, i) => s + i.cost, 0);
      const spr = pcs.reduce((s, i) => s + i.sprucingCost, 0);
      const hl = pcs.reduce((s, i) => s + i.heatLossRevenue, 0);
      return { segmentId: seg, segment: seg.charAt(0).toUpperCase() + seg.slice(1), revenue: rev, cost, margin: rev - cost - spr + hl, fill: SEGMENT_COLORS[seg] };
    });
  }, []);

  const fixedVarData = [
    { name: 'Vaste omzet', value: profitCenters.reduce((s, i) => s + i.revenueFixed, 0), color: ENECO_COLORS.green },
    { name: 'Variabele omzet', value: profitCenters.reduce((s, i) => s + i.revenueVariable, 0), color: ENECO_COLORS.teal },
    { name: 'Vaste kosten', value: profitCenters.reduce((s, i) => s + i.costFixed, 0), color: ENECO_COLORS.warm },
    { name: 'Variabele kosten', value: profitCenters.reduce((s, i) => s + i.costVariable, 0), color: '#7b2cbf' },
  ];

  const marginPct = totals.revenue > 0 ? (totals.margin / totals.revenue) * 100 : 0;
  const totalPortfolioRevenue = profitCenters.reduce((s, i) => s + i.revenue, 0);

  const handleSegmentClick = (data: { payload?: { segmentId?: Segment } }) => {
    if (data?.payload?.segmentId) onFilterChange(drillToSegment(filters, data.payload.segmentId));
  };

  return (
    <div className="space-y-6">
      {/* Hero banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-eneco-dark via-[#004d35] to-eneco-darker p-8 shadow-eneco animate-fade-up">
        <div className="absolute -right-16 -top-16 h-64 w-64 rounded-full bg-eneco-green/20 blur-3xl" />
        <div className="absolute -bottom-8 -left-8 h-48 w-48 rounded-full bg-eneco-teal/15 blur-2xl" />
        <div className="relative flex flex-wrap items-center justify-between gap-6">
          <div>
            <p className="text-sm font-semibold text-eneco-mint/80 uppercase tracking-widest">Finance Intelligence</p>
            <h2 className="mt-1 text-3xl font-extrabold text-white tracking-tight">
              Eneco Warmte Portfolio
            </h2>
            <p className="mt-2 text-white/60 text-sm max-w-md">
              Real-time inzicht in omzet, marge en aansluitingen — YTD 2025
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <StatPill label="Portfolio omzet" value={formatCurrency(totalPortfolioRevenue, true)} color="green" />
            <StatPill label="Aansluitingen" value={String(connections.length)} color="teal" />
            <StatPill label="Verliesgevend" value={String(connections.filter((c) => c.isLossMaking).length)} color="red" />
          </div>
        </div>
        {/* Decorative pipeline */}
        <div className="absolute bottom-0 left-0 right-0 h-1 bg-gradient-to-r from-transparent via-eneco-green to-transparent opacity-60" />
      </div>

      <DrillBreadcrumb filters={filters} onNavigate={onFilterChange} />
      <FilterBar filters={filters} onChange={onFilterChange} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard className="animate-fade-up-delay-1" label="Omzet YTD" value={formatCurrency(totals.revenue, true)} subValue="incl. geschat deel" trend={4.2} variant="hero" icon={<DollarSign size={20} />} />
        <KpiCard className="animate-fade-up-delay-2" label="Bruto marge" value={formatCurrency(totals.margin, true)} subValue={formatPercent(marginPct)} trend={2.8} variant="positive" icon={<TrendingUp size={20} />} />
        <KpiCard className="animate-fade-up-delay-3" label="Volume (GJ)" value={`${(totals.volume / 1000).toFixed(1)}K`} subValue="warmte geleverd" icon={<Flame size={20} />} />
        <KpiCard className="animate-fade-up-delay-4" label="Marge %" value={formatPercent(marginPct)} subValue="bruto marge ratio" variant="accent" icon={<Percent size={20} />} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Bruto marge brug" subtitle="Waterfall: omzet → kosten → sprucing → heat loss → marge" className="lg:col-span-2" variant="elevated">
          <MarginBridgeChart data={bridge} />
        </Card>

        <Card title="Vast vs. Variabel" subtitle="Omzet- en kostenstructuur">
          <ResponsiveContainer width="100%" height={340}>
            <PieChart>
              <Pie
                data={fixedVarData}
                dataKey="value"
                nameKey="name"
                cx="50%"
                cy="50%"
                innerRadius={65}
                outerRadius={105}
                paddingAngle={3}
                strokeWidth={2}
                stroke="#fff"
              >
                {fixedVarData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0), true)} contentStyle={chartTooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 11, fontFamily: 'Plus Jakarta Sans' }} />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Marge per segment" subtitle="Klik op een segment om door te drillen" variant="elevated">
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={segmentData} barGap={4}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,166,81,0.1)" vertical={false} />
            <XAxis dataKey="segment" tick={chartAxisStyle} axisLine={false} tickLine={false} />
            <YAxis tickFormatter={(v) => formatCurrency(v, true)} tick={chartAxisStyle} axisLine={false} tickLine={false} width={72} />
            <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0), true)} contentStyle={chartTooltipStyle} cursor={{ fill: 'rgba(0,166,81,0.05)' }} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <Bar dataKey="revenue" name="Omzet" fill={ENECO_COLORS.green} radius={[6, 6, 0, 0]} onClick={handleSegmentClick} style={{ cursor: 'pointer' }} maxBarSize={48} />
            <Bar dataKey="cost" name="Kosten" fill={ENECO_COLORS.red} radius={[6, 6, 0, 0]} onClick={handleSegmentClick} style={{ cursor: 'pointer' }} maxBarSize={48} opacity={0.85} />
            <Bar dataKey="margin" name="Bruto marge" fill={ENECO_COLORS.dark} radius={[6, 6, 0, 0]} onClick={handleSegmentClick} style={{ cursor: 'pointer' }} maxBarSize={48} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <DrillDownTable filters={filters} onDrill={onFilterChange} />
    </div>
  );
}
