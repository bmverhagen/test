import { useMemo } from 'react';
import type { DashboardFilters, ViewId } from '../types';
import { customers, contracts, tariffs, profitCenters, SEGMENTS } from '../data/dummyData';
import { connections } from '../data/connections';
import { formatCurrency, formatNumber, formatDate } from '../utils/format';
import { drillToCustomer, drillToConnection } from '../utils/drill';
import { Card, Badge } from '../components/ui';
import { KpiCard } from '../components/KpiCard';
import { DrillBreadcrumb } from '../components/DrillBreadcrumb';
import { DrillDownTable } from '../components/DrillDownTable';
import { Users, FileText, Tag, Map } from 'lucide-react';

interface CustomersViewProps {
  filters: DashboardFilters;
  onFilterChange: (f: DashboardFilters) => void;
  onNavigate: (view: ViewId) => void;
}

export function CustomersView({ filters, onFilterChange, onNavigate }: CustomersViewProps) {
  const filtered = useMemo(() => {
    let list = customers;
    if (filters.segment !== 'alle') list = list.filter((c) => c.segment === filters.segment);
    if (filters.profitCenterId !== 'alle') list = list.filter((c) => c.profitCenterId === filters.profitCenterId);
    return list;
  }, [filters]);

  const selectedId = filters.customerId !== 'alle' ? filters.customerId : null;
  const selected = selectedId ? customers.find((c) => c.id === selectedId) : null;
  const customerContract = selected ? contracts.find((c) => c.customerId === selected.id) : null;
  const customerTariff = customerContract ? tariffs.find((t) => t.id === customerContract.tariffId) : null;
  const profitCenter = selected ? profitCenters.find((pc) => pc.id === selected.profitCenterId) : null;
  const customerConnections = selected ? connections.filter((c) => c.customerId === selected.id) : [];

  return (
    <div className="space-y-6">
      <DrillBreadcrumb filters={filters} onNavigate={onFilterChange} />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard label="Klanten" value={String(filtered.length)} icon={<Users size={18} />} />
        <KpiCard label="Actieve contracten" value={String(contracts.filter((c) => c.status === 'actief').length)} icon={<FileText size={18} />} />
        <KpiCard label="Tarieven" value={String(tariffs.length)} icon={<Tag size={18} />} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Klantenoverzicht" subtitle="Klik om te drillen" className="lg:col-span-1">
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {filtered.map((c) => {
              const margin = c.revenue - c.cost - c.sprucingCost + c.heatLossRevenue;
              const seg = SEGMENTS.find((s) => s.id === c.segment);
              const lossConns = connections.filter((x) => x.customerId === c.id && x.isLossMaking).length;
              return (
                <button
                  key={c.id}
                  onClick={() => onFilterChange(drillToCustomer(filters, c.id))}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${
                    selectedId === c.id ? 'border-eneco-green bg-eneco-light/50' : 'border-gray-100 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-sm text-eneco-dark">{c.name}</p>
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: seg?.color }} />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{seg?.label} · {formatCurrency(margin, true)} marge</p>
                  {lossConns > 0 && <Badge variant="danger">{lossConns} piekverlies</Badge>}
                </button>
              );
            })}
          </div>
        </Card>

        <div className="lg:col-span-2 space-y-6">
          {selected ? (
            <>
              <Card
                title={selected.name}
                subtitle={`${profitCenter?.name} · ${SEGMENTS.find((s) => s.id === selected.segment)?.label}`}
                action={
                  <button
                    onClick={() => onNavigate('kaart')}
                    className="flex items-center gap-1 text-sm text-eneco-green hover:underline"
                  >
                    <Map size={14} /> Bekijk op kaart
                  </button>
                }
              >
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div><p className="text-xs text-gray-500">Omzet</p><p className="font-semibold">{formatCurrency(selected.revenue, true)}</p></div>
                  <div><p className="text-xs text-gray-500">Kosten</p><p className="font-semibold">{formatCurrency(selected.cost, true)}</p></div>
                  <div><p className="text-xs text-gray-500">Volume</p><p className="font-semibold">{formatNumber(selected.volumeGJ)} GJ</p></div>
                  <div><p className="text-xs text-gray-500">Bruto marge</p><p className="font-semibold text-eneco-green">{formatCurrency(selected.revenue - selected.cost - selected.sprucingCost + selected.heatLossRevenue, true)}</p></div>
                </div>
              </Card>

              <Card title="Aansluitingen" subtitle="Klik op aansluiting voor detailniveau">
                <div className="space-y-2">
                  {customerConnections.map((conn) => (
                    <button
                      key={conn.id}
                      onClick={() => onFilterChange(drillToConnection(filters, conn.id))}
                      className={`w-full flex items-center justify-between rounded-lg border px-4 py-3 text-left transition-colors ${
                        filters.connectionId === conn.id ? 'border-eneco-green bg-eneco-light/30' : 'border-gray-100 hover:bg-gray-50'
                      }`}
                    >
                      <div>
                        <p className="font-medium text-sm">{conn.address}</p>
                        <p className="text-xs text-gray-500 capitalize">{conn.type} · {conn.volumeGJ} GJ</p>
                      </div>
                      <div className="text-right">
                        <p className="font-semibold text-sm">{formatCurrency(conn.revenue)}</p>
                        {conn.isLossMaking && <Badge variant="danger">Piekverlies</Badge>}
                      </div>
                    </button>
                  ))}
                </div>
              </Card>

              {customerContract && (
                <Card title="Contract" subtitle={customerContract.id}>
                  <div className="grid grid-cols-2 gap-4 sm:grid-cols-3">
                    <div><p className="text-xs text-gray-500">Status</p><Badge variant="success">{customerContract.status}</Badge></div>
                    <div><p className="text-xs text-gray-500">Start</p><p className="text-sm font-medium">{formatDate(customerContract.startDate)}</p></div>
                    <div><p className="text-xs text-gray-500">Eind</p><p className="text-sm font-medium">{formatDate(customerContract.endDate)}</p></div>
                    <div><p className="text-xs text-gray-500">Volume</p><p className="text-sm font-medium">{formatNumber(customerContract.volumeGJ)} GJ</p></div>
                    <div><p className="text-xs text-gray-500">Aansluitingen</p><p className="text-sm font-medium">{customerContract.connectionCount}</p></div>
                    <div><p className="text-xs text-gray-500">Tarief</p><p className="text-sm font-medium">{customerTariff?.name}</p></div>
                  </div>
                </Card>
              )}

              {customerTariff && (
                <Card title="Tarieven & componenten" subtitle={customerTariff.name}>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                          <th className="pb-3 pr-4">Component</th>
                          <th className="pb-3 pr-4">Type</th>
                          <th className="pb-3 pr-4">Eenheid</th>
                          <th className="pb-3 pr-4 text-right">Tarief</th>
                          <th className="pb-3">Omschrijving</th>
                        </tr>
                      </thead>
                      <tbody>
                        {customerTariff.components.map((tc) => (
                          <tr key={tc.id} className="border-b border-gray-100">
                            <td className="py-3 pr-4 font-medium">{tc.name}</td>
                            <td className="py-3 pr-4"><Badge variant="info">{tc.type}</Badge></td>
                            <td className="py-3 pr-4 text-gray-600">{tc.unit}</td>
                            <td className="py-3 pr-4 text-right font-mono">€{tc.rate.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}</td>
                            <td className="py-3 text-gray-600">{tc.description}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </>
          ) : (
            <Card title="Selecteer een klant" subtitle="Klik op een klant links of gebruik drill-down hieronder">
              <p className="text-gray-500 text-sm">Alle klantdata inclusief contracten, tarieven, tariefcomponenten en aansluitingen.</p>
            </Card>
          )}
        </div>
      </div>

      <DrillDownTable filters={filters} onDrill={onFilterChange} />
    </div>
  );
}
