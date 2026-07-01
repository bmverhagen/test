import type {
  ProfitCenter,
  Customer,
  Contract,
  Tariff,
  SourcingHourly,
  RevenueYTDMonth,
  MarginBridgeItem,
} from '../types';
import { connections } from './connections';

export const SEGMENTS = [
  { id: 'residentieel', label: 'Residentieel', color: '#00a651' },
  { id: 'zakelijk', label: 'Zakelijk', color: '#0077b6' },
  { id: 'industrie', label: 'Industrie', color: '#ff6b35' },
  { id: 'overheid', label: 'Overheid', color: '#7b2cbf' },
] as const;

export const profitCenters: ProfitCenter[] = [
  {
    id: 'pc-ams',
    name: 'Amsterdam Warmtenet',
    segment: 'residentieel',
    revenue: 42_800_000,
    revenueFixed: 18_400_000,
    revenueVariable: 24_400_000,
    cost: 31_200_000,
    costFixed: 12_800_000,
    costVariable: 18_400_000,
    sprucingCost: 1_240_000,
    heatLossRevenue: 3_180_000,
    volumeGJ: 1_240_000,
  },
  {
    id: 'pc-rtd',
    name: 'Rotterdam Industrie',
    segment: 'industrie',
    revenue: 68_500_000,
    revenueFixed: 22_100_000,
    revenueVariable: 46_400_000,
    cost: 52_300_000,
    costFixed: 18_600_000,
    costVariable: 33_700_000,
    sprucingCost: 2_890_000,
    heatLossRevenue: 4_720_000,
    volumeGJ: 2_180_000,
  },
  {
    id: 'pc-utr',
    name: 'Utrecht Zakelijk',
    segment: 'zakelijk',
    revenue: 31_200_000,
    revenueFixed: 14_800_000,
    revenueVariable: 16_400_000,
    cost: 24_100_000,
    costFixed: 9_200_000,
    costVariable: 14_900_000,
    sprucingCost: 980_000,
    heatLossRevenue: 2_140_000,
    volumeGJ: 890_000,
  },
  {
    id: 'pc-dhv',
    name: 'Den Haag Overheid',
    segment: 'overheid',
    revenue: 18_900_000,
    revenueFixed: 11_200_000,
    revenueVariable: 7_700_000,
    cost: 14_600_000,
    costFixed: 7_400_000,
    costVariable: 7_200_000,
    sprucingCost: 620_000,
    heatLossRevenue: 1_380_000,
    volumeGJ: 520_000,
  },
  {
    id: 'pc-ehv',
    name: 'Eindhoven Residentieel',
    segment: 'residentieel',
    revenue: 28_400_000,
    revenueFixed: 12_600_000,
    revenueVariable: 15_800_000,
    cost: 21_800_000,
    costFixed: 8_900_000,
    costVariable: 12_900_000,
    sprucingCost: 840_000,
    heatLossRevenue: 1_960_000,
    volumeGJ: 780_000,
  },
];

