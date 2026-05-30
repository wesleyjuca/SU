export default function Loading() {
  return (
    <div className="max-w-3xl mx-auto space-y-5">
      <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-48" />
      <div className="afj-card p-6 space-y-4">
        {Array.from({ length: 7 }).map((_, i) => (
          <div key={i} className="h-10 bg-afj-cream-dark rounded animate-pulse" />
        ))}
      </div>
    </div>
  );
}
