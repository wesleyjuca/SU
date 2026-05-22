export default function PeticoesLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="flex justify-between items-center">
        <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-32" />
        <div className="h-9 bg-afj-cream-dark rounded animate-pulse w-40" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="afj-card p-5 space-y-3">
            <div className="h-5 bg-afj-cream-dark rounded animate-pulse w-3/4" />
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-1/2" />
            <div className="flex gap-2">
              <div className="h-6 bg-afj-cream-dark rounded animate-pulse w-20" />
              <div className="h-6 bg-afj-cream-dark rounded animate-pulse w-16" />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
