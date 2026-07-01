import { useMemo } from 'react';
import type { DashboardFilters } from '../types';
import { getMarginBridge } from '../data/dummyData';
import { formatCurrency, formatPercent } from '../utils/format';
import { getDrillRows } from '../utils/drill';
import { Card, StatPill } from '../components/ui';
import { MarginBridgeChart } from '../components/MarginBridgeChart';
import { FilterBar } from '../components/FilterBar';
import { DrillBreadcrumb } from '../components/DrillBreadcrumb';
import { DrillDownTable } from '../components/DrillDownTable';
import { chartTooltipStyle, chartAxisStyle } from '../theme/chartTheme';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend,
} from 'recharts';

interface MarginViewProps {
  filters: DashboardFilters;
  onFilterChange: (f: DashboardFilters) => void;
}

export function MarginView({ filters, onFilterChange }: MarginViewProps) {
  const bridge = useMemo(() => getMarginBridge({
    segment: filters.segment,
    profitCenterId: filters.profitCenterId,
    customerId: filters.customerId,
    connectionId: filters.connectionId,
  }), [filters]);

  const drillData = useMemo(() => getDrillRows(filters), [filters]);

  const brutoMarge = bridge.find((b) => b.type === 'total')?.value ?? 0;
  const omzet = bridge.find((b) => b.type === 'start')?.value ?? 0;

  return (
    <div className="space-y-6">
      <DrillBreadcrumb filters={filters} onNavigate={onFilterChange} />
      <FilterBar filters={filters} onChange={onFilterChange} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatPill label="Bruto marge" value={`${formatCurrency(brutoMarge, true)} (${formatPercent(omzet > 0 ? (brutoMarge / omzet) * 100 : 0)})`} color="green" />
        <StatPill label="Sprucing cost" value={formatCurrency(Math.abs(bridge.find((b) => b.category === 'sprucing')?.value ?? 0), true)} color="warm" />
        <StatPill label="Heat loss revenue" value={formatCurrency(bridge.find((b) => b.category === 'heatloss')?.value ?? 0, true)} color="teal" />
      </div>

      <Card title="Waterfall bruto marge" subtitle="Sprucing cost, heat loss revenues en bruto marge in brug">
        <MarginBridgeChart data={bridge} />
      </Card>

      <DrillDownTable filters={filters} onDrill={onFilterChange} title="Drill-down detail" />

      <Card title="Vast vs. variabel vergelijking" subtitle="Omzet en kosten per entiteit — klik rij hierboven om te drillen">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={drillData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={80} />
            <YAxis tickFormatter={(v) => formatCurrency(v, true)} tick={chartAxisStyle} axisLine={false} tickLine={false} />
            <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0), true)} contentStyle={chartTooltipStyle} />
            <Legend />
            <Bar dataKey="revenueFixed" name="Omzet vast" stackId="rev" fill="#00a651" />
            <Bar dataKey="revenueVariable" name="Omzet variabel" stackId="rev" fill="#4ade80" />
            <Bar dataKey="costFixed" name="Kosten vast" stackId="cost" fill="#ef4444" />
            <Bar dataKey="costVariable" name="Kosten variabel" stackId="cost" fill="#fca5a5" />
          </BarChart>
        </ResponsiveContainer>
      </Card>
    </div>
  );
}
