export default function Loading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-64" />
      <div className="afj-card p-6 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-6 bg-afj-cream-dark rounded animate-pulse" style={{ width: `${60 + i * 5}%` }} />
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="afj-card p-5 h-48 animate-pulse bg-afj-cream-dark/30" />
        <div className="afj-card p-5 h-48 animate-pulse bg-afj-cream-dark/30" />
      </div>
    </div>
  );
}
