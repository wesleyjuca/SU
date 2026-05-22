export default function FinanceiroLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="flex justify-between items-center">
        <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-36" />
        <div className="h-9 bg-afj-cream-dark rounded animate-pulse w-40" />
      </div>
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="afj-card p-5 space-y-2">
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-20" />
            <div className="h-7 bg-afj-cream-dark rounded animate-pulse w-28" />
          </div>
        ))}
      </div>
      <div className="afj-card p-6 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-11 bg-afj-cream-dark rounded animate-pulse" />
        ))}
      </div>
    </div>
  );
}
