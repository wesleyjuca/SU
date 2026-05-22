export default function ConfiguracoesLoading() {
  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-40" />
      <div className="flex gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-9 bg-afj-cream-dark rounded animate-pulse w-28" />
        ))}
      </div>
      <div className="afj-card p-6 space-y-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="space-y-2">
            <div className="h-4 bg-afj-cream-dark rounded animate-pulse w-28" />
            <div className="h-10 bg-afj-cream-dark rounded animate-pulse" />
          </div>
        ))}
      </div>
    </div>
  );
}
