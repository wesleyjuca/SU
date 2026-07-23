// Registro ÚNICO de navegação (Bloco F / F3). Antes o menu vivia só no
// layout; agora BottomNav e SearchModal consomem a MESMA definição — fim da
// divergência (ex.: BottomNav mostrava Aprovações/Agentes a papéis proibidos).
import {
  LayoutDashboard, Scale, FileText, Users, FolderOpen, Bot, CheckSquare,
  DollarSign, Shield, Shapes, Settings, FileEdit, BarChart2, CalendarClock,
  BookOpen, Activity, Users2, Palette, KeyRound, GraduationCap, Compass,
  Coins, ShieldCheck, Plug, Gauge, Building2, Receipt, Gavel, MonitorPlay,
  Newspaper, Briefcase, Brain,
} from "lucide-react";

export type NavItem = {
  href: string;
  label: string;
  icon: React.ElementType;
  roles: string[] | null;   // null = todos os papéis
  newTab?: boolean;
};

export type NavSection = { title: string | null; items: NavItem[] };

const ADV = ["ADMIN", "SUPERADMIN", "SOCIO", "ADVOGADO"];
const GESTAO = ["ADMIN", "SUPERADMIN", "SOCIO", "GESTOR"];

export const navSections: NavSection[] = [
  { title: null, items: [
    { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard, roles: null },
  ]},
  { title: "JURÍDICO", items: [
    { href: "/minha-area", label: "Minha Área", icon: Briefcase, roles: null },
    { href: "/processos", label: "Processos", icon: Scale, roles: null },
    { href: "/publicacoes", label: "Publicações", icon: Newspaper, roles: null },
    { href: "/agenda", label: "Agenda", icon: CalendarClock, roles: null },
    { href: "/peticoes", label: "Petições", icon: FileEdit, roles: ADV },
    { href: "/clientes", label: "Clientes", icon: Users, roles: null },
    { href: "/documentos", label: "Documentos", icon: FolderOpen, roles: null },
    { href: "/contratos", label: "Contratos", icon: FileText, roles: ADV },
  ]},
  { title: "INTELIGÊNCIA IA", items: [
    { href: "/agentes", label: "Agentes IA", icon: Bot, roles: ADV },
    { href: "/minha-ia", label: "Minha IA", icon: KeyRound, roles: ADV },
    { href: "/aprovacoes", label: "Aprovações", icon: CheckSquare, roles: ADV },
    { href: "/busca-juridica", label: "Pesquisa Jurídica", icon: BookOpen, roles: null },
    { href: "/visual-law", label: "Visual Law", icon: Shapes, roles: ADV },
  ]},
  { title: "GESTÃO", items: [
    { href: "/financeiro", label: "Financeiro", icon: DollarSign, roles: GESTAO },
    { href: "/relatorios", label: "Relatórios", icon: BarChart2, roles: GESTAO },
    { href: "/custos-ia", label: "Custos de IA", icon: Coins, roles: ["ADMIN", "SOCIO"] },
    { href: "/tv", label: "Painel TV", icon: MonitorPlay, roles: GESTAO, newTab: true },
  ]},
  { title: "AJUDA", items: [
    { href: "/ajuda", label: "Ajuda & Treinamento", icon: GraduationCap, roles: null },
    { href: "/sobre", label: "Visão Geral", icon: Compass, roles: null },
    { href: "/etica", label: "Ética & Integridade", icon: ShieldCheck, roles: null },
    { href: "/configuracoes", label: "Configurações", icon: Settings, roles: null },
  ]},
  { title: "ADMINISTRAÇÃO", items: [
    { href: "/admin/escritorios", label: "Escritórios", icon: Building2, roles: ["SUPERADMIN"] },
    { href: "/admin/faturamento", label: "Faturamento", icon: Receipt, roles: ["SUPERADMIN"] },
    { href: "/admin/relatorios-banca", label: "Relatórios da Banca", icon: BarChart2, roles: ["SUPERADMIN", "ADMIN", "SOCIO"] },
    { href: "/admin/usuarios", label: "Usuários", icon: Users2, roles: ["ADMIN", "SUPERADMIN"] },
    { href: "/admin/plano", label: "Plano & Uso", icon: Gauge, roles: ["ADMIN", "SUPERADMIN"] },
    { href: "/admin/personalizacao", label: "Personalização", icon: Palette, roles: ["ADMIN", "SUPERADMIN"] },
    { href: "/admin/juridico", label: "Config. Jurídica", icon: Gavel, roles: ["ADMIN", "SUPERADMIN"] },
    { href: "/integracoes", label: "Integrações", icon: Plug, roles: ["ADMIN", "SUPERADMIN"] },
    { href: "/auditoria", label: "Auditoria", icon: Shield, roles: ["ADMIN", "SOCIO", "SUPERADMIN"] },
    { href: "/admin/health", label: "Saúde do Sistema", icon: Activity, roles: ["ADMIN", "SUPERADMIN"] },
    { href: "/admin/cerebro", label: "Cérebro", icon: Brain, roles: ["SUPERADMIN"] },
  ]},
];

/** Um item é visível se `roles` é null (todos) ou inclui o papel do usuário. */
export function canSee(item: NavItem, role: string | undefined): boolean {
  return item.roles === null || (!!role && item.roles.includes(role));
}

/** Seções com os itens filtrados pelo papel; seções vazias são removidas. */
export function navForRole(role: string | undefined): NavSection[] {
  return navSections
    .map((s) => ({ ...s, items: s.items.filter((i) => canSee(i, role)) }))
    .filter((s) => s.items.length > 0);
}

/** Lista achatada dos itens visíveis (p/ BottomNav "Mais" e busca de rotas). */
export function flatNavForRole(role: string | undefined): NavItem[] {
  return navSections.flatMap((s) => s.items).filter((i) => canSee(i, role));
}

// Ordem de preferência dos atalhos da barra inferior (mobile). O BottomNav
// pega os primeiros deste conjunto que o papel pode acessar e completa com "Mais".
export const MOBILE_PRIMARY_HREFS = [
  "/dashboard", "/processos", "/agenda", "/publicacoes", "/aprovacoes",
  "/clientes", "/agentes", "/documentos",
];