export const customers: Customer[] = [
  {
    id: 'kl-001',
    name: 'VvE De Groene Hof',
    profitCenterId: 'pc-ams',
    segment: 'residentieel',
    revenue: 4_200_000,
    revenueFixed: 1_800_000,
    revenueVariable: 2_400_000,
    cost: 3_100_000,
    costFixed: 1_200_000,
    costVariable: 1_900_000,
    sprucingCost: 124_000,
    heatLossRevenue: 318_000,
    volumeGJ: 124_000,
    contractId: 'ctr-001',
  },
  {
    id: 'kl-002',
    name: 'Stichting Woonzorg NL',
    profitCenterId: 'pc-ams',
    segment: 'residentieel',
    revenue: 8_600_000,
    revenueFixed: 3_600_000,
    revenueVariable: 5_000_000,
    cost: 6_200_000,
    costFixed: 2_400_000,
    costVariable: 3_800_000,
    sprucingCost: 248_000,
    heatLossRevenue: 636_000,
    volumeGJ: 248_000,
    contractId: 'ctr-002',
  },
  {
    id: 'kl-003',
    name: 'ChemCorp Industries BV',
    profitCenterId: 'pc-rtd',
    segment: 'industrie',
    revenue: 32_400_000,
    revenueFixed: 10_200_000,
    revenueVariable: 22_200_000,
    cost: 24_800_000,
    costFixed: 8_400_000,
    costVariable: 16_400_000,
    sprucingCost: 1_368_000,
    heatLossRevenue: 2_232_000,
    volumeGJ: 1_020_000,
    contractId: 'ctr-003',
  },
  {
    id: 'kl-004',
    name: 'Havenbedrijf Rotterdam',
    profitCenterId: 'pc-rtd',
    segment: 'industrie',
    revenue: 22_100_000,
    revenueFixed: 7_800_000,
    revenueVariable: 14_300_000,
    cost: 17_200_000,
    costFixed: 6_200_000,
    costVariable: 11_000_000,
    sprucingCost: 932_000,
    heatLossRevenue: 1_520_000,
    volumeGJ: 720_000,
    contractId: 'ctr-004',
  },
  {
    id: 'kl-005',
    name: 'Rabobank Utrecht',
    profitCenterId: 'pc-utr',
    segment: 'zakelijk',
    revenue: 6_800_000,
    revenueFixed: 3_200_000,
    revenueVariable: 3_600_000,
    cost: 5_200_000,
    costFixed: 2_000_000,
    costVariable: 3_200_000,
    sprucingCost: 214_000,
    heatLossRevenue: 468_000,
    volumeGJ: 195_000,
    contractId: 'ctr-005',
  },
  {
    id: 'kl-006',
    name: 'Gemeente Den Haag',
    profitCenterId: 'pc-dhv',
    segment: 'overheid',
    revenue: 12_400_000,
    revenueFixed: 7_400_000,
    revenueVariable: 5_000_000,
    cost: 9_600_000,
    costFixed: 4_800_000,
    costVariable: 4_800_000,
    sprucingCost: 408_000,
    heatLossRevenue: 906_000,
    volumeGJ: 340_000,
    contractId: 'ctr-006',
  },
  {
    id: 'kl-007',
    name: 'ASML Eindhoven Campus',
    profitCenterId: 'pc-ehv',
    segment: 'zakelijk',
    revenue: 14_200_000,
    revenueFixed: 6_400_000,
    revenueVariable: 7_800_000,
    cost: 10_800_000,
    costFixed: 4_200_000,
    costVariable: 6_600_000,
    sprucingCost: 420_000,
    heatLossRevenue: 980_000,
    volumeGJ: 390_000,
    contractId: 'ctr-007',
  },
  {
    id: 'kl-008',
    name: 'Woningcorporatie Woonstad',
    profitCenterId: 'pc-ehv',
    segment: 'residentieel',
    revenue: 9_800_000,
    revenueFixed: 4_200_000,
    revenueVariable: 5_600_000,
    cost: 7_600_000,
    costFixed: 3_100_000,
    costVariable: 4_500_000,
    sprucingCost: 290_000,
    heatLossRevenue: 680_000,
    volumeGJ: 270_000,
    contractId: 'ctr-008',
  },
];

