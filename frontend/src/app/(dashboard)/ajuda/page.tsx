"use client";
import { useState } from "react";
import {
  GraduationCap, Search, ChevronDown, Scale, CalendarClock, FileEdit, Users,
  FolderOpen, FileText, Bot, KeyRound, CheckSquare, BookOpen, Shapes,
  DollarSign, BarChart2, UserCircle, Sparkles, Lightbulb,
} from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

type Guia = {
  icon: React.ElementType;
  categoria: string;
  titulo: string;
  resumo: string;
  passos: string[];
  dica?: string;
};

const GUIAS: Guia[] = [
  {
    icon: Scale, categoria: "Jurídico", titulo: "Processos",
    resumo: "Cadastre, acompanhe e monitore processos judiciais com captura automática de andamentos.",
    passos: [
      "Menu → Processos. A lista mostra situação, área e o próximo prazo (com destaque de cor para prazos próximos ou vencidos).",
      "Clique em “Novo Processo” para cadastrar manualmente, informando número CNJ, tribunal, área e cliente.",
      "Para captura em massa, use “Buscar por OAB”: informe OAB + UF e o sistema importa os processos vinculados.",
      "Clique no lápis para editar; na lixeira para excluir. Ative o monitoramento para receber alertas de novos andamentos.",
    ],
    dica: "Prazos em vermelho estão vencidos ou a menos de 3 dias — priorize-os na Agenda.",
  },
  {
    icon: CalendarClock, categoria: "Jurídico", titulo: "Agenda & Prazos",
    resumo: "Visualize compromissos e prazos processuais em um só lugar.",
    passos: [
      "Menu → Agenda. Os prazos vêm dos processos monitorados e de lançamentos manuais.",
      "Marque um prazo como cumprido para removê-lo da lista de pendências.",
      "Prazos fatais recebem destaque — não deixe passar.",
    ],
  },
  {
    icon: FileEdit, categoria: "Jurídico", titulo: "Petições",
    resumo: "Gere petições com IA e edite antes de protocolar.",
    passos: [
      "Menu → Petições → Nova. Escolha o tipo (inicial, contestação, recurso…) e vincule ao processo/cliente.",
      "Opcional: selecione um Modelo do escritório — importe modelos prontos do Word (.docx) em Petições → Modelos, ou baixe um modelo em .docx, edite no Word e reimporte.",
      "Descreva as instruções e dispare a geração — a IA redige usando a chave do escritório ou a sua (BYOK).",
      "Revise e edite o conteúdo. Baixe em PDF — o cabeçalho/rodapé usa o Timbrado do escritório (Personalização → Escritório).",
    ],
    dica: "Ações críticas (protocolar) passam por aprovação humana antes de executar.",
  },
  {
    icon: Users, categoria: "Jurídico", titulo: "Clientes (CRM)",
    resumo: "Gestão de clientes e leads com consentimento LGPD.",
    passos: [
      "Menu → Clientes. Filtre por status (prospecto, ativo, inativo) ou busque por nome/email.",
      "“Novo Cliente”: pessoa física ou jurídica, com contatos e origem do lead.",
      "Registre o consentimento LGPD — o painel de compliance acompanha quem ainda não consentiu.",
      "Edite ou exclua pelos ícones no cartão/linha do cliente.",
    ],
  },
  {
    icon: FolderOpen, categoria: "Jurídico", titulo: "Documentos & OCR",
    resumo: "Envie arquivos, extraia texto e organize a documentação.",
    passos: [
      "Menu → Documentos → botão de upload. Envie arquivos até 10MB (comece com .txt/.pdf).",
      "Arquivos de texto têm o conteúdo extraído automaticamente; PDFs e imagens usam o botão de OCR.",
      "Documentos arquivados somem da lista por padrão; a exclusão permanente remove de vez.",
    ],
  },
  {
    icon: FileText, categoria: "Jurídico", titulo: "Contratos",
    resumo: "Crie contratos com conteúdo, gere minutas com IA e gerencie o ciclo de vida.",
    passos: [
      "Menu → Contratos → “Novo Contrato”. Preencha título, tipo, valor e o conteúdo/minuta.",
      "No modo edição, use “Gerar com IA” para redigir a minuta a partir dos dados — revise antes de salvar.",
      "Ao excluir, escolha “Arquivar” (reversível) ou “Excluir” (permanente).",
    ],
  },
  {
    icon: Bot, categoria: "Inteligência IA", titulo: "Agentes IA",
    resumo: "19 agentes especializados coordenados por um orquestrador.",
    passos: [
      "Menu → Agentes IA. Cada agente cobre uma função (petição, revisão, jurisprudência, estratégia, financeiro…).",
      "Use “Disparar Tarefa” para acionar via orquestrador; descreva a tarefa e execute.",
      "Acompanhe a execução pelo run iniciado. Se precisar, clique em “Cancelar execução”.",
    ],
    dica: "Execuções que geram ações críticas param na fila de Aprovações até um humano decidir.",
  },
  {
    icon: KeyRound, categoria: "Inteligência IA", titulo: "Minha IA (BYOK)",
    resumo: "Use sua própria chave de IA — os tokens saem da sua conta, preservando o crédito do escritório.",
    passos: [
      "Menu → Minha IA. Escolha o provedor (Google Gemini ou Anthropic Claude).",
      "Informe o modelo recomendado (ex.: gemini-2.5-flash) e cole sua chave de API.",
      "Marque “Usar minha IA nas execuções” e clique em Salvar. Depois, “Testar conexão”.",
      "Com isso ativo, seus agentes passam a usar sua chave. Se desativar, volta a IA padrão do escritório.",
      "Opcional: em “Ajuste por área”, defina um modelo diferente por tarefa (ex.: premium para petições, rápido para relatórios) — em branco, vale o modelo global.",
    ],
    dica: "Se aparecer “modelo inválido”, use um modelo atual como gemini-2.5-flash. Obtenha a chave no Google AI Studio.",
  },
  {
    icon: CheckSquare, categoria: "Inteligência IA", titulo: "Aprovações (HITL)",
    resumo: "Human-in-the-Loop: nada crítico é executado sem decisão humana.",
    passos: [
      "Menu → Aprovações. Veja as sugestões pendentes da IA, priorizadas.",
      "Abra uma aprovação para ver a sugestão e eventuais modificações.",
      "Aprove (a ação é executada na hora) ou rejeite — a rejeição exige justificativa.",
    ],
  },
  {
    icon: BookOpen, categoria: "Inteligência IA", titulo: "Pesquisa Jurídica (RAG)",
    resumo: "Busca semântica em jurisprudência, legislação, doutrina e memórias do escritório.",
    passos: [
      "Menu → Pesquisa Jurídica. Digite a consulta em linguagem natural.",
      "Selecione as bases de conhecimento (jurisprudência, legislação, doutrina, petições, memórias, docs de clientes).",
      "Pressione Enter ou “Buscar”. Os resultados trazem a fonte para rastreabilidade.",
    ],
    dica: "Documentos aprovados/protocolados são indexados automaticamente nas bases do escritório. A busca usa embeddings — requer a chave OpenAI do sistema configurada.",
  },
  {
    icon: Shapes, categoria: "Inteligência IA", titulo: "Visual Law",
    resumo: "Gere fluxogramas e linhas do tempo jurídicas para clareza visual.",
    passos: [
      "Menu → Visual Law. Descreva o fluxo ou o caso.",
      "A IA gera o diagrama/timeline; ajuste e use em peças e apresentações.",
    ],
  },
  {
    icon: DollarSign, categoria: "Gestão", titulo: "Financeiro",
    resumo: "Honorários, receitas, despesas e inadimplência.",
    passos: [
      "Menu → Financeiro → “Novo Lançamento” (receita ou despesa).",
      "Edite lançamentos pelo lápis; marque como pago quando quitado.",
      "O resumo mostra recebido, pendente e resultado — sempre isolado ao seu escritório.",
    ],
  },
  {
    icon: BarChart2, categoria: "Gestão", titulo: "Relatórios",
    resumo: "Gráficos de processos, financeiro e uso dos agentes.",
    passos: [
      "Menu → Relatórios. Navegue pelas visões (processos, financeiro, agentes).",
      "Use os filtros de período para recortar os dados.",
    ],
  },
  {
    icon: DollarSign, categoria: "Gestão", titulo: "Custos de IA",
    resumo: "Acompanhe o consumo de tokens e o custo de IA por advogado (ADMIN/SÓCIO).",
    passos: [
      "Menu → Custos de IA. Escolha o período (7, 30 ou 90 dias).",
      "Veja os totais do escritório e a tabela por usuário (execuções, tokens, custo).",
      "Clique no valor da coluna “Limite mensal” para definir o teto de cada usuário (vazio remove).",
      "Ao atingir 80% do teto o usuário é alertado; a 100%, novas execuções são bloqueadas até ajuste do limite ou virada do mês.",
    ],
    dica: "Custos de chaves próprias (BYOK) são pagos pelo usuário ao provedor — aqui aparecem como estimativa.",
  },
  {
    icon: Sparkles, categoria: "Sistema", titulo: "Ética & Integridade",
    resumo: "Código de Conduta com aceite registrado e Canal de Denúncias confidencial.",
    passos: [
      "Menu → Ética & Integridade. O ADMIN publica o Código de Conduta (cada publicação gera nova versão).",
      "Cada usuário lê e clica em “Li e aceito” — o aceite fica registrado por versão; o gestor vê quantos já aceitaram.",
      "Canal de Denúncias: escolha a categoria, descreva o relato e envie — no modo anônimo sua identidade não é gravada. Guarde o protocolo.",
      "ADMIN/SÓCIO acompanham os relatos e atualizam o status (aberto → em análise → resolvido).",
      "Abaixo, os controles técnicos ativos (HITL, auditoria, LGPD) e os próximos passos do programa.",
    ],
  },
  {
    icon: Sparkles, categoria: "Sistema", titulo: "Administração (Usuários, Plano & Uso)",
    resumo: "Gestão de usuários, limites do plano e revisão de acessos (ADMIN).",
    passos: [
      "Menu → Usuários: convide membros (senha temporária por email), edite papel/status, redefina senhas e veja a atividade.",
      "Botão “Revisão de Acessos”: usuários ativos ordenados pelo acesso mais antigo — desative contas ociosas (30/60+ dias destacados).",
      "Menu → Plano & Uso: plano atual e barras de consumo (usuários vs limite, armazenamento, custo de IA do mês).",
      "Menu → Saúde do Sistema: status dos serviços em tempo real e roadmap do produto.",
    ],
    dica: "A Revisão de Acessos também atende ao Programa de Integridade (recertificação periódica).",
  },
  {
    icon: Sparkles, categoria: "Sistema", titulo: "Integrações (WhatsApp, Assinatura, PWA)",
    resumo: "Conexões com serviços externos — o que já está pronto e o que falta para ativar.",
    passos: [
      "Menu → Integrações (ADMIN). Cada cartão mostra o recurso, o que o sistema já tem pronto e o que falta (credenciais/provedor).",
      "Para instalar o app (PWA): abra o sistema no navegador do celular e use “Adicionar à tela inicial”.",
      "Para ativar WhatsApp ou assinatura eletrônica, providencie as credenciais do provedor e solicite a conexão.",
    ],
  },
  {
    icon: UserCircle, categoria: "Relacionamento", titulo: "Portal do Cliente",
    resumo: "Acesso externo com processos, documentos, financeiro e mensagens ao escritório.",
    passos: [
      "Em Clientes, convide o cliente para o portal (gera acesso vinculado).",
      "O cliente vê apenas os próprios processos, documentos aprovados e financeiro, e baixa documentos em PDF com o timbrado do escritório.",
      "Em “Mensagens”, o cliente fala com o escritório — o advogado responsável (ou os ADMINs) é notificado na hora.",
      "Para responder: abra o cliente no CRM → aba Interações → nova interação com tipo “PORTAL” — a resposta aparece no portal do cliente.",
      "O isolamento é duplo (cliente + escritório) — nenhum dado vaza entre contas.",
    ],
  },
];

