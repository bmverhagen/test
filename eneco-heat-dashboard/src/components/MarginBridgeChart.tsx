import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ReferenceLine,
} from 'recharts';
import type { MarginBridgeItem } from '../types';
import { formatCurrency } from '../utils/format';
import { chartTooltipStyle, chartAxisStyle, ENECO_COLORS } from '../theme/chartTheme';
import { ChartWrap } from './ChartWrap';

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
      fillId: `bridge-${index}`,
      fill: getBarColor(item),
      index,
    };
  });

  return (
    <ChartWrap height={400}>
      <ResponsiveContainer width="100%" height="100%">
      <BarChart data={chartData} margin={{ top: 24, right: 24, left: 8, bottom: 8 }} barCategoryGap="20%">
        <defs>
          <linearGradient id="grad-green" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={ENECO_COLORS.greenBright} />
            <stop offset="100%" stopColor={ENECO_COLORS.green} />
          </linearGradient>
          <linearGradient id="grad-dark" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#005a40" />
            <stop offset="100%" stopColor={ENECO_COLORS.dark} />
          </linearGradient>
          <linearGradient id="grad-red" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ff4d58" />
            <stop offset="100%" stopColor={ENECO_COLORS.red} />
          </linearGradient>
          <linearGradient id="grad-warm" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ffb347" />
            <stop offset="100%" stopColor={ENECO_COLORS.warm} />
          </linearGradient>
          <linearGradient id="grad-teal" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#00a89e" />
            <stop offset="100%" stopColor={ENECO_COLORS.teal} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,166,81,0.1)" vertical={false} />
        <XAxis dataKey="name" tick={chartAxisStyle} axisLine={false} tickLine={false} />
        <YAxis tickFormatter={(v) => formatCurrency(v, true)} tick={chartAxisStyle} axisLine={false} tickLine={false} width={72} />
        <Tooltip
          formatter={(value) => [formatCurrency(Number(value ?? 0)), '']}
          contentStyle={chartTooltipStyle}
          cursor={{ fill: 'rgba(0, 166, 81, 0.05)' }}
        />
        <ReferenceLine y={0} stroke="rgba(0,61,46,0.2)" strokeWidth={1.5} />
        <Bar dataKey="base" stackId="bridge" fill="transparent" />
        <Bar dataKey="height" stackId="bridge" radius={[6, 6, 0, 0]} maxBarSize={64}>
          {chartData.map((entry, index) => (
            <Cell key={index} fill={getBarGradient(entry)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
    </ChartWrap>
  );
}

function getBarColor(item: MarginBridgeItem): string {
  if (item.type === 'start') return ENECO_COLORS.green;
  if (item.type === 'total') return ENECO_COLORS.dark;
  if (item.category === 'sprucing') return ENECO_COLORS.warm;
  if (item.category === 'heatloss') return ENECO_COLORS.teal;
  if (item.type === 'negative') return ENECO_COLORS.red;
  return ENECO_COLORS.green;
}

function getBarGradient(entry: { type: string; category?: string }): string {
  if (entry.type === 'start') return 'url(#grad-green)';
  if (entry.type === 'total') return 'url(#grad-dark)';
  if (entry.category === 'sprucing') return 'url(#grad-warm)';
  if (entry.category === 'heatloss') return 'url(#grad-teal)';
  if (entry.type === 'negative') return 'url(#grad-red)';
  return 'url(#grad-green)';
}