export const tariffs: Tariff[] = [
  {
    id: 'tar-001',
    name: 'Warmte Residentieel Standaard',
    segment: 'residentieel',
    validFrom: '2025-01-01',
    validTo: '2025-12-31',
    components: [
      { id: 'tc-001', name: 'Vastrecht', type: 'vast', unit: '€/aansluiting/jaar', rate: 185.0, description: 'Jaarlijks vastrecht per aansluiting' },
      { id: 'tc-002', name: 'Warmte variabel', type: 'variabel', unit: '€/GJ', rate: 28.45, description: 'Variabele warmteprijs per GJ' },
      { id: 'tc-003', name: 'Transport', type: 'transport', unit: '€/GJ', rate: 4.20, description: 'Transportkosten warmtenet' },
      { id: 'tc-004', name: 'Capaciteitstarief', type: 'capaciteit', unit: '€/kW/jaar', rate: 42.0, description: 'Capaciteitsreservering' },
    ],
  },
  {
    id: 'tar-002',
    name: 'Warmte Industrie Grootverbruik',
    segment: 'industrie',
    validFrom: '2025-01-01',
    validTo: '2025-12-31',
    components: [
      { id: 'tc-005', name: 'Vastrecht industrie', type: 'vast', unit: '€/aansluiting/jaar', rate: 12_500.0, description: 'Jaarlijks vastrecht grootverbruik' },
      { id: 'tc-006', name: 'Warmte variabel industrie', type: 'variabel', unit: '€/GJ', rate: 22.80, description: 'Variabele warmteprijs industrie' },
      { id: 'tc-007', name: 'Energiecomponent', type: 'energie', unit: '€/GJ', rate: 8.60, description: 'Energie-inhoud warmte' },
      { id: 'tc-008', name: 'Transport industrie', type: 'transport', unit: '€/GJ', rate: 3.10, description: 'Transportkosten industrieel net' },
    ],
  },
  {
    id: 'tar-003',
    name: 'Warmte Zakelijk MKB',
    segment: 'zakelijk',
    validFrom: '2025-01-01',
    validTo: '2025-12-31',
    components: [
      { id: 'tc-009', name: 'Vastrecht zakelijk', type: 'vast', unit: '€/aansluiting/jaar', rate: 890.0, description: 'Jaarlijks vastrecht MKB' },
      { id: 'tc-010', name: 'Warmte variabel zakelijk', type: 'variabel', unit: '€/GJ', rate: 31.20, description: 'Variabele warmteprijs zakelijk' },
      { id: 'tc-011', name: 'Transport zakelijk', type: 'transport', unit: '€/GJ', rate: 4.80, description: 'Transportkosten zakelijk net' },
    ],
  },
  {
    id: 'tar-004',
    name: 'Warmte Overheid',
    segment: 'overheid',
    validFrom: '2025-01-01',
    validTo: '2025-12-31',
    components: [
      { id: 'tc-012', name: 'Vastrecht overheid', type: 'vast', unit: '€/aansluiting/jaar', rate: 2_400.0, description: 'Jaarlijks vastrecht overheid' },
      { id: 'tc-013', name: 'Warmte variabel overheid', type: 'variabel', unit: '€/GJ', rate: 26.90, description: 'Variabele warmteprijs overheid' },
      { id: 'tc-014', name: 'Capaciteit overheid', type: 'capaciteit', unit: '€/kW/jaar', rate: 38.0, description: 'Capaciteitsreservering overheid' },
    ],
  },
];

export const contracts: Contract[] = [
  { id: 'ctr-001', customerId: 'kl-001', customerName: 'VvE De Groene Hof', startDate: '2023-01-01', endDate: '2027-12-31', status: 'actief', tariffId: 'tar-001', volumeGJ: 124_000, connectionCount: 186 },
  { id: 'ctr-002', customerId: 'kl-002', customerName: 'Stichting Woonzorg NL', startDate: '2022-06-01', endDate: '2027-05-31', status: 'actief', tariffId: 'tar-001', volumeGJ: 248_000, connectionCount: 412 },
  { id: 'ctr-003', customerId: 'kl-003', customerName: 'ChemCorp Industries BV', startDate: '2021-01-01', endDate: '2028-12-31', status: 'actief', tariffId: 'tar-002', volumeGJ: 1_020_000, connectionCount: 8 },
  { id: 'ctr-004', customerId: 'kl-004', customerName: 'Havenbedrijf Rotterdam', startDate: '2020-03-01', endDate: '2026-02-28', status: 'actief', tariffId: 'tar-002', volumeGJ: 720_000, connectionCount: 14 },
  { id: 'ctr-005', customerId: 'kl-005', customerName: 'Rabobank Utrecht', startDate: '2024-01-01', endDate: '2028-12-31', status: 'actief', tariffId: 'tar-003', volumeGJ: 195_000, connectionCount: 3 },
  { id: 'ctr-006', customerId: 'kl-006', customerName: 'Gemeente Den Haag', startDate: '2023-04-01', endDate: '2028-03-31', status: 'actief', tariffId: 'tar-004', volumeGJ: 340_000, connectionCount: 28 },
  { id: 'ctr-007', customerId: 'kl-007', customerName: 'ASML Eindhoven Campus', startDate: '2024-06-01', endDate: '2029-05-31', status: 'actief', tariffId: 'tar-003', volumeGJ: 390_000, connectionCount: 6 },
  { id: 'ctr-008', customerId: 'kl-008', customerName: 'Woningcorporatie Woonstad', startDate: '2022-01-01', endDate: '2026-12-31', status: 'actief', tariffId: 'tar-001', volumeGJ: 270_000, connectionCount: 520 },
];

