import { ChevronRight, Home } from 'lucide-react';
import type { DashboardFilters } from '../types';
import { getBreadcrumbs, filtersFromBreadcrumb } from '../utils/drill';
import { cn } from '../utils/format';

interface DrillBreadcrumbProps {
  filters: DashboardFilters;
  onNavigate: (filters: DashboardFilters) => void;
  className?: string;
}

export function DrillBreadcrumb({ filters, onNavigate, className }: DrillBreadcrumbProps) {
  const crumbs = getBreadcrumbs(filters);

  return (
    <nav className={cn('flex flex-wrap items-center gap-1 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm', className)}>
      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        const targetFilters: DashboardFilters = {
          ...filtersFromBreadcrumb(crumb),
          period: filters.period,
          costType: filters.costType,
          revenueType: filters.revenueType,
        };

        return (
          <span key={`${crumb.level}-${crumb.label}`} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={14} className="text-gray-300" />}
            <button
              onClick={() => onNavigate(targetFilters)}
              disabled={isLast}
              className={cn(
                'flex items-center gap-1.5 rounded-md px-2 py-1 text-sm transition-colors',
                isLast
                  ? 'font-semibold text-eneco-dark cursor-default'
                  : 'text-eneco-green hover:bg-eneco-light/50 hover:underline',
              )}
            >
              {i === 0 && <Home size={14} />}
              {crumb.label}
            </button>
          </span>
        );
      })}
      <span className="ml-auto text-xs text-gray-400">
        Niveau: {crumbs[crumbs.length - 1]?.level === 'portfolio' ? 'Portfolio' :
          crumbs[crumbs.length - 1]?.level === 'segment' ? 'Segment' :
          crumbs[crumbs.length - 1]?.level === 'profitCenter' ? 'Profit center' :
          crumbs[crumbs.length - 1]?.level === 'customer' ? 'Klant' : 'Aansluiting'}
      </span>
    </nav>
  );
}
