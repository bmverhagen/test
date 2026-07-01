import { useState, useMemo } from 'react';
import { customers, contracts, tariffs, profitCenters, SEGMENTS } from '../data/dummyData';
import { formatCurrency, formatNumber, formatDate } from '../utils/format';
import { Card, Badge } from '../components/ui';
import { KpiCard } from '../components/KpiCard';
import { Users, FileText, Tag } from 'lucide-react';

export function CustomersView() {
  const [selectedCustomer, setSelectedCustomer] = useState<string | null>(null);
  const [segmentFilter, setSegmentFilter] = useState('alle');

  const filtered = useMemo(() => {
    if (segmentFilter === 'alle') return customers;
    return customers.filter((c) => c.segment === segmentFilter);
  }, [segmentFilter]);

  const selected = customers.find((c) => c.id === selectedCustomer);
  const customerContract = selected ? contracts.find((c) => c.customerId === selected.id) : null;
  const customerTariff = customerContract ? tariffs.find((t) => t.id === customerContract.tariffId) : null;
  const profitCenter = selected ? profitCenters.find((pc) => pc.id === selected.profitCenterId) : null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard label="Klanten" value={String(customers.length)} icon={<Users size={18} />} />
        <KpiCard label="Actieve contracten" value={String(contracts.filter((c) => c.status === 'actief').length)} icon={<FileText size={18} />} />
        <KpiCard label="Tarieven" value={String(tariffs.length)} icon={<Tag size={18} />} />
      </div>

      <div className="flex items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <label className="text-xs font-medium text-gray-500">Segment</label>
        <select
          value={segmentFilter}
          onChange={(e) => { setSegmentFilter(e.target.value); setSelectedCustomer(null); }}
          className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm"
        >
          <option value="alle">Alle segmenten</option>
          {SEGMENTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Klantenoverzicht" subtitle="Selecteer voor detail" className="lg:col-span-1">
          <div className="space-y-2 max-h-[500px] overflow-y-auto">
            {filtered.map((c) => {
              const margin = c.revenue - c.cost - c.sprucingCost + c.heatLossRevenue;
              const seg = SEGMENTS.find((s) => s.id === c.segment);
              return (
                <button
                  key={c.id}
                  onClick={() => setSelectedCustomer(c.id)}
                  className={`w-full text-left rounded-lg border p-3 transition-colors ${
                    selectedCustomer === c.id ? 'border-eneco-green bg-eneco-light/50' : 'border-gray-100 hover:bg-gray-50'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <p className="font-medium text-sm text-eneco-dark">{c.name}</p>
                    <span className="h-2 w-2 rounded-full" style={{ backgroundColor: seg?.color }} />
                  </div>
                  <p className="text-xs text-gray-500 mt-1">{seg?.label} · {formatCurrency(margin, true)} marge</p>
                </button>
              );
            })}
          </div>
        </Card>

        <div className="lg:col-span-2 space-y-6">
          {selected ? (
            <>
              <Card title={selected.name} subtitle={`${profitCenter?.name} · ${SEGMENTS.find((s) => s.id === selected.segment)?.label}`}>
                <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  <div><p className="text-xs text-gray-500">Omzet</p><p className="font-semibold">{formatCurrency(selected.revenue, true)}</p></div>
                  <div><p className="text-xs text-gray-500">Kosten</p><p className="font-semibold">{formatCurrency(selected.cost, true)}</p></div>
                  <div><p className="text-xs text-gray-500">Volume</p><p className="font-semibold">{formatNumber(selected.volumeGJ)} GJ</p></div>
                  <div><p className="text-xs text-gray-500">Bruto marge</p><p className="font-semibold text-eneco-green">{formatCurrency(selected.revenue - selected.cost - selected.sprucingCost + selected.heatLossRevenue, true)}</p></div>
                </div>
                <div className="mt-4 grid grid-cols-2 gap-4">
                  <div className="rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-medium text-gray-500 mb-2">Omzet structuur</p>
                    <div className="flex justify-between text-sm"><span>Vast</span><span>{formatCurrency(selected.revenueFixed, true)}</span></div>
                    <div className="flex justify-between text-sm mt-1"><span>Variabel</span><span>{formatCurrency(selected.revenueVariable, true)}</span></div>
                  </div>
                  <div className="rounded-lg bg-gray-50 p-3">
                    <p className="text-xs font-medium text-gray-500 mb-2">Kosten structuur</p>
                    <div className="flex justify-between text-sm"><span>Vast</span><span>{formatCurrency(selected.costFixed, true)}</span></div>
                    <div className="flex justify-between text-sm mt-1"><span>Variabel</span><span>{formatCurrency(selected.costVariable, true)}</span></div>
                  </div>
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
            <Card title="Selecteer een klant" subtitle="Klik op een klant links voor contract- en tariefdetails">
              <p className="text-gray-500 text-sm">Alle klantdata inclusief contracten, tarieven en tariefcomponenten is beschikbaar na selectie.</p>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
