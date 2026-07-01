import type { DashboardFilters, ViewId } from '../types';
import { connections } from '../data/connections';
import { customers } from '../data/dummyData';
import { formatCurrency, formatPercent } from '../utils/format';
import { ConnectionMap } from '../components/ConnectionMap';
import { DrillBreadcrumb } from '../components/DrillBreadcrumb';
import { DrillDownTable } from '../components/DrillDownTable';
import { Card, Badge } from '../components/ui';
import { KpiCard } from '../components/KpiCard';
import { drillToConnection } from '../utils/drill';
import { MapPin, Home, Building2 } from 'lucide-react';

interface MapViewProps {
  filters: DashboardFilters;
  onFilterChange: (f: DashboardFilters) => void;
  onNavigate: (view: ViewId) => void;
}

export function MapView({ filters, onFilterChange, onNavigate }: MapViewProps) {
  const visible = connections.filter((c) => {
    if (filters.segment !== 'alle' && c.segment !== filters.segment) return false;
    if (filters.profitCenterId !== 'alle' && c.profitCenterId !== filters.profitCenterId) return false;
    if (filters.customerId !== 'alle' && c.customerId !== filters.customerId) return false;
    return true;
  });

  const totalRevenue = visible.reduce((s, c) => s + c.revenue, 0);
  const woningen = visible.filter((c) => c.type === 'woning');
  const b2b = visible.filter((c) => c.type === 'bedrijfspand' || c.type === 'gebouw' || c.type === 'industrie');
  const lossCount = visible.filter((c) => c.isLossMaking).length;

  const selectedConn = filters.connectionId !== 'alle'
    ? connections.find((c) => c.id === filters.connectionId)
    : null;

  return (
    <div className="space-y-6">
      <DrillBreadcrumb filters={filters} onNavigate={onFilterChange} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Aansluitingen" value={String(visible.length)} icon={<MapPin size={18} />} />
        <KpiCard label="Omzet totaal" value={formatCurrency(totalRevenue, true)} />
        <KpiCard label="Woningen" value={String(woningen.length)} subValue={formatCurrency(woningen.reduce((s, c) => s + c.revenue, 0), true)} icon={<Home size={18} />} />
        <KpiCard label="B2B / Industrie" value={String(b2b.length)} subValue={`${lossCount} verliesgevend`} variant={lossCount > 0 ? 'negative' : 'default'} icon={<Building2 size={18} />} />
      </div>

      <Card title="Warmtenet kaart" subtitle="Klik op woning of bedrijfspand voor omzet en marge per aansluiting">
        <ConnectionMap
          filters={filters}
          onSelectConnection={(id) => onFilterChange(drillToConnection(filters, id))}
        />
      </Card>

      {selectedConn && (
        <Card title={`Aansluiting: ${selectedConn.address}`} subtitle={customers.find((c) => c.id === selectedConn.customerId)?.name}>
          <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
            <div><p className="text-xs text-gray-500">Type</p><p className="font-semibold capitalize">{selectedConn.type}</p></div>
            <div><p className="text-xs text-gray-500">Omzet YTD</p><p className="font-semibold text-eneco-green">{formatCurrency(selectedConn.revenue)}</p></div>
            <div><p className="text-xs text-gray-500">Kosten YTD</p><p className="font-semibold">{formatCurrency(selectedConn.cost)}</p></div>
            <div><p className="text-xs text-gray-500">Marge</p><p className={`font-semibold ${selectedConn.revenue - selectedConn.cost >= 0 ? 'text-eneco-green' : 'text-red-500'}`}>{formatCurrency(selectedConn.revenue - selectedConn.cost)}</p></div>
            <div><p className="text-xs text-gray-500">Volume</p><p className="font-semibold">{selectedConn.volumeGJ} GJ</p></div>
            <div><p className="text-xs text-gray-500">Contracttarief</p><p className="font-semibold">€{selectedConn.tariffRatePerGJ}/GJ</p></div>
            <div><p className="text-xs text-gray-500">Effectieve kostprijs</p><p className={`font-semibold ${selectedConn.isLossMaking ? 'text-red-500' : ''}`}>€{selectedConn.effectiveCostPerGJ}/GJ</p></div>
            <div><p className="text-xs text-gray-500">Piekverbruik</p><p className="font-semibold">{formatPercent(selectedConn.peakSharePct)}</p></div>
          </div>
          {selectedConn.isLossMaking && (
            <div className="mt-4 flex items-center justify-between rounded-lg border border-red-200 bg-red-50 p-4">
              <div>
                <Badge variant="danger">Verliesgevend — piekverbruiker</Badge>
                <p className="mt-2 text-sm text-red-800">
                  Effectieve kostprijs (€{selectedConn.effectiveCostPerGJ}/GJ) ligt boven contracttarief (€{selectedConn.tariffRatePerGJ}/GJ)
                  doordat warmte wordt afgenomen op dure momenten.
                </p>
                <p className="text-sm font-semibold text-red-700 mt-1">Jaarlijks verlies: {formatCurrency(selectedConn.lossAmount)}</p>
              </div>
              <button
                onClick={() => onNavigate('piekverlies')}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white hover:bg-red-700"
              >
                Piekverlies analyse →
              </button>
            </div>
          )}
        </Card>
      )}

      <DrillDownTable filters={filters} onDrill={onFilterChange} title="Aansluitingen lijst" />
    </div>
  );
}
