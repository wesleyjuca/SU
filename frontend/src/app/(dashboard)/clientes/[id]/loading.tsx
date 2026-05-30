export default function Loading() {
  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div className="h-7 w-48 bg-afj-cream-dark rounded animate-pulse" />
      <div className="h-8 w-64 bg-afj-cream-dark rounded animate-pulse" />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        <div className="space-y-4">
          <div className="afj-card p-5 h-48 animate-pulse bg-afj-cream-dark/40" />
          <div className="afj-card p-5 h-32 animate-pulse bg-afj-cream-dark/30" />
        </div>
        <div className="afj-card p-5 h-80 animate-pulse bg-afj-cream-dark/30" />
      </div>
    </div>
  );
}
