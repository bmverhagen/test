import { cn } from '../utils/format';

interface KpiCardProps {
  label: string;
  value: string;
  subValue?: string;
  trend?: number;
  variant?: 'default' | 'positive' | 'negative' | 'accent';
  icon?: React.ReactNode;
}

export function KpiCard({ label, value, subValue, trend, variant = 'default', icon }: KpiCardProps) {
  const variants = {
    default: 'border-gray-200',
    positive: 'border-eneco-green/30 bg-eneco-light/50',
    negative: 'border-red-200 bg-red-50/50',
    accent: 'border-eneco-accent/30 bg-orange-50/50',
  };

  return (
    <div className={cn('rounded-xl border bg-white p-5 shadow-sm', variants[variant])}>
      <div className="flex items-start justify-between">
        <p className="text-sm font-medium text-gray-500">{label}</p>
        {icon && <div className="text-eneco-green">{icon}</div>}
      </div>
      <p className="mt-2 text-2xl font-bold text-eneco-dark">{value}</p>
      <div className="mt-1 flex items-center gap-2">
        {subValue && <span className="text-xs text-gray-500">{subValue}</span>}
        {trend !== undefined && (
          <span className={cn('text-xs font-medium', trend >= 0 ? 'text-eneco-green' : 'text-red-500')}>
            {trend >= 0 ? '↑' : '↓'} {Math.abs(trend).toFixed(1)}%
          </span>
        )}
      </div>
    </div>
  );
}
