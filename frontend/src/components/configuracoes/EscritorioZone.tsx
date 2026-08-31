"use client";
import { useState, useRef, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { Layout, Download, Upload, Check, ImageIcon, Building2, Puzzle, LayoutDashboard, Undo2, History, Gavel } from "lucide-react";
import { applyTheme } from "@/lib/theme";
import { useThemeStore } from "@/store";
import { useToast } from "@/components/ui/Toast";
import { useSavedFlash } from "@/hooks/useSavedFlash";
import { SettingsSaveButton } from "@/components/configuracoes/SettingsSaveButton";
import { JuridicoTab } from "./JuridicoTab";
import { maskCep } from "@/lib/masks";

// Fase 256 — reorganização estrutural: as 5 abas antigas "Aparência"/
// "Cores"/"Tipografia"/"Templates"/"Exportar-Importar" eram todas facetas
// do mesmo conceito ("identidade visual do escritório"), separadas só por
// acidente histórico de quando cada uma foi adicionada. Consolidadas numa
// única aba "Identidade Visual" com seções internas — reduz a barra de
// abas de 9 pra 5. Nenhum controle foi removido, só reorganizado.
const TABS = [
  { id: "escritorio", label: "Escritório", icon: Building2 },
  { id: "identidade", label: "Identidade Visual", icon: Layout },
  { id: "modulos", label: "Módulos", icon: Puzzle },
  { id: "dashboard", label: "Dashboard", icon: LayoutDashboard },
  { id: "juridico", label: "Jurídico", icon: Gavel },
] as const;
type TabId = (typeof TABS)[number]["id"];

const AVAILABLE_WIDGETS = [
  { key: "processos_ativos", label: "Processos Ativos" },
  { key: "prazos_proximos", label: "Prazos Próximos" },
  { key: "aprovacoes_pendentes", label: "Aprovações Pendentes" },
  { key: "custo_ia_mes", label: "Custo IA do Mês" },
  { key: "agentes_ativos", label: "Agentes Ativos" },
  { key: "total_clientes", label: "Total de Clientes" },
];

// Fase 256 (Alteração 2 — unificação) — antes só existiam em
// integracoes/page.tsx, invisíveis na aba Módulos (que não era o "lugar
// único" que prometia ser, apesar de escrever na mesma
// TenantConfig.modules_enabled). Mesma chave, mesmo endpoint — o
// checkbox em Integrações continua existindo, embutido no fluxo de
// conectar cada provedor (não dá pra remover de lá sem quebrar esse
// fluxo), mas agora também aparece aqui.
const MODULOS_GOOGLE = [
  { key: "google_drive_doutrina", label: "Google Drive Doutrina", desc: "Sincronização de doutrina jurídica de uma pasta do Drive" },
  { key: "google_workspace", label: "Google Workspace", desc: "Gmail, Agenda e Drive do escritório integrados ao sistema" },
];

const COLOR_PRESETS = [
  { label: "Ouro AFJ", value: "#B8954A" },
  { label: "Âmbar", value: "#D97706" },
  { label: "Azul Navy", value: "#1E3A5F" },
  { label: "Verde Esmeralda", value: "#064E3B" },
  { label: "Roxo", value: "#4C1D95" },
  { label: "Vermelho", value: "#991B1B" },
  { label: "Ciano", value: "#0E7490" },
  { label: "Índigo", value: "#3730A3" },
];

// Presets da cor do menu (barra lateral) — tons escuros que combinam com texto claro.
const MENU_PRESETS = [
  { label: "Slate AFJ", value: "#3D4557" },
  { label: "Navy", value: "#1E2229" },
  { label: "Azul Executivo", value: "#1E3A5F" },
  { label: "Esmeralda", value: "#064E3B" },
  { label: "Vinho", value: "#4C1D2E" },
  { label: "Grafite", value: "#2D2D2D" },
  { label: "Violeta", value: "#3B2D5E" },
  { label: "Café", value: "#3B2A20" },
];

const TEMPLATES = [
  {
    id: "afj",
    name: "AFJ Original",
    desc: "Ouro & Slate — identidade visual padrão do escritório",
    primary: "#B8954A",
    secondary: "#3D4557",
    accent: "#F4F0EA",
    font: "Optima",
  },
  {
    id: "executivo",
    name: "Azul Executivo",
    desc: "Navy & Dourado — corporativo e sóbrio",
    primary: "#C4962A",
    secondary: "#1E3A5F",
    accent: "#F0F4F8",
    font: "Georgia",
  },
  {
    id: "esmeralda",
    name: "Verde Esmeralda",
    desc: "Verde & Âmbar — fresco e moderno",
    primary: "#F59E0B",
    secondary: "#064E3B",
    accent: "#ECFDF5",
    font: "Inter",
  },
  {
    id: "roxo",
    name: "Roxo Premium",
    desc: "Violeta & Dourado — sofisticado e diferenciado",
    primary: "#D97706",
    secondary: "#4C1D95",
    accent: "#F5F3FF",
    font: "Georgia",
  },
];

const FONTS = [
  { id: "optima", label: "Optima", css: "Optima, 'Optima Nova', Georgia, serif", sample: "Optima — elegante e jurídico" },
  { id: "inter", label: "Inter", css: "Inter, system-ui, sans-serif", sample: "Inter — moderno e legível" },
  { id: "georgia", label: "Georgia", css: "Georgia, 'Times New Roman', serif", sample: "Georgia — clássico e formal" },
  { id: "playfair", label: "Playfair Display", css: "'Playfair Display', Georgia, serif", sample: "Playfair — sofisticado e editorial" },
  { id: "baskerville", label: "Libre Baskerville", css: "'Libre Baskerville', Georgia, serif", sample: "Baskerville — autoridade e tradição" },
];

function LivePreview({ color, font }: { color: string; font: string }) {
  return (
    <div className="afj-card p-5 sticky top-4">
      <p className="afj-section-title mb-4">Preview ao vivo</p>
      <div className="space-y-3">
        {/* Header mini */}
        <div
          className="rounded-sm p-3 flex items-center justify-between"
          style={{ background: "linear-gradient(135deg, #2C3547 0%, #3D4557 100%)" }}
        >
          <div className="flex items-center gap-2">
            <div className="w-5 h-5 rounded-sm" style={{ backgroundColor: color, opacity: 0.9 }} />
            <span className="text-afj-cream text-[10px] font-bold tracking-widest uppercase" style={{ fontFamily: font }}>
              AFJ CORE
            </span>
          </div>
          <div className="w-4 h-4 rounded-sm" style={{ backgroundColor: color }} />
        </div>

        {/* Card mini */}
        <div className="border rounded-sm p-3" style={{ borderColor: `${color}33` }}>
          <p className="text-[10px] font-semibold uppercase tracking-widest mb-1" style={{ color }}>
            Processos Ativos
          </p>
          <p className="text-xl font-bold text-afj-black" style={{ fontFamily: font }}>42</p>
          <p className="text-[10px] text-afj-black/40 mt-1">prazos próximos: 5</p>
        </div>

        {/* Botão mini */}
        <button
          className="w-full py-2 rounded-sm text-xs font-semibold uppercase tracking-wider text-white transition-opacity hover:opacity-90"
          style={{ backgroundColor: color }}
        >
          Botão Primário
        </button>

        {/* Badge mini */}
        <div className="flex gap-2">
          <span
            className="text-[10px] px-2 py-0.5 rounded-full font-medium"
            style={{ backgroundColor: `${color}20`, color }}
          >
            Ativo
          </span>
          <span className="text-[10px] px-2 py-0.5 rounded-full font-medium bg-green-100 text-green-700">
            Aprovado
          </span>
        </div>

        {/* Tipografia mini */}
        <div className="border-t border-afj-cream-dark pt-3">
          <p className="text-sm font-semibold text-afj-black" style={{ fontFamily: font }}>
            Almeida, Freire &amp; Jucá
          </p>
          <p className="text-xs text-afj-black/40">Fonte: {font.split(",")[0]}</p>
        </div>
      </div>
    </div>
  );
}

/** Fase 224 — zona "Escritório & Jurídico" de Configurações (ADMIN/SUPERADMIN
 * apenas). Fase 256 reorganizou as 9 abas originais em 5 (ver TABS acima),
 * corrigiu 3 bugs reais confirmados (office_name/slogan sempre em branco —
 * causa-raiz no backend, `core/tenant.py`; seletor de widgets do Dashboard
 * que nunca salvava nada; e adicionou os 2 módulos Google que só existiam
 * em Integrações), e padronizou o feedback de salvar (useSavedFlash +
 * SettingsSaveButton em vez de ~7 pares soltos de saving/saved). */
export function EscritorioZone() {
  const { theme, setTheme } = useThemeStore();
  const toast = useToast();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<TabId>("escritorio");

  // ?aba= na URL (ex.: redirect de /admin/personalizacao ou /admin/juridico)
  // tem prioridade sobre a última aba salva — senão o link nunca abriria na
  // aba certa. Mesmo padrão de `admin/cerebro`. Fase 256: as antigas abas
  // "marca"/"cores"/"tipografia"/"templates"/"exportar" agora vivem dentro
  // de "identidade" — um deep link antigo pra qualquer uma delas cai na
  // aba consolidada certa.
  const ABA_LEGADA_PARA_NOVA: Record<string, TabId> = {
    marca: "identidade", cores: "identidade", tipografia: "identidade",
    templates: "identidade", exportar: "identidade",
  };
  useEffect(() => {
    const daUrl = searchParams.get("aba");
    if (daUrl) {
      if (TABS.some((t) => t.id === daUrl)) { setTab(daUrl as TabId); return; }
      if (ABA_LEGADA_PARA_NOVA[daUrl]) { setTab(ABA_LEGADA_PARA_NOVA[daUrl]); return; }
    }
    const salva = typeof window !== "undefined" ? localStorage.getItem("afj_configuracoes_aba") : null;
    if (salva) {
      if (TABS.some((t) => t.id === salva)) { setTab(salva as TabId); return; }
      if (ABA_LEGADA_PARA_NOVA[salva]) setTab(ABA_LEGADA_PARA_NOVA[salva]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams]);

  // Fase 256 — cada ação de salvar ganha seu próprio estado saving/saved
  // (antes várias compartilhavam um `saved` só entre abas/seções
  // diferentes — o checkmark de "Cores" podia "vazar" pro botão de
  // "Módulos" se o usuário trocasse de aba rápido demais).
  const infoFlash = useSavedFlash();
  const enderecoFlash = useSavedFlash();
  const lhFlash = useSavedFlash();
  const marcaFlash = useSavedFlash();
  const coresFlash = useSavedFlash();
  const modulesFlash = useSavedFlash();
  const widgetsFlash = useSavedFlash();
  const undoFlash = useSavedFlash();
  const templateFlash = useSavedFlash();

  const [previewColor, setPreviewColor] = useState(theme.primaryColor);
  const [previewSecondary, setPreviewSecondary] = useState(theme.secondaryColor);
  const [previewFont, setPreviewFont] = useState("Optima, 'Optima Nova', Georgia, serif");
  const [appName, setAppName] = useState(theme.appName);
  const [logoUrl, setLogoUrl] = useState(theme.logoUrl ?? "");
  const [logoUploading, setLogoUploading] = useState(false);
  const [faviconUrl, setFaviconUrl] = useState("");
  const [faviconUploading, setFaviconUploading] = useState(false);
  const [useLogoAsFavicon, setUseLogoAsFavicon] = useState(false);
  const [officeName, setOfficeName] = useState("");
  const [slogan, setSlogan] = useState("");
  // Fase 230 — endereço físico do escritório, geocodificado no backend
  // (groundwork pro mapa com marcadores, Fase 231+).
  const [endereco, setEndereco] = useState({ cep: "", logradouro: "", numero: "", bairro: "", cidade: "", uf: "" });
  const [enderecoTemCoordenadas, setEnderecoTemCoordenadas] = useState(false);
  // Timbrado dos documentos (PDFs gerados)
  const [lh, setLh] = useState({ office_name: "", address: "", contact: "", oab: "", footer: "", use_logo: true });
  // Fase 232 — "Nome no cabeçalho"/"Endereço" do timbrado seguem
  // automaticamente "Nome do Escritório"/"Endereço do Escritório" por
  // padrão (elimina o cadastro duplicado); só ficam editáveis quando o
  // usuário opta explicitamente por personalizar.
  const [officeNameCustom, setOfficeNameCustom] = useState(false);
  const [addressCustom, setAddressCustom] = useState(false);
  const [modules, setModules] = useState<Record<string, boolean>>({});
  const [widgets, setWidgets] = useState<string[]>(AVAILABLE_WIDGETS.map((w) => w.key));
  const [previousTheme, setPreviousTheme] = useState<typeof theme | null>(null);
  const [themeHistory, setThemeHistory] = useState<Array<{ color: string; appName: string; ts: string }>>([]);
  const [showHistory, setShowHistory] = useState(false);
  const importRef = useRef<HTMLInputElement>(null);
  const logoFileRef = useRef<HTMLInputElement>(null);
  const faviconFileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetchConfig();
    fetchLetterhead();
    fetchEndereco();
    const stored = localStorage.getItem("afj_theme_history");
    if (stored) { try { setThemeHistory(JSON.parse(stored)); } catch {} }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function fetchEndereco() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/endereco", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const d = await res.json();
        setEndereco({
          cep: d.cep || "", logradouro: d.logradouro || "", numero: d.numero || "", bairro: d.bairro || "",
          cidade: d.cidade || "", uf: d.uf || "",
        });
        setEnderecoTemCoordenadas(d.latitude != null && d.longitude != null);
      }
    } catch { /* mantém defaults */ }
  }

  async function autofillCepEscritorio(cep: string) {
    if (!cep || cep.replace(/\D/g, "").length !== 8) return;
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/clients/consultar-cep", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ cep }),
      });
      if (!res.ok) return;
      const data = await res.json();
      if (data.logradouro || data.cidade) {
        setEndereco((atual) => ({
          ...atual,
          logradouro: atual.logradouro || data.logradouro || "",
          bairro: atual.bairro || data.bairro || "",
          cidade: atual.cidade || data.cidade || "",
          uf: atual.uf || data.uf || "",
        }));
      }
    } catch { /* fail-soft — endereço continua editável manualmente */ }
  }

  async function saveEndereco() {
    await enderecoFlash.run(async () => {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/endereco", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(endereco),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Erro ao salvar o endereço.");
      }
      const d = await res.json();
      setEnderecoTemCoordenadas(d.latitude != null && d.longitude != null);
    }, "Endereço do escritório salvo.");
  }

  async function fetchLetterhead() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/letterhead", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const d = await res.json();
        setLh({
          office_name: d.office_name || "",
          address: d.address || "",
          contact: d.contact || "",
          oab: d.oab || "",
          footer: d.footer || "",
          use_logo: d.use_logo !== false,
        });
        setOfficeNameCustom(!!d.office_name_custom);
        setAddressCustom(!!d.address_custom);
      }
    } catch { /* mantém defaults */ }
  }

  async function saveLetterhead() {
    await lhFlash.run(async () => {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/letterhead", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ ...lh, office_name_custom: officeNameCustom, address_custom: addressCustom }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Erro ao salvar o timbrado.");
      }
      const d = await res.json();
      // Reflete o valor efetivo devolvido pelo backend (pode ter sido
      // recalculado automaticamente se algum dos 2 campos voltou a
      // "automático" nesta mesma chamada).
      setLh((atual) => ({ ...atual, office_name: d.office_name || "", address: d.address || "" }));
    }, "Timbrado salvo.");
  }

  async function fetchConfig() {
    try {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/config", { headers: { Authorization: `Bearer ${token}` } });
      if (res.ok) {
        const data = await res.json();
        setModules(data.modules_enabled || {});
        // Fase 256 — achado real corrigido no backend (core/tenant.py):
        // office_name/slogan nunca vinham nesta resposta, mesmo já
        // salvos, porque o cache do tenant nunca incluía
        // TenantConfig.extra_data. Continuam lidos aqui exatamente como
        // antes — a correção foi no backend, não nesta leitura.
        if (data.office_name) setOfficeName(data.office_name);
        if (data.slogan) setSlogan(data.slogan);
        if (data.favicon_url) setFaviconUrl(data.favicon_url);
        if (data.dashboard_widgets?.length) setWidgets(data.dashboard_widgets);
      }
    } catch {
      toast.error("Erro ao carregar configurações.");
    }
  }

  async function saveBranding(
    updates: Record<string, string>,
    flash: ReturnType<typeof useSavedFlash>,
    successMessage?: string
  ) {
    setPreviousTheme({ ...theme });
    await flash.run(async () => {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/branding", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(updates),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Erro ao salvar. Tente novamente.");
      }
      const entry = { color: previewColor, appName, ts: new Date().toISOString() };
      const next = [entry, ...themeHistory].slice(0, 5);
      setThemeHistory(next);
      localStorage.setItem("afj_theme_history", JSON.stringify(next));
    }, successMessage);
  }

  async function handleUndo() {
    if (!previousTheme) return;
    applyTheme(previousTheme);
    setTheme(previousTheme);
    setPreviewColor(previousTheme.primaryColor);
    await saveBranding({ primary_color: previousTheme.primaryColor }, undoFlash, "Alteração desfeita.");
    setPreviousTheme(null);
  }

  async function uploadFaviconFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setFaviconUploading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/v1/tenant/favicon-upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setFaviconUrl(data.favicon_url);
      }
    } catch {
      toast.error("Erro ao enviar favicon. Tente novamente.");
    }
    setFaviconUploading(false);
    if (faviconFileRef.current) faviconFileRef.current.value = "";
  }

  async function saveModules() {
    await modulesFlash.run(async () => {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/modules", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(modules),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Erro ao salvar módulos.");
      }
    }, "Módulos salvos.");
  }

  async function saveWidgets() {
    // Fase 256 — achado real corrigido no backend (BrandingUpdate ganhou
    // o campo dashboard_widgets, que faltava): antes esse botão sempre
    // devolvia 200 OK sem persistir nada — placebo completo.
    await widgetsFlash.run(async () => {
      const token = localStorage.getItem("afj_access_token");
      const res = await fetch("/api/v1/tenant/branding", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ dashboard_widgets: widgets }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || "Erro ao salvar widgets.");
      }
    }, "Widgets do dashboard salvos.");
  }

  async function uploadLogoFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setLogoUploading(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      const formData = new FormData();
      formData.append("file", file);
      const res = await fetch("/api/v1/tenant/logo-upload", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        body: formData,
      });
      if (res.ok) {
        const data = await res.json();
        setLogoUrl(data.logo_url);
        setTheme({ ...theme, logoUrl: data.logo_url });
        if (useLogoAsFavicon) {
          const token2 = localStorage.getItem("afj_access_token");
          await fetch("/api/v1/tenant/branding", {
            method: "PUT",
            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token2}` },
            body: JSON.stringify({ favicon_url: data.logo_url }),
          });
          setFaviconUrl(data.logo_url);
          applyTheme({ ...theme, logoUrl: data.logo_url, faviconUrl: data.logo_url });
        }
        toast.success("Logo enviado.");
      }
    } catch {
      toast.error("Erro ao enviar logo. Tente novamente.");
    }
    setLogoUploading(false);
    if (logoFileRef.current) logoFileRef.current.value = "";
  }

  function applyColor(color: string) {
    setPreviewColor(color);
    applyTheme({ ...theme, primaryColor: color });
    setTheme({ ...theme, primaryColor: color });
  }

  function applySecondary(color: string) {
    setPreviewSecondary(color);
    // Repinta a barra lateral (menu) em runtime via --brand-secondary.
    applyTheme({ ...theme, secondaryColor: color });
    setTheme({ ...theme, secondaryColor: color });
  }

  function applyTemplate(t: (typeof TEMPLATES)[number]) {
    setPreviewColor(t.primary);
    const f = FONTS.find((f) => f.id === t.font.toLowerCase()) ?? FONTS[0];
    setPreviewFont(f.css);
    document.documentElement.style.setProperty("--font-display", f.css);
    // applyTheme converte hex→canais e seta --brand-* (inclui secondary/accent).
    applyTheme({ ...theme, primaryColor: t.primary, secondaryColor: t.secondary, accentColor: t.accent });
    setTheme({ ...theme, primaryColor: t.primary, secondaryColor: t.secondary, accentColor: t.accent });
    saveBranding(
      { primary_color: t.primary, secondary_color: t.secondary, accent_color: t.accent },
      templateFlash,
      `Tema "${t.name}" aplicado.`
    );
  }

  function exportTheme() {
    const data = {
      primaryColor: previewColor,
      fontDisplay: previewFont,
      appName,
      logoUrl,
      exportedAt: new Date().toISOString(),
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const a = Object.assign(document.createElement("a"), {
      href: URL.createObjectURL(blob),
      download: "afj-tema.json",
    });
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function trocarTab(id: TabId) {
    setTab(id);
    try { localStorage.setItem("afj_configuracoes_aba", id); } catch { /* noop */ }
  }

  function importTheme(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      try {
        const data = JSON.parse(ev.target?.result as string);
        if (data.primaryColor) applyColor(data.primaryColor);
        if (data.appName) setAppName(data.appName);
        if (data.logoUrl) setLogoUrl(data.logoUrl);
        if (data.fontDisplay) {
          setPreviewFont(data.fontDisplay);
          document.documentElement.style.setProperty("--font-display", data.fontDisplay);
        }
        toast.success("Tema importado — revise e clique em Salvar nas seções abaixo pra persistir.");
      } catch {
        toast.error("Arquivo de tema inválido.");
      }
    };
    reader.readAsText(file);
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-end gap-2">
        {previousTheme && (
          <button onClick={handleUndo} disabled={undoFlash.saving} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5 disabled:opacity-60">
            <Undo2 size={12} /> {undoFlash.saving ? "Desfazendo..." : "Desfazer"}
          </button>
        )}
        <button onClick={() => setShowHistory(true)} className="btn-afj-outline text-xs py-1.5 px-3 rounded-sm flex items-center gap-1.5">
          <History size={12} /> Histórico
        </button>
      </div>

      {/* Tabs */}
      <div role="tablist" aria-label="Seções de Escritório & Jurídico" className="flex gap-1 bg-afj-cream border border-afj-cream-dark rounded-sm p-1 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => trocarTab(id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-sm text-xs font-semibold uppercase tracking-wider whitespace-nowrap transition-colors ${
              tab === id
                ? "bg-white text-afj-black shadow-sm"
                : "text-afj-black/45 hover:text-afj-black"
            }`}
          >
            <Icon size={13} />
            {label}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Conteúdo principal */}
        <div className="lg:col-span-2 space-y-5">

          {/* ── Tab: Escritório ── */}
          {tab === "escritorio" && (
            <>
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Informações do Escritório</p>
              </div>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                    Nome do Escritório
                  </label>
                  <input type="text" value={officeName} onChange={(e) => setOfficeName(e.target.value)}
                    placeholder="Almeida, Freire & Jucá Advogados"
                    className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  <p className="text-[10px] text-afj-black/35 mt-1">Exibido no cabeçalho e nos documentos gerados.</p>
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                    Slogan / Tagline
                  </label>
                  <input type="text" value={slogan} onChange={(e) => setSlogan(e.target.value)}
                    placeholder="Excelência jurídica com inteligência"
                    className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                    Favicon
                  </label>
                  <input ref={faviconFileRef} type="file" accept="image/png,image/x-icon,image/svg+xml" className="hidden" onChange={uploadFaviconFile} />
                  <button type="button" onClick={() => faviconFileRef.current?.click()} disabled={faviconUploading}
                    className="flex items-center gap-2 border border-dashed border-afj-cream-dark hover:border-afj-gold/50 rounded-sm px-4 py-3 text-sm text-afj-black/50 hover:text-afj-black transition-colors disabled:opacity-60">
                    <ImageIcon size={14} className="text-afj-gold" />
                    {faviconUploading ? "Enviando..." : "Upload de Favicon (PNG, ICO, SVG — máx. 512KB)"}
                  </button>
                  {faviconUrl && (
                    <div className="mt-2 p-3 border border-afj-cream-dark rounded-sm bg-afj-cream/50 flex items-center gap-3">
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={faviconUrl} alt="Favicon preview" className="w-8 h-8 object-contain" />
                      <div>
                        <p className="text-[10px] text-afj-black/40 uppercase tracking-widest">Preview 32×32</p>
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img src={faviconUrl} alt="Favicon preview small" className="w-4 h-4 object-contain mt-1" />
                        <p className="text-[10px] text-afj-black/30">Preview 16×16</p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
              <SettingsSaveButton
                onClick={() => saveBranding({ office_name: officeName, slogan }, infoFlash, "Informações do escritório salvas.")}
                saving={infoFlash.saving}
                saved={infoFlash.saved}
                label="Salvar Escritório"
              />
            </div>

            {/* ── Endereço do Escritório ── */}
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Endereço do Escritório</p>
              </div>
              <p className="text-xs text-afj-black/45 -mt-2">
                Usado no mapa (menu Mapa) e como base pro timbrado dos documentos.
                Preencher o número refina a localização pro endereço exato — sem ele, a localização
                fica aproximada (centro do CEP).
              </p>
              <div className="space-y-4">
                <div className="max-w-[200px]">
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">CEP</label>
                  <input type="text" value={endereco.cep}
                    onChange={(e) => setEndereco({ ...endereco, cep: maskCep(e.target.value) })}
                    onBlur={(e) => autofillCepEscritorio(e.target.value)}
                    placeholder="00000-000"
                    className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
                  <div className="sm:col-span-3">
                    <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Logradouro</label>
                    <input type="text" value={endereco.logradouro}
                      onChange={(e) => setEndereco({ ...endereco, logradouro: e.target.value })}
                      placeholder="Rua, complemento"
                      className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Número</label>
                    <input type="text" value={endereco.numero}
                      onChange={(e) => setEndereco({ ...endereco, numero: e.target.value })}
                      className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  </div>
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Bairro</label>
                    <input type="text" value={endereco.bairro}
                      onChange={(e) => setEndereco({ ...endereco, bairro: e.target.value })}
                      className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Cidade</label>
                    <input type="text" value={endereco.cidade}
                      onChange={(e) => setEndereco({ ...endereco, cidade: e.target.value })}
                      className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">UF</label>
                    <input type="text" value={endereco.uf} maxLength={2}
                      onChange={(e) => setEndereco({ ...endereco, uf: e.target.value.toUpperCase() })}
                      className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  </div>
                </div>
                {enderecoTemCoordenadas && (
                  <p className="text-[11px] text-green-700 flex items-center gap-1.5">
                    <Check size={12} /> Localização geográfica capturada.
                  </p>
                )}
              </div>
              <SettingsSaveButton
                onClick={saveEndereco}
                saving={enderecoFlash.saving}
                saved={enderecoFlash.saved}
                label="Salvar Endereço"
              />
            </div>

            {/* ── Timbrado dos Documentos ── */}
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Timbrado dos Documentos</p>
              </div>
              <p className="text-xs text-afj-black/45 -mt-2">
                Cabeçalho e rodapé dos PDFs gerados (petições, contratos). Campos vazios não aparecem;
                sem nenhum campo preenchido, vale o padrão do sistema.
              </p>
              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Nome no cabeçalho</label>
                  {officeNameCustom ? (
                    <>
                      <input type="text" value={lh.office_name} onChange={(e) => setLh({ ...lh, office_name: e.target.value })}
                        placeholder="Almeida, Freire & Jucá Advogados"
                        className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                      <button type="button" onClick={() => setOfficeNameCustom(false)}
                        className="text-[11px] text-afj-gold hover:underline mt-1">
                        Usar o nome do escritório automaticamente
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="w-full bg-afj-cream/60 border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm text-afj-black/70">
                        {lh.office_name || "Cadastre o nome em \"Informações do Escritório\", acima"}
                      </div>
                      <button type="button" onClick={() => setOfficeNameCustom(true)}
                        className="text-[11px] text-afj-gold hover:underline mt-1">
                        Personalizar nome no timbrado
                      </button>
                    </>
                  )}
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Endereço</label>
                  {addressCustom ? (
                    <>
                      <input type="text" value={lh.address} onChange={(e) => setLh({ ...lh, address: e.target.value })}
                        placeholder="Rua, número — Bairro — Cidade/UF — CEP"
                        className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                      <button type="button" onClick={() => setAddressCustom(false)}
                        className="text-[11px] text-afj-gold hover:underline mt-1">
                        Usar o endereço do escritório automaticamente
                      </button>
                    </>
                  ) : (
                    <>
                      <div className="w-full bg-afj-cream/60 border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm text-afj-black/70">
                        {lh.address || "Cadastre o endereço em \"Endereço do Escritório\", acima"}
                      </div>
                      <button type="button" onClick={() => setAddressCustom(true)}
                        className="text-[11px] text-afj-gold hover:underline mt-1">
                        Personalizar endereço no timbrado
                      </button>
                    </>
                  )}
                </div>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Contato</label>
                    <input type="text" value={lh.contact} onChange={(e) => setLh({ ...lh, contact: e.target.value })}
                      placeholder="Tel: (85) 3333-4444 | contato@..."
                      className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  </div>
                  <div>
                    <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">OAB</label>
                    <input type="text" value={lh.oab} onChange={(e) => setLh({ ...lh, oab: e.target.value })}
                      placeholder="OAB/CE 00.000"
                      className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                  </div>
                </div>
                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">Rodapé (opcional)</label>
                  <input type="text" value={lh.footer} onChange={(e) => setLh({ ...lh, footer: e.target.value })}
                    placeholder="Ex.: Este documento é confidencial."
                    className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors" />
                </div>
                <label className="flex items-center gap-2.5 cursor-pointer">
                  <input type="checkbox" checked={lh.use_logo} onChange={(e) => setLh({ ...lh, use_logo: e.target.checked })} className="accent-afj-gold w-4 h-4" />
                  <span className="text-sm text-afj-black/75">Incluir o logo do escritório no topo dos PDFs</span>
                </label>
                <p className="text-[10px] text-afj-black/35">O logo usado é o da aba Identidade Visual (upload de logo).</p>
              </div>
              <SettingsSaveButton
                onClick={saveLetterhead}
                saving={lhFlash.saving}
                saved={lhFlash.saved}
                label="Salvar Timbrado"
              />
            </div>
            </>
          )}

          {/* ── Tab: Identidade Visual (Fase 256 — fusão de Aparência +
              Cores + Tipografia + Templates + Exportar/Importar) ── */}
          {tab === "identidade" && (
            <>
            {/* ── Seção: Nome e Logo (antiga aba "Aparência") ── */}
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Nome e Logo do Sistema</p>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                    Nome do Sistema
                  </label>
                  <input
                    type="text"
                    value={appName}
                    onChange={(e) => setAppName(e.target.value)}
                    className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors"
                    placeholder="AFJ CORE"
                  />
                  <p className="text-[10px] text-afj-black/35 mt-1">
                    Nome do produto/software, exibido na interface — diferente de &quot;Nome do Escritório&quot; (aba Escritório), que é o nome legal usado nos documentos.
                  </p>
                </div>

                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                    Logo do Sistema
                  </label>
                  <input
                    ref={logoFileRef}
                    type="file"
                    accept="image/png,image/jpeg,image/svg+xml,image/webp"
                    className="hidden"
                    onChange={uploadLogoFile}
                  />
                  <button
                    type="button"
                    onClick={() => logoFileRef.current?.click()}
                    disabled={logoUploading}
                    className="w-full flex items-center justify-center gap-2 border-2 border-dashed border-afj-cream-dark hover:border-afj-gold/50 rounded-sm py-4 text-sm text-afj-black/50 hover:text-afj-black transition-colors disabled:opacity-60"
                  >
                    <ImageIcon size={18} className="text-afj-gold" />
                    {logoUploading ? "Enviando..." : "Clique para enviar imagem (PNG, JPG, SVG, WebP — máx. 2MB)"}
                  </button>
                  <p className="text-[10px] text-afj-black/35 mt-1.5">ou informe uma URL</p>
                  <input
                    type="url"
                    value={logoUrl}
                    onChange={(e) => setLogoUrl(e.target.value)}
                    className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors mt-1"
                    placeholder="https://..."
                  />
                  {logoUrl && (
                    <div className="mt-3 p-3 border border-afj-cream-dark rounded-sm bg-afj-cream/50">
                      <p className="text-[10px] text-afj-black/40 uppercase tracking-widest mb-2">Preview</p>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={logoUrl} alt="Logo preview" className="h-10 object-contain" />
                    </div>
                  )}
                  <label className="flex items-center gap-2 mt-3 cursor-pointer select-none">
                    <input
                      type="checkbox"
                      checked={useLogoAsFavicon}
                      onChange={(e) => setUseLogoAsFavicon(e.target.checked)}
                      className="accent-afj-gold w-4 h-4"
                    />
                    <span className="text-sm text-afj-black/70">Usar esta imagem também como favicon</span>
                  </label>
                </div>
              </div>

              <SettingsSaveButton
                onClick={() => saveBranding(
                  { app_name: appName, logo_url: logoUrl, ...(useLogoAsFavicon && logoUrl ? { favicon_url: logoUrl } : {}) },
                  marcaFlash,
                  "Nome e logo salvos."
                )}
                saving={marcaFlash.saving}
                saved={marcaFlash.saved}
                label="Salvar Nome e Logo"
              />
            </div>

            {/* ── Seção: Cores (antiga aba "Cores") ── */}
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Cor Primária</p>
              </div>

              <div className="flex items-center gap-4">
                <input
                  type="color"
                  value={previewColor}
                  onChange={(e) => applyColor(e.target.value)}
                  className="w-14 h-14 rounded-sm border border-afj-cream-dark cursor-pointer"
                />
                <div>
                  <input
                    type="text"
                    value={previewColor}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (/^#[0-9A-Fa-f]{0,6}$/.test(v)) {
                        setPreviewColor(v);
                        if (v.length === 7) applyColor(v);
                      }
                    }}
                    className="w-32 bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm font-mono focus:outline-none focus:border-afj-gold"
                    maxLength={7}
                  />
                  <p className="text-[10px] text-afj-black/40 mt-1">Código hexadecimal</p>
                </div>
              </div>

              <div>
                <p className="text-[10px] font-semibold text-afj-black/40 uppercase tracking-widest mb-3">
                  Paleta de presets
                </p>
                <div className="grid grid-cols-4 gap-2">
                  {COLOR_PRESETS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => applyColor(p.value)}
                      title={p.label}
                      className={`relative h-10 rounded-sm border-2 transition-all ${
                        previewColor === p.value ? "border-afj-black scale-105" : "border-transparent hover:scale-105"
                      }`}
                      style={{ backgroundColor: p.value }}
                    >
                      {previewColor === p.value && (
                        <Check size={12} className="absolute inset-0 m-auto text-white drop-shadow" />
                      )}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-4 gap-2 mt-1">
                  {COLOR_PRESETS.map((p) => (
                    <p key={p.value} className="text-[9px] text-afj-black/30 text-center truncate">{p.label}</p>
                  ))}
                </div>
              </div>

              {/* ── Cor do Menu (barra lateral) ── */}
              <div className="afj-section-header pt-2">
                <p className="afj-section-title">Cor do Menu (barra lateral)</p>
              </div>
              <p className="text-[11px] text-afj-black/45 -mt-2">
                Define o fundo da barra lateral de navegação. Use tons escuros — o texto do menu é claro.
              </p>

              <div className="flex items-center gap-4">
                <input
                  type="color"
                  value={previewSecondary}
                  onChange={(e) => applySecondary(e.target.value)}
                  className="w-14 h-14 rounded-sm border border-afj-cream-dark cursor-pointer"
                  aria-label="Selecionar cor do menu"
                />
                <div>
                  <input
                    type="text"
                    value={previewSecondary}
                    onChange={(e) => {
                      const v = e.target.value;
                      if (/^#[0-9A-Fa-f]{0,6}$/.test(v)) {
                        setPreviewSecondary(v);
                        if (v.length === 7) applySecondary(v);
                      }
                    }}
                    className="w-32 bg-afj-cream border border-afj-cream-dark rounded-sm px-3 py-2 text-sm font-mono focus:outline-none focus:border-afj-gold"
                    maxLength={7}
                  />
                  <p className="text-[10px] text-afj-black/40 mt-1">Código hexadecimal</p>
                </div>
                {/* Prévia do gradiente do menu */}
                <div
                  className="w-10 h-14 rounded-sm border border-afj-cream-dark ml-1"
                  style={{ background: `linear-gradient(180deg, ${previewSecondary} 0%, ${previewSecondary} 100%)` }}
                  aria-hidden
                />
              </div>

              <div>
                <p className="text-[10px] font-semibold text-afj-black/40 uppercase tracking-widest mb-3">
                  Tons de menu
                </p>
                <div className="grid grid-cols-4 gap-2">
                  {MENU_PRESETS.map((p) => (
                    <button
                      key={p.value}
                      onClick={() => applySecondary(p.value)}
                      title={p.label}
                      className={`relative h-10 rounded-sm border-2 transition-all ${
                        previewSecondary === p.value ? "border-afj-black scale-105" : "border-transparent hover:scale-105"
                      }`}
                      style={{ backgroundColor: p.value }}
                    >
                      {previewSecondary === p.value && (
                        <Check size={12} className="absolute inset-0 m-auto text-white drop-shadow" />
                      )}
                    </button>
                  ))}
                </div>
                <div className="grid grid-cols-4 gap-2 mt-1">
                  {MENU_PRESETS.map((p) => (
                    <p key={p.value} className="text-[9px] text-afj-black/30 text-center truncate">{p.label}</p>
                  ))}
                </div>
              </div>

              <SettingsSaveButton
                onClick={() => saveBranding(
                  { primary_color: previewColor, secondary_color: previewSecondary },
                  coresFlash,
                  "Cores salvas."
                )}
                saving={coresFlash.saving}
                saved={coresFlash.saved}
                label="Aplicar Cores"
              />
            </div>

            {/* ── Seção: Tipografia (antiga aba "Tipografia") ── */}
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Fonte de Destaque</p>
              </div>

              <div className="space-y-2">
                {FONTS.map((f) => (
                  <button
                    key={f.id}
                    onClick={() => {
                      setPreviewFont(f.css);
                      document.documentElement.style.setProperty("--font-display", f.css);
                    }}
                    className={`w-full text-left p-4 rounded-sm border transition-all ${
                      previewFont === f.css
                        ? "border-afj-gold bg-afj-gold/5"
                        : "border-afj-cream-dark hover:border-afj-gold/40 bg-white"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-afj-black text-sm" style={{ fontFamily: f.css }}>
                          {f.label}
                        </p>
                        <p className="text-afj-black/40 text-xs mt-0.5" style={{ fontFamily: f.css }}>
                          {f.sample}
                        </p>
                      </div>
                      {previewFont === f.css && (
                        <Check size={16} className="text-afj-gold flex-shrink-0" />
                      )}
                    </div>
                  </button>
                ))}
              </div>

              <p className="text-xs text-afj-black/30">
                A fonte é aplicada em títulos, cabeçalhos e elementos de destaque. O corpo do texto usa sempre Inter.
              </p>
              {/* Fase 256 — achado real, não corrigido nesta fase (exigiria
                  um campo novo persistido no backend, fora do escopo desta
                  reformulação): escolher uma fonte aqui sozinho só atualiza
                  a pré-visualização, não é salvo em lugar nenhum. Em vez de
                  deixar isso como uma armadilha silenciosa, o aviso abaixo
                  torna esse comportamento explícito. */}
              <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-sm px-3 py-2">
                Escolher uma fonte aqui atualiza só a pré-visualização — para persistir, aplique um dos Temas Prontos
                abaixo (que já salva cor e fonte juntos).
              </p>
            </div>

            {/* ── Seção: Temas Prontos (antiga aba "Templates") ── */}
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Temas Prontos</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => applyTemplate(t)}
                    disabled={templateFlash.saving}
                    className="text-left border border-afj-cream-dark rounded-sm overflow-hidden hover:border-afj-gold/50 hover:shadow-md transition-all group disabled:opacity-60"
                  >
                    {/* Thumbnail */}
                    <div
                      className="h-20 flex items-center justify-center gap-3"
                      style={{ background: `linear-gradient(135deg, ${t.secondary} 0%, ${t.secondary}dd 100%)` }}
                    >
                      <div className="w-8 h-8 rounded-sm" style={{ backgroundColor: t.primary }} />
                      <div className="space-y-1">
                        <div className="h-1.5 w-16 rounded-full" style={{ backgroundColor: t.primary, opacity: 0.8 }} />
                        <div className="h-1 w-12 rounded-full bg-white/20" />
                        <div className="h-1 w-10 rounded-full bg-white/15" />
                      </div>
                    </div>
                    <div className="p-3 bg-white">
                      <p className="font-semibold text-afj-black text-sm">{t.name}</p>
                      <p className="text-afj-black/40 text-xs mt-0.5">{t.desc}</p>
                    </div>
                  </button>
                ))}
              </div>

              <p className="text-xs text-afj-black/30">
                Ao aplicar um template, a cor, fundo e tipografia são atualizados instantaneamente e já ficam salvos —
                não precisa clicar em nenhum botão de salvar separado.
              </p>
            </div>

            {/* ── Seção: Exportar / Importar (antiga aba "Exportar/Importar") ── */}
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Exportar / Importar Tema</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="border border-afj-cream-dark rounded-sm p-5 text-center space-y-3">
                  <Download size={28} className="mx-auto text-afj-gold" />
                  <p className="font-semibold text-afj-black text-sm">Exportar Tema</p>
                  <p className="text-afj-black/40 text-xs">
                    Baixa as configurações de cor, fonte e nome do sistema como arquivo JSON.
                  </p>
                  <button onClick={exportTheme} className="btn-afj-primary py-2 rounded-sm w-full">
                    Exportar JSON
                  </button>
                </div>

                <div className="border border-afj-cream-dark rounded-sm p-5 text-center space-y-3">
                  <Upload size={28} className="mx-auto text-afj-gold" />
                  <p className="font-semibold text-afj-black text-sm">Importar Tema</p>
                  <p className="text-afj-black/40 text-xs">
                    Carrega um JSON exportado e aplica na pré-visualização — clique em Salvar em Cores/Nome e Logo,
                    acima, pra persistir de verdade.
                  </p>
                  <input
                    ref={importRef}
                    type="file"
                    accept=".json"
                    className="hidden"
                    onChange={importTheme}
                  />
                  <button
                    onClick={() => importRef.current?.click()}
                    className="btn-afj-outline py-2 rounded-sm w-full"
                  >
                    Importar JSON
                  </button>
                </div>
              </div>

              <div className="bg-afj-cream/60 border border-afj-cream-dark rounded-sm p-4">
                <p className="text-[10px] font-semibold text-afj-black/40 uppercase tracking-widest mb-2">
                  Configuração atual
                </p>
                <pre className="text-xs text-afj-black/60 font-mono whitespace-pre-wrap">
                  {JSON.stringify({ primaryColor: previewColor, fontDisplay: previewFont.split(",")[0], appName }, null, 2)}
                </pre>
              </div>
            </div>
            </>
          )}

          {/* ── Tab: Módulos ── */}
          {tab === "modulos" && (
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Módulos Disponíveis</p>
              </div>
              <div className="space-y-3">
                {[
                  { key: "processos", label: "Processos Jurídicos", desc: "Gestão de processos, prazos e movimentações" },
                  { key: "peticoes", label: "Petições com IA", desc: "Geração automática de petições via agentes" },
                  { key: "clientes", label: "CRM de Clientes", desc: "Cadastro e gestão de clientes (PF e PJ)" },
                  { key: "financeiro", label: "Financeiro", desc: "Receitas, despesas e controle financeiro" },
                  { key: "agentes", label: "Agentes IA", desc: "Painel de controle dos agentes de IA" },
                  { key: "visual_law", label: "Visual Law", desc: "Visualizações gráficas de processos" },
                ].map(({ key, label, desc }) => (
                  <div key={key} className="flex items-center justify-between p-4 border border-afj-cream-dark rounded-sm bg-white">
                    <div>
                      <p className="font-medium text-sm text-afj-black">{label}</p>
                      <p className="text-xs text-afj-black/40 mt-0.5">{desc}</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer ml-4">
                      <input type="checkbox" className="sr-only peer"
                        checked={modules[key] !== false}
                        onChange={(e) => setModules((m) => ({ ...m, [key]: e.target.checked }))} />
                      <div className="w-10 h-5 bg-afj-cream-dark peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-afj-gold" />
                    </label>
                  </div>
                ))}
              </div>
              {/* Fase 256 — achado real: nenhum desses 6 toggles tem efeito
                  hoje (confirmado por grep: `modules_enabled` não é lido em
                  `nav.ts` nem em nenhum guard de rota) — a legenda antiga
                  ("ficam ocultos no menu") prometia um comportamento que
                  não existe. Corrigido pra ser honesta em vez de remover
                  ou fingir a funcionalidade — construir o bloqueio de
                  verdade é uma feature nova, fora do escopo desta fase. */}
              <p className="text-[11px] text-afj-black/45 bg-afj-cream/60 border border-afj-cream-dark rounded-sm px-3 py-2">
                Estes 6 módulos ainda não afetam a navegação ou o acesso a telas — só registram a preferência.
              </p>

              {/* Fase 256 (Alteração 2) — antes só existiam em Integrações,
                  invisíveis aqui apesar de escreverem na mesma
                  TenantConfig.modules_enabled. */}
              <div className="afj-section-header pt-2">
                <p className="afj-section-title">Integrações Google</p>
              </div>
              <div className="space-y-3">
                {MODULOS_GOOGLE.map(({ key, label, desc }) => (
                  <div key={key} className="flex items-center justify-between p-4 border border-afj-cream-dark rounded-sm bg-white">
                    <div>
                      <p className="font-medium text-sm text-afj-black">{label}</p>
                      <p className="text-xs text-afj-black/40 mt-0.5">{desc}</p>
                    </div>
                    <label className="relative inline-flex items-center cursor-pointer ml-4">
                      <input type="checkbox" className="sr-only peer"
                        checked={modules[key] === true}
                        onChange={(e) => setModules((m) => ({ ...m, [key]: e.target.checked }))} />
                      <div className="w-10 h-5 bg-afj-cream-dark peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-0.5 after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:bg-afj-gold" />
                    </label>
                  </div>
                ))}
              </div>
              <p className="text-[11px] text-afj-black/45">
                Configure a credencial de acesso em Integrações — este toggle é o mesmo que aparece por lá.
              </p>

              <SettingsSaveButton
                onClick={saveModules}
                saving={modulesFlash.saving}
                saved={modulesFlash.saved}
                label="Salvar Módulos"
              />
            </div>
          )}

          {/* ── Tab: Dashboard ── */}
          {tab === "dashboard" && (
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Widgets do Dashboard</p>
              </div>
              <p className="text-sm text-afj-black/50">
                Selecione quais indicadores aparecem no dashboard principal.
              </p>
              <div className="space-y-2">
                {AVAILABLE_WIDGETS.map(({ key, label }) => (
                  <label key={key} className="flex items-center gap-3 p-3 border border-afj-cream-dark rounded-sm bg-white cursor-pointer hover:border-afj-gold/40 transition-colors">
                    <input type="checkbox" className="accent-afj-gold w-4 h-4"
                      checked={widgets.includes(key)}
                      onChange={(e) => setWidgets((w) => e.target.checked ? [...w, key] : w.filter((k) => k !== key))} />
                    <span className="text-sm text-afj-black">{label}</span>
                  </label>
                ))}
              </div>
              <SettingsSaveButton
                onClick={saveWidgets}
                saving={widgetsFlash.saving}
                saved={widgetsFlash.saved}
                label="Salvar Widgets"
              />
            </div>
          )}

          {/* ── Tab: Jurídico ── */}
          {tab === "juridico" && <JuridicoTab />}
        </div>

        {/* Preview lateral */}
        <div className="hidden lg:block">
          <LivePreview color={previewColor} font={previewFont} />
        </div>
      </div>

      {/* Modal histórico */}
      {showHistory && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4" onClick={() => setShowHistory(false)}>
          <div className="bg-white rounded-sm shadow-xl max-w-sm w-full p-6 space-y-4 max-h-[85vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h3 className="font-display text-lg font-semibold text-afj-black">Histórico de Temas</h3>
            {themeHistory.length === 0 ? (
              <p className="text-sm text-afj-black/40">Nenhuma alteração registrada ainda.</p>
            ) : (
              <div className="space-y-2">
                {themeHistory.map((entry, i) => (
                  <div key={i} className="flex items-center gap-3 p-3 border border-afj-cream-dark rounded-sm">
                    <div className="w-6 h-6 rounded-sm border border-afj-cream-dark flex-shrink-0" style={{ backgroundColor: entry.color }} />
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-medium text-afj-black truncate">{entry.appName}</p>
                      <p className="text-[10px] text-afj-black/40">{new Date(entry.ts).toLocaleString("pt-BR")}</p>
                    </div>
                    <button
                      onClick={() => {
                        applyColor(entry.color);
                        setAppName(entry.appName);
                        setShowHistory(false);
                      }}
                      className="text-xs text-afj-gold hover:underline"
                    >
                      Restaurar
                    </button>
                  </div>
                ))}
              </div>
            )}
            <button onClick={() => setShowHistory(false)} className="w-full btn-afj-outline rounded-sm">Fechar</button>
          </div>
        </div>
      )}
    </div>
  );
}
