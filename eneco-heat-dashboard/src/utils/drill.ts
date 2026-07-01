import type { DashboardFilters, DrillLevel, DrillTarget, Segment } from '../types';
import { profitCenters, customers, SEGMENTS } from '../data/dummyData';
import { connections } from '../data/connections';

export function getDrillLevel(filters: DashboardFilters): DrillLevel {
  if (filters.connectionId !== 'alle') return 'connection';
  if (filters.customerId !== 'alle') return 'customer';
  if (filters.profitCenterId !== 'alle') return 'profitCenter';
  if (filters.segment !== 'alle') return 'segment';
  return 'portfolio';
}

export function getBreadcrumbs(filters: DashboardFilters): DrillTarget[] {
  const crumbs: DrillTarget[] = [
    { level: 'portfolio', label: 'Portfolio', segment: 'alle' },
  ];

  if (filters.segment !== 'alle') {
    const seg = SEGMENTS.find((s) => s.id === filters.segment);
    crumbs.push({ level: 'segment', segment: filters.segment, label: seg?.label ?? filters.segment });
  }
  if (filters.profitCenterId !== 'alle') {
    const pc = profitCenters.find((p) => p.id === filters.profitCenterId);
    crumbs.push({
      level: 'profitCenter',
      segment: filters.segment,
      profitCenterId: filters.profitCenterId,
      label: pc?.name ?? filters.profitCenterId,
    });
  }
  if (filters.customerId !== 'alle') {
    const c = customers.find((x) => x.id === filters.customerId);
    crumbs.push({
      level: 'customer',
      segment: filters.segment,
      profitCenterId: filters.profitCenterId,
      customerId: filters.customerId,
      label: c?.name ?? filters.customerId,
    });
  }
  if (filters.connectionId !== 'alle') {
    const conn = connections.find((x) => x.id === filters.connectionId);
    crumbs.push({
      level: 'connection',
      segment: filters.segment,
      profitCenterId: filters.profitCenterId,
      customerId: filters.customerId,
      connectionId: filters.connectionId,
      label: conn?.address ?? filters.connectionId,
    });
  }
  return crumbs;
}

export function filtersFromBreadcrumb(crumb: DrillTarget): DashboardFilters {
  return {
    segment: crumb.segment ?? 'alle',
    profitCenterId: crumb.profitCenterId ?? 'alle',
    customerId: crumb.customerId ?? 'alle',
    connectionId: crumb.connectionId ?? 'alle',
    period: 'ytd',
    costType: 'alle',
    revenueType: 'alle',
  };
}

export function drillToSegment(filters: DashboardFilters, segment: Segment): DashboardFilters {
  return { ...filters, segment, profitCenterId: 'alle', customerId: 'alle', connectionId: 'alle' };
}

export function drillToProfitCenter(filters: DashboardFilters, profitCenterId: string, segment?: Segment): DashboardFilters {
  const pc = profitCenters.find((p) => p.id === profitCenterId);
  return {
    ...filters,
    segment: segment ?? pc?.segment ?? filters.segment,
    profitCenterId,
    customerId: 'alle',
    connectionId: 'alle',
  };
}

export function drillToCustomer(filters: DashboardFilters, customerId: string): DashboardFilters {
  const c = customers.find((x) => x.id === customerId);
  return {
    ...filters,
    segment: c?.segment ?? filters.segment,
    profitCenterId: c?.profitCenterId ?? filters.profitCenterId,
    customerId,
    connectionId: 'alle',
  };
}

export function drillToConnection(filters: DashboardFilters, connectionId: string): DashboardFilters {
  const conn = connections.find((x) => x.id === connectionId);
  return {
    ...filters,
    segment: conn?.segment ?? filters.segment,
    profitCenterId: conn?.profitCenterId ?? filters.profitCenterId,
    customerId: conn?.customerId ?? filters.customerId,
    connectionId,
  };
}

export function resetDrill(filters: DashboardFilters): DashboardFilters {
  return { ...filters, segment: 'alle', profitCenterId: 'alle', customerId: 'alle', connectionId: 'alle' };
}

export interface DrillRow {
  id: string;
  name: string;
  level: DrillLevel;
  segment?: Segment;
  revenue: number;
  revenueFixed: number;
  revenueVariable: number;
  cost: number;
  costFixed: number;
  costVariable: number;
  sprucing: number;
  heatLoss: number;
  margin: number;
  volumeGJ: number;
  canDrill: boolean;
}