const CATEGORIAS = ["Todas", "Jurídico", "Inteligência IA", "Gestão", "Relacionamento", "Sistema"];

export default function AjudaPage() {
  const [busca, setBusca] = useState("");
  const [cat, setCat] = useState("Todas");
  const [aberto, setAberto] = useState<string | null>(null);

  const filtrados = GUIAS.filter((g) => {
    const okCat = cat === "Todas" || g.categoria === cat;
    const q = busca.toLowerCase();
    const okBusca = !q || g.titulo.toLowerCase().includes(q) || g.resumo.toLowerCase().includes(q) ||
      g.passos.some((p) => p.toLowerCase().includes(q));
    return okCat && okBusca;
  });

  return (
    <div className="max-w-4xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Ajuda & Treinamento" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title flex items-center gap-2">
            <GraduationCap size={22} className="text-afj-gold" /> Ajuda & Treinamento
          </h1>
          <p className="text-afj-black/45 text-sm mt-1">
            Guias passo a passo de cada funcionalidade do AFJ CORE. Use a busca ou filtre por área.
          </p>
        </div>
      </div>

      {/* Busca + filtros */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
          <input
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            placeholder="Buscar como fazer algo (ex.: gerar petição, BYOK, prazo)..."
            className="w-full pl-9 pr-4 py-2.5 text-sm border border-afj-cream-dark rounded-sm bg-white focus:outline-none focus:border-afj-gold"
          />
        </div>
        <div className="flex gap-1.5 flex-wrap">
          {CATEGORIAS.map((c) => (
            <button
              key={c}
              onClick={() => setCat(c)}
              className={`text-xs px-3 py-1.5 rounded-sm border transition-colors ${
                cat === c
                  ? "bg-afj-gold text-white border-afj-gold"
                  : "bg-white text-afj-black/60 border-afj-cream-dark hover:border-afj-gold/50"
              }`}
            >
              {c}
            </button>
          ))}
        </div>
      </div>

      {/* Guias */}
      <div className="space-y-2.5">
        {filtrados.map((g) => {
          const Icon = g.icon;
          const isOpen = aberto === g.titulo;
          return (
            <div key={g.titulo} className="afj-card overflow-hidden">
              <button
                onClick={() => setAberto(isOpen ? null : g.titulo)}
                className="w-full flex items-center gap-3 p-4 text-left hover:bg-afj-cream/40 transition-colors"
              >
                <span className="w-9 h-9 rounded-sm bg-afj-gold/10 flex items-center justify-center flex-shrink-0">
                  <Icon size={17} className="text-afj-gold" />
                </span>
                <span className="flex-1 min-w-0">
                  <span className="flex items-center gap-2">
                    <span className="font-semibold text-afj-black text-sm">{g.titulo}</span>
                    <span className="text-[10px] uppercase tracking-wider text-afj-black/35">{g.categoria}</span>
                  </span>
                  <span className="block text-xs text-afj-black/50 mt-0.5 truncate">{g.resumo}</span>
                </span>
                <ChevronDown size={16} className={`text-afj-black/30 flex-shrink-0 transition-transform ${isOpen ? "rotate-180" : ""}`} />
              </button>

              {isOpen && (
                <div className="px-4 pb-4 pt-1 border-t border-afj-cream-dark">
                  <ol className="space-y-2 mt-3">
                    {g.passos.map((p, i) => (
                      <li key={i} className="flex gap-3 text-sm text-afj-black/75">
                        <span className="w-5 h-5 rounded-full bg-afj-navy text-white text-[11px] font-semibold flex items-center justify-center flex-shrink-0 mt-0.5">
                          {i + 1}
                        </span>
                        <span className="leading-relaxed">{p}</span>
                      </li>
                    ))}
                  </ol>
                  {g.dica && (
                    <div className="flex items-start gap-2 mt-3 text-xs text-afj-black/60 bg-afj-cream/60 border border-afj-cream-dark rounded-sm p-3">
                      <Lightbulb size={14} className="text-afj-gold flex-shrink-0 mt-0.5" />
                      <span><strong className="text-afj-black/75">Dica:</strong> {g.dica}</span>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {filtrados.length === 0 && (
          <div className="afj-card p-10 text-center">
            <Sparkles size={26} className="mx-auto text-afj-black/20 mb-2" />
            <p className="text-sm text-afj-black/50">Nenhum guia encontrado para “{busca}”.</p>
          </div>
        )}
      </div>
    </div>
  );
}
