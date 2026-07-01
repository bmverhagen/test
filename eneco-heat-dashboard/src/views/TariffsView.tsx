import { tariffs, SEGMENTS } from '../data/dummyData';
import { formatDate } from '../utils/format';
import { Card, Badge } from '../components/ui';
import { useState } from 'react';

export function TariffsView() {
  const [expanded, setExpanded] = useState<string | null>(tariffs[0]?.id ?? null);

  const typeColors: Record<string, 'default' | 'success' | 'warning' | 'danger' | 'info'> = {
    vast: 'success',
    variabel: 'info',
    capaciteit: 'warning',
    transport: 'default',
    energie: 'danger',
  };

  return (
    <div className="space-y-4">
      {tariffs.map((tariff) => {
        const seg = SEGMENTS.find((s) => s.id === tariff.segment);
        const isOpen = expanded === tariff.id;
        return (
          <Card
            key={tariff.id}
            title={tariff.name}
            subtitle={`${seg?.label} · ${formatDate(tariff.validFrom)} — ${formatDate(tariff.validTo)}`}
            action={
              <button
                onClick={() => setExpanded(isOpen ? null : tariff.id)}
                className="text-sm text-eneco-green hover:underline"
              >
                {isOpen ? 'Inklappen' : 'Uitklappen'}
              </button>
            }
          >
            {isOpen && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-xs font-medium uppercase text-gray-500">
                      <th className="pb-3 pr-4">ID</th>
                      <th className="pb-3 pr-4">Component</th>
                      <th className="pb-3 pr-4">Type</th>
                      <th className="pb-3 pr-4">Eenheid</th>
                      <th className="pb-3 pr-4 text-right">Tarief</th>
                      <th className="pb-3">Omschrijving</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tariff.components.map((tc) => (
                      <tr key={tc.id} className="border-b border-gray-100 hover:bg-gray-50">
                        <td className="py-3 pr-4 font-mono text-xs text-gray-500">{tc.id}</td>
                        <td className="py-3 pr-4 font-medium">{tc.name}</td>
                        <td className="py-3 pr-4">
                          <Badge variant={typeColors[tc.type] ?? 'default'}>{tc.type}</Badge>
                        </td>
                        <td className="py-3 pr-4 text-gray-600">{tc.unit}</td>
                        <td className="py-3 pr-4 text-right font-mono font-semibold">
                          €{tc.rate.toLocaleString('nl-NL', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="py-3 text-gray-600">{tc.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {!isOpen && (
              <p className="text-sm text-gray-500">{tariff.components.length} tariefcomponenten · klik om uit te klappen</p>
            )}
          </Card>
        );
      })}
    </div>
  );
}