export function getDrillRows(filters: DashboardFilters): DrillRow[] {
  const level = getDrillLevel(filters);

  if (level === 'connection') {
    const conn = connections.find((c) => c.id === filters.connectionId);
    if (!conn) return [];
    return [{
      id: conn.id,
      name: conn.address,
      level: 'connection',
      segment: conn.segment,
      revenue: conn.revenue,
      revenueFixed: conn.revenue * 0.35,
      revenueVariable: conn.revenue * 0.65,
      cost: conn.cost,
      costFixed: conn.cost * 0.4,
      costVariable: conn.cost * 0.6,
      sprucing: 0,
      heatLoss: 0,
      margin: conn.revenue - conn.cost,
      volumeGJ: conn.volumeGJ,
      canDrill: false,
    }];
  }

  if (level === 'customer') {
    return connections
      .filter((c) => c.customerId === filters.customerId)
      .map((conn) => ({
        id: conn.id,
        name: conn.address,
        level: 'connection' as DrillLevel,
        segment: conn.segment,
        revenue: conn.revenue,
        revenueFixed: conn.revenue * 0.35,
        revenueVariable: conn.revenue * 0.65,
        cost: conn.cost,
        costFixed: conn.cost * 0.4,
        costVariable: conn.cost * 0.6,
        sprucing: 0,
        heatLoss: 0,
        margin: conn.revenue - conn.cost,
        volumeGJ: conn.volumeGJ,
        canDrill: true,
      }));
  }

  if (level === 'profitCenter') {
    return customers
      .filter((c) => c.profitCenterId === filters.profitCenterId)
      .map((c) => ({
        id: c.id,
        name: c.name,
        level: 'customer' as DrillLevel,
        segment: c.segment,
        revenue: c.revenue,
        revenueFixed: c.revenueFixed,
        revenueVariable: c.revenueVariable,
        cost: c.cost,
        costFixed: c.costFixed,
        costVariable: c.costVariable,
        sprucing: c.sprucingCost,
        heatLoss: c.heatLossRevenue,
        margin: c.revenue - c.cost - c.sprucingCost + c.heatLossRevenue,
        volumeGJ: c.volumeGJ,
        canDrill: true,
      }));
  }

  if (level === 'segment') {
    return profitCenters
      .filter((pc) => pc.segment === filters.segment)
      .map((pc) => ({
        id: pc.id,
        name: pc.name,
        level: 'profitCenter' as DrillLevel,
        segment: pc.segment,
        revenue: pc.revenue,
        revenueFixed: pc.revenueFixed,
        revenueVariable: pc.revenueVariable,
        cost: pc.cost,
        costFixed: pc.costFixed,
        costVariable: pc.costVariable,
        sprucing: pc.sprucingCost,
        heatLoss: pc.heatLossRevenue,
        margin: pc.revenue - pc.cost - pc.sprucingCost + pc.heatLossRevenue,
        volumeGJ: pc.volumeGJ,
        canDrill: true,
      }));
  }

  // portfolio level — show segments
  return SEGMENTS.map((seg) => {
    const pcs = profitCenters.filter((pc) => pc.segment === seg.id);
    const revenue = pcs.reduce((s, i) => s + i.revenue, 0);
    const cost = pcs.reduce((s, i) => s + i.cost, 0);
    const sprucing = pcs.reduce((s, i) => s + i.sprucingCost, 0);
    const heatLoss = pcs.reduce((s, i) => s + i.heatLossRevenue, 0);
    return {
      id: seg.id,
      name: seg.label,
      level: 'segment' as DrillLevel,
      segment: seg.id,
      revenue,
      revenueFixed: pcs.reduce((s, i) => s + i.revenueFixed, 0),
      revenueVariable: pcs.reduce((s, i) => s + i.revenueVariable, 0),
      cost,
      costFixed: pcs.reduce((s, i) => s + i.costFixed, 0),
      costVariable: pcs.reduce((s, i) => s + i.costVariable, 0),
      sprucing,
      heatLoss,
      margin: revenue - cost - sprucing + heatLoss,
      volumeGJ: pcs.reduce((s, i) => s + i.volumeGJ, 0),
      canDrill: true,
    };
  });
}

export function applyDrillClick(filters: DashboardFilters, row: DrillRow): DashboardFilters {
  switch (row.level) {
    case 'segment':
      return drillToSegment(filters, row.id as Segment);
    case 'profitCenter':
      return drillToProfitCenter(filters, row.id, row.segment);
    case 'customer':
      return drillToCustomer(filters, row.id);
    case 'connection':
      return drillToConnection(filters, row.id);
    default:
      return filters;
  }
}