const GRIDS = [
  { id: 'grid-ams-01', name: 'AMS Noord' },
  { id: 'grid-ams-02', name: 'AMS Zuid' },
  { id: 'grid-rtd-01', name: 'RTD Haven' },
  { id: 'grid-rtd-02', name: 'RTD Botlek' },
  { id: 'grid-utr-01', name: 'UTR Centrum' },
];

function generateSourcingData(): SourcingHourly[] {
  const data: SourcingHourly[] = [];
  const baseDate = new Date('2025-06-15T00:00:00');

  for (let day = 0; day < 7; day++) {
    for (let hour = 0; hour < 24; hour++) {
      for (const grid of GRIDS) {
        const ts = new Date(baseDate);
        ts.setDate(ts.getDate() + day);
        ts.setHours(hour);

        const isPeak = hour >= 7 && hour <= 9 || hour >= 17 && hour <= 20;
        const baseP = grid.id.includes('rtd') ? 42 : grid.id.includes('ams') ? 38 : 35;
        const priceP = baseP + (isPeak ? 8 : 0) + Math.sin(hour / 3) * 3 + (Math.random() - 0.5) * 2;
        const baseQ = grid.id.includes('rtd') ? 180 : grid.id.includes('ams') ? 120 : 85;
        const volumeQ = baseQ + (isPeak ? 40 : -10) + Math.random() * 20;

        const hasInvoice = Math.random() > 0.15;
        const invoiceAmount = hasInvoice ? Math.round(priceP * volumeQ * 100) / 100 : undefined;
        const invoiceStatuses: Array<'gefactureerd' | 'open' | 'afwijking'> = ['gefactureerd', 'open', 'afwijking'];
        const invoiceStatus = hasInvoice
          ? invoiceStatuses[Math.floor(Math.random() * (Math.random() > 0.9 ? 3 : 2))]
          : 'open';

        data.push({
          timestamp: ts.toISOString(),
          gridId: grid.id,
          gridName: grid.name,
          priceP: Math.round(priceP * 100) / 100,
          volumeQ: Math.round(volumeQ * 10) / 10,
          invoiceId: hasInvoice ? `INV-${grid.id.slice(-2).toUpperCase()}-${day}${hour.toString().padStart(2, '0')}` : undefined,
          invoiceAmount,
          invoiceStatus,
        });
      }
    }
  }
  return data;
}

export const sourcingHourly = generateSourcingData();

export const revenueYTD: RevenueYTDMonth[] = [
  { month: 'Jan', monthIndex: 0, revenueActual: 15_200_000, revenueEstimated: 0, volumeActualGJ: 520_000, volumeEstimatedGJ: 0, isEstimated: false },
  { month: 'Feb', monthIndex: 1, revenueActual: 14_800_000, revenueEstimated: 0, volumeActualGJ: 498_000, volumeEstimatedGJ: 0, isEstimated: false },
  { month: 'Mrt', monthIndex: 2, revenueActual: 13_400_000, revenueEstimated: 0, volumeActualGJ: 445_000, volumeEstimatedGJ: 0, isEstimated: false },
  { month: 'Apr', monthIndex: 3, revenueActual: 10_200_000, revenueEstimated: 0, volumeActualGJ: 340_000, volumeEstimatedGJ: 0, isEstimated: false },
  { month: 'Mei', monthIndex: 4, revenueActual: 7_800_000, revenueEstimated: 0, volumeActualGJ: 260_000, volumeEstimatedGJ: 0, isEstimated: false },
  { month: 'Jun', monthIndex: 5, revenueActual: 5_400_000, revenueEstimated: 1_200_000, volumeActualGJ: 180_000, volumeEstimatedGJ: 40_000, isEstimated: true },
  { month: 'Jul', monthIndex: 6, revenueActual: 0, revenueEstimated: 4_800_000, volumeActualGJ: 0, volumeEstimatedGJ: 160_000, isEstimated: true },
  { month: 'Aug', monthIndex: 7, revenueActual: 0, revenueEstimated: 4_200_000, volumeActualGJ: 0, volumeEstimatedGJ: 140_000, isEstimated: true },
  { month: 'Sep', monthIndex: 8, revenueActual: 0, revenueEstimated: 8_600_000, volumeActualGJ: 0, volumeEstimatedGJ: 285_000, isEstimated: true },
  { month: 'Okt', monthIndex: 9, revenueActual: 0, revenueEstimated: 12_400_000, volumeActualGJ: 0, volumeEstimatedGJ: 410_000, isEstimated: true },
  { month: 'Nov', monthIndex: 10, revenueActual: 0, revenueEstimated: 14_800_000, volumeActualGJ: 0, volumeEstimatedGJ: 490_000, isEstimated: true },
  { month: 'Dec', monthIndex: 11, revenueActual: 0, revenueEstimated: 16_200_000, volumeActualGJ: 0, volumeEstimatedGJ: 540_000, isEstimated: true },
];

