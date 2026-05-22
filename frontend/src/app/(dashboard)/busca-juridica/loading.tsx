export default function Loading() {
  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <div className="h-8 w-56 bg-afj-cream-dark rounded animate-pulse" />
      <div className="afj-card p-5 h-32 animate-pulse bg-afj-cream-dark/40" />
      <div className="space-y-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="afj-card p-5 h-24 animate-pulse bg-afj-cream-dark/30" />
        ))}
      </div>
    </div>
  );
}
