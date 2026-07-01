import { contracts, tariffs, customers } from '../data/dummyData';
import { formatCurrency, formatNumber, formatDate } from '../utils/format';
import { Card, Badge } from '../components/ui';

export function ContractsView() {
  const statusVariant = (s: string) => {
    if (s === 'actief') return 'success' as const;
    if (s === 'verlopen') return 'danger' as const;
    return 'warning' as const;
  };

  return (
    <div className="space-y-6">
      <Card title="Alle contracten" subtitle={`${contracts.length} contracten · koppeling klant ↔ tarief`}>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                <th className="pb-3 pr-4">Contract ID</th>
                <th className="pb-3 pr-4">Klant</th>
                <th className="pb-3 pr-4">Status</th>
                <th className="pb-3 pr-4">Periode</th>
                <th className="pb-3 pr-4">Tarief</th>
                <th className="pb-3 pr-4 text-right">Volume (GJ)</th>
                <th className="pb-3 pr-4 text-right">Aansluitingen</th>
                <th className="pb-3 text-right">Omzet YTD</th>
              </tr>
            </thead>
            <tbody>
              {contracts.map((ctr) => {
                const tariff = tariffs.find((t) => t.id === ctr.tariffId);
                const customer = customers.find((c) => c.id === ctr.customerId);
                return (
                  <tr key={ctr.id} className="border-b border-gray-100 hover:bg-gray-50">
                    <td className="py-3 pr-4 font-mono text-xs">{ctr.id}</td>
                    <td className="py-3 pr-4 font-medium">{ctr.customerName}</td>
                    <td className="py-3 pr-4"><Badge variant={statusVariant(ctr.status)}>{ctr.status}</Badge></td>
                    <td className="py-3 pr-4 text-gray-600 text-xs">{formatDate(ctr.startDate)} — {formatDate(ctr.endDate)}</td>
                    <td className="py-3 pr-4 text-gray-600">{tariff?.name}</td>
                    <td className="py-3 pr-4 text-right">{formatNumber(ctr.volumeGJ)}</td>
                    <td className="py-3 pr-4 text-right">{ctr.connectionCount}</td>
                    <td className="py-3 text-right font-semibold">{customer ? formatCurrency(customer.revenue, true) : '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
