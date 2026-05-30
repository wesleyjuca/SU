"use client";
import { useState } from "react";
import { Scale, CheckCircle, ChevronRight, X, Calendar, Bot, DollarSign, Users, FileEdit } from "lucide-react";

const TRIBUNAIS = ["TJSP", "TJRJ", "TJMG", "TJRS", "STJ", "STF", "TRT", "TRF", "TST", "TSE", "Outro"];

const MODULOS = [
  { id: "peticoes", label: "Petições IA", icon: <FileEdit size={16} />, desc: "Gerar petições automaticamente" },
  { id: "monitoramento", label: "Monitoramento", icon: <Scale size={16} />, desc: "Alertas de andamentos processuais" },
  { id: "financeiro", label: "Financeiro", icon: <DollarSign size={16} />, desc: "Controle de receitas e despesas" },
  { id: "crm", label: "CRM Clientes", icon: <Users size={16} />, desc: "Histórico e contatos de clientes" },
  { id: "prazos", label: "Agenda de Prazos", icon: <Calendar size={16} />, desc: "Controle de datas e prazos fatais" },
  { id: "agentes", label: "Agentes IA", icon: <Bot size={16} />, desc: "Automações com inteligência artificial" },
];

interface OnboardingWizardProps {
  onComplete: () => void;
}

