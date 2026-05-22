export default function ClientesLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="flex justify-between items-center">
        <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-32" />
        <div className="h-9 bg-afj-cream-dark rounded animate-pulse w-36" />
      </div>
      <div className="afj-card p-6 space-y-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-12 bg-afj-cream-dark rounded animate-pulse" />
        ))}
      </div>
    </div>
  );
}
