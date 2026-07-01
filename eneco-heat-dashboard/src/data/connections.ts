import type { Connection, PeakLossProfile } from '../types';

export const connections: Connection[] = [
  // VvE De Groene Hof — residentieel Amsterdam
  { id: 'conn-001', customerId: 'kl-001', profitCenterId: 'pc-ams', segment: 'residentieel', type: 'woning', address: 'Groene Hof 12-A', mapX: 22, mapY: 35, revenue: 22_400, cost: 18_200, volumeGJ: 680, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 26.80, peakSharePct: 18, isLossMaking: false, lossAmount: 0 },
  { id: 'conn-002', customerId: 'kl-001', profitCenterId: 'pc-ams', segment: 'residentieel', type: 'woning', address: 'Groene Hof 12-B', mapX: 24, mapY: 36, revenue: 19_800, cost: 21_400, volumeGJ: 620, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 34.52, peakSharePct: 62, isLossMaking: true, lossAmount: 3_760 },
  { id: 'conn-003', customerId: 'kl-001', profitCenterId: 'pc-ams', segment: 'residentieel', type: 'woning', address: 'Groene Hof 14', mapX: 26, mapY: 34, revenue: 24_100, cost: 19_600, volumeGJ: 720, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 27.22, peakSharePct: 22, isLossMaking: false, lossAmount: 0 },
  { id: 'conn-004', customerId: 'kl-001', profitCenterId: 'pc-ams', segment: 'residentieel', type: 'woning', address: 'Groene Hof 16', mapX: 28, mapY: 37, revenue: 18_600, cost: 22_800, volumeGJ: 590, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 38.64, peakSharePct: 71, isLossMaking: true, lossAmount: 6_020 },
  { id: 'conn-005', customerId: 'kl-001', profitCenterId: 'pc-ams', segment: 'residentieel', type: 'woning', address: 'Groene Hof 18', mapX: 30, mapY: 35, revenue: 21_200, cost: 17_900, volumeGJ: 650, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 27.54, peakSharePct: 25, isLossMaking: false, lossAmount: 0 },

  // Woonzorg NL
  { id: 'conn-006', customerId: 'kl-002', profitCenterId: 'pc-ams', segment: 'residentieel', type: 'gebouw', address: 'Zorglaan 1', mapX: 35, mapY: 28, revenue: 186_000, cost: 142_000, volumeGJ: 5_800, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 24.48, peakSharePct: 15, isLossMaking: false, lossAmount: 0 },
  { id: 'conn-007', customerId: 'kl-002', profitCenterId: 'pc-ams', segment: 'residentieel', type: 'gebouw', address: 'Zorglaan 3', mapX: 37, mapY: 30, revenue: 164_000, cost: 138_000, volumeGJ: 5_200, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 26.54, peakSharePct: 28, isLossMaking: false, lossAmount: 0 },

  // ChemCorp — industrie Rotterdam
  { id: 'conn-008', customerId: 'kl-003', profitCenterId: 'pc-rtd', segment: 'industrie', type: 'industrie', address: 'Chemieweg 42', mapX: 68, mapY: 55, revenue: 8_200_000, cost: 7_100_000, volumeGJ: 320_000, tariffRatePerGJ: 22.80, effectiveCostPerGJ: 22.19, peakSharePct: 12, isLossMaking: false, lossAmount: 0 },
  { id: 'conn-009', customerId: 'kl-003', profitCenterId: 'pc-rtd', segment: 'industrie', type: 'industrie', address: 'Chemieweg 44', mapX: 72, mapY: 58, revenue: 6_400_000, cost: 7_280_000, volumeGJ: 248_000, tariffRatePerGJ: 22.80, effectiveCostPerGJ: 29.35, peakSharePct: 58, isLossMaking: true, lossAmount: 1_628_000 },

  // Havenbedrijf
  { id: 'conn-010', customerId: 'kl-004', profitCenterId: 'pc-rtd', segment: 'industrie', type: 'industrie', address: 'Havendijk 100', mapX: 75, mapY: 48, revenue: 5_800_000, cost: 5_200_000, volumeGJ: 210_000, tariffRatePerGJ: 22.80, effectiveCostPerGJ: 24.76, peakSharePct: 35, isLossMaking: true, lossAmount: 412_000 },
  { id: 'conn-011', customerId: 'kl-004', profitCenterId: 'pc-rtd', segment: 'industrie', type: 'industrie', address: 'Havendijk 102', mapX: 78, mapY: 50, revenue: 4_200_000, cost: 3_900_000, volumeGJ: 168_000, tariffRatePerGJ: 22.80, effectiveCostPerGJ: 23.21, peakSharePct: 28, isLossMaking: true, lossAmount: 69_000 },

  // Rabobank Utrecht — zakelijk B2B
  { id: 'conn-012', customerId: 'kl-005', profitCenterId: 'pc-utr', segment: 'zakelijk', type: 'bedrijfspand', address: 'Croeselaan 18', mapX: 48, mapY: 52, revenue: 2_400_000, cost: 2_820_000, volumeGJ: 72_000, tariffRatePerGJ: 31.20, effectiveCostPerGJ: 39.17, peakSharePct: 74, isLossMaking: true, lossAmount: 574_000 },
  { id: 'conn-013', customerId: 'kl-005', profitCenterId: 'pc-utr', segment: 'zakelijk', type: 'bedrijfspand', address: 'Croeselaan 20', mapX: 50, mapY: 54, revenue: 1_800_000, cost: 1_720_000, volumeGJ: 54_000, tariffRatePerGJ: 31.20, effectiveCostPerGJ: 31.85, peakSharePct: 42, isLossMaking: true, lossAmount: 35_000 },
  { id: 'conn-014', customerId: 'kl-005', profitCenterId: 'pc-utr', segment: 'zakelijk', type: 'bedrijfspand', address: 'Croeselaan 22', mapX: 52, mapY: 51, revenue: 1_200_000, cost: 980_000, volumeGJ: 36_000, tariffRatePerGJ: 31.20, effectiveCostPerGJ: 27.22, peakSharePct: 18, isLossMaking: false, lossAmount: 0 },

  // Gemeente Den Haag
  { id: 'conn-015', customerId: 'kl-006', profitCenterId: 'pc-dhv', segment: 'overheid', type: 'gebouw', address: 'Spui 70', mapX: 42, mapY: 68, revenue: 3_200_000, cost: 2_680_000, volumeGJ: 112_000, tariffRatePerGJ: 26.90, effectiveCostPerGJ: 23.93, peakSharePct: 20, isLossMaking: false, lossAmount: 0 },
  { id: 'conn-016', customerId: 'kl-006', profitCenterId: 'pc-dhv', segment: 'overheid', type: 'gebouw', address: 'Kalvermarkt 1', mapX: 44, mapY: 70, revenue: 2_800_000, cost: 3_120_000, volumeGJ: 98_000, tariffRatePerGJ: 26.90, effectiveCostPerGJ: 31.84, peakSharePct: 68, isLossMaking: true, lossAmount: 484_000 },

  // ASML Eindhoven — zakelijk B2B
  { id: 'conn-017', customerId: 'kl-007', profitCenterId: 'pc-ehv', segment: 'zakelijk', type: 'bedrijfspand', address: 'De Run 6500', mapX: 55, mapY: 78, revenue: 4_800_000, cost: 4_200_000, volumeGJ: 142_000, tariffRatePerGJ: 31.20, effectiveCostPerGJ: 29.58, peakSharePct: 38, isLossMaking: false, lossAmount: 0 },
  { id: 'conn-018', customerId: 'kl-007', profitCenterId: 'pc-ehv', segment: 'zakelijk', type: 'bedrijfspand', address: 'De Run 6502', mapX: 58, mapY: 80, revenue: 3_600_000, cost: 4_380_000, volumeGJ: 108_000, tariffRatePerGJ: 31.20, effectiveCostPerGJ: 40.56, peakSharePct: 78, isLossMaking: true, lossAmount: 1_010_000 },
  { id: 'conn-019', customerId: 'kl-007', profitCenterId: 'pc-ehv', segment: 'zakelijk', type: 'bedrijfspand', address: 'De Run 6504', mapX: 60, mapY: 77, revenue: 2_400_000, cost: 2_100_000, volumeGJ: 72_000, tariffRatePerGJ: 31.20, effectiveCostPerGJ: 29.17, peakSharePct: 32, isLossMaking: false, lossAmount: 0 },

  // Woonstad Eindhoven — residentieel
  { id: 'conn-020', customerId: 'kl-008', profitCenterId: 'pc-ehv', segment: 'residentieel', type: 'woning', address: 'Woonstraat 5', mapX: 52, mapY: 82, revenue: 14_200, cost: 11_800, volumeGJ: 420, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 28.10, peakSharePct: 30, isLossMaking: false, lossAmount: 0 },
  { id: 'conn-021', customerId: 'kl-008', profitCenterId: 'pc-ehv', segment: 'residentieel', type: 'woning', address: 'Woonstraat 7', mapX: 54, mapY: 84, revenue: 12_800, cost: 15_600, volumeGJ: 380, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 41.05, peakSharePct: 76, isLossMaking: true, lossAmount: 4_790 },
  { id: 'conn-022', customerId: 'kl-008', profitCenterId: 'pc-ehv', segment: 'residentieel', type: 'woning', address: 'Woonstraat 9', mapX: 56, mapY: 83, revenue: 13_600, cost: 12_200, volumeGJ: 400, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 30.50, peakSharePct: 35, isLossMaking: true, lossAmount: 820 },
  { id: 'conn-023', customerId: 'kl-008', profitCenterId: 'pc-ehv', segment: 'residentieel', type: 'gebouw', address: 'Wooncomplex Noord', mapX: 50, mapY: 86, revenue: 890_000, cost: 720_000, volumeGJ: 28_000, tariffRatePerGJ: 28.45, effectiveCostPerGJ: 25.71, peakSharePct: 14, isLossMaking: false, lossAmount: 0 },
];

