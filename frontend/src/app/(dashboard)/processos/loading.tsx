export default function ProcessosLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-48" />
      <div className="afj-card p-8">
        <div className="space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />
          ))}
        </div>
      </div>
    </div>
  );
}
