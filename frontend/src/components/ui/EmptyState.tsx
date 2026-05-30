import { LucideIcon } from "lucide-react";

interface EmptyStateProps {
  icon: LucideIcon;
  title: string;
  description?: string;
  action?: { label: string; onClick: () => void };
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="afj-card p-16 text-center">
      <div className="w-14 h-14 rounded-full bg-afj-cream-dark flex items-center justify-center mx-auto mb-4">
        <Icon className="text-afj-black/20" size={28} />
      </div>
      <p className="font-semibold text-afj-black mb-1">{title}</p>
      {description && <p className="text-afj-black/40 text-sm mt-1">{description}</p>}
      {action && (
        <button onClick={action.onClick} className="btn-afj-primary rounded-sm mt-5">
          {action.label}
        </button>
      )}
    </div>
  );
}
