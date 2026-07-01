import { useMemo, useState } from 'react';
import { sourcingHourly } from '../data/dummyData';
import { formatCurrency, formatNumber, formatDateTime } from '../utils/format';
import { Card, Badge } from '../components/ui';
import { KpiCard } from '../components/KpiCard';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, ScatterChart, Scatter, ZAxis,
} from 'recharts';
import { Zap, Droplets, FileText } from 'lucide-react';

const GRIDS = [
  { id: 'grid-ams-01', name: 'AMS Noord' },
  { id: 'grid-ams-02', name: 'AMS Zuid' },
  { id: 'grid-rtd-01', name: 'RTD Haven' },
  { id: 'grid-rtd-02', name: 'RTD Botlek' },
  { id: 'grid-utr-01', name: 'UTR Centrum' },
];

export function SourcingView() {
  const [selectedGrid, setSelectedGrid] = useState('grid-ams-01');
  const [selectedDay, setSelectedDay] = useState(0);

  const gridData = useMemo(() => {
    return sourcingHourly.filter((s) => s.gridId === selectedGrid);
  }, [selectedGrid]);

  const dayData = useMemo(() => {
    const baseDate = new Date('2025-06-15T00:00:00');
    baseDate.setDate(baseDate.getDate() + selectedDay);
    const dayStart = baseDate.toISOString().slice(0, 10);
    return gridData.filter((s) => s.timestamp.startsWith(dayStart));
  }, [gridData, selectedDay]);

  const hourlyChart = useMemo(() => {
    return dayData.map((s) => ({
      hour: new Date(s.timestamp).getHours().toString().padStart(2, '0') + ':00',
      priceP: s.priceP,
      volumeQ: s.volumeQ,
      value: s.priceP * s.volumeQ,
      invoiceStatus: s.invoiceStatus,
    }));
  }, [dayData]);

  const stats = useMemo(() => {
    const totalQ = dayData.reduce((s, d) => s + d.volumeQ, 0);
    const avgP = dayData.length > 0 ? dayData.reduce((s, d) => s + d.priceP, 0) / dayData.length : 0;
    const invoiced = dayData.filter((d) => d.invoiceStatus === 'gefactureerd').length;
    const open = dayData.filter((d) => d.invoiceStatus === 'open').length;
    const deviation = dayData.filter((d) => d.invoiceStatus === 'afwijking').length;
    const totalInvoice = dayData.reduce((s, d) => s + (d.invoiceAmount ?? 0), 0);
    return { totalQ, avgP, invoiced, open, deviation, totalInvoice };
  }, [dayData]);

  const pqScatter = useMemo(() => {
    return dayData.map((s) => ({
      p: s.priceP,
      q: s.volumeQ,
      status: s.invoiceStatus,
      hour: new Date(s.timestamp).getHours(),
    }));
  }, [dayData]);

  const statusVariant = (s: string) => {
    if (s === 'gefactureerd') return 'success' as const;
    if (s === 'afwijking') return 'danger' as const;
    return 'warning' as const;
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-500">Grid</label>
          <select
            value={selectedGrid}
            onChange={(e) => setSelectedGrid(e.target.value)}
            className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none"
          >
            {GRIDS.map((g) => (
              <option key={g.id} value={g.id}>{g.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-xs font-medium text-gray-500">Dag</label>
          <select
            value={selectedDay}
            onChange={(e) => setSelectedDay(Number(e.target.value))}
            className="rounded-lg border border-gray-200 bg-gray-50 px-3 py-1.5 text-sm focus:border-eneco-green focus:outline-none"
          >
            {Array.from({ length: 7 }, (_, i) => {
              const d = new Date('2025-06-15');
              d.setDate(d.getDate() + i);
              return (
                <option key={i} value={i}>
                  {d.toLocaleDateString('nl-NL', { weekday: 'short', day: 'numeric', month: 'short' })}
                </option>
              );
            })}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Gem. prijs (P)" value={`€${stats.avgP.toFixed(2)}/GJ`} icon={<Zap size={18} />} />
        <KpiCard label="Totaal volume (Q)" value={`${formatNumber(stats.totalQ, 1)} GJ`} icon={<Droplets size={18} />} />
        <KpiCard label="Factuurwaarde" value={formatCurrency(stats.totalInvoice, true)} icon={<FileText size={18} />} />
        <KpiCard
          label="Factuurstatus"
          value={`${stats.invoiced} / ${stats.open + stats.deviation}`}
          subValue={`${stats.deviation} afwijkingen`}
          variant={stats.deviation > 0 ? 'negative' : 'positive'}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="P & Q op uurniveau" subtitle={`${GRIDS.find((g) => g.id === selectedGrid)?.name} — prijs en volume per uur`}>
          <ResponsiveContainer width="100%" height={320}>
            <ComposedChart data={hourlyChart}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
              <XAxis dataKey="hour" tick={{ fontSize: 10 }} interval={2} />
              <YAxis yAxisId="left" tick={{ fontSize: 11 }} label={{ value: 'P (€/GJ)', angle: -90, position: 'insideLeft', fontSize: 11 }} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 11 }} label={{ value: 'Q (GJ)', angle: 90, position: 'insideRight', fontSize: 11 }} />
              <Tooltip />
              <Legend />
              <Bar yAxisId="right" dataKey="volumeQ" name="Volume Q (GJ)" fill="#0077b6" opacity={0.6} radius={[2, 2, 0, 0]} />
              <Line yAxisId="left" type="monotone" dataKey="priceP" name="Prijs P (€/GJ)" stroke="#ff6b35" strokeWidth={2} dot={{ r: 2 }} />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>

        <Card title="P vs. Q scatter" subtitle="Relatie prijs-volume met factuurstatus">
          <ResponsiveContainer width="100%" height={320}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
              <XAxis type="number" dataKey="p" name="P" unit=" €/GJ" tick={{ fontSize: 11 }} />
              <YAxis type="number" dataKey="q" name="Q" unit=" GJ" tick={{ fontSize: 11 }} />
              <ZAxis range={[40, 40]} />
              <Tooltip cursor={{ strokeDasharray: '3 3' }} />
              <Scatter name="Gefactureerd" data={pqScatter.filter((p) => p.status === 'gefactureerd')} fill="#00a651" />
              <Scatter name="Open" data={pqScatter.filter((p) => p.status === 'open')} fill="#f59e0b" />
              <Scatter name="Afwijking" data={pqScatter.filter((p) => p.status === 'afwijking')} fill="#ef4444" />
              <Legend />
            </ScatterChart>
          </ResponsiveContainer>
        </Card>
      </div>

      <Card title="Uurdata met factuurkoppeling" subtitle="Sourcing volumes gekoppeld aan invoices">
        <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                <th className="pb-3 pr-4">Tijdstip</th>
                <th className="pb-3 pr-4 text-right">P (€/GJ)</th>
                <th className="pb-3 pr-4 text-right">Q (GJ)</th>
                <th className="pb-3 pr-4 text-right">Waarde</th>
                <th className="pb-3 pr-4">Invoice</th>
                <th className="pb-3 pr-4 text-right">Factuurbedrag</th>
                <th className="pb-3">Status</th>
              </tr>
            </thead>
            <tbody>
              {dayData.map((row) => (
                <tr key={row.timestamp} className="border-b border-gray-100 hover:bg-gray-50">
                  <td className="py-2.5 pr-4 font-mono text-xs">{formatDateTime(row.timestamp)}</td>
                  <td className="py-2.5 pr-4 text-right">{row.priceP.toFixed(2)}</td>
                  <td className="py-2.5 pr-4 text-right">{row.volumeQ.toFixed(1)}</td>
                  <td className="py-2.5 pr-4 text-right font-medium">{formatCurrency(row.priceP * row.volumeQ)}</td>
                  <td className="py-2.5 pr-4 font-mono text-xs text-gray-600">{row.invoiceId ?? '—'}</td>
                  <td className="py-2.5 pr-4 text-right">{row.invoiceAmount ? formatCurrency(row.invoiceAmount) : '—'}</td>
                  <td className="py-2.5">
                    <Badge variant={statusVariant(row.invoiceStatus)}>{row.invoiceStatus}</Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
