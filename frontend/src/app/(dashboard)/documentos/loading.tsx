export default function DocumentosLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="flex justify-between items-center">
        <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-36" />
        <div className="h-9 bg-afj-cream-dark rounded animate-pulse w-40" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="afj-card p-5 space-y-3">
            <div className="h-5 bg-afj-cream-dark rounded animate-pulse w-3/4" />
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-1/2" />
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-1/3" />
          </div>
        ))}
      </div>
    </div>
  );
}
