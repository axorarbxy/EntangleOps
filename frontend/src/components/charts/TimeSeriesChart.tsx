import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from 'recharts';
export function TimeSeriesChart({
  data,
}: {
  data: { time: number; value: number | null }[];
}) {
  const usable = data.filter((row) => row.value !== null);
  if (usable.length < 2)
    return (
      <div className="chart-empty">
        Not enough time-series values to draw a chart.
      </div>
    );
  return (
    <div className="chart-wrap">
      <ResponsiveContainer width="100%" height={240}>
        <LineChart
          data={usable}
          margin={{ top: 8, right: 10, bottom: 3, left: 0 }}
        >
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 5" />
          <XAxis
            dataKey="time"
            tick={{ fill: 'var(--muted)', fontSize: 9 }}
            tickLine={false}
            axisLine={{ stroke: 'var(--border)' }}
          />
          <YAxis
            width={38}
            tick={{ fill: 'var(--muted)', fontSize: 9 }}
            tickLine={false}
            axisLine={false}
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke="var(--accent)"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
