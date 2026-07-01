export const ENECO_COLORS = {
  green: '#00a651',
  greenBright: '#00c965',
  greenLight: '#4ade80',
  greenPale: '#b8f0d0',
  dark: '#003d2e',
  darker: '#002419',
  red: '#e30613',
  warm: '#ff8c42',
  teal: '#00857c',
  blue: '#0077b6',
  gray: '#6b7280',
  grid: 'rgba(0, 166, 81, 0.08)',
} as const;

export const CHART_GRADIENTS = {
  green: ['#00a651', '#00c965'],
  dark: ['#003d2e', '#005a40'],
  red: ['#e30613', '#ff4d58'],
  warm: ['#ff8c42', '#ffb347'],
  teal: ['#00857c', '#00a89e'],
  blue: ['#0077b6', '#00a0e0'],
} as const;

export const chartTooltipStyle = {
  borderRadius: 12,
  border: '1px solid rgba(0, 166, 81, 0.15)',
  boxShadow: '0 8px 32px -8px rgba(0, 61, 46, 0.2)',
  fontSize: 13,
  fontFamily: '"Plus Jakarta Sans", sans-serif',
  padding: '10px 14px',
};

export const chartAxisStyle = {
  fontSize: 11,
  fill: '#6b7280',
  fontFamily: '"Plus Jakarta Sans", sans-serif',
};

export const chartGridStyle = {
  strokeDasharray: '3 3',
  stroke: 'rgba(0, 166, 81, 0.1)',
  vertical: false,
};

export const SEGMENT_COLORS: Record<string, string> = {
  residentieel: ENECO_COLORS.green,
  zakelijk: ENECO_COLORS.teal,
  industrie: ENECO_COLORS.warm,
  overheid: '#7b2cbf',
};
