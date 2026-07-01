export type Segment = 'residentieel' | 'zakelijk' | 'industrie' | 'overheid';
export type CostType = 'fixed' | 'variable';
export type RevenueType = 'fixed' | 'variable';
export type ConnectionType = 'woning' | 'bedrijfspand' | 'industrie' | 'gebouw';

export interface MarginBridgeItem {
  label: string;
  value: number;
  type: 'start' | 'positive' | 'negative' | 'total';
  category?: string;
}

export interface ProfitCenter {
  id: string;
  name: string;
  segment: Segment;
  revenue: number;
  revenueFixed: number;
  revenueVariable: number;
  cost: number;
  costFixed: number;
  costVariable: number;
  sprucingCost: number;
  heatLossRevenue: number;
  volumeGJ: number;
}

export interface Customer {
  id: string;
  name: string;
  profitCenterId: string;
  segment: Segment;
  revenue: number;
  revenueFixed: number;
  revenueVariable: number;
  cost: number;
  costFixed: number;
  costVariable: number;
  sprucingCost: number;
  heatLossRevenue: number;
  volumeGJ: number;
  contractId: string;
}

export interface Connection {
  id: string;
  customerId: string;
  profitCenterId: string;
  segment: Segment;
  type: ConnectionType;
  address: string;
  mapX: number;
  mapY: number;
  revenue: number;
  cost: number;
  volumeGJ: number;
  tariffRatePerGJ: number;
  effectiveCostPerGJ: number;
  peakSharePct: number;
  isLossMaking: boolean;
  lossAmount: number;
}

export interface PeakLossProfile {
  customerId: string;
  customerName: string;
  segment: Segment;
  tariffRatePerGJ: number;
  effectiveCostPerGJ: number;
  spreadPerGJ: number;
  volumeGJ: number;
  peakSharePct: number;
  annualLoss: number;
  connectionCount: number;
  lossConnectionCount: number;
  peakHours: string[];
  hourlyProfile: { hour: number; consumptionPct: number; marketPrice: number }[];
}

export interface Contract {
  id: string;
  customerId: string;
  customerName: string;
  startDate: string;
  endDate: string;
  status: 'actief' | 'verlopen' | 'concept';
  tariffId: string;
  volumeGJ: number;
  connectionCount: number;
}

export interface TariffComponent {
  id: string;
  name: string;
  type: 'vast' | 'variabel' | 'capaciteit' | 'transport' | 'energie';
  unit: string;
  rate: number;
  description: string;
}

export interface Tariff {
  id: string;
  name: string;
  segment: Segment;
  validFrom: string;
  validTo: string;
  components: TariffComponent[];
}

export interface SourcingHourly {
  timestamp: string;
  gridId: string;
  gridName: string;
  priceP: number;
  volumeQ: number;
  invoiceId?: string;
  invoiceAmount?: number;
  invoiceStatus: 'gefactureerd' | 'open' | 'afwijking';
}

export interface RevenueYTDMonth {
  month: string;
  monthIndex: number;
  revenueActual: number;
  revenueEstimated: number;
  volumeActualGJ: number;
  volumeEstimatedGJ: number;
  isEstimated: boolean;
}

export interface DashboardFilters {
  segment: Segment | 'alle';
  profitCenterId: string | 'alle';
  customerId: string | 'alle';
  connectionId: string | 'alle';
  period: 'ytd' | 'q1' | 'q2' | 'q3' | 'q4' | 'jaar';
  costType: CostType | 'alle';
  revenueType: RevenueType | 'alle';
}

export type DrillLevel = 'portfolio' | 'segment' | 'profitCenter' | 'customer' | 'connection';

export interface DrillTarget {
  level: DrillLevel;
  segment?: Segment | 'alle';
  profitCenterId?: string;
  customerId?: string;
  connectionId?: string;
  label: string;
}

export type ViewId =
  | 'overzicht'
  | 'bruto-marge'
  | 'revenue-ytd'
  | 'sourcing'
  | 'kaart'
  | 'piekverlies'
  | 'klanten'
  | 'contracten'
  | 'tarieven';
