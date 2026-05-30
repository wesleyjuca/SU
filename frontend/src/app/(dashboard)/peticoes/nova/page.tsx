"use client";
import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { ChevronRight, ChevronLeft, Scale, FileText, Send, CheckCircle, Loader2, Edit3 } from "lucide-react";
import dynamic from "next/dynamic";
const PetitionEditor = dynamic(
  () => import("@/components/petitions/PetitionEditor").then((m) => ({ default: m.PetitionEditor })),
  { ssr: false, loading: () => <div className="afj-card p-8 text-center text-afj-black/40 animate-pulse">Carregando editor...</div> }
);

interface Processo {
  id: string;
  numero_cnj: string | null;
  tribunal: string;
  area_direito: string | null;
}

const TIPOS_PETICAO = [
  "PETICAO_INICIAL",
  "CONTESTACAO",
  "RECURSO_APELACAO",
  "AGRAVO",
  "MANDADO_SEGURANCA",
  "HABEAS_CORPUS",
  "IMPUGNACAO",
  "MEMORIA_CALCULO",
  "OUTROS",
];

const STEPS = [
  { label: "Processo", icon: Scale },
  { label: "Tipo", icon: FileText },
  { label: "Instruções", icon: FileText },
  { label: "Gerando", icon: Loader2 },
  { label: "Revisar", icon: Edit3 },
  { label: "Concluído", icon: CheckCircle },
];

