"use client";
import { FileText } from "lucide-react";
import type { Movimentacao } from "@/types";

interface ProcessTimelineProps {
  movimentacoes: Movimentacao[];
}

export function ProcessTimeline({ movimentacoes }: ProcessTimelineProps) {
  if (movimentacoes.length === 0) {
    return (
      <div className="py-8 text-center text-afj-black/40 text-sm">
        Nenhuma movimentação registrada
      </div>
    );
  }

  return (
    <div className="relative">
      {/* Vertical line */}
      <div className="absolute left-3.5 top-0 bottom-0 w-px bg-afj-cream-dark" />

      <div className="space-y-4">
        {movimentacoes.map((m, idx) => (
          <div key={m.id} className="pl-9 relative">
            {/* Dot */}
            <div
              className={`absolute left-2 top-1.5 w-3 h-3 rounded-full flex-shrink-0 ${
                idx === 0
                  ? "bg-afj-gold border-2 border-afj-gold/30"
                  : "bg-white border-2 border-afj-black/20"
              }`}
            />

            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <p className="text-sm text-afj-black leading-snug">{m.descricao}</p>

                {m.ai_summary && (
                  <div className="mt-1.5 bg-purple-50 border border-purple-100 rounded px-2.5 py-1.5">
                    <p className="text-xs text-purple-800 leading-relaxed">
                      <span className="font-medium">IA: </span>
                      {m.ai_summary}
                    </p>
                  </div>
                )}

                {m.tipo && (
                  <span className="inline-block mt-1 text-xs bg-afj-cream text-afj-black/50 px-1.5 py-0.5 rounded">
                    {m.tipo}
                  </span>
                )}
              </div>

              <span className="text-xs text-afj-black/40 flex-shrink-0 pt-0.5">
                {new Date(m.data_movimento).toLocaleDateString("pt-BR")}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

interface ProcessTimelineCardProps {
  movimentacoes: Movimentacao[];
  title?: string;
}

export function ProcessTimelineCard({ movimentacoes, title = "Movimentações" }: ProcessTimelineCardProps) {
  return (
    <div className="afj-card p-4">
      <h2 className="font-semibold text-afj-black text-sm mb-4 flex items-center gap-2">
        <FileText size={14} />
        {title} ({movimentacoes.length})
      </h2>
      <ProcessTimeline movimentacoes={movimentacoes} />
    </div>
  );
}
