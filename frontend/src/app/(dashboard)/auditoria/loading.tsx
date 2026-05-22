export default function AuditoriaLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-32" />
      <div className="afj-card p-6 space-y-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="flex items-center gap-4">
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-32 flex-shrink-0" />
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse flex-1" />
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-20 flex-shrink-0" />
          </div>
        ))}
      </div>
    </div>
  );
}
