import { useMemo } from 'react';
import type { DashboardFilters } from '../types';
import { profitCenters, customers, getMarginBridge } from '../data/dummyData';
import { formatCurrency, formatPercent } from '../utils/format';
import { Card, Badge } from '../components/ui';
import { MarginBridgeChart } from '../components/MarginBridgeChart';
import { FilterBar } from '../components/FilterBar';
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
  }), [filters]);

  const drillData = useMemo(() => {
    if (filters.customerId !== 'alle') {
      const c = customers.find((x) => x.id === filters.customerId);
      return c ? [{
        name: c.name,
        revenue: c.revenue,
        revenueFixed: c.revenueFixed,
        revenueVariable: c.revenueVariable,
        cost: c.cost,
        costFixed: c.costFixed,
        costVariable: c.costVariable,
        sprucing: c.sprucingCost,
        heatLoss: c.heatLossRevenue,
        margin: c.revenue - c.cost - c.sprucingCost + c.heatLossRevenue,
      }] : [];
    }
    if (filters.profitCenterId !== 'alle') {
      return customers
        .filter((c) => c.profitCenterId === filters.profitCenterId)
        .map((c) => ({
          name: c.name,
          revenue: c.revenue,
          revenueFixed: c.revenueFixed,
          revenueVariable: c.revenueVariable,
          cost: c.cost,
          costFixed: c.costFixed,
          costVariable: c.costVariable,
          sprucing: c.sprucingCost,
          heatLoss: c.heatLossRevenue,
          margin: c.revenue - c.cost - c.sprucingCost + c.heatLossRevenue,
        }));
    }
    let pcs = profitCenters;
    if (filters.segment !== 'alle') pcs = pcs.filter((pc) => pc.segment === filters.segment);
    return pcs.map((pc) => ({
      name: pc.name,
      revenue: pc.revenue,
      revenueFixed: pc.revenueFixed,
      revenueVariable: pc.revenueVariable,
      cost: pc.cost,
      costFixed: pc.costFixed,
      costVariable: pc.costVariable,
      sprucing: pc.sprucingCost,
      heatLoss: pc.heatLossRevenue,
      margin: pc.revenue - pc.cost - pc.sprucingCost + pc.heatLossRevenue,
    }));
  }, [filters]);

  const brutoMarge = bridge.find((b) => b.type === 'total')?.value ?? 0;
  const omzet = bridge.find((b) => b.type === 'start')?.value ?? 0;

  return (
    <div className="space-y-6">
      <FilterBar filters={filters} onChange={onFilterChange} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-eneco-green/30 bg-eneco-light/30 p-4">
          <p className="text-sm text-gray-600">Bruto marge</p>
          <p className="text-2xl font-bold text-eneco-dark">{formatCurrency(brutoMarge, true)}</p>
          <p className="text-xs text-gray-500">{formatPercent(omzet > 0 ? (brutoMarge / omzet) * 100 : 0)} van omzet</p>
        </div>
        <div className="rounded-xl border border-orange-200 bg-orange-50/50 p-4">
          <p className="text-sm text-gray-600">Sprucing cost</p>
          <p className="text-2xl font-bold text-eneco-accent">{formatCurrency(Math.abs(bridge.find((b) => b.category === 'sprucing')?.value ?? 0), true)}</p>
          <Badge variant="warning">Netwerk verlies</Badge>
        </div>
        <div className="rounded-xl border border-blue-200 bg-blue-50/50 p-4">
          <p className="text-sm text-gray-600">Heat loss revenue</p>
          <p className="text-2xl font-bold text-blue-700">{formatCurrency(bridge.find((b) => b.category === 'heatloss')?.value ?? 0, true)}</p>
          <Badge variant="info">Compensatie</Badge>
        </div>
      </div>

      <Card title="Waterfall bruto marge" subtitle="Sprucing cost, heat loss revenues en bruto marge in brug">
        <MarginBridgeChart data={bridge} />
      </Card>

      <Card title="Drill-down detail" subtitle={
        filters.customerId !== 'alle' ? 'Klantniveau' :
        filters.profitCenterId !== 'alle' ? 'Klanten per profit center' :
        filters.segment !== 'alle' ? 'Profit centers per segment' : 'Alle profit centers'
      }>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                <th className="pb-3 pr-4">Naam</th>
                <th className="pb-3 pr-4 text-right">Omzet vast</th>
                <th className="pb-3 pr-4 text-right">Omzet var.</th>
                <th className="pb-3 pr-4 text-right">Kosten vast</th>
                <th className="pb-3 pr-4 text-right">Kosten var.</th>
                <th className="pb-3 pr-4 text-right">Sprucing</th>
                <th className="pb-3 pr-4 text-right">Heat loss</th>
                <th className="pb-3 text-right">Bruto marge</th>
              </tr>
            </thead>
            <tbody>
              {drillData.map((row) => (
                <tr key={row.name} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-3 pr-4 font-medium text-eneco-dark">{row.name}</td>
                  <td className="py-3 pr-4 text-right text-gray-600">{formatCurrency(row.revenueFixed, true)}</td>
                  <td className="py-3 pr-4 text-right text-gray-600">{formatCurrency(row.revenueVariable, true)}</td>
                  <td className="py-3 pr-4 text-right text-gray-600">{formatCurrency(row.costFixed, true)}</td>
                  <td className="py-3 pr-4 text-right text-gray-600">{formatCurrency(row.costVariable, true)}</td>
                  <td className="py-3 pr-4 text-right text-eneco-accent">{formatCurrency(row.sprucing, true)}</td>
                  <td className="py-3 pr-4 text-right text-blue-600">{formatCurrency(row.heatLoss, true)}</td>
                  <td className="py-3 text-right font-semibold text-eneco-green">{formatCurrency(row.margin, true)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card title="Vast vs. variabel vergelijking" subtitle="Omzet en kosten per entiteit">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={drillData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="name" tick={{ fontSize: 10 }} interval={0} angle={-20} textAnchor="end" height={80} />
            <YAxis tickFormatter={(v) => formatCurrency(v, true)} tick={{ fontSize: 11 }} />
            <Tooltip formatter={(v) => formatCurrency(Number(v ?? 0), true)} />
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
