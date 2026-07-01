import type { ViewId, DashboardFilters } from '../types';
import {
  LayoutDashboard, TrendingUp, CalendarRange, Zap, Users, FileText, Tag, Flame, Map, AlertTriangle,
} from 'lucide-react';
import { cn, formatCurrency } from '../utils/format';
import { getTotalLossAmount } from '../data/connections';

const NAV_ITEMS: { id: ViewId; label: string; icon: React.ReactNode; group: string }[] = [
  { id: 'overzicht', label: 'Overzicht', icon: <LayoutDashboard size={18} />, group: 'Finance' },
  { id: 'bruto-marge', label: 'Bruto marge', icon: <TrendingUp size={18} />, group: 'Finance' },
  { id: 'revenue-ytd', label: 'Revenue YTD', icon: <CalendarRange size={18} />, group: 'Finance' },
  { id: 'piekverlies', label: 'Piekverlies', icon: <AlertTriangle size={18} />, group: 'Finance' },
  { id: 'sourcing', label: 'Sourcing', icon: <Zap size={18} />, group: 'Operations' },
  { id: 'kaart', label: 'Kaart', icon: <Map size={18} />, group: 'Operations' },
  { id: 'klanten', label: 'Klanten', icon: <Users size={18} />, group: 'Data' },
  { id: 'contracten', label: 'Contracten', icon: <FileText size={18} />, group: 'Data' },
  { id: 'tarieven', label: 'Tarieven', icon: <Tag size={18} />, group: 'Data' },
];

interface LayoutProps {
  currentView: ViewId;
  onNavigate: (view: ViewId) => void;
  filters: DashboardFilters;
  children: React.ReactNode;
}

export function Layout({ currentView, onNavigate, filters, children }: LayoutProps) {
  const groups = [...new Set(NAV_ITEMS.map((i) => i.group))];
  const totalLoss = getTotalLossAmount();
  const currentItem = NAV_ITEMS.find((i) => i.id === currentView);

  return (
    <div className="flex min-h-screen">
      {/* Sidebar */}
      <aside className="sidebar-bg fixed left-0 top-0 z-30 flex h-full w-64 flex-col border-r border-white/5">
        {/* Logo */}
        <div className="relative flex items-center gap-3 border-b border-white/10 px-6 py-6">
          <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-eneco-green to-eneco-green-bright shadow-lg shadow-eneco-green/40">
            <Flame size={22} className="text-white" />
            <div className="absolute inset-0 rounded-2xl bg-white/20 opacity-0 hover:opacity-100 transition-opacity" />
          </div>
          <div>
            <p className="text-base font-extrabold tracking-tight text-white">Eneco</p>
            <p className="text-[11px] font-medium text-eneco-mint/80">Heat Finance</p>
          </div>
        </div>

        {/* Nav */}
        <nav className="relative flex-1 overflow-y-auto px-3 py-5">
          {groups.map((group) => (
            <div key={group} className="mb-5">
              <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-widest text-white/30">{group}</p>
              {NAV_ITEMS.filter((i) => i.group === group).map((item) => {
                const isActive = currentView === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => onNavigate(item.id)}
                    className={cn(
                      'mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-200',
                      isActive
                        ? 'nav-active font-semibold text-white'
                        : 'text-white/60 hover:bg-white/8 hover:text-white',
                    )}
                  >
                    <span className={cn('flex h-8 w-8 items-center justify-center rounded-lg transition-colors', isActive ? 'bg-white/20' : 'bg-white/5')}>
                      {item.icon}
                    </span>
                    <span className="flex-1 text-left">{item.label}</span>
                    {item.id === 'piekverlies' && (
                      <span className="rounded-full bg-eneco-red/90 px-2 py-0.5 text-[9px] font-bold text-white shadow-sm">
                        {formatCurrency(totalLoss, true)}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          ))}
        </nav>

        {/* Footer */}
        <div className="relative border-t border-white/10 px-6 py-5">
          <div className="rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
            <div className="flex items-center gap-2">
              <div className="h-2 w-2 rounded-full bg-eneco-green animate-pulse" />
              <p className="text-[11px] font-medium text-white/70">Live demo · YTD 2025</p>
            </div>
            <p className="mt-1 text-[10px] text-white/35">Eneco Warmte Finance Platform</p>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main className="ml-64 flex-1 app-bg">
        {/* Header */}
        <header className="sticky top-0 z-20 border-b border-eneco-green/10 bg-white/80 backdrop-blur-xl">
          <div className="px-8 py-5">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h1 className="text-2xl font-extrabold tracking-tight text-gradient-eneco">
                    {currentItem?.label}
                  </h1>
                  {currentItem && (
                    <span className="hidden sm:flex h-8 w-8 items-center justify-center rounded-xl bg-eneco-light text-eneco-green">
                      {currentItem.icon}
                    </span>
                  )}
                </div>
                <p className="mt-0.5 text-sm text-gray-500">Eneco Warmte — Finance & Operations Intelligence</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-gradient-to-r from-eneco-light to-white px-4 py-1.5 text-xs font-semibold text-eneco-dark ring-1 ring-eneco-green/20">
                  Demo modus
                </span>
                <span className="rounded-full bg-eneco-dark px-4 py-1.5 text-xs font-semibold text-white">
                  YTD 2025
                </span>
                {filters.connectionId !== 'alle' && (
                  <span className="rounded-full bg-eneco-teal/10 px-4 py-1.5 text-xs font-semibold text-eneco-teal ring-1 ring-eneco-teal/20">
                    Aansluiting actief
                  </span>
                )}
              </div>
            </div>
          </div>
          {/* Green accent bar */}
          <div className="h-0.5 bg-gradient-to-r from-transparent via-eneco-green to-transparent opacity-60" />
        </header>

        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}
