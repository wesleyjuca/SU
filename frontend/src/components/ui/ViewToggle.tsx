"use client";
import { List, LayoutGrid } from "lucide-react";

interface ViewToggleProps {
  view: "table" | "grid";
  onChange: (v: "table" | "grid") => void;
}

export function ViewToggle({ view, onChange }: ViewToggleProps) {
  return (
    <div className="flex border border-afj-cream-dark rounded-sm overflow-hidden">
      {(["table", "grid"] as const).map((v) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          aria-label={v === "table" ? "Visualização em tabela" : "Visualização em cards"}
          className={`p-2 transition-colors ${
            view === v
              ? "bg-afj-gold text-white"
              : "bg-white text-afj-black/40 hover:text-afj-gold"
          }`}
        >
          {v === "table" ? <List size={14} /> : <LayoutGrid size={14} />}
        </button>
      ))}
    </div>
  );
}
