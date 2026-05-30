"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useForm } from "react-hook-form";
import type { Resolver } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ProcessoSchema, type ProcessoInput } from "@/lib/schemas";

const AREAS = ["CIVIL", "TRABALHISTA", "TRIBUTARIO", "PENAL", "PREVIDENCIARIO", "CONSUMIDOR"];

export default function NovoProcessoPage() {
  const router = useRouter();
  const [apiError, setApiError] = useState("");
  const [monitoringActive, setMonitoringActive] = useState(true);
  const [vara, setVara] = useState("");

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ProcessoInput>({
    resolver: zodResolver(ProcessoSchema) as Resolver<ProcessoInput>,
    defaultValues: { area_direito: "CIVIL" },
  });

  async function onSubmit(data: ProcessoInput) {
    setApiError("");
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/processes", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...data, vara, monitoring_active: monitoringActive }),
      });
      if (res.ok) {
        router.push("/processos");
      } else {
        const d = await res.json().catch(() => ({}));
        setApiError(d.detail || `Erro ${res.status}`);
      }
    } catch {
      setApiError("Erro de conexão. Tente novamente.");
    }
  }

  return (
    <div className="max-w-2xl mx-auto space-y-5">
      <div className="flex items-center gap-3">
        <Link href="/processos" className="text-afj-black/40 hover:text-afj-black transition-colors">
          <ArrowLeft size={18} />
        </Link>
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Novo Processo</h1>
          <p className="text-afj-black/50 text-sm">Cadastrar processo para monitoramento</p>
        </div>
      </div>

      <div className="afj-card p-6">
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Número CNJ</label>
              <input
                {...register("numero_cnj")}
                type="text"
                placeholder="0000000-00.0000.0.00.0000"
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold font-mono"
              />
              {errors.numero_cnj && (
                <p className="text-xs text-red-500 mt-1">{errors.numero_cnj.message}</p>
              )}
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Tribunal *</label>
              <input
                {...register("tribunal")}
                type="text"
                placeholder="TJSP, STJ, TRT2..."
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
              {errors.tribunal && (
                <p className="text-xs text-red-500 mt-1">{errors.tribunal.message}</p>
              )}
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Vara</label>
              <input
                type="text"
                value={vara}
                onChange={(e) => setVara(e.target.value)}
                placeholder="1ª Vara Cível..."
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Área do Direito</label>
              <select
                {...register("area_direito")}
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              >
                {AREAS.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Tipo de Ação</label>
              <input
                {...register("tipo_acao")}
                type="text"
                placeholder="Ação de indenização..."
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Valor da Causa (R$)</label>
              <input
                {...register("valor_causa")}
                type="number"
                step="0.01"
                placeholder="0,00"
                className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
              {errors.valor_causa && (
                <p className="text-xs text-red-500 mt-1">{errors.valor_causa.message}</p>
              )}
            </div>
          </div>

          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Descrição</label>
            <textarea
              {...register("descricao")}
              rows={3}
              placeholder="Resumo dos fatos..."
              className="w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-afj-black/70 cursor-pointer">
            <input
              type="checkbox"
              checked={monitoringActive}
              onChange={(e) => setMonitoringActive(e.target.checked)}
            />
            Ativar monitoramento automático
          </label>

          {apiError && (
            <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-sm px-3 py-2">
              {apiError}
            </p>
          )}

          <div className="flex gap-3 pt-2">
            <Link href="/processos" className="flex-1 btn-afj-outline rounded-sm text-center py-2 text-sm">
              Cancelar
            </Link>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex-1 btn-afj-primary rounded-sm disabled:opacity-50"
            >
              {isSubmitting ? "Salvando..." : "Cadastrar Processo"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