const peakHourlyTemplate = Array.from({ length: 24 }, (_, hour) => {
  const isPeak = (hour >= 7 && hour <= 9) || (hour >= 17 && hour <= 20);
  const basePrice = 35 + (isPeak ? 12 : 0) + Math.sin(hour / 3) * 3;
  return { hour, marketPrice: Math.round(basePrice * 100) / 100 };
});

function buildPeakProfile(
  customerId: string,
  customerName: string,
  segment: Connection['segment'],
  tariffRate: number,
  effectiveCost: number,
  volumeGJ: number,
  peakShare: number,
  connCount: number,
  lossConnCount: number,
  consumptionShape: 'office' | 'industrial' | 'residential' | 'mixed',
): PeakLossProfile {
  const hourlyProfile = peakHourlyTemplate.map(({ hour, marketPrice }) => {
    let consumptionPct: number;
    switch (consumptionShape) {
      case 'office':
        consumptionPct = (hour >= 8 && hour <= 18) ? (hour >= 17 ? 9 : 6) : 1.5;
        break;
      case 'industrial':
        consumptionPct = hour >= 6 && hour <= 22 ? 5.5 : 1;
        break;
      case 'residential':
        consumptionPct = (hour >= 6 && hour <= 9) || (hour >= 17 && hour <= 22) ? 8 : 2.5;
        break;
      default:
        consumptionPct = 4;
    }
    return { hour, consumptionPct, marketPrice };
  });
  const total = hourlyProfile.reduce((s, h) => s + h.consumptionPct, 0);
  const normalized = hourlyProfile.map((h) => ({ ...h, consumptionPct: (h.consumptionPct / total) * 100 }));

  return {
    customerId,
    customerName,
    segment,
    tariffRatePerGJ: tariffRate,
    effectiveCostPerGJ: effectiveCost,
    spreadPerGJ: effectiveCost - tariffRate,
    volumeGJ,
    peakSharePct: peakShare,
    annualLoss: Math.max(0, (effectiveCost - tariffRate) * volumeGJ),
    connectionCount: connCount,
    lossConnectionCount: lossConnCount,
    peakHours: ['07-09', '17-20'],
    hourlyProfile: normalized,
  };
}

