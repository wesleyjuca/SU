export function Skeleton({ className }: { className?: string }) {
  return <div className={`animate-pulse bg-afj-cream-dark rounded-sm ${className ?? ""}`} />;
}

export function SkeletonCard() {
  return (
    <div className="afj-card p-5 space-y-3">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-8 w-1/2" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}

export function SkeletonTable({ rows = 5 }: { rows?: number }) {
  return (
    <div className="afj-card p-4 space-y-2">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-11 w-full" />
      ))}
    </div>
  );
}

export function SkeletonGrid({ cols = 3, rows = 2 }: { cols?: number; rows?: number }) {
  const colClass = { 1: "grid-cols-1", 2: "grid-cols-1 sm:grid-cols-2", 3: "grid-cols-1 sm:grid-cols-2 lg:grid-cols-3", 4: "grid-cols-2 lg:grid-cols-4" }[cols] ?? "grid-cols-3";
  return (
    <div className={`grid ${colClass} gap-4`}>
      {Array.from({ length: cols * rows }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
