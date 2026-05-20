export default function AgentesLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-40" />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="afj-card p-4 h-24 animate-pulse bg-afj-cream-dark" />
        ))}
      </div>
    </div>
  );
}
