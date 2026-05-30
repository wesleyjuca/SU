"use client";
import Link from "next/link";
import { useState, useEffect } from "react";
import {
  Scale, Bot, Users, FileText, DollarSign, BookOpen,
  ChevronRight, Zap, Lock, Globe, Award, Shield, BarChart2,
} from "lucide-react";

function AfjMonogram({ size = 80 }: { size?: number }) {
  return (
    <svg viewBox="0 0 80 80" width={size} height={size} fill="currentColor" aria-hidden="true">
      <path d="M 4,4 L 76,4 L 76,56 Q 76,78 40,78 Q 4,78 4,56 Z"
            fill="none" stroke="currentColor" strokeWidth="3.5" />
      <rect x="10" y="11" width="7" height="57" />
      <rect x="29" y="11" width="7" height="57" />
      <rect x="10" y="38" width="26" height="6" />
      <rect x="43" y="11" width="7" height="41" />
      <rect x="43" y="11" width="25" height="6" />
      <rect x="43" y="27" width="18" height="6" />
      <rect x="62" y="11" width="7" height="44" />
      <path d="M 69,55 Q 69,68 55,68 Q 49,68 49,62"
            fill="none" stroke="currentColor" strokeWidth="7" strokeLinecap="round" />
    </svg>
  );
}

const FEATURES = [
  { icon: Scale, title: "Gestão de Processos", desc: "Acompanhe todos os processos com monitoramento automático de movimentações e prazos processuais." },
  { icon: Bot, title: "19 Agentes IA", desc: "Agentes especializados em petições, pesquisa jurídica, análise contratual, OCR e muito mais." },
  { icon: Users, title: "CRM Jurídico", desc: "Gestão completa de clientes com histórico de interações, contatos múltiplos e conformidade LGPD." },
  { icon: DollarSign, title: "Financeiro", desc: "Controle de receitas, despesas, honorários e geração de relatórios financeiros com gráficos." },
  { icon: BookOpen, title: "Pesquisa Jurídica", desc: "Busca semântica em jurisprudência, legislação e doutrina via inteligência artificial (RAG)." },
  { icon: FileText, title: "Documentos & Contratos", desc: "Gestão de documentos, contratos e petições com fluxo de aprovação e assinatura digital." },
];

const AREAS = [
  "Direito Civil", "Direito Trabalhista", "Direito Empresarial", "Direito Tributário",
  "Direito Contratual", "Direito Processual", "Direito Imobiliário", "Direito Digital",
];

