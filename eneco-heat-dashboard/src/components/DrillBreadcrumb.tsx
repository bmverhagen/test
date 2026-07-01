import type { DashboardFilters } from '../types';
import { getBreadcrumbs, filtersFromBreadcrumb } from '../utils/drill';
import { cn } from '../utils/format';
import { ChevronRight, Home, Layers } from 'lucide-react';

interface DrillBreadcrumbProps {
  filters: DashboardFilters;
  onNavigate: (filters: DashboardFilters) => void;
  className?: string;
}

const LEVEL_LABELS: Record<string, string> = {
  portfolio: 'Portfolio',
  segment: 'Segment',
  profitCenter: 'Profit center',
  customer: 'Klant',
  connection: 'Aansluiting',
};

export function DrillBreadcrumb({ filters, onNavigate, className }: DrillBreadcrumbProps) {
  const crumbs = getBreadcrumbs(filters);
  const currentLevel = crumbs[crumbs.length - 1]?.level ?? 'portfolio';

  return (
    <div className={cn(
      'flex flex-wrap items-center gap-2 rounded-2xl border border-eneco-green/15 bg-white/80 px-3 py-3 sm:px-5 sm:py-3.5 shadow-card backdrop-blur-sm w-full max-w-full',
      className,
    )}>
      <div className="flex items-center gap-1.5 text-eneco-green mr-1">
        <Layers size={15} />
        <span className="text-xs font-bold uppercase tracking-wider">Drill-down</span>
      </div>

      <div className="h-4 w-px bg-eneco-green/20" />

      {crumbs.map((crumb, i) => {
        const isLast = i === crumbs.length - 1;
        const targetFilters = {
          ...filtersFromBreadcrumb(crumb),
          period: filters.period,
          costType: filters.costType,
          revenueType: filters.revenueType,
        };

        return (
          <span key={`${crumb.level}-${crumb.label}`} className="flex items-center gap-1">
            {i > 0 && <ChevronRight size={14} className="text-eneco-green/30" />}
            <button
              onClick={() => onNavigate(targetFilters)}
              disabled={isLast}
              className={cn(
                'flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-sm transition-all duration-200',
                isLast
                  ? 'bg-gradient-to-r from-eneco-light to-white font-bold text-eneco-dark ring-1 ring-eneco-green/20 cursor-default'
                  : 'font-medium text-eneco-green hover:bg-eneco-light/60',
              )}
            >
              {i === 0 && <Home size={13} />}
              {crumb.label}
            </button>
          </span>
        );
      })}

      <span className="sm:ml-auto flex items-center gap-1.5 rounded-full bg-eneco-dark px-3 py-1 text-[10px] font-bold uppercase tracking-wider text-eneco-mint w-full sm:w-auto justify-center sm:justify-start mt-2 sm:mt-0">
        <span className="h-1.5 w-1.5 rounded-full bg-eneco-green animate-pulse" />
        {LEVEL_LABELS[currentLevel]}
      </span>
    </div>
  );
}
