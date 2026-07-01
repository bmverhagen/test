import type { ViewId } from '../types';
import {
  LayoutDashboard, TrendingUp, CalendarRange, Zap, Users, FileText, Tag, Flame,
} from 'lucide-react';
import { cn } from '../utils/format';

const NAV_ITEMS: { id: ViewId; label: string; icon: React.ReactNode; group: string }[] = [
  { id: 'overzicht', label: 'Overzicht', icon: <LayoutDashboard size={18} />, group: 'Finance' },
  { id: 'bruto-marge', label: 'Bruto marge', icon: <TrendingUp size={18} />, group: 'Finance' },
  { id: 'revenue-ytd', label: 'Revenue YTD', icon: <CalendarRange size={18} />, group: 'Finance' },
  { id: 'sourcing', label: 'Sourcing', icon: <Zap size={18} />, group: 'Operations' },
  { id: 'klanten', label: 'Klanten', icon: <Users size={18} />, group: 'Data' },
  { id: 'contracten', label: 'Contracten', icon: <FileText size={18} />, group: 'Data' },
  { id: 'tarieven', label: 'Tarieven', icon: <Tag size={18} />, group: 'Data' },
];

interface LayoutProps {
  currentView: ViewId;
  onNavigate: (view: ViewId) => void;
  children: React.ReactNode;
}

export function Layout({ currentView, onNavigate, children }: LayoutProps) {
  const groups = [...new Set(NAV_ITEMS.map((i) => i.group))];

  return (
    <div className="flex min-h-screen">
      <aside className="fixed left-0 top-0 z-30 flex h-full w-60 flex-col border-r border-gray-200 bg-eneco-dark text-white">
        <div className="flex items-center gap-3 border-b border-white/10 px-5 py-5">
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-eneco-green">
            <Flame size={20} />
          </div>
          <div>
            <p className="text-sm font-bold leading-tight">Eneco Heat</p>
            <p className="text-[10px] text-white/60">Finance Dashboard</p>
          </div>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          {groups.map((group) => (
            <div key={group} className="mb-4">
              <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-wider text-white/40">{group}</p>
              {NAV_ITEMS.filter((i) => i.group === group).map((item) => (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={cn(
                    'flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-sm transition-colors',
                    currentView === item.id
                      ? 'bg-eneco-green text-white font-medium'
                      : 'text-white/70 hover:bg-white/10 hover:text-white',
                  )}
                >
                  {item.icon}
                  {item.label}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="border-t border-white/10 px-5 py-4">
          <p className="text-[10px] text-white/40">Demo data · YTD 2025</p>
          <p className="text-[10px] text-white/30 mt-0.5">v1.0 — Finance & Sourcing</p>
        </div>
      </aside>

      <main className="ml-60 flex-1">
        <header className="sticky top-0 z-20 border-b border-gray-200 bg-white/90 backdrop-blur-sm px-8 py-4">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-bold text-eneco-dark">
                {NAV_ITEMS.find((i) => i.id === currentView)?.label}
              </h1>
              <p className="text-sm text-gray-500">Eneco Warmte — Finance & Operations</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full bg-eneco-light px-3 py-1 text-xs font-medium text-eneco-dark">
                Demo modus
              </span>
              <span className="rounded-full bg-gray-100 px-3 py-1 text-xs text-gray-600">
                Periode: YTD 2025
              </span>
            </div>
          </div>
        </header>
        <div className="p-8">{children}</div>
      </main>
    </div>
  );
}
