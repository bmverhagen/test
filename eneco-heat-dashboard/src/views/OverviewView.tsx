import { useMemo } from 'react';
import type { DashboardFilters, Segment } from '../types';
import { profitCenters, customers, getMarginBridge } from '../data/dummyData';
import { connections } from '../data/connections';
import { formatCurrency, formatPercent } from '../utils/format';
import { drillToSegment } from '../utils/drill';
import { KpiCard } from '../components/KpiCard';
import { Card } from '../components/ui';
import { MarginBridgeChart } from '../components/MarginBridgeChart';
import { FilterBar } from '../components/FilterBar';
import { DrillBreadcrumb } from '../components/DrillBreadcrumb';
import { DrillDownTable } from '../components/DrillDownTable';
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
      if (conn) {
        return { revenue: conn.revenue, cost: conn.cost, margin: conn.revenue - conn.cost, volume: conn.volumeGJ, sprucing: 0, heatLoss: 0 };
      }
    }
    if (filters.customerId !== 'alle') {
      const c = customers.find((x) => x.id === filters.customerId);
      if (c) {
        const rev = filters.revenueType === 'fixed' ? c.revenueFixed : filters.revenueType === 'variable' ? c.revenueVariable : c.revenue;
        const cost = filters.costType === 'fixed' ? c.costFixed : filters.costType === 'variable' ? c.costVariable : c.cost;
        const margin = rev - cost - c.sprucingCost + c.heatLossRevenue;
        return { revenue: rev, cost, margin, volume: c.volumeGJ, sprucing: c.sprucingCost, heatLoss: c.heatLossRevenue };
      }
    }
    let items = profitCenters;
    if (filters.segment !== 'alle') items = items.filter((pc) => pc.segment === filters.segment);
    if (filters.profitCenterId !== 'alle') items = items.filter((pc) => pc.id === filters.profitCenterId);
    const revenue = items.reduce((s, i) => {
      const r = filters.revenueType === 'fixed' ? i.revenueFixed : filters.revenueType === 'variable' ? i.revenueVariable : i.revenue;
      return s + r;
    }, 0);
    const cost = items.reduce((s, i) => {
      const c = filters.costType === 'fixed' ? i.costFixed : filters.costType === 'variable' ? i.costVariable : i.cost;
      return s + c;
    }, 0);
    const sprucing = items.reduce((s, i) => s + i.sprucingCost, 0);
    const heatLoss = items.reduce((s, i) => s + i.heatLossRevenue, 0);
    const volume = items.reduce((s, i) => s + i.volumeGJ, 0);
    return { revenue, cost, margin: revenue - cost - sprucing + heatLoss, volume, sprucing, heatLoss };
  }, [filters]);

  const segmentData = useMemo(() => {
    const segments = ['residentieel', 'zakelijk', 'industrie', 'overheid'] as const;
    return segments.map((seg) => {
      const pcs = profitCenters.filter((pc) => pc.segment === seg);
      const rev = pcs.reduce((s, i) => s + i.revenue, 0);
      const cost = pcs.reduce((s, i) => s + i.cost, 0);
      const spr = pcs.reduce((s, i) => s + i.sprucingCost, 0);
      const hl = pcs.reduce((s, i) => s + i.heatLossRevenue, 0);
      return {
        segmentId: seg,
        segment: seg.charAt(0).toUpperCase() + seg.slice(1),
        revenue: rev,
        cost,
        margin: rev - cost - spr + hl,
      };
    });
  }, []);

  const fixedVarData = [
    { name: 'Vaste omzet', value: profitCenters.reduce((s, i) => s + i.revenueFixed, 0), color: '#00a651' },
    { name: 'Variabele omzet', value: profitCenters.reduce((s, i) => s + i.revenueVariable, 0), color: '#0077b6' },
    { name: 'Vaste kosten', value: profitCenters.reduce((s, i) => s + i.costFixed, 0), color: '#ff6b35' },
    { name: 'Variabele kosten', value: profitCenters.reduce((s, i) => s + i.costVariable, 0), color: '#7b2cbf' },
  ];

  const marginPct = totals.revenue > 0 ? (totals.margin / totals.revenue) * 100 : 0;

  const handleSegmentClick = (data: { payload?: { segmentId?: Segment } }) => {
    const segmentId = data?.payload?.segmentId;
    if (segmentId) {
      onFilterChange(drillToSegment(filters, segmentId));
    }
  };

  return (
    <div className="space-y-6">
      <DrillBreadcrumb filters={filters} onNavigate={onFilterChange} />
      <FilterBar filters={filters} onChange={onFilterChange} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Omzet YTD" value={formatCurrency(totals.revenue, true)} subValue="incl. geschat deel" trend={4.2} icon={<DollarSign size={18} />} />
        <KpiCard label="Bruto marge" value={formatCurrency(totals.margin, true)} subValue={formatPercent(marginPct)} trend={2.8} variant="positive" icon={<TrendingUp size={18} />} />
        <KpiCard label="Volume (GJ)" value={`${(totals.volume / 1000).toFixed(1)}K`} subValue="warmte geleverd" icon={<Flame size={18} />} />
        <KpiCard label="Marge %" value={formatPercent(marginPct)} subValue="bruto marge ratio" variant="accent" icon={<Percent size={18} />} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Bruto marge brug" subtitle="Omzet → kosten → sprucing → heat loss → bruto marge" className="lg:col-span-2">
          <MarginBridgeChart data={bridge} />
        </Card>

        <Card title="Vast vs. Variabel" subtitle="Omzet en kosten structuur">
          <ResponsiveContainer width="100%" height={320}>
            <PieChart>
              <Pie data={fixedVarData} dataKey="value" nameKey="name" cx="50%" cy="50%" innerRadius={60} outerRadius={100} paddingAngle={2}>
                {fixedVarData.map((entry, i) => (
                  <Cell key={i} fill={entry.color} />
                ))}
              </Pie>
              <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0), true)} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Marge per segment" subtitle="Klik op segment om door te drillen">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={segmentData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="segment" tick={{ fontSize: 12 }} />
            <YAxis tickFormatter={(v) => formatCurrency(v, true)} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0), true)} />
            <Legend />
            <Bar dataKey="revenue" name="Omzet" fill="#00a651" radius={[4, 4, 0, 0]} onClick={handleSegmentClick} style={{ cursor: 'pointer' }} />
            <Bar dataKey="cost" name="Kosten" fill="#ef4444" radius={[4, 4, 0, 0]} onClick={handleSegmentClick} style={{ cursor: 'pointer' }} />
            <Bar dataKey="margin" name="Bruto marge" fill="#003d2e" radius={[4, 4, 0, 0]} onClick={handleSegmentClick} style={{ cursor: 'pointer' }} />
          </BarChart>
        </ResponsiveContainer>
      </Card>

      <DrillDownTable filters={filters} onDrill={onFilterChange} />
    </div>
  );
}
