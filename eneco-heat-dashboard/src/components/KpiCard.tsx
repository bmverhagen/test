import { cn } from '../utils/format';
import { TrendingUp, TrendingDown } from 'lucide-react';

interface KpiCardProps {
  label: string;
  value: string;
  subValue?: string;
  trend?: number;
  variant?: 'default' | 'positive' | 'negative' | 'accent' | 'hero';
  icon?: React.ReactNode;
  className?: string;
}

const variantStyles = {
  default: {
    card: 'bg-white border-white/80',
    icon: 'bg-gradient-to-br from-eneco-light to-white text-eneco-green',
    accent: 'from-eneco-green/5 to-transparent',
  },
  positive: {
    card: 'bg-gradient-to-br from-white to-eneco-light/60 border-eneco-green/20',
    icon: 'bg-gradient-to-br from-eneco-green to-eneco-green-bright text-white shadow-lg shadow-eneco-green/30',
    accent: 'from-eneco-green/10 to-transparent',
  },
  negative: {
    card: 'bg-gradient-to-br from-white to-red-50/80 border-eneco-red/15',
    icon: 'bg-gradient-to-br from-eneco-red to-red-500 text-white shadow-lg shadow-red-500/25',
    accent: 'from-eneco-red/8 to-transparent',
  },
  accent: {
    card: 'bg-gradient-to-br from-white to-orange-50/60 border-eneco-warm/20',
    icon: 'bg-gradient-to-br from-eneco-warm to-orange-400 text-white shadow-lg shadow-orange-400/25',
    accent: 'from-eneco-warm/10 to-transparent',
  },
  hero: {
    card: 'bg-gradient-to-br from-eneco-dark via-[#004d35] to-eneco-darker border-eneco-green/30 text-white',
    icon: 'bg-white/15 text-eneco-mint backdrop-blur-sm border border-white/20',
    accent: 'from-eneco-green/20 to-transparent',
  },
};

export function KpiCard({ label, value, subValue, trend, variant = 'default', icon, className }: KpiCardProps) {
  const styles = variantStyles[variant];
  const isHero = variant === 'hero';

  return (
    <div
      className={cn(
        'group relative overflow-hidden rounded-2xl border p-5 transition-all duration-300',
        'hover:-translate-y-0.5 hover:shadow-card-hover',
        styles.card,
        !isHero && 'kpi-glow shadow-card',
        className,
      )}
    >
      {/* Background accent blob */}
      <div className={cn('absolute -right-6 -top-6 h-24 w-24 rounded-full bg-gradient-to-br opacity-60 blur-2xl', styles.accent)} />

      <div className="relative flex items-start justify-between">
        <p className={cn('text-sm font-medium', isHero ? 'text-white/70' : 'text-gray-500')}>{label}</p>
        {icon && (
          <div className={cn('flex h-10 w-10 items-center justify-center rounded-xl transition-transform group-hover:scale-110', styles.icon)}>
            {icon}
          </div>
        )}
      </div>

      <p className={cn('relative mt-3 text-3xl font-extrabold tracking-tight', isHero ? 'text-white' : 'text-eneco-dark')}>
        {value}
      </p>

      <div className="relative mt-2 flex items-center gap-2">
        {subValue && (
          <span className={cn('text-xs', isHero ? 'text-white/60' : 'text-gray-500')}>{subValue}</span>
        )}
        {trend !== undefined && (
          <span className={cn(
            'inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold',
            trend >= 0
              ? 'bg-eneco-green/15 text-eneco-green'
              : 'bg-eneco-red/10 text-eneco-red',
          )}>
            {trend >= 0 ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {Math.abs(trend).toFixed(1)}%
          </span>
        )}
      </div>

      {/* Bottom accent line */}
      <div className={cn(
        'absolute bottom-0 left-4 right-4 h-0.5 rounded-full opacity-0 transition-opacity group-hover:opacity-100',
        isHero ? 'bg-gradient-to-r from-transparent via-eneco-mint to-transparent' : 'bg-gradient-to-r from-transparent via-eneco-green to-transparent',
      )} />
    </div>
  );
}