export const peakLossProfiles: PeakLossProfile[] = [
  buildPeakProfile('kl-005', 'Rabobank Utrecht', 'zakelijk', 31.20, 36.42, 162_000, 74, 3, 2, 'office'),
  buildPeakProfile('kl-007', 'ASML Eindhoven Campus', 'zakelijk', 31.20, 35.18, 322_000, 78, 3, 1, 'office'),
  buildPeakProfile('kl-001', 'VvE De Groene Hof', 'residentieel', 28.45, 31.28, 3_260, 58, 5, 2, 'residential'),
  buildPeakProfile('kl-003', 'ChemCorp Industries BV', 'industrie', 22.80, 25.42, 568_000, 58, 2, 1, 'industrial'),
  buildPeakProfile('kl-004', 'Havenbedrijf Rotterdam', 'industrie', 22.80, 24.12, 378_000, 35, 2, 2, 'industrial'),
  buildPeakProfile('kl-006', 'Gemeente Den Haag', 'overheid', 26.90, 28.84, 210_000, 68, 2, 1, 'office'),
  buildPeakProfile('kl-008', 'Woningcorporatie Woonstad', 'residentieel', 28.45, 30.12, 28_800, 52, 4, 2, 'residential'),
];

export function getConnectionsForFilters(filters: {
  segment?: string;
  profitCenterId?: string;
  customerId?: string;
  connectionId?: string;
}): Connection[] {
  let result = connections;
  if (filters.segment && filters.segment !== 'alle') {
    result = result.filter((c) => c.segment === filters.segment);
  }
  if (filters.profitCenterId && filters.profitCenterId !== 'alle') {
    result = result.filter((c) => c.profitCenterId === filters.profitCenterId);
  }
  if (filters.customerId && filters.customerId !== 'alle') {
    result = result.filter((c) => c.customerId === filters.customerId);
  }
  if (filters.connectionId && filters.connectionId !== 'alle') {
    result = result.filter((c) => c.id === filters.connectionId);
  }
  return result;
}

export function getLossMakingConnections(): Connection[] {
  return connections.filter((c) => c.isLossMaking);
}

export function getTotalLossAmount(): number {
  return connections.filter((c) => c.isLossMaking).reduce((s, c) => s + c.lossAmount, 0);
}
