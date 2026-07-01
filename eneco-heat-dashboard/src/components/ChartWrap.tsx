import type { ReactNode } from 'react';

interface ChartWrapProps {
  height: number;
  children: ReactNode;
  className?: string;
}

/** Wrapper zodat Recharts op mobiel de juiste breedte pakt */
export function ChartWrap({ height, children, className }: ChartWrapProps) {
  return (
    <div className={className} style={{ width: '100%', maxWidth: '100%', height, minHeight: height }}>
      {children}
    </div>
  );
}
