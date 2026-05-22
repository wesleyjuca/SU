export default function AprovacoesLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-36" />
      <div className="space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="afj-card p-5 flex items-start gap-4">
            <div className="w-10 h-10 bg-afj-cream-dark rounded-full animate-pulse flex-shrink-0" />
            <div className="flex-1 space-y-2">
              <div className="h-5 bg-afj-cream-dark rounded animate-pulse w-2/3" />
              <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-1/2" />
            </div>
            <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-24" />
          </div>
        ))}
      </div>
    </div>
  );
}
