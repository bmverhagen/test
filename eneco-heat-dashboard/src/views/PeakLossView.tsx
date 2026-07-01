import { useMemo, useState } from 'react';
import type { DashboardFilters } from '../types';
import { peakLossProfiles } from '../data/connections';
import { connections } from '../data/connections';
import { formatCurrency, formatPercent } from '../utils/format';
import { drillToCustomer, drillToConnection } from '../utils/drill';
import { Card, Badge } from '../components/ui';
import { KpiCard } from '../components/KpiCard';
import { DrillBreadcrumb } from '../components/DrillBreadcrumb';
import { ConnectionMap } from '../components/ConnectionMap';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ReferenceArea,
} from 'recharts';
import { AlertTriangle, TrendingDown, Clock } from 'lucide-react';

interface PeakLossViewProps {
  filters: DashboardFilters;
  onFilterChange: (f: DashboardFilters) => void;
}

export function PeakLossView({ filters, onFilterChange }: PeakLossViewProps) {
  const [selectedCustomerId, setSelectedCustomerId] = useState<string | null>(null);

  const lossProfiles = useMemo(() =>
    [...peakLossProfiles].sort((a, b) => b.annualLoss - a.annualLoss),
  []);

  const totalLoss = lossProfiles.reduce((s, p) => s + p.annualLoss, 0);
  const selected = selectedCustomerId
    ? lossProfiles.find((p) => p.customerId === selectedCustomerId)
    : lossProfiles[0];

  const lossConnections = connections.filter((c) => c.isLossMaking);

  return (
    <div className="space-y-6">
      <DrillBreadcrumb filters={filters} onNavigate={onFilterChange} />

      <div className="rounded-xl border border-red-200 bg-red-50 p-4 flex items-start gap-3">
        <AlertTriangle className="text-red-600 mt-0.5 shrink-0" size={22} />
        <div>
          <p className="font-semibold text-red-900">Piekverbruik verliesanalyse</p>
          <p className="text-sm text-red-800 mt-1">
            Klanten waarvan de effectieve kostprijs boven het contracttarief uitkomt doordat zij warmte afnemen
            op dure momenten (ochtend- en avondpiek 07–09 en 17–20 uur). Het vaste tarief dekt deze piek-kosten niet.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Totaal piekverlies" value={formatCurrency(totalLoss, true)} variant="negative" icon={<TrendingDown size={18} />} />
        <KpiCard label="Verliesgevende klanten" value={String(lossProfiles.filter((p) => p.annualLoss > 0).length)} icon={<AlertTriangle size={18} />} />
        <KpiCard label="Verliesgevende aansluitingen" value={String(lossConnections.length)} subValue={`van ${connections.length} totaal`} />
        <KpiCard label="Gem. piekshare" value={formatPercent(lossProfiles.reduce((s, p) => s + p.peakSharePct, 0) / lossProfiles.length)} icon={<Clock size={18} />} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <Card title="Verliesgevende klanten" subtitle="Klik voor uurprofiel analyse" className="lg:col-span-1">
          <div className="space-y-2 max-h-[480px] overflow-y-auto">
            {lossProfiles.map((p) => (
              <button
                key={p.customerId}
                onClick={() => {
                  setSelectedCustomerId(p.customerId);
                  onFilterChange(drillToCustomer(filters, p.customerId));
                }}
                className={`w-full text-left rounded-lg border p-3 transition-colors ${
                  selected?.customerId === p.customerId
                    ? 'border-red-300 bg-red-50'
                    : 'border-gray-100 hover:bg-gray-50'
                }`}
              >
                <div className="flex items-center justify-between">
                  <p className="font-medium text-sm text-eneco-dark">{p.customerName}</p>
                  <Badge variant="danger">-{formatCurrency(p.annualLoss, true)}</Badge>
                </div>
                <div className="mt-2 grid grid-cols-3 gap-2 text-xs text-gray-500">
                  <div>Tarief: €{p.tariffRatePerGJ}</div>
                  <div className="text-red-600">Effectief: €{p.effectiveCostPerGJ.toFixed(2)}</div>
                  <div>Piek: {formatPercent(p.peakSharePct)}</div>
                </div>
                <p className="mt-1 text-[10px] text-gray-400">
                  {p.lossConnectionCount}/{p.connectionCount} aansluitingen verliesgevend
                </p>
              </button>
            ))}
          </div>
        </Card>

        {selected && (
          <div className="lg:col-span-2 space-y-6">
            <Card title={`Uurprofiel: ${selected.customerName}`} subtitle="Verbruik vs. marktprijs (P) — overlap op piekuren = verlies">
              <ResponsiveContainer width="100%" height={320}>
                <ComposedChart data={selected.hourlyProfile}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
                  <XAxis dataKey="hour" tickFormatter={(h) => `${h}:00`} tick={{ fontSize: 10 }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 10 }} label={{ value: 'Verbruik %', angle: -90, position: 'insideLeft', fontSize: 10 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} label={{ value: 'P €/GJ', angle: 90, position: 'insideRight', fontSize: 10 }} />
                  <Tooltip
                    formatter={(value, name) => {
                      const v = Number(value ?? 0);
                      const n = String(name ?? '');
                      if (n.includes('prijs') || n.includes('Markt')) return [`€${v.toFixed(2)}/GJ`, n];
                      return [`${v.toFixed(1)}%`, n];
                    }}
                    labelFormatter={(h) => `Uur ${h}:00`}
                  />
                  <ReferenceArea yAxisId="left" x1={7} x2={9} fill="#ff6b35" fillOpacity={0.08} />
                  <ReferenceArea yAxisId="left" x1={17} x2={20} fill="#ff6b35" fillOpacity={0.08} />
                  <Bar yAxisId="left" dataKey="consumptionPct" name="Verbruik %" fill="#0077b6" opacity={0.7} radius={[2, 2, 0, 0]} />
                  <Line yAxisId="right" type="monotone" dataKey="marketPrice" name="Marktprijs P" stroke="#ff6b35" strokeWidth={2} dot={false} />
                  <Legend />
                </ComposedChart>
              </ResponsiveContainer>
              <div className="mt-3 flex flex-wrap gap-3 text-xs">
                <span className="rounded bg-orange-100 px-2 py-1 text-orange-800">Piekuren: 07–09 & 17–20</span>
                <span className="text-gray-500">Spread: <strong className="text-red-600">+€{selected.spreadPerGJ.toFixed(2)}/GJ</strong> boven tarief</span>
                <span className="text-gray-500">Volume: {selected.volumeGJ.toLocaleString('nl-NL')} GJ</span>
              </div>
            </Card>

            <Card title="Verliesgevende aansluitingen" subtitle={`${selected.customerName}`}>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                      <th className="pb-3 pr-4">Adres</th>
                      <th className="pb-3 pr-4 text-right">Tarief</th>
                      <th className="pb-3 pr-4 text-right">Effectief</th>
                      <th className="pb-3 pr-4 text-right">Piek %</th>
                      <th className="pb-3 text-right">Verlies</th>
                    </tr>
                  </thead>
                  <tbody>
                    {connections
                      .filter((c) => c.customerId === selected.customerId && c.isLossMaking)
                      .map((c) => (
                        <tr
                          key={c.id}
                          onClick={() => onFilterChange(drillToConnection(filters, c.id))}
                          className="border-b border-gray-100 hover:bg-red-50/50 cursor-pointer"
                        >
                          <td className="py-2.5 pr-4 font-medium">{c.address}</td>
                          <td className="py-2.5 pr-4 text-right">€{c.tariffRatePerGJ}</td>
                          <td className="py-2.5 pr-4 text-right text-red-600">€{c.effectiveCostPerGJ}</td>
                          <td className="py-2.5 pr-4 text-right">{formatPercent(c.peakSharePct)}</td>
                          <td className="py-2.5 text-right font-semibold text-red-600">{formatCurrency(c.lossAmount)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}
      </div>

      <Card title="Kaart verliesgevende aansluitingen" subtitle="Rood = effectieve kostprijs &gt; tarief door piekverbruik">
        <ConnectionMap
          filters={filters}
          showLossOnly
          onSelectConnection={(id) => onFilterChange(drillToConnection(filters, id))}
        />
      </Card>
    </div>
  );
}
