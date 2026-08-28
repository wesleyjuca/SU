"use client";
import { useState } from "react";
import { Calendar } from "lucide-react";
import { useToast } from "@/components/ui/Toast";

interface CalcResult {
  data_prazo: string;
  feriados_no_periodo: number;
  dias_uteis: boolean;
}

interface PrazoCalculatorProps {
  // Chamado com a data calculada assim que POST /processes/deadlines/calcular
  // volta com sucesso — quem usa decide em quais campos aplicar (ex.: só
  // data_prazo, ou data_prazo + data_fatal).
  onCalculado: (dataPrazo: string) => void;
}

// Fase 243 — antes desta fase, `processos/[id]/page.tsx` e `agenda/page.tsx`
// mantinham 2 cópias manuais desta calculadora, com campos divergentes
// (a de Agenda nem tinha como sugerir data_fatal). Componentizado numa fonte
// única — cada tela decide só o que fazer com a data calculada.
export function PrazoCalculator({ onCalculado }: PrazoCalculatorProps) {
  const toast = useToast();
  const [calc, setCalc] = useState({ data_intimacao: "", dias: "", dias_uteis: true });
  const [calcResult, setCalcResult] = useState<CalcResult | null>(null);
  const [calculando, setCalculando] = useState(false);

  async function calcularPrazo() {
    if (!calc.data_intimacao || !calc.dias || Number(calc.dias) < 1) {
      toast.error("Informe a data da intimação e o nº de dias.");
      return;
    }
    setCalculando(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/processes/deadlines/calcular", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ data_intimacao: calc.data_intimacao, dias: Number(calc.dias), dias_uteis: calc.dias_uteis }),
      });
      if (res.ok) {
        const r: CalcResult = await res.json();
        setCalcResult(r);
        onCalculado(r.data_prazo);
      } else {
        toast.error("Não foi possível calcular o prazo.");
      }
    } catch {
      toast.error("Falha de conexão.");
    } finally {
      setCalculando(false);
    }
  }

  return (
    <div className="border border-afj-gold/30 bg-afj-gold/5 rounded-sm p-3 space-y-2">
      <p className="text-xs font-semibold text-afj-black/70 flex items-center gap-1.5">
        <Calendar size={13} className="text-afj-gold" /> Calcular por intimação
      </p>
      <div className="grid grid-cols-3 gap-2">
        <div className="col-span-1">
          <label className="text-[11px] text-afj-black/50 block mb-0.5">Intimação/publicação</label>
          <input
            type="date"
            value={calc.data_intimacao}
            onChange={(e) => setCalc({ ...calc, data_intimacao: e.target.value })}
            className="w-full border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white"
          />
        </div>
        <div>
          <label className="text-[11px] text-afj-black/50 block mb-0.5">Prazo (dias)</label>
          <input
            type="number"
            min={1}
            value={calc.dias}
            onChange={(e) => setCalc({ ...calc, dias: e.target.value })}
            placeholder="15"
            className="w-full border border-afj-cream-dark rounded-sm px-2 py-1.5 text-sm bg-white"
          />
        </div>
        <div className="flex items-end">
          <label className="flex items-center gap-1.5 text-[11px] text-afj-black/60 pb-1.5 cursor-pointer">
            <input
              type="checkbox"
              checked={calc.dias_uteis}
              onChange={(e) => setCalc({ ...calc, dias_uteis: e.target.checked })}
              className="accent-afj-gold"
            />
            Dias úteis
          </label>
        </div>
      </div>
      <button
        type="button"
        onClick={calcularPrazo}
        disabled={calculando}
        className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm w-full disabled:opacity-50"
      >
        {calculando ? "Calculando..." : "Calcular data do prazo"}
      </button>
      {calcResult && (
        <p className="text-xs text-afj-black/70 bg-white border border-afj-gold/30 rounded-sm px-2 py-1.5">
          Vence em <strong>{new Date(calcResult.data_prazo + "T00:00:00").toLocaleDateString("pt-BR")}</strong>
          {" "}({calc.dias} {calcResult.dias_uteis ? "dias úteis" : "dias corridos"}
          {calcResult.feriados_no_periodo > 0 ? `, ${calcResult.feriados_no_periodo} feriado(s)/não-úteis no período` : ""}).
          <span className="block text-[10px] text-afj-black/40 mt-0.5">Confira feriados locais da comarca — o cálculo usa feriados nacionais + recesso.</span>
        </p>
      )}
    </div>
  );
}
