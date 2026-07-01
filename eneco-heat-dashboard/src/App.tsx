import { useState } from 'react';
import type { DashboardFilters, ViewId } from './types';
import { Layout } from './components/Layout';
import { OverviewView } from './views/OverviewView';
import { MarginView } from './views/MarginView';
import { RevenueYTDView } from './views/RevenueYTDView';
import { SourcingView } from './views/SourcingView';
import { MapView } from './views/MapView';
import { PeakLossView } from './views/PeakLossView';
import { CustomersView } from './views/CustomersView';
import { ContractsView } from './views/ContractsView';
import { TariffsView } from './views/TariffsView';

const defaultFilters: DashboardFilters = {
  segment: 'alle',
  profitCenterId: 'alle',
  customerId: 'alle',
  connectionId: 'alle',
  period: 'ytd',
  costType: 'alle',
  revenueType: 'alle',
};

export default function App() {
  const [currentView, setCurrentView] = useState<ViewId>('overzicht');
  const [filters, setFilters] = useState<DashboardFilters>(defaultFilters);

  const renderView = () => {
    switch (currentView) {
      case 'overzicht':
        return <OverviewView filters={filters} onFilterChange={setFilters} />;
      case 'bruto-marge':
        return <MarginView filters={filters} onFilterChange={setFilters} />;
      case 'revenue-ytd':
        return <RevenueYTDView />;
      case 'sourcing':
        return <SourcingView />;
      case 'kaart':
        return <MapView filters={filters} onFilterChange={setFilters} onNavigate={setCurrentView} />;
      case 'piekverlies':
        return <PeakLossView filters={filters} onFilterChange={setFilters} />;
      case 'klanten':
        return <CustomersView filters={filters} onFilterChange={setFilters} onNavigate={setCurrentView} />;
      case 'contracten':
        return <ContractsView filters={filters} onFilterChange={setFilters} />;
      case 'tarieven':
        return <TariffsView />;
      default:
        return <OverviewView filters={filters} onFilterChange={setFilters} />;
    }
  };

  return (
    <Layout currentView={currentView} onNavigate={setCurrentView} filters={filters}>
      {renderView()}
    </Layout>
  );
}
