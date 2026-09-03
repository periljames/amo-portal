import React from "react";

type SparklineProps = {
  data: number[];
  width?: number;
  height?: number;
  color?: string;
  /** Fixed maximum for the y-axis (e.g. 100 for percentages). Auto-scales when omitted. */
  max?: number;
};

/**
 * Lightweight inline-SVG sparkline for real-time metric history. No chart
 * dependency so it stays cheap to re-render every second.
 */
export const Sparkline: React.FC<SparklineProps> = ({
  data,
  width = 200,
  height = 48,
  color = "var(--platform-accent, #3b67f2)",
  max,
}) => {
  const points = data.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (points.length < 2) {
    return <svg className="platform-sparkline" width={width} height={height} aria-hidden="true" />;
  }

  const hi = max ?? Math.max(...points, 1);
  const lo = Math.min(...points, 0);
  const range = hi - lo || 1;
  const stepX = width / (points.length - 1);

  const line = points
    .map((value, index) => {
      const x = index * stepX;
      const y = height - ((value - lo) / range) * height;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const area = `0,${height} ${line} ${width},${height}`;

  return (
    <svg
      className="platform-sparkline"
      width="100%"
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-hidden="true"
    >
      <polygon points={area} fill={color} opacity={0.12} />
      <polyline
        points={line}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
};
