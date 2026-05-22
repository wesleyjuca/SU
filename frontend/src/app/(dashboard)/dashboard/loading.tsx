export default function DashboardLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-56" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="afj-card p-5 space-y-3">
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-24" />
            <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-16" />
          </div>
        ))}
      </div>
      <div className="afj-card p-6 space-y-3">
        <div className="h-5 bg-afj-cream-dark rounded animate-pulse w-40" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />
        ))}
      </div>
    </div>
  );
}
