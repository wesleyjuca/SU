export default function VisualLawLoading() {
  return (
    <div className="max-w-7xl mx-auto space-y-4">
      <div className="flex justify-between items-center">
        <div className="h-8 bg-afj-cream-dark rounded animate-pulse w-36" />
        <div className="h-9 bg-afj-cream-dark rounded animate-pulse w-32" />
      </div>
      <div className="afj-card animate-pulse" style={{ height: "600px" }} />
    </div>
  );
}
