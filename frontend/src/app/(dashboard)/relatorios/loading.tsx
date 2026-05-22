export default function Loading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="h-8 w-48 bg-afj-cream-dark rounded animate-pulse" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="afj-card p-5 h-24 animate-pulse bg-afj-cream-dark/50" />
        ))}
      </div>
      <div className="afj-card p-5 h-80 animate-pulse bg-afj-cream-dark/30" />
    </div>
  );
}
