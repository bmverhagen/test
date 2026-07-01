import type { DashboardFilters } from '../types';
import { SEGMENTS, profitCenters, customers } from '../data/dummyData';
import { connections } from '../data/connections';
import { Filter } from 'lucide-react';

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

  const selectClass = 'rounded-xl border border-gray-200/80 bg-white px-3 py-2 text-sm font-medium text-eneco-dark shadow-sm transition-all focus:border-eneco-green focus:outline-none focus:ring-2 focus:ring-eneco-green/20 hover:border-eneco-green/40';

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-2xl border border-eneco-green/10 bg-white/90 px-5 py-4 shadow-card backdrop-blur-sm">
      <div className="flex items-center gap-2 text-eneco-green">
        <Filter size={15} />
        <span className="text-xs font-bold uppercase tracking-wider">Filters</span>
      </div>

      <div className="h-5 w-px bg-eneco-green/15" />

      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-gray-400">Periode</label>
        <select value={filters.period} onChange={(e) => onChange({ ...filters, period: e.target.value as DashboardFilters['period'] })} className={selectClass}>
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
          <div className="h-5 w-px bg-eneco-green/15" />
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-gray-400">Segment</label>
            <select value={filters.segment} onChange={(e) => onChange({ ...filters, segment: e.target.value as DashboardFilters['segment'], profitCenterId: 'alle', customerId: 'alle', connectionId: 'alle' })} className={selectClass}>
              <option value="alle">Alle segmenten</option>
              {SEGMENTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-gray-400">Profit center</label>
            <select value={filters.profitCenterId} onChange={(e) => onChange({ ...filters, profitCenterId: e.target.value, customerId: 'alle', connectionId: 'alle' })} className={selectClass}>
              <option value="alle">Alle profit centers</option>
              {filteredPCs.map((pc) => <option key={pc.id} value={pc.id}>{pc.name}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-gray-400">Klant</label>
            <select value={filters.customerId} onChange={(e) => onChange({ ...filters, customerId: e.target.value, connectionId: 'alle' })} className={selectClass}>
              <option value="alle">Alle klanten</option>
              {filteredCustomers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </div>
          <div className="flex items-center gap-2">
            <label className="text-xs font-semibold text-gray-400">Aansluiting</label>
            <select value={filters.connectionId} onChange={(e) => onChange({ ...filters, connectionId: e.target.value })} className={selectClass} disabled={filteredConnections.length === 0}>
              <option value="alle">Alle aansluitingen</option>
              {filteredConnections.map((c) => <option key={c.id} value={c.id}>{c.address}</option>)}
            </select>
          </div>
        </>
      )}

      <div className="h-5 w-px bg-eneco-green/15" />

      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-gray-400">Omzet</label>
        <select value={filters.revenueType} onChange={(e) => onChange({ ...filters, revenueType: e.target.value as DashboardFilters['revenueType'] })} className={selectClass}>
          <option value="alle">Vast + Variabel</option>
          <option value="fixed">Vast</option>
          <option value="variable">Variabel</option>
        </select>
      </div>
      <div className="flex items-center gap-2">
        <label className="text-xs font-semibold text-gray-400">Kosten</label>
        <select value={filters.costType} onChange={(e) => onChange({ ...filters, costType: e.target.value as DashboardFilters['costType'] })} className={selectClass}>
          <option value="alle">Vast + Variabel</option>
          <option value="fixed">Vast</option>
          <option value="variable">Variabel</option>
        </select>
      </div>
    </div>
  );
}
