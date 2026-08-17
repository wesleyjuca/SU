"use client";
// Fase 196 — sincronizado com o código até a Fase 196 (ver git log). Esta
// página é 100% estática (nenhum fetch — tudo nos arrays abaixo); ficou
// congelada na Fase 92 por ~80 fases até esta sincronização. Ao entregar
// uma fase que mude recurso visível ao usuário, atualize os arrays abaixo
// E o marcador "Atualizado até a Fase N" no cabeçalho — é o que evita essa
// página ficar defasada de novo sem ninguém perceber.
import {
  Compass, CheckCircle2, Wrench, Clock, Lightbulb, Scale, Bot, DollarSign,
  Users, BookOpen, Shield, Shapes, FileText, KeyRound, CheckSquare, UserCircle,
  BarChart2, Sparkles, ScanLine, AlertTriangle, Workflow,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

type Estado = "operacional" | "parcial" | "planejado";

const ESTADO_CFG: Record<Estado, { label: string; cls: string; icon: React.ElementType }> = {
  operacional: { label: "Em operação", cls: "bg-green-50 text-green-700 border-green-200", icon: CheckCircle2 },
  parcial: { label: "Em evolução", cls: "bg-amber-50 text-amber-700 border-amber-200", icon: Wrench },
  planejado: { label: "Planejado", cls: "bg-gray-50 text-gray-500 border-gray-200", icon: Clock },
};

type Recurso = { icon: React.ElementType; nome: string; desc: string; estado: Estado };

const AREAS: { titulo: string; recursos: Recurso[] }[] = [
  {
    titulo: "Jurídico",
    recursos: [
      { icon: Scale, nome: "Processos & Prazos", desc: "Cadastro, captura por OAB (Comunica), andamentos reais do DataJud com aviso à equipe e sinal de \"possível prazo\", alertas e cálculo automático de prazo (dias úteis, recesso e feriados forenses locais); lançamento direto da Agenda.", estado: "operacional" },
      { icon: Scale, nome: "Equipe por Processo & Minha Área", desc: "Cada processo tem um responsável e colaboradores; intimações notificam a equipe toda. O filtro \"Meus\" em Processos/Agenda/Publicações e a página Minha Área mostram só o que é seu.", estado: "operacional" },
      { icon: BookOpen, nome: "Publicações & Intimações (DJe)", desc: "Monitoramento automático do Diário de Justiça Eletrônico (DJEN/Comunica) pelas OABs do escritório: cada intimação vira andamento no processo e notifica o responsável; a triagem confirma tipo e dias e gera o prazo.", estado: "operacional" },
      { icon: FileText, nome: "Petições & Contratos", desc: "Geração com IA, editor, versionamento, PDF e ciclo de vida (arquivar/excluir).", estado: "operacional" },
      { icon: BookOpen, nome: "Pesquisa Jurídica (RAG)", desc: "Busca semântica em jurisprudência (inclusive sincronização automática do STJ via dados abertos, com favorabilidade de precedentes por relator), legislação federal (LexML), doutrina privada do escritório (sincronizada do Google Drive), memórias e petições aprovadas/documentos digitalizados (OCR) — ADMIN também pode indexar manualmente, com cobertura por base visível na busca.", estado: "parcial" },
      { icon: FileText, nome: "Modelos de Petição", desc: "Biblioteca de modelos reutilizados pela IA — importe do Word (.docx), edite no app ou baixe para editar no Word.", estado: "operacional" },
      { icon: ScanLine, nome: "Digitalização & OCR", desc: "PDFs e imagens enviados são digitalizados automaticamente: o texto é extraído em segundo plano, fica pesquisável e pode ser conferido na hora.", estado: "operacional" },
      { icon: Shapes, nome: "Visual Law", desc: "Fluxogramas e linhas do tempo jurídicas geradas por IA.", estado: "operacional" },
    ],
  },
  {
    titulo: "Inteligência Artificial",
    recursos: [
      { icon: Bot, nome: "19 Agentes + Orquestrador", desc: "Agentes especializados coordenados via LangGraph, com cancelamento de execução e agentes customizados sob demanda (ADMIN propõe, SUPERADMIN aprova).", estado: "operacional" },
      { icon: Workflow, nome: "Encadeamento de Agentes (Chains)", desc: "Fluxos automáticos que rodam vários agentes em sequência (ex.: entrada de processo → jurisprudência → estratégia → CRM), passando o resultado de um pro próximo — retoma sozinho de onde parou depois de uma aprovação humana, mesmo quando a cadeia tem mais de um ponto de aprovação.", estado: "operacional" },
      { icon: KeyRound, nome: "BYOK (Minha IA)", desc: "Traga sua própria chave — 7 provedores suportados (Claude, GPT, Gemini e outros) —, com balanceamento automático de custo entre chave própria e do sistema, estatísticas de uso e modelo ajustável por área de trabalho.", estado: "operacional" },
      { icon: CheckSquare, nome: "Aprovações (HITL)", desc: "Ações críticas exigem decisão humana antes de executar; aprovar retoma automaticamente o restante de um fluxo encadeado.", estado: "operacional" },
    ],
  },
  {
    titulo: "Gestão & Relacionamento",
    recursos: [
      { icon: DollarSign, nome: "Financeiro", desc: "Receitas, despesas, honorários, inadimplência e faturas a cliente (PDF timbrado) — isolado por escritório.", estado: "operacional" },
      { icon: Users, nome: "Clientes (CRM) & LGPD", desc: "Gestão de clientes/leads, funil de vendas (forecast), ficha 360° com financeiro do cliente e controle de consentimento.", estado: "operacional" },
      { icon: BarChart2, nome: "Relatórios", desc: "Gráficos de processos, financeiro, agentes e gestão do sócio (rentabilidade por cliente, produtividade e taxa de êxito).", estado: "operacional" },
      { icon: BarChart2, nome: "Painel TV (recepção)", desc: "Modo quiosque para Smart TV: KPIs, relógio e prazos próximos em fonte grande, com atualização automática — ideal para a recepção ou a sala da equipe.", estado: "operacional" },
      { icon: DollarSign, nome: "Custos de IA por Usuário", desc: "Consumo por advogado com teto mensal configurável, alertas e bloqueio suave.", estado: "operacional" },
      { icon: UserCircle, nome: "Portal do Cliente", desc: "Acesso externo com mensagens ao escritório, download de PDFs timbrados e isolamento duplo.", estado: "operacional" },
    ],
  },
  {
    titulo: "Plataforma & Segurança",
    recursos: [
      { icon: Shield, nome: "Multi-tenant & Auditoria", desc: "Isolamento total entre escritórios, log imutável de ações e CPF/CNPJ criptografado em repouso. Planos por escritório (STANDARD/PRO/ENTERPRISE) — o escritório dono da plataforma sempre opera no plano Máximo, isento de cobrança, com essa garantia restaurada automaticamente mesmo se alterada por engano.", estado: "operacional" },
      { icon: Sparkles, nome: "Cérebro (SuperAdmin)", desc: "Painel exclusivo do dono da plataforma: mapa vivo de módulos em camadas concêntricas, integrações e infraestrutura (Celery, Redis, Qdrant, Postgres) em tempo real, insights proativos por IA (a própria plataforma analisa saúde, riscos e sugere evolução), assistente de IA com RAG da documentação e conversa por voz — todo acesso autenticado, autorizado e auditado.", estado: "operacional" },
      { icon: KeyRound, nome: "Autenticação JWT", desc: "Tokens de acesso/refresh com sessões estáveis.", estado: "operacional" },
      { icon: Shield, nome: "Ética, Controle & Integridade", desc: "Código de Conduta com aceite registrado, Canal de Denúncias anônimo e controles técnicos ativos (HITL, auditoria, LGPD).", estado: "operacional" },
      { icon: Sparkles, nome: "App Instalável (PWA)", desc: "Manifest e service worker publicados; offline ampliado e push em evolução.", estado: "parcial" },
      { icon: Sparkles, nome: "Google Workspace", desc: "Agenda, Drive e Gmail integrados via OAuth: prazos confirmados sincronizam automaticamente com sua Agenda, e-mails do sistema saem pela sua conta Gmail quando conectada — conecte em Integrações.", estado: "operacional" },
      { icon: Clock, nome: "Integrações Externas", desc: "Hub \"Conectar conta\" pronto (Stripe, Mercado Pago, Clicksign, WhatsApp) com credenciais cifradas por escritório — recursos ativam nas fases de cada provedor.", estado: "parcial" },
    ],
  },
];

const ROADMAP: { fase: string; itens: string; estado: Estado }[] = [
  { fase: "Fundação", itens: "Auth, Processos, Clientes, Agenda", estado: "operacional" },
  { fase: "IA Core", itens: "Agentes, Petições, RAG, Aprovações", estado: "operacional" },
  { fase: "Financeiro", itens: "Dashboard, gráficos, contratos", estado: "operacional" },
  { fase: "Admin SaaS", itens: "Saúde, personalização, usuários, plano & uso, revisão de acessos", estado: "operacional" },
  { fase: "Portal do Cliente", itens: "Acesso externo, mensagens, documentos PDF (WhatsApp aguarda credenciais)", estado: "operacional" },
  { fase: "Ética, Controle & Integridade", itens: "Controles ativos + código de conduta, canal de denúncias, treinamentos", estado: "parcial" },
  { fase: "Monitoramento de Publicações (DJe)", itens: "Captura automática de intimações (Comunica/DJEN) por OAB → andamento + notificação; prazo por triagem", estado: "operacional" },
  { fase: "Equipe por processo + Minha Área", itens: "Responsável + colaboradores por processo; filtro \"Meus\" em Processos/Agenda/Publicações; painel pessoal do advogado", estado: "operacional" },
  { fase: "OABs do escritório + planos + filiais", itens: "OABs dos sócios na varredura DJe e captura em massa; limites reais por plano (STANDARD/PRO/ENTERPRISE); filiais self-serve no ENTERPRISE", estado: "operacional" },
  { fase: "Reatribuição de carteira", itens: "Transferir processos e prazos de um advogado para outro (saída/licença), com prévia da carteira e opção de incluir colaborações", estado: "operacional" },
  { fase: "Distribuição de carga", itens: "Painel de carga por advogado no relatório de gestão (processos ativos + prazos pendentes) para equilibrar o trabalho da equipe", estado: "operacional" },
  { fase: "Modo confidencial", itens: "Interruptor por escritório: advogados veem só os processos da sua equipe; sócios/gestão mantêm a visão total. Aplica em Processos, Agenda, Publicações e detalhe", estado: "operacional" },
  { fase: "Captura por OAB (Comunica/DJEN)", itens: "Captura de processos pelas OABs do escritório via fonte pública (sem credenciais); liga o processo ao advogado dono da OAB. Painel TV abre em nova janela", estado: "operacional" },
  { fase: "CRUD de Documentos", itens: "Criar documento manual, editar (título, tipo, status, conteúdo) e arquivar direto na tela de Documentos; diagnóstico claro na captura por OAB (fonte inalcançável × sem publicações)", estado: "operacional" },
  { fase: "Histórico de versões de documentos", itens: "Cada edição guarda a versão anterior; a tela de Documentos mostra o histórico e permite restaurar qualquer versão", estado: "operacional" },
  { fase: "DataJud: enriquecimento + andamentos", itens: "Processos capturados são enriquecidos por número (classe, assunto, órgão) e trazem andamentos reais do DataJud; botão \"Atualizar andamentos\" no processo. Busca por OAB é via Comunica (DataJud público não indexa partes)", estado: "operacional" },
  { fase: "Aviso de novos andamentos", itens: "Quando o monitoramento traz um andamento novo (automático a cada 30 min ou manual), o responsável e a equipe do processo são notificados; polling em lote sem custo de IA por padrão", estado: "operacional" },
  { fase: "Possível prazo no andamento", itens: "Andamentos que provavelmente iniciam um prazo (intimação, despacho) recebem um selo e um botão \"Gerar prazo\" que abre a calculadora (CPC art. 219) pré-preenchida — anti-perda-de-prazo com confirmação humana", estado: "operacional" },
  { fase: "Segurança & Produção", itens: "Papéis/HITL blindados, worker em produção, tempo-real, CI com gates", estado: "operacional" },
  { fase: "Mobile / PWA / App nativo", itens: "PWA instalável e offline; base Capacitor pronta para publicar Android/iOS", estado: "operacional" },
  { fase: "Integrações Externas", itens: "Hub de conexão pronto (credenciais cifradas por escritório); pagamento, assinatura e WhatsApp ativam com a conta do provedor", estado: "parcial" },
  { fase: "Multi-unidade & SaaS", itens: "P1+P2 entregues (isolamento, provisionamento, cobrança manual) · P3 em curso: relatórios consolidados da banca com exportação PDF/Excel/CSV entregues; gateway de pagamento e subdomínios seguem", estado: "parcial" },
  { fase: "IA multi-provedor & orçamento", itens: "7 provedores de IA suportados (BYOK), balanceamento automático entre chave própria e do sistema, estatísticas de uso e teto de custo por usuário", estado: "operacional" },
  { fase: "Base de conhecimento jurídica expandida", itens: "Jurisprudência do STJ (dados abertos) com favorabilidade por relator, legislação federal (LexML) e doutrina privada do escritório (Google Drive) somam-se à busca semântica", estado: "operacional" },
  { fase: "Agentes de IA customizados", itens: "ADMIN propõe um agente sob medida, SUPERADMIN aprova; execução com barreira de custo e RAG opcional", estado: "operacional" },
  { fase: "Armazenamento de documentos em nuvem", itens: "Documentos e timbrado do escritório migram de base64-no-banco pra object storage S3-compatível", estado: "operacional" },
  { fase: "Encadeamento automático de agentes", itens: "Fluxos multi-agente (chains) com retomada automática após aprovação humana, inclusive com mais de um ponto de aprovação na mesma cadeia", estado: "operacional" },
  { fase: "Plano exclusivo da plataforma", itens: "O escritório dono da plataforma sempre opera no plano Máximo, isento de cobrança, com garantia automática contra alteração acidental", estado: "operacional" },
  { fase: "Endurecimento de segurança & desempenho", itens: "Criptografia de CPF/CNPJ, correções de isolamento entre escritórios, paginação real (documentos/financeiro/CRM/auditoria) e monitoramento de erros em produção", estado: "operacional" },
];

const PENDENCIAS: { titulo: string; desc: string }[] = [
  { titulo: "Retenção dos logs de auditoria (LGPD)", desc: "O log de auditoria é imutável e cresce sem limite — o prazo de expurgo/arquivamento ainda depende de orientação jurídica do escritório antes de ser implementado." },
];

const SUGESTOES: { titulo: string; desc: string }[] = [
  { titulo: "Protocolo automático nos tribunais (PJe)", desc: "Protocolar petições aprovadas diretamente nos sistemas dos tribunais, com comprovante anexado ao processo." },
  { titulo: "Transcrição de audiências com IA", desc: "Upload do áudio da audiência com transcrição, resumo e extração de compromissos/prazos." },
  { titulo: "Chat jurídico interno (RAG)", desc: "Assistente conversacional que responde com base nas petições, memórias e documentos do escritório." },
];

function EstadoBadge({ estado }: { estado: Estado }) {
  const cfg = ESTADO_CFG[estado];
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-sm border ${cfg.cls}`}>
      <Icon size={11} /> {cfg.label}
    </span>
  );
}

export default function SobrePage() {
  const totalRecursos = AREAS.reduce((n, a) => n + a.recursos.length, 0);
  const operacionais = AREAS.reduce((n, a) => n + a.recursos.filter((r) => r.estado === "operacional").length, 0);

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Visão Geral" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <Compass size={22} className="text-afj-gold" /> Visão Geral do Sistema
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Tudo que o AFJ CORE oferece — o que já está em operação, o que está em evolução e o que vem a seguir.
          </p>
          <p className="text-afj-black/30 text-xs mt-1">Atualizado até a Fase 196.</p>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { n: "19", l: "Agentes especializados" },
          { n: String(totalRecursos), l: "Áreas de recurso" },
          { n: `${operacionais}`, l: "Em operação" },
          { n: "100%", l: "Isolamento multi-tenant" },
        ].map((k) => (
          <div key={k.l} className="afj-stat-card">
            <p className="text-2xl font-bold text-afj-black font-display">{k.n}</p>
            <p className="text-xs text-afj-black/50 mt-0.5">{k.l}</p>
          </div>
        ))}
      </div>

      {/* Recursos por área */}
      {AREAS.map((area) => (
        <div key={area.titulo}>
          <h2 className="afj-section-header">{area.titulo}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
            {area.recursos.map((r) => {
              const Icon = r.icon;
              return (
                <div key={r.nome} className="afj-card p-4 flex gap-3">
                  <span className="w-9 h-9 rounded-sm bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
                    <Icon size={17} className="text-afj-gold" />
                  </span>
                  <div className="min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-semibold text-afj-black text-sm">{r.nome}</span>
                      <EstadoBadge estado={r.estado} />
                    </div>
                    <p className="text-xs text-afj-black/55 mt-1 leading-relaxed">{r.desc}</p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      ))}

      {/* Roadmap */}
      <div>
        <h2 className="afj-section-header">Roadmap</h2>
        <div className="afj-card p-5 mt-3 space-y-3">
          {ROADMAP.map((f, i) => {
            const cfg = ESTADO_CFG[f.estado];
            const Icon = cfg.icon;
            return (
              <div key={i} className="flex items-start gap-3">
                <span className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 ${
                  f.estado === "operacional" ? "bg-green-500 text-white"
                  : f.estado === "parcial" ? "bg-afj-gold text-white" : "bg-afj-cream-dark text-afj-black/40"
                }`}>
                  <Icon size={12} />
                </span>
                <div>
                  <p className="text-sm font-medium text-afj-black">{f.fase}</p>
                  <p className="text-xs text-afj-black/45">{f.itens}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* O que falta — lacunas conhecidas em recursos que já existem, separado
          de "Sugestões" (que são ideias de recurso novo) de propósito. */}
      <div>
        <h2 className="afj-section-header flex items-center gap-2">
          <AlertTriangle size={16} className="text-amber-600" /> O que falta / débito técnico conhecido
        </h2>
        <p className="text-xs text-afj-black/45 mt-1 mb-3">
          Lacunas já identificadas em recursos que existem hoje — não são bugs escondidos, são limites conhecidos e documentados.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {PENDENCIAS.map((p) => (
            <div key={p.titulo} className="afj-card p-4 border-l-2 border-amber-400/50">
              <p className="font-semibold text-afj-black text-sm flex items-center gap-1.5">
                <AlertTriangle size={13} className="text-amber-600" /> {p.titulo}
              </p>
              <p className="text-xs text-afj-black/55 mt-1 leading-relaxed">{p.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Sugestões */}
      <div>
        <h2 className="afj-section-header flex items-center gap-2">
          <Lightbulb size={16} className="text-afj-gold" /> Sugestões de novos recursos
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-3">
          {SUGESTOES.map((s) => (
            <div key={s.titulo} className="afj-card p-4 border-l-2 border-afj-gold/40">
              <p className="font-semibold text-afj-black text-sm flex items-center gap-1.5">
                <Sparkles size={13} className="text-afj-gold" /> {s.titulo}
              </p>
              <p className="text-xs text-afj-black/55 mt-1 leading-relaxed">{s.desc}</p>
            </div>
          ))}
        </div>
        <p className="text-[11px] text-afj-black/35 mt-3 text-center">
          Tem uma ideia? Fale com o administrador do escritório para priorizá-la no roadmap.
        </p>
      </div>
    </div>
  );
}