export function getMarginBridge(filters?: {
  segment?: string;
  profitCenterId?: string;
  customerId?: string;
  connectionId?: string;
}): MarginBridgeItem[] {
  if (filters?.connectionId && filters.connectionId !== 'alle') {
    const conn = connections.find((c) => c.id === filters.connectionId);
    if (!conn) return [];
    const revenue = conn.revenue;
    const cost = conn.cost;
    const brutoMarge = revenue - cost;
    return [
      { label: 'Omzet', value: revenue, type: 'start' },
      { label: 'Inkoopkosten', value: -cost, type: 'negative' },
      { label: 'Bruto marge', value: brutoMarge, type: 'total' },
    ];
  }

  let items = profitCenters;

  if (filters?.segment && filters.segment !== 'alle') {
    items = items.filter((pc) => pc.segment === filters.segment);
  }
  if (filters?.profitCenterId && filters.profitCenterId !== 'alle') {
    items = items.filter((pc) => pc.id === filters.profitCenterId);
  }

  if (filters?.customerId && filters.customerId !== 'alle') {
    const cust = customers.find((c) => c.id === filters.customerId);
    if (!cust) return [];
    const revenue = cust.revenue;
    const cost = cust.cost;
    const sprucing = cust.sprucingCost;
    const heatLoss = cust.heatLossRevenue;
    const brutoMarge = revenue - cost - sprucing + heatLoss;
    return [
      { label: 'Omzet', value: revenue, type: 'start' },
      { label: 'Inkoopkosten', value: -cost, type: 'negative' },
      { label: 'Sprucing cost', value: -sprucing, type: 'negative', category: 'sprucing' },
      { label: 'Heat loss revenue', value: heatLoss, type: 'positive', category: 'heatloss' },
      { label: 'Bruto marge', value: brutoMarge, type: 'total' },
    ];
  }

  const revenue = items.reduce((s, i) => s + i.revenue, 0);
  const cost = items.reduce((s, i) => s + i.cost, 0);
  const sprucing = items.reduce((s, i) => s + i.sprucingCost, 0);
  const heatLoss = items.reduce((s, i) => s + i.heatLossRevenue, 0);
  const brutoMarge = revenue - cost - sprucing + heatLoss;

  return [
    { label: 'Omzet', value: revenue, type: 'start' },
    { label: 'Inkoopkosten', value: -cost, type: 'negative' },
    { label: 'Sprucing cost', value: -sprucing, type: 'negative', category: 'sprucing' },
    { label: 'Heat loss revenue', value: heatLoss, type: 'positive', category: 'heatloss' },
    { label: 'Bruto marge', value: brutoMarge, type: 'total' },
  ];
}

export function formatCurrency(value: number, compact = false): string {
  if (compact) {
    if (Math.abs(value) >= 1_000_000) return `€${(value / 1_000_000).toFixed(1)}M`;
    if (Math.abs(value) >= 1_000) return `€${(value / 1_000).toFixed(0)}K`;
  }
  return new Intl.NumberFormat('nl-NL', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(value);
}

export function formatNumber(value: number, decimals = 0): string {
  return new Intl.NumberFormat('nl-NL', { maximumFractionDigits: decimals }).format(value);
}

export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}
