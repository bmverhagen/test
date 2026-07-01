import { useState } from 'react';
import type { ViewId, DashboardFilters } from '../types';
import {
  LayoutDashboard, TrendingUp, CalendarRange, Zap, Users, FileText, Tag, Flame, Map, AlertTriangle, Menu, X,
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

export function Layout({ currentView, onNavigate, children }: LayoutProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const groups = [...new Set(NAV_ITEMS.map((i) => i.group))];
  const totalLoss = getTotalLossAmount();
  const currentItem = NAV_ITEMS.find((i) => i.id === currentView);

  const handleNavigate = (view: ViewId) => {
    onNavigate(view);
    setMenuOpen(false);
  };

  const sidebar = (
    <>
      <div className="relative flex items-center justify-between border-b border-white/10 px-5 py-5 lg:px-6">
        <div className="flex items-center gap-3">
          <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-eneco-green to-eneco-green-bright shadow-lg shadow-eneco-green/40">
            <Flame size={22} className="text-white" />
          </div>
          <div>
            <p className="text-base font-extrabold tracking-tight text-white">Eneco</p>
            <p className="text-[11px] font-medium text-eneco-mint/80">Heat Finance</p>
          </div>
        </div>
        <button
          onClick={() => setMenuOpen(false)}
          className="flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 text-white lg:hidden"
          aria-label="Menu sluiten"
        >
          <X size={20} />
        </button>
      </div>

      <nav className="relative flex-1 overflow-y-auto px-3 py-5">
        {groups.map((group) => (
          <div key={group} className="mb-5">
            <p className="mb-2 px-3 text-[10px] font-bold uppercase tracking-widest text-white/30">{group}</p>
            {NAV_ITEMS.filter((i) => i.group === group).map((item) => {
              const isActive = currentView === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => handleNavigate(item.id)}
                  className={cn(
                    'mb-1 flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-sm transition-all duration-200',
                    isActive ? 'nav-active font-semibold text-white' : 'text-white/60 hover:bg-white/8 hover:text-white',
                  )}
                >
                  <span className={cn('flex h-8 w-8 items-center justify-center rounded-lg', isActive ? 'bg-white/20' : 'bg-white/5')}>
                    {item.icon}
                  </span>
                  <span className="flex-1 text-left">{item.label}</span>
                  {item.id === 'piekverlies' && (
                    <span className="rounded-full bg-eneco-red/90 px-2 py-0.5 text-[9px] font-bold text-white">
                      {formatCurrency(totalLoss, true)}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      <div className="relative border-t border-white/10 px-5 py-4 lg:px-6">
        <div className="rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
          <div className="flex items-center gap-2">
            <div className="h-2 w-2 rounded-full bg-eneco-green animate-pulse" />
            <p className="text-[11px] font-medium text-white/70">Live demo · YTD 2025</p>
          </div>
        </div>
      </div>
    </>
  );

  return (
    <div className="flex min-h-screen">
      {/* Mobile overlay */}
      {menuOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm lg:hidden"
          onClick={() => setMenuOpen(false)}
        />
      )}

      {/* Sidebar — drawer on mobile, fixed on desktop */}
      <aside
        className={cn(
          'sidebar-bg fixed left-0 top-0 z-50 flex h-full w-72 flex-col border-r border-white/5 transition-transform duration-300 lg:z-30 lg:w-64 lg:translate-x-0',
          menuOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {sidebar}
      </aside>

      {/* Main */}
      <main className="flex-1 lg:ml-64 app-bg min-w-0">
        <header className="sticky top-0 z-20 border-b border-eneco-green/10 bg-white/80 backdrop-blur-xl">
          <div className="px-4 py-4 sm:px-6 lg:px-8 lg:py-5">
            <div className="flex items-center justify-between gap-3">
              <div className="flex items-center gap-3 min-w-0">
                <button
                  onClick={() => setMenuOpen(true)}
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-eneco-dark text-white lg:hidden"
                  aria-label="Menu openen"
                >
                  <Menu size={20} />
                </button>
                <div className="min-w-0">
                  <h1 className="text-lg sm:text-2xl font-extrabold tracking-tight text-gradient-eneco truncate">
                    {currentItem?.label}
                  </h1>
                  <p className="hidden sm:block mt-0.5 text-sm text-gray-500 truncate">Eneco Warmte — Finance & Operations</p>
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-1.5 sm:gap-2">
                <span className="hidden sm:inline rounded-full bg-gradient-to-r from-eneco-light to-white px-3 py-1.5 text-xs font-semibold text-eneco-dark ring-1 ring-eneco-green/20">
                  Demo
                </span>
                <span className="rounded-full bg-eneco-dark px-3 py-1.5 text-xs font-semibold text-white">
                  YTD
                </span>
              </div>
            </div>
          </div>
          <div className="h-0.5 bg-gradient-to-r from-transparent via-eneco-green to-transparent opacity-60" />
        </header>

        <div className="p-4 sm:p-6 lg:p-8">{children}</div>
      </main>
    </div>
  );
}
