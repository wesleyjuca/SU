"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";

const AREAS = ["CIVIL", "TRABALHISTA", "TRIBUTARIO", "PENAL", "PREVIDENCIARIO", "CONSUMIDOR"];

export default function NovoProcessoPage() {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [form, setForm] = useState({
    numero_cnj: "",
    tribunal: "",
    vara: "",
    area_direito: "CIVIL",
    tipo_acao: "",
    descricao: "",
    valor_causa: "",
    monitoring_active: true,
  });

  function set(key: string, value: string | boolean) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError("");
    try {
      const token = localStorage.getItem("afj_access_token");
      const body = {
        ...form,
        valor_causa: form.valor_causa ? parseFloat(form.valor_causa) : null,
      };
      const res = await fetch("/api/v1/processes", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        router.push("/processos");
      } else {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || `Erro ${res.status}`);
      }
    } catch {
      setError("Erro de conexão. Tente novamente.");
    } finally {
      setSaving(false);
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
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Número CNJ</label>
              <input
                type="text"
                value={form.numero_cnj}
                onChange={(e) => set("numero_cnj", e.target.value)}
                placeholder="0000000-00.0000.0.00.0000"
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Tribunal *</label>
              <input
                type="text"
                value={form.tribunal}
                onChange={(e) => set("tribunal", e.target.value)}
                placeholder="TJSP, STJ, TRT2..."
                required
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Vara</label>
              <input
                type="text"
                value={form.vara}
                onChange={(e) => set("vara", e.target.value)}
                placeholder="1ª Vara Cível..."
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Área do Direito *</label>
              <select
                value={form.area_direito}
                onChange={(e) => set("area_direito", e.target.value)}
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              >
                {AREAS.map((a) => <option key={a} value={a}>{a}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Tipo de Ação</label>
              <input
                type="text"
                value={form.tipo_acao}
                onChange={(e) => set("tipo_acao", e.target.value)}
                placeholder="Ação de indenização..."
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Valor da Causa (R$)</label>
              <input
                type="number"
                step="0.01"
                value={form.valor_causa}
                onChange={(e) => set("valor_causa", e.target.value)}
                placeholder="0,00"
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Descrição</label>
            <textarea
              value={form.descricao}
              onChange={(e) => set("descricao", e.target.value)}
              rows={3}
              placeholder="Resumo dos fatos..."
              className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none"
            />
          </div>

          <label className="flex items-center gap-2 text-sm text-afj-black/70">
            <input
              type="checkbox"
              checked={form.monitoring_active}
              onChange={(e) => set("monitoring_active", e.target.checked)}
            />
            Ativar monitoramento automático
          </label>

          {error && (
            <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-md px-3 py-2">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <Link href="/processos" className="flex-1 btn-afj-outline rounded-md text-center py-2 text-sm">
              Cancelar
            </Link>
            <button
              type="submit"
              disabled={saving}
              className="flex-1 btn-afj-primary rounded-md disabled:opacity-50"
            >
              {saving ? "Salvando..." : "Cadastrar Processo"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
