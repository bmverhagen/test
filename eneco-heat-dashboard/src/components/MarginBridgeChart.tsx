import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from 'recharts';
import type { MarginBridgeItem } from '../types';
import { formatCurrency } from '../utils/format';

interface MarginBridgeChartProps {
  data: MarginBridgeItem[];
}

export function MarginBridgeChart({ data }: MarginBridgeChartProps) {
  let running = 0;
  const chartData = data.map((item, index) => {
    let base = 0;
    let height = 0;
    if (item.type === 'start') {
      base = 0;
      height = item.value;
      running = item.value;
    } else if (item.type === 'total') {
      base = 0;
      height = item.value;
    } else {
      if (item.value < 0) {
        running += item.value;
        base = running;
        height = Math.abs(item.value);
      } else {
        base = running;
        height = item.value;
        running += item.value;
      }
    }

    return {
      name: item.label,
      base,
      height,
      value: item.value,
      type: item.type,
      category: item.category,
      fill: getBarColor(item),
      index,
    };
  });

  return (
    <ResponsiveContainer width="100%" height={380}>
      <BarChart data={chartData} margin={{ top: 20, right: 30, left: 20, bottom: 5 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" vertical={false} />
        <XAxis dataKey="name" tick={{ fontSize: 12, fill: '#6b7280' }} axisLine={false} tickLine={false} />
        <YAxis
          tickFormatter={(v) => formatCurrency(v, true)}
          tick={{ fontSize: 11, fill: '#6b7280' }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          formatter={(value) => formatCurrency(Number(value ?? 0))}
          contentStyle={{ borderRadius: 8, border: '1px solid #e5e7eb', fontSize: 13 }}
        />
        <ReferenceLine y={0} stroke="#9ca3af" />
        <Bar dataKey="base" stackId="bridge" fill="transparent" />
        <Bar dataKey="height" stackId="bridge" radius={[4, 4, 0, 0]}>
          {chartData.map((entry, index) => (
            <Cell key={index} fill={entry.fill} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

function getBarColor(item: MarginBridgeItem): string {
  if (item.type === 'start') return '#00a651';
  if (item.type === 'total') return '#003d2e';
  if (item.category === 'sprucing') return '#ff6b35';
  if (item.category === 'heatloss') return '#0077b6';
  if (item.type === 'negative') return '#ef4444';
  return '#00a651';
}