export function OnboardingWizard({ onComplete }: OnboardingWizardProps) {
  const [step, setStep] = useState(1);
  const [tribunal, setTribunal] = useState("TJSP");
  const [vara, setVara] = useState("");
  const [cnj, setCnj] = useState("");
  const [cnjTribunal, setCnjTribunal] = useState("");
  const [modulos, setModulos] = useState<string[]>(["peticoes", "monitoramento", "prazos"]);
  const [saving, setSaving] = useState(false);

  const TOTAL_STEPS = 5;
  const progress = ((step - 1) / (TOTAL_STEPS - 1)) * 100;

  function toggleModulo(id: string) {
    setModulos((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    );
  }

  async function handleProcesso() {
    if (!cnj.trim()) {
      setStep(4);
      return;
    }
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      await fetch("/api/v1/processes", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ numero_cnj: cnj, tribunal: cnjTribunal || tribunal }),
      });
    } catch {
      // Non-blocking — continue onboarding
    } finally {
      setSaving(false);
      setStep(4);
    }
  }

  function finish() {
    localStorage.setItem("afj_onboarded", "1");
    localStorage.setItem("afj_pref_tribunal", tribunal);
    localStorage.setItem("afj_pref_modulos", JSON.stringify(modulos));
    onComplete();
  }

  return (
    <div className="fixed inset-0 bg-afj-navy/80 z-50 flex items-center justify-center p-4 backdrop-blur-sm">
      <div className="bg-white rounded-sm shadow-2xl w-full max-w-lg animate-fade-in">
        {/* Progress bar */}
        <div className="h-1 bg-afj-cream-dark rounded-t-sm overflow-hidden">
          <div
            className="h-full bg-afj-gold transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-afj-cream-dark">
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 text-afj-gold">
              <svg viewBox="0 0 80 80" fill="currentColor">
                <rect x="2" y="2" width="76" height="76" fill="none" stroke="currentColor" strokeWidth="3.5"/>
                <rect x="10" y="10" width="6" height="60"/>
                <rect x="29" y="10" width="6" height="60"/>
                <rect x="10" y="37" width="25" height="5"/>
                <rect x="43" y="10" width="6" height="42"/>
                <rect x="43" y="10" width="25" height="5"/>
                <rect x="43" y="27" width="19" height="5"/>
                <rect x="62" y="10" width="6" height="46"/>
                <path d="M68,56 Q68,70 55,70 Q49,70 49,63" fill="none" stroke="currentColor" strokeWidth="6" strokeLinecap="round"/>
              </svg>
            </div>
            <span className="text-xs font-bold tracking-widest uppercase text-afj-black/50">
              Configuração Inicial
            </span>
          </div>
          <span className="text-xs text-afj-black/30">{step}/{TOTAL_STEPS}</span>
        </div>

        {/* Content */}
        <div className="px-6 py-6 min-h-[280px]">
          {/* Step 1: Welcome */}
          {step === 1 && (
            <div className="text-center space-y-4">
              <div className="w-16 h-16 bg-afj-gold/10 rounded-full flex items-center justify-center mx-auto">
                <Scale size={28} className="text-afj-gold" />
              </div>
              <h2 className="font-display text-xl font-semibold text-afj-black">
                Bem-vindo ao AFJ CORE
              </h2>
              <p className="text-afj-black/60 text-sm leading-relaxed">
                Sistema Jurídico com Inteligência Artificial para{" "}
                <span className="font-semibold text-afj-black">Almeida, Freire & Jucá Advogados</span>.
                Vamos configurar o sistema em 4 passos rápidos.
              </p>
              <div className="grid grid-cols-3 gap-3 pt-2">
                {["19 Agentes IA", "Monitoramento 24h", "Relatórios Automáticos"].map((f) => (
                  <div key={f} className="afj-card p-3 text-center">
                    <p className="text-xs font-medium text-afj-black/70">{f}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Step 2: Tribunal */}
          {step === 2 && (
            <div className="space-y-4">
              <div>
                <h2 className="font-semibold text-afj-black text-lg">Tribunal Principal</h2>
                <p className="text-afj-black/50 text-sm mt-1">
                  Qual tribunal você monitora com mais frequência?
                </p>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1.5">Tribunal</label>
                <select
                  value={tribunal}
                  onChange={(e) => setTribunal(e.target.value)}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm focus:outline-none focus:border-afj-gold"
                >
                  {TRIBUNAIS.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1.5">Vara / Juízo (opcional)</label>
                <input
                  type="text"
                  value={vara}
                  onChange={(e) => setVara(e.target.value)}
                  placeholder="Ex: 3ª Vara Cível de São Paulo"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm focus:outline-none focus:border-afj-gold"
                />
              </div>
            </div>
          )}

          {/* Step 3: First Process */}
          {step === 3 && (
            <div className="space-y-4">
              <div>
                <h2 className="font-semibold text-afj-black text-lg">Primeiro Processo</h2>
                <p className="text-afj-black/50 text-sm mt-1">
                  Adicione um processo para iniciar o monitoramento automático. Você pode pular e adicionar depois.
                </p>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1.5">Número CNJ</label>
                <input
                  type="text"
                  value={cnj}
                  onChange={(e) => setCnj(e.target.value)}
                  placeholder="0000000-00.0000.0.00.0000"
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm focus:outline-none focus:border-afj-gold font-mono"
                />
                <p className="text-xs text-afj-black/30 mt-1">Formato: 7 dígitos - 2.4.1.2.4</p>
              </div>
              <div>
                <label className="text-xs text-afj-black/60 block mb-1.5">Tribunal</label>
                <select
                  value={cnjTribunal || tribunal}
                  onChange={(e) => setCnjTribunal(e.target.value)}
                  className="w-full border border-afj-cream-dark rounded-sm px-3 py-2.5 text-sm focus:outline-none focus:border-afj-gold"
                >
                  {TRIBUNAIS.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </div>
            </div>
          )}

          {/* Step 4: Modules */}
          {step === 4 && (
            <div className="space-y-4">
              <div>
                <h2 className="font-semibold text-afj-black text-lg">Módulos de Trabalho</h2>
                <p className="text-afj-black/50 text-sm mt-1">
                  Selecione quais módulos você usa no dia a dia.
                </p>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {MODULOS.map((m) => {
                  const active = modulos.includes(m.id);
                  return (
                    <button
                      key={m.id}
                      type="button"
                      onClick={() => toggleModulo(m.id)}
                      className={`flex items-start gap-2.5 p-3 rounded-sm border text-left transition-colors ${
                        active
                          ? "border-afj-gold bg-afj-gold/5"
                          : "border-afj-cream-dark hover:border-afj-gold/40"
                      }`}
                    >
                      <span className={active ? "text-afj-gold mt-0.5" : "text-afj-black/30 mt-0.5"}>
                        {m.icon}
                      </span>
                      <div>
                        <p className={`text-xs font-semibold ${active ? "text-afj-black" : "text-afj-black/60"}`}>
                          {m.label}
                        </p>
                        <p className="text-[10px] text-afj-black/40 mt-0.5">{m.desc}</p>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Step 5: Done */}
          {step === 5 && (
            <div className="text-center space-y-4">
              <div className="w-16 h-16 bg-green-50 rounded-full flex items-center justify-center mx-auto">
                <CheckCircle size={32} className="text-green-500" />
              </div>
              <h2 className="font-display text-xl font-semibold text-afj-black">Tudo pronto!</h2>
              <p className="text-afj-black/60 text-sm leading-relaxed">
                O AFJ CORE está configurado e pronto para uso.
                Os 19 agentes de IA estão monitorando seus processos em tempo real.
              </p>
              <div className="bg-afj-gold/5 border border-afj-gold/20 rounded-sm p-3 text-left">
                <p className="text-xs text-afj-black/70">
                  <span className="font-semibold text-afj-black">Tribunal:</span> {tribunal}
                  {vara && <> · {vara}</>}
                </p>
                {cnj && (
                  <p className="text-xs text-afj-black/70 mt-1">
                    <span className="font-semibold text-afj-black">Processo:</span> {cnj}
                  </p>
                )}
                <p className="text-xs text-afj-black/70 mt-1">
                  <span className="font-semibold text-afj-black">Módulos:</span>{" "}
                  {modulos.map((id) => MODULOS.find((m) => m.id === id)?.label).filter(Boolean).join(", ")}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 pb-6 flex gap-3">
          {step > 1 && step < 5 && (
            <button
              type="button"
              onClick={() => setStep((s) => s - 1)}
              className="btn-afj-outline rounded-sm text-sm"
            >
              Voltar
            </button>
          )}

          {step === 1 && (
            <button
              type="button"
              onClick={() => setStep(2)}
              className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2"
            >
              Começar configuração
              <ChevronRight size={15} />
            </button>
          )}

          {step === 2 && (
            <button
              type="button"
              onClick={() => setStep(3)}
              className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2"
            >
              Próximo
              <ChevronRight size={15} />
            </button>
          )}

          {step === 3 && (
            <>
              <button
                type="button"
                onClick={() => setStep(4)}
                className="text-sm text-afj-black/40 hover:text-afj-black px-3"
              >
                Pular
              </button>
              <button
                type="button"
                onClick={handleProcesso}
                disabled={saving}
                className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2 disabled:opacity-40"
              >
                {cnj.trim() ? "Adicionar e continuar" : "Continuar"}
                <ChevronRight size={15} />
              </button>
            </>
          )}

          {step === 4 && (
            <button
              type="button"
              onClick={() => setStep(5)}
              className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2"
            >
              Próximo
              <ChevronRight size={15} />
            </button>
          )}

          {step === 5 && (
            <button
              type="button"
              onClick={finish}
              className="flex-1 btn-afj-primary rounded-sm flex items-center justify-center gap-2"
            >
              <CheckCircle size={15} />
              Ir para o Dashboard
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
