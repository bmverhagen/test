import type { DashboardFilters } from '../types';
import { getDrillRows, applyDrillClick } from '../utils/drill';
import { formatCurrency } from '../utils/format';
import { Card } from './ui';
import { ChevronRight, MousePointerClick } from 'lucide-react';

interface DrillDownTableProps {
  filters: DashboardFilters;
  onDrill: (filters: DashboardFilters) => void;
  title?: string;
  subtitle?: string;
}

export function DrillDownTable({ filters, onDrill, title = 'Drill-down', subtitle }: DrillDownTableProps) {
  const rows = getDrillRows(filters);

  const defaultSubtitle =
    filters.connectionId !== 'alle' ? 'Aansluiting detail — laagste niveau' :
    filters.customerId !== 'alle' ? 'Klik op aansluiting voor detail' :
    filters.profitCenterId !== 'alle' ? 'Klik op klant om door te drillen' :
    filters.segment !== 'alle' ? 'Klik op profit center om door te drillen' :
    'Klik op segment om door te drillen';

  return (
    <Card title={title} subtitle={subtitle ?? defaultSubtitle} variant="elevated">
      <div className="overflow-x-auto -mx-2">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-[10px] font-bold uppercase tracking-wider text-gray-400">
              <th className="pb-3 pl-2 pr-4">Naam</th>
              <th className="pb-3 pr-4 text-right">Omzet</th>
              <th className="pb-3 pr-4 text-right">Kosten</th>
              <th className="pb-3 pr-4 text-right">Bruto marge</th>
              <th className="pb-3 pr-4 text-right">Volume GJ</th>
              <th className="pb-3 w-10" />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={row.id}
                onClick={() => row.canDrill && onDrill(applyDrillClick(filters, row))}
                className={`drill-row border-t border-gray-100/80 ${row.canDrill ? 'cursor-pointer' : 'opacity-80'}`}
                style={{ animationDelay: `${i * 0.03}s` }}
              >
                <td className="py-3.5 pl-2 pr-4">
                  <span className="font-semibold text-eneco-dark">{row.name}</span>
                </td>
                <td className="py-3.5 pr-4 text-right font-medium text-gray-600">{formatCurrency(row.revenue, true)}</td>
                <td className="py-3.5 pr-4 text-right text-gray-500">{formatCurrency(row.cost, true)}</td>
                <td className={`py-3.5 pr-4 text-right font-bold ${row.margin >= 0 ? 'text-eneco-green' : 'text-eneco-red'}`}>
                  {formatCurrency(row.margin, true)}
                </td>
                <td className="py-3.5 pr-4 text-right text-gray-400 tabular-nums">{row.volumeGJ.toLocaleString('nl-NL')}</td>
                <td className="py-3.5 pr-2">
                  {row.canDrill && (
                    <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-eneco-light text-eneco-green transition-colors group-hover:bg-eneco-green group-hover:text-white">
                      <ChevronRight size={15} />
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {rows.some((r) => r.canDrill) && (
        <div className="mt-4 flex items-center gap-2 text-xs text-gray-400">
          <MousePointerClick size={13} className="text-eneco-green" />
          Klik op een rij om naar het volgende detailniveau te gaan
        </div>
      )}
    </Card>
  );
}