export default function HomePage() {
  const [scrolled, setScrolled] = useState(false);
  const [metrics, setMetrics] = useState({ processos: "—", agentes: "19", modulos: "12+", uptime: "99.9%" });

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => {
    fetch("/api/v1/system/metrics")
      .then((r) => r.ok ? r.json() : null)
      .then((d) => {
        if (d?.processos_ativos != null) {
          setMetrics((m) => ({ ...m, processos: String(d.processos_ativos) }));
        }
      })
      .catch(() => {});
  }, []);

  return (
    <div className="min-h-screen bg-afj-cream font-sans">
      {/* ─── Header fixo ─────────────────────────────────────────────────────── */}
      <header
        className={`fixed top-0 inset-x-0 z-50 transition-all duration-200 ${
          scrolled
            ? "bg-[#2C3547]/98 backdrop-blur-sm shadow-lg border-b border-white/10"
            : "bg-[#2C3547]/90 backdrop-blur-sm border-b border-white/8"
        }`}
      >
        <div className="max-w-7xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center gap-3 text-afj-gold">
            <AfjMonogram size={32} />
            <div>
              <p className="text-afj-cream text-[11px] font-bold tracking-[0.18em] uppercase font-display">
                AFJ CORE
              </p>
              <p className="text-afj-cream/35 text-[9px] tracking-widest uppercase">
                Sistema Jurídico IA
              </p>
            </div>
          </div>
          <Link
            href="/login"
            className="flex items-center gap-1.5 bg-afj-gold text-white text-xs font-semibold uppercase tracking-wider px-5 py-2.5 rounded-sm hover:bg-afj-gold-dark transition-colors"
          >
            Entrar no Sistema
            <ChevronRight size={12} />
          </Link>
        </div>
      </header>

      {/* ─── Hero ─────────────────────────────────────────────────────────────── */}
      <section
        className="min-h-screen flex items-center pt-16"
        style={{ background: "linear-gradient(135deg, #1A1F2E 0%, #2C3547 50%, #3D4557 100%)" }}
      >
        <div className="max-w-4xl mx-auto px-6 py-28 text-center">
          <div className="text-afj-gold mb-10 flex justify-center animate-fade-in">
            <AfjMonogram size={110} />
          </div>

          <p className="text-afj-gold text-[10px] tracking-[0.45em] uppercase mb-5 font-display animate-fade-in">
            Almeida, Freire &amp; Jucá Advogados
          </p>

          <h1 className="font-display text-4xl md:text-[3.5rem] font-semibold text-afj-cream leading-[1.15] mb-6 animate-fade-in">
            Sistema Jurídico com<br />
            <span className="text-afj-gold">Inteligência Artificial</span>
          </h1>

          <p className="text-afj-cream/55 text-lg mb-10 max-w-2xl mx-auto leading-relaxed animate-fade-in">
            Plataforma completa para gestão de processos, clientes, documentos e petições —
            potencializada por 19 agentes de IA especializados.
          </p>

          <div className="flex flex-col sm:flex-row items-center justify-center gap-4 mb-16 animate-fade-in">
            <Link
              href="/login"
              className="bg-afj-gold text-white text-sm font-semibold uppercase tracking-wider px-10 py-4 rounded-sm hover:bg-afj-gold-dark transition-colors inline-flex items-center gap-2"
            >
              Acessar o Sistema
              <ChevronRight size={14} />
            </Link>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap justify-center gap-x-8 gap-y-3 text-afj-cream/30 text-[10px] tracking-[0.2em] uppercase animate-fade-in">
            {[
              { icon: Lock, label: "Segurança Bancária" },
              { icon: Bot, label: "19 Agentes IA" },
              { icon: Globe, label: "Multi-tenant" },
              { icon: Zap, label: "Tempo Real" },
              { icon: Shield, label: "LGPD Compliance" },
            ].map(({ icon: Icon, label }) => (
              <span key={label} className="flex items-center gap-2">
                <Icon size={11} />
                {label}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Stats ───────────────────────────────────────────────────────────── */}
      <section className="bg-white border-y border-afj-cream-dark py-14">
        <div className="max-w-5xl mx-auto px-6 grid grid-cols-2 lg:grid-cols-4 gap-8 text-center">
          {[
            { label: "Processos Ativos", value: metrics.processos },
            { label: "Agentes IA", value: metrics.agentes },
            { label: "Módulos", value: metrics.modulos },
            { label: "Disponibilidade", value: metrics.uptime },
          ].map((s) => (
            <div key={s.label} className="group">
              <p className="font-display text-4xl font-bold text-afj-black mb-1.5 group-hover:text-afj-gold transition-colors">
                {s.value}
              </p>
              <div className="w-8 h-0.5 bg-afj-gold/30 mx-auto mb-2" />
              <p className="text-afj-black/40 text-[10px] uppercase tracking-widest">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ─── Features ────────────────────────────────────────────────────────── */}
      <section className="py-20 bg-afj-cream">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-14">
            <p className="text-afj-gold text-[10px] tracking-[0.35em] uppercase mb-3 font-display">
              Funcionalidades
            </p>
            <h2 className="font-display text-3xl font-semibold text-afj-black">
              Tudo que seu escritório precisa
            </h2>
            <div className="w-12 h-0.5 bg-gradient-to-r from-transparent via-afj-gold to-transparent mx-auto mt-4" />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="bg-white border border-afj-cream-dark rounded-sm p-6 group hover:border-afj-gold/30 hover:shadow-md transition-all duration-200"
              >
                <div className="w-10 h-10 rounded-sm bg-afj-gold/10 flex items-center justify-center mb-4 group-hover:bg-afj-gold/20 transition-colors">
                  <f.icon size={20} className="text-afj-gold" />
                </div>
                <h3 className="font-semibold text-afj-black mb-2 text-sm">{f.title}</h3>
                <p className="text-afj-black/50 text-sm leading-relaxed">{f.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Áreas de atuação ────────────────────────────────────────────────── */}
      <section className="py-16 bg-white border-t border-afj-cream-dark">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-10">
            <p className="text-afj-gold text-[10px] tracking-[0.35em] uppercase mb-3 font-display">
              Especialização
            </p>
            <h2 className="font-display text-2xl font-semibold text-afj-black">
              Áreas de Atuação
            </h2>
            <div className="w-12 h-0.5 bg-gradient-to-r from-transparent via-afj-gold to-transparent mx-auto mt-4" />
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {AREAS.map((area) => (
              <div
                key={area}
                className="flex items-center gap-2.5 p-3.5 rounded-sm border border-afj-cream-dark bg-afj-cream/50 hover:border-afj-gold/40 hover:bg-white transition-all cursor-default"
              >
                <div className="w-1.5 h-1.5 rounded-full bg-afj-gold flex-shrink-0" />
                <span className="text-sm text-afj-black/70 font-medium">{area}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── Por que AFJ CORE ─────────────────────────────────────────────────── */}
      <section className="py-16 bg-afj-cream border-t border-afj-cream-dark">
        <div className="max-w-6xl mx-auto px-6">
          <div className="text-center mb-12">
            <p className="text-afj-gold text-[10px] tracking-[0.35em] uppercase mb-3 font-display">
              Diferenciais
            </p>
            <h2 className="font-display text-2xl font-semibold text-afj-black">
              Por que AFJ CORE?
            </h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {[
              { icon: Shield, title: "Segurança Total", desc: "Dados criptografados, autenticação JWT, MFA, rate limiting e auditoria completa de acessos." },
              { icon: BarChart2, title: "Analytics Avançado", desc: "Relatórios financeiros, métricas de agentes IA, custo por token e performance dos processos." },
              { icon: Award, title: "Design Premium", desc: "Interface de nível SaaS com tema personalizável, dark mode, PWA e notificações push." },
            ].map((item) => (
              <div key={item.title} className="text-center p-6">
                <div className="w-12 h-12 rounded-full bg-afj-gold/10 flex items-center justify-center mx-auto mb-4">
                  <item.icon size={22} className="text-afj-gold" />
                </div>
                <h3 className="font-semibold text-afj-black mb-2">{item.title}</h3>
                <p className="text-afj-black/50 text-sm leading-relaxed">{item.desc}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ─── CTA Final ───────────────────────────────────────────────────────── */}
      <section
        className="py-24"
        style={{ background: "linear-gradient(135deg, #1A1F2E 0%, #3D4557 100%)" }}
      >
        <div className="max-w-3xl mx-auto px-6 text-center">
          <Award size={40} className="text-afj-gold mx-auto mb-6" />
          <h2 className="font-display text-3xl font-semibold text-afj-cream mb-4">
            Pronto para modernizar seu escritório?
          </h2>
          <p className="text-afj-cream/45 mb-10 text-lg">
            Acesse o sistema e experimente a plataforma jurídica mais completa do Brasil.
          </p>
          <Link
            href="/login"
            className="bg-afj-gold text-white text-sm font-semibold uppercase tracking-wider px-12 py-4 rounded-sm hover:bg-afj-gold-dark transition-colors inline-block"
          >
            Acessar o Sistema
          </Link>
        </div>
      </section>

      {/* ─── Footer ──────────────────────────────────────────────────────────── */}
      <footer className="py-8 border-t border-white/10" style={{ background: "#141821" }}>
        <div className="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-4">
          <div className="flex items-center gap-3 text-afj-gold">
            <AfjMonogram size={24} />
            <div>
              <p className="text-afj-cream text-xs font-semibold tracking-wider uppercase font-display">
                AFJ CORE
              </p>
              <p className="text-afj-cream/25 text-[9px] tracking-widest">Sistema Jurídico IA</p>
            </div>
          </div>
          <p className="text-afj-cream/20 text-xs text-center">
            © 2025 Almeida, Freire &amp; Jucá Advogados · Sistema Interno · Acesso Restrito
          </p>
          <Link href="/login" className="text-afj-cream/35 hover:text-afj-gold text-xs transition-colors">
            Entrar no Sistema →
          </Link>
        </div>
      </footer>
    </div>
  );
}
