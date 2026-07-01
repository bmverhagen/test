import type { DashboardFilters } from '../types';
import { getDrillRows, applyDrillClick } from '../utils/drill';
import { formatCurrency } from '../utils/format';
import { Card } from './ui';
import { ChevronRight } from 'lucide-react';

interface DrillDownTableProps {
  filters: DashboardFilters;
  onDrill: (filters: DashboardFilters) => void;
  title?: string;
  subtitle?: string;
}

export function DrillDownTable({ filters, onDrill, title = 'Drill-down', subtitle }: DrillDownTableProps) {
  const rows = getDrillRows(filters);

  const defaultSubtitle =
    filters.connectionId !== 'alle' ? 'Aansluiting detail' :
    filters.customerId !== 'alle' ? 'Klik op aansluiting voor detail' :
    filters.profitCenterId !== 'alle' ? 'Klik op klant om door te drillen' :
    filters.segment !== 'alle' ? 'Klik op profit center om door te drillen' :
    'Klik op segment om door te drillen';

  return (
    <Card title={title} subtitle={subtitle ?? defaultSubtitle}>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
              <th className="pb-3 pr-4">Naam</th>
              <th className="pb-3 pr-4 text-right">Omzet</th>
              <th className="pb-3 pr-4 text-right">Kosten</th>
              <th className="pb-3 pr-4 text-right">Bruto marge</th>
              <th className="pb-3 pr-4 text-right">Volume GJ</th>
              <th className="pb-3 w-8" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.id}
                onClick={() => row.canDrill && onDrill(applyDrillClick(filters, row))}
                className={`border-b border-gray-100 transition-colors ${
                  row.canDrill ? 'cursor-pointer hover:bg-eneco-light/40' : 'bg-gray-50/50'
                }`}
              >
                <td className="py-3 pr-4 font-medium text-eneco-dark">{row.name}</td>
                <td className="py-3 pr-4 text-right text-gray-600">{formatCurrency(row.revenue, true)}</td>
                <td className="py-3 pr-4 text-right text-gray-600">{formatCurrency(row.cost, true)}</td>
                <td className={`py-3 pr-4 text-right font-semibold ${row.margin >= 0 ? 'text-eneco-green' : 'text-red-500'}`}>
                  {formatCurrency(row.margin, true)}
                </td>
                <td className="py-3 pr-4 text-right text-gray-500">{row.volumeGJ.toLocaleString('nl-NL')}</td>
                <td className="py-3 text-gray-400">
                  {row.canDrill && <ChevronRight size={16} />}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.some((r) => r.canDrill) && (
        <p className="mt-3 text-xs text-gray-400">Klik op een rij om naar het volgende detailniveau te gaan</p>
      )}
    </Card>
  );
}
