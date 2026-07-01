import { cn } from '../utils/format';

interface BadgeProps {
  children: React.ReactNode;
  variant?: 'default' | 'success' | 'warning' | 'danger' | 'info';
  pulse?: boolean;
}

export function Badge({ children, variant = 'default', pulse }: BadgeProps) {
  const variants = {
    default: 'bg-gray-100 text-gray-700 ring-1 ring-gray-200/60',
    success: 'bg-eneco-light text-eneco-dark ring-1 ring-eneco-green/20',
    warning: 'bg-amber-50 text-amber-800 ring-1 ring-amber-200/60',
    danger: 'bg-red-50 text-eneco-red ring-1 ring-red-200/60',
    info: 'bg-teal-50 text-eneco-teal ring-1 ring-teal-200/60',
  };

  return (
    <span className={cn(
      'inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold',
      variants[variant],
      pulse && variant === 'danger' && 'animate-pulse',
    )}>
      {children}
    </span>
  );
}

interface CardProps {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
  className?: string;
  action?: React.ReactNode;
  variant?: 'default' | 'elevated' | 'dark';
  noPadding?: boolean;
}

export function Card({ title, subtitle, children, className, action, variant = 'default', noPadding }: CardProps) {
  const variants = {
    default: 'bg-white border-gray-100/80 shadow-card',
    elevated: 'bg-white border-eneco-green/10 shadow-card-hover',
    dark: 'bg-gradient-to-br from-eneco-dark to-eneco-darker border-eneco-green/20 text-white shadow-eneco',
  };

  const isDark = variant === 'dark';

  return (
    <div className={cn('card-shine rounded-2xl border overflow-hidden transition-shadow duration-300 hover:shadow-card-hover', variants[variant], className)}>
      <div className={cn(
        'flex items-center justify-between px-6 py-4',
        isDark ? 'border-b border-white/10' : 'border-b border-gray-100/80 bg-gradient-to-r from-gray-50/50 to-transparent',
      )}>
        <div>
          <h3 className={cn('text-base font-bold tracking-tight', isDark ? 'text-white' : 'text-eneco-dark')}>{title}</h3>
          {subtitle && <p className={cn('mt-0.5 text-sm', isDark ? 'text-white/60' : 'text-gray-500')}>{subtitle}</p>}
        </div>
        {action}
      </div>
      <div className={noPadding ? '' : 'p-6'}>{children}</div>
    </div>
  );
}

interface StatPillProps {
  label: string;
  value: string;
  color?: 'green' | 'red' | 'warm' | 'teal';
}

export function StatPill({ label, value, color = 'green' }: StatPillProps) {
  const colors = {
    green: 'from-eneco-green/10 to-eneco-light/50 border-eneco-green/20 text-eneco-dark',
    red: 'from-red-50 to-red-50/50 border-eneco-red/15 text-eneco-red',
    warm: 'from-orange-50 to-amber-50/50 border-eneco-warm/20 text-orange-800',
    teal: 'from-teal-50 to-cyan-50/50 border-eneco-teal/20 text-eneco-teal',
  };

  return (
    <div className={cn('rounded-xl border bg-gradient-to-br px-4 py-3', colors[color])}>
      <p className="text-xs font-medium opacity-70">{label}</p>
      <p className="mt-0.5 text-xl font-extrabold tracking-tight">{value}</p>
    </div>
  );
}
