export function MetricCard({ eyebrow, title, value, tone = "neutral" }) {
  return (
    <article className={`metric-card metric-card-${tone}`}>
      <span className="metric-eyebrow">{eyebrow}</span>
      <div className="metric-value">{value}</div>
      <p className="metric-title">{title}</p>
    </article>
  );
}
