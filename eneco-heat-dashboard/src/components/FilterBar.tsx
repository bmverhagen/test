import type { DashboardFilters } from '../types';
import { SEGMENTS, profitCenters, customers } from '../data/dummyData';
import { connections } from '../data/connections';

interface FilterBarProps {
  filters: DashboardFilters;
  onChange: (filters: DashboardFilters) => void;
  showDrillDown?: boolean;
}

export function FilterBar({ filters, onChange, showDrillDown = true }: FilterBarProps) {
  const filteredPCs = filters.segment === 'alle'
    ? profitCenters
    : profitCenters.filter((pc) => pc.segment === filters.segment);

  const filteredCustomers = filters.profitCenterId === 'alle'
    ? (filters.segment === 'alle' ? customers : customers.filter((c) => c.segment === filters.segment))
    : customers.filter((c) => c.profitCenterId === filters.profitCenterId);

  const filteredConnections = filters.customerId === 'alle'
    ? (filters.profitCenterId === 'alle'
      ? connections.filter((c) => filters.segment === 'alle' || c.segment === filters.segment)
      : connections.filter((c) => c.profitCenterId === filters.profitCenterId))
    : connections.filter((c) => c.customerId === filters.customerId);

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-gray-500">Periode</label>
        <select
          value={filters.period}
          onChange={(e) => onChange({ ...filters, period: e.target.value as DashboardFilters['period'] })}
          className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none focus:ring-1 focus:ring-eneco-green"
        >
          <option value="ytd">YTD 2025</option>
          <option value="q1">Q1 2025</option>
          <option value="q2">Q2 2025</option>
          <option value="q3">Q3 2025</option>
          <option value="q4">Q4 2025</option>
          <option value="jaar">Volledig jaar</option>
        </select>
      </div>

      {showDrillDown && (
        <>
          <div className="h-6 w-px bg-gray-200" />
          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-500">Segment</label>
            <select
              value={filters.segment}
              onChange={(e) => onChange({
                ...filters,
                segment: e.target.value as DashboardFilters['segment'],
                profitCenterId: 'alle',
                customerId: 'alle',
                connectionId: 'alle',
              })}
              className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none focus:ring-1 focus:ring-eneco-green"
            >
              <option value="alle">Alle segmenten</option>
              {SEGMENTS.map((s) => (
                <option key={s.id} value={s.id}>{s.label}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-500">Profit center</label>
            <select
              value={filters.profitCenterId}
              onChange={(e) => onChange({
                ...filters,
                profitCenterId: e.target.value,
                customerId: 'alle',
                connectionId: 'alle',
              })}
              className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none focus:ring-1 focus:ring-eneco-green"
            >
              <option value="alle">Alle profit centers</option>
              {filteredPCs.map((pc) => (
                <option key={pc.id} value={pc.id}>{pc.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-500">Klant</label>
            <select
              value={filters.customerId}
              onChange={(e) => onChange({ ...filters, customerId: e.target.value, connectionId: 'alle' })}
              className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none focus:ring-1 focus:ring-eneco-green"
            >
              <option value="alle">Alle klanten</option>
              {filteredCustomers.map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </div>

          <div className="flex items-center gap-2">
            <label className="text-xs font-medium text-gray-500">Aansluiting</label>
            <select
              value={filters.connectionId}
              onChange={(e) => onChange({ ...filters, connectionId: e.target.value })}
              className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none focus:ring-1 focus:ring-eneco-green"
              disabled={filteredConnections.length === 0}
            >
              <option value="alle">Alle aansluitingen</option>
              {filteredConnections.map((c) => (
                <option key={c.id} value={c.id}>{c.address}</option>
              ))}
            </select>
          </div>
        </>
      )}

      <div className="h-6 w-px bg-gray-200" />

      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-gray-500">Omzet</label>
        <select
          value={filters.revenueType}
          onChange={(e) => onChange({ ...filters, revenueType: e.target.value as DashboardFilters['revenueType'] })}
          className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none focus:ring-1 focus:ring-eneco-green"
        >
          <option value="alle">Vast + Variabel</option>
          <option value="fixed">Vast</option>
          <option value="variable">Variabel</option>
        </select>
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs font-medium text-gray-500">Kosten</label>
        <select
          value={filters.costType}
          onChange={(e) => onChange({ ...filters, costType: e.target.value as DashboardFilters['costType'] })}
          className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none focus:ring-1 focus:ring-eneco-green"
        >
          <option value="alle">Vast + Variabel</option>
          <option value="fixed">Vast</option>
          <option value="variable">Variabel</option>
        </select>
      </div>
    </div>
  );
}
