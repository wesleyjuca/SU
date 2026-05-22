export default function Loading() {
  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <div className="h-8 w-48 bg-afj-cream-dark rounded animate-pulse" />
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="afj-card p-4 h-20 animate-pulse bg-afj-cream-dark/50" />
        ))}
      </div>
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="afj-card p-4 h-20 animate-pulse bg-afj-cream-dark/30" />
        ))}
      </div>
    </div>
  );
}