export default function NovaPeticaoPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [processos, setProcessos] = useState<Processo[]>([]);
  const [form, setForm] = useState({
    process_id: "",
    tipo_peticao: "PETICAO_INICIAL",
    instrucoes: "",
  });
  const [runId, setRunId] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [documentoHtml, setDocumentoHtml] = useState<string>("");
  const [documentoId, setDocumentoId] = useState<string | null>(null);

  useEffect(() => {
    fetchProcessos();
  }, []);

  async function fetchProcessos() {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/processes", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setProcessos(await res.json());
  }

  async function gerarPeticao() {
    setStep(3);
    setError(null);
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/documents/petitions/generate", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          process_id: form.process_id || null,
          tipo_peticao: form.tipo_peticao,
          instrucoes: form.instrucoes,
        }),
      });
      if (!res.ok) {
        const err = await res.json();
        setError(err.detail || "Erro ao gerar petição");
        setStep(2);
        return;
      }
      const data = await res.json();
      setRunId(data.run_id);
      pollStatus(data.run_id);
    } catch {
      setError("Erro de conexão");
      setStep(2);
    }
  }

  async function pollStatus(rid: string) {
    const token = localStorage.getItem("afj_access_token");
    let attempts = 0;
    const MAX_ATTEMPTS = 60; // 3 minutos
    const interval = setInterval(async () => {
      if (++attempts > MAX_ATTEMPTS) {
        clearInterval(interval);
        setError("Tempo limite excedido. A geração demorou mais que o esperado. Tente novamente.");
        setStep(2);
        return;
      }
      try {
        const res = await fetch(`/api/v1/agents/runs/${rid}`, {
          headers: { Authorization: `Bearer ${token}` },
        });
        if (res.ok) {
          const run = await res.json();
          setStatus(run.status);
          if (run.status === "AWAITING_APPROVAL" || run.status === "SUCCESS") {
            clearInterval(interval);
            const docId = run.output_data?.document_id as string | undefined;
            if (docId) {
              setDocumentoId(docId);
              try {
                const docRes = await fetch(`/api/v1/documents/${docId}`, {
                  headers: { Authorization: `Bearer ${token}` },
                });
                if (docRes.ok) {
                  const doc = await docRes.json();
                  setDocumentoHtml(doc.conteudo_html || doc.conteudo_texto || "");
                }
              } catch {}
            }
            setStep(4);
          } else if (run.status === "FAILED") {
            clearInterval(interval);
            setError("O agente falhou ao gerar a petição.");
            setStep(2);
          }
        }
      } catch {}
    }, 3000);
  }

  const processoSelecionado = processos.find((p) => p.id === form.process_id);

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* Progress bar */}
      <div>
        <h1 className="font-display text-2xl font-semibold text-afj-black mb-5">Nova Petição com IA</h1>
        <div className="flex items-center gap-0">
          {STEPS.map((s, i) => (
            <div key={i} className="flex items-center flex-1 last:flex-none">
              <div className={`flex items-center gap-2 text-xs font-medium ${i <= step ? "text-afj-gold" : "text-afj-black/30"}`}>
                <div className={`w-7 h-7 rounded-full flex items-center justify-center border-2 ${i < step ? "bg-afj-gold border-afj-gold text-white" : i === step ? "border-afj-gold text-afj-gold" : "border-afj-cream-dark text-afj-black/30"}`}>
                  {i < step ? <CheckCircle size={14} /> : <span>{i + 1}</span>}
                </div>
                <span className="hidden sm:block">{s.label}</span>
              </div>
              {i < STEPS.length - 1 && (
                <div className={`flex-1 h-0.5 mx-2 ${i < step ? "bg-afj-gold" : "bg-afj-cream-dark"}`} />
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="afj-card p-6">
        {/* Step 0: Selecionar processo */}
        {step === 0 && (
          <div className="space-y-4">
            <h2 className="font-semibold text-afj-black">Selecione o Processo</h2>
            <p className="text-sm text-afj-black/50">Associe a petição a um processo ou gere sem vínculo.</p>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Processo (opcional)</label>
              <select
                value={form.process_id}
                onChange={(e) => setForm({ ...form, process_id: e.target.value })}
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold"
              >
                <option value="">Sem processo vinculado</option>
                {processos.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.numero_cnj || "Sem CNJ"} — {p.tribunal} {p.area_direito ? `(${p.area_direito})` : ""}
                  </option>
                ))}
              </select>
            </div>
            {processoSelecionado && (
              <div className="bg-afj-cream rounded-md p-3 text-sm">
                <p className="font-medium text-afj-black">{processoSelecionado.numero_cnj || "Sem CNJ"}</p>
                <p className="text-afj-black/50 text-xs">{processoSelecionado.tribunal} · {processoSelecionado.area_direito || "Área não definida"}</p>
              </div>
            )}
          </div>
        )}

        {/* Step 1: Tipo de petição */}
        {step === 1 && (
          <div className="space-y-4">
            <h2 className="font-semibold text-afj-black">Tipo de Petição</h2>
            <p className="text-sm text-afj-black/50">Selecione o tipo de peça jurídica a ser gerada.</p>
            <div className="grid grid-cols-2 gap-2">
              {TIPOS_PETICAO.map((tipo) => (
                <button
                  key={tipo}
                  onClick={() => setForm({ ...form, tipo_peticao: tipo })}
                  className={`p-3 text-left rounded-md border text-sm transition-colors ${
                    form.tipo_peticao === tipo
                      ? "border-afj-gold bg-afj-gold/5 text-afj-gold font-medium"
                      : "border-afj-cream-dark hover:border-afj-gold/50 text-afj-black"
                  }`}
                >
                  {tipo.replace(/_/g, " ")}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 2: Instruções */}
        {step === 2 && (
          <div className="space-y-4">
            <h2 className="font-semibold text-afj-black">Instruções para o Agente</h2>
            <p className="text-sm text-afj-black/50">
              Descreva o que você precisa. Quanto mais contexto, melhor a petição gerada.
            </p>
            <div>
              <label className="text-xs text-afj-black/60 block mb-1">Instruções específicas</label>
              <textarea
                value={form.instrucoes}
                onChange={(e) => setForm({ ...form, instrucoes: e.target.value })}
                rows={8}
                placeholder="Ex: Recurso de Apelação em face da sentença que julgou improcedente o pedido. O autor é trabalhador demitido sem justa causa. Principais argumentos: horas extras não pagas, adicional noturno não computado, FGTS com saldo insuficiente. A sentença desconsiderou os cartões ponto apresentados como prova..."
                className="w-full border border-afj-cream-dark rounded-md px-3 py-2 text-sm focus:outline-none focus:border-afj-gold resize-none"
              />
            </div>
            {error && (
              <div className="bg-red-50 border border-red-200 rounded-md p-3 text-sm text-red-700">
                {error}
              </div>
            )}
            <div className="bg-amber-50 border border-amber-200 rounded-md p-3 text-xs text-amber-800">
              <strong>Atenção:</strong> O agente utilizará APENAS jurisprudência verificada nas bases do escritório.
              Citações não confirmadas serão marcadas como [NÃO VERIFICADO] e bloquearão a aprovação automática.
            </div>
          </div>
        )}

        {/* Step 3: Gerando */}
        {step === 3 && (
          <div className="py-8 text-center space-y-4">
            <Loader2 className="mx-auto animate-spin text-afj-gold" size={40} />
            <p className="font-semibold text-afj-black">Agente trabalhando...</p>
            <div className="space-y-1 text-sm text-afj-black/50">
              <p>1. Buscando jurisprudência relevante na base vetorial</p>
              <p>2. Recuperando petições similares do escritório</p>
              <p>3. Consultando legislação aplicável</p>
              <p>4. Redigindo petição com Claude</p>
              <p>5. Validando citações e referências</p>
            </div>
            {runId && (
              <p className="text-xs text-afj-black/30 font-mono">run_id: {runId}</p>
            )}
          </div>
        )}

        {/* Step 4: Revisar */}
        {step === 4 && (
          <div className="space-y-4">
            <div>
              <h2 className="font-semibold text-afj-black">Revisar Petição Gerada</h2>
              <p className="text-sm text-afj-black/50 mt-0.5">
                Revise o conteúdo gerado. Campos em vermelho indicam informações a completar.
              </p>
            </div>
            {documentoHtml ? (
              <PetitionEditor
                initialContent={documentoHtml}
                onChange={setDocumentoHtml}
              />
            ) : (
              <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 text-center">
                <p className="text-sm text-amber-800 font-medium">Petição enviada para aprovação</p>
                <p className="text-xs text-amber-700 mt-1">
                  O conteúdo detalhado estará disponível na fila de aprovações.
                </p>
              </div>
            )}
            <div className="flex gap-3 pt-2">
              <button
                onClick={() => setStep(5)}
                className="flex-1 btn-afj-primary rounded-md flex items-center justify-center gap-2"
              >
                <CheckCircle size={14} />
                Confirmar e Ir para Aprovações
              </button>
            </div>
          </div>
        )}

        {/* Step 5: Concluído */}
        {step === 5 && (
          <div className="py-8 text-center space-y-4">
            <CheckCircle className="mx-auto text-green-500" size={40} />
            <p className="font-semibold text-afj-black text-lg">Petição Gerada!</p>
            {status === "AWAITING_APPROVAL" ? (
              <>
                <p className="text-sm text-afj-black/60">
                  A petição foi gerada e está aguardando sua aprovação na fila de aprovações.
                </p>
                <div className="flex gap-3 justify-center">
                  <button
                    onClick={() => router.push("/aprovacoes")}
                    className="btn-afj-primary rounded-md flex items-center gap-2"
                  >
                    <CheckCircle size={14} />
                    Ver Aprovações Pendentes
                  </button>
                  <button onClick={() => router.push("/peticoes")} className="btn-afj-outline rounded-md">
                    Ver Petições
                  </button>
                </div>
              </>
            ) : (
              <div className="flex gap-3 justify-center">
                <button onClick={() => router.push("/peticoes")} className="btn-afj-primary rounded-md">
                  Ver Petições
                </button>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Navigation */}
      {step < 3 && step !== 4 && (
        <div className="flex gap-3 justify-between">
          <button
            onClick={() => step > 0 && setStep(step - 1)}
            disabled={step === 0}
            className="btn-afj-outline rounded-md flex items-center gap-2 disabled:opacity-40"
          >
            <ChevronLeft size={14} />
            Anterior
          </button>
          {step < 2 ? (
            <button
              onClick={() => setStep(step + 1)}
              className="btn-afj-primary rounded-md flex items-center gap-2"
            >
              Próximo
              <ChevronRight size={14} />
            </button>
          ) : (
            <button
              onClick={gerarPeticao}
              disabled={!form.instrucoes.trim()}
              className="btn-afj-primary rounded-md flex items-center gap-2 disabled:opacity-40"
            >
              <Send size={14} />
              Gerar Petição com IA
            </button>
          )}
        </div>
      )}
    </div>
  );
}
