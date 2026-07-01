import { useMemo } from 'react';
import { revenueYTD } from '../data/dummyData';
import { formatCurrency, formatNumber } from '../utils/format';
import { Card, Badge } from '../components/ui';
import { KpiCard } from '../components/KpiCard';
import {
  ComposedChart, Bar, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend, Area, ReferenceLine,
} from 'recharts';
import { AlertTriangle, CheckCircle, Calculator } from 'lucide-react';

export function RevenueYTDView() {
  const chartData = revenueYTD.map((m) => ({
    month: m.month,
    actual: m.revenueActual,
    estimated: m.revenueEstimated,
    volumeActual: m.volumeActualGJ,
    volumeEstimated: m.volumeEstimatedGJ,
    isEstimated: m.isEstimated,
    total: m.revenueActual + m.revenueEstimated,
    volumeTotal: m.volumeActualGJ + m.volumeEstimatedGJ,
  }));

  const totals = useMemo(() => {
    const actualRev = revenueYTD.reduce((s, m) => s + m.revenueActual, 0);
    const estRev = revenueYTD.reduce((s, m) => s + m.revenueEstimated, 0);
    const actualVol = revenueYTD.reduce((s, m) => s + m.volumeActualGJ, 0);
    const estVol = revenueYTD.reduce((s, m) => s + m.volumeEstimatedGJ, 0);
    return { actualRev, estRev, actualVol, estVol, total: actualRev + estRev };
  }, []);

  const estimatedPct = totals.total > 0 ? (totals.estRev / totals.total) * 100 : 0;
  const lastActualMonth = revenueYTD.filter((m) => !m.isEstimated).pop()?.month ?? 'Mei';

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 flex items-start gap-3">
        <AlertTriangle className="text-amber-600 mt-0.5 shrink-0" size={20} />
        <div>
          <p className="font-medium text-amber-900">Modelmatige schatting actief vanaf juni</p>
          <p className="text-sm text-amber-700 mt-1">
            Vanaf {lastActualMonth} worden omzet en volumes (GJ) deels modelmatig ingeschat.
            Geschat deel: {estimatedPct.toFixed(0)}% van YTD omzet ({formatCurrency(totals.estRev, true)}).
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Omzet YTD totaal" value={formatCurrency(totals.total, true)} icon={<Calculator size={18} />} />
        <KpiCard label="Werkelijk (jan–jun)" value={formatCurrency(totals.actualRev, true)} variant="positive" icon={<CheckCircle size={18} />} />
        <KpiCard label="Geschat (jun–dec)" value={formatCurrency(totals.estRev, true)} subValue={`${estimatedPct.toFixed(0)}% van totaal`} variant="accent" icon={<AlertTriangle size={18} />} />
        <KpiCard label="Volume YTD (GJ)" value={formatNumber(totals.actualVol + totals.estVol)} subValue={`${formatNumber(totals.estVol)} GJ geschat`} />
      </div>

      <Card title="Revenue YTD — backward view" subtitle="Werkelijke vs. modelmatig geschatte omzet per maand">
        <ResponsiveContainer width="100%" height={380}>
          <ComposedChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
            <XAxis dataKey="month" tick={{ fontSize: 12 }} />
            <YAxis yAxisId="left" tickFormatter={(v) => formatCurrency(v, true)} tick={{ fontSize: 11 }} />
            <YAxis yAxisId="right" orientation="right" tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 11 }} />
            <Tooltip
              formatter={(value, name) => {
                const v = Number(value ?? 0);
                const n = String(name ?? '');
                if (n.includes('Volume')) return [`${formatNumber(v)} GJ`, n];
                return [formatCurrency(v, true), n];
              }}
            />
            <Legend />
            <ReferenceLine x="Jun" stroke="#ff6b35" strokeDasharray="5 5" label={{ value: 'Schatting start', position: 'top', fontSize: 11 }} />
            <Bar yAxisId="left" dataKey="actual" name="Omzet werkelijk" fill="#00a651" stackId="rev" radius={[0, 0, 0, 0]} />
            <Bar yAxisId="left" dataKey="estimated" name="Omzet geschat" fill="#ff6b35" stackId="rev" radius={[4, 4, 0, 0]} opacity={0.7} />
            <Line yAxisId="right" type="monotone" dataKey="volumeTotal" name="Volume totaal (GJ)" stroke="#0077b6" strokeWidth={2} dot={{ r: 3 }} />
          </ComposedChart>
        </ResponsiveContainer>
      </Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Volume YTD (GJ)" subtitle="Werkelijk vs. geschat volume">
          <ResponsiveContainer width="100%" height={280}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
              <XAxis dataKey="month" tick={{ fontSize: 12 }} />
              <YAxis tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => [`${formatNumber(Number(v ?? 0))} GJ`, '']} />
              <Legend />
              <Area type="monotone" dataKey="volumeActual" name="Volume werkelijk" fill="#00a651" fillOpacity={0.2} stroke="#00a651" />
              <Area type="monotone" dataKey="volumeEstimated" name="Volume geschat" fill="#ff6b35" fillOpacity={0.15} stroke="#ff6b35" strokeDasharray="5 5" />
            </ComposedChart>
          </ResponsiveContainer>
        </Card>

        <Card title="Maanddetail" subtitle="Status per maand">
          <div className="space-y-2 max-h-[280px] overflow-y-auto">
            {revenueYTD.map((m) => (
              <div key={m.month} className="flex items-center justify-between rounded-lg border border-gray-100 px-4 py-3 hover:bg-gray-50">
                <div className="flex items-center gap-3">
                  <span className="font-medium text-eneco-dark w-8">{m.month}</span>
                  <Badge variant={m.isEstimated ? 'warning' : 'success'}>
                    {m.isEstimated ? 'Geschat' : 'Werkelijk'}
                  </Badge>
                </div>
                <div className="text-right">
                  <p className="font-semibold text-sm">{formatCurrency(m.revenueActual + m.revenueEstimated, true)}</p>
                  <p className="text-xs text-gray-500">{formatNumber(m.volumeActualGJ + m.volumeEstimatedGJ)} GJ</p>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
