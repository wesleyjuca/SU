"use client";
import { useState, useRef } from "react";
import { Palette, Type, Layout, Download, Upload, Check, Sun } from "lucide-react";
import { applyTheme } from "@/lib/theme";
import { useThemeStore } from "@/store";
import { Breadcrumb } from "@/components/layout/Breadcrumb";

const TABS = [
  { id: "marca", label: "Marca", icon: Layout },
  { id: "cores", label: "Cores", icon: Palette },
  { id: "tipografia", label: "Tipografia", icon: Type },
  { id: "templates", label: "Templates", icon: Sun },
  { id: "exportar", label: "Exportar / Importar", icon: Download },
] as const;
type TabId = (typeof TABS)[number]["id"];

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

export default function PersonalizacaoPage() {
  const { theme, setTheme } = useThemeStore();
  const [tab, setTab] = useState<TabId>("marca");
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [previewColor, setPreviewColor] = useState(theme.primaryColor);
  const [previewFont, setPreviewFont] = useState("Optima, 'Optima Nova', Georgia, serif");
  const [appName, setAppName] = useState(theme.appName);
  const [logoUrl, setLogoUrl] = useState(theme.logoUrl ?? "");
  const importRef = useRef<HTMLInputElement>(null);

  async function saveBranding(updates: Record<string, string>) {
    setSaving(true);
    try {
      const token = localStorage.getItem("afj_access_token");
      await fetch("/api/v1/tenant/branding", {
        method: "PUT",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(updates),
      });
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
    } catch {}
    setSaving(false);
  }

  function applyColor(color: string) {
    setPreviewColor(color);
    applyTheme({ ...theme, primaryColor: color });
    setTheme({ ...theme, primaryColor: color });
  }

  function applyTemplate(t: (typeof TEMPLATES)[number]) {
    setPreviewColor(t.primary);
    const f = FONTS.find((f) => f.id === t.font.toLowerCase()) ?? FONTS[0];
    setPreviewFont(f.css);
    document.documentElement.style.setProperty("--brand-primary", t.primary);
    document.documentElement.style.setProperty("--brand-secondary", t.secondary);
    document.documentElement.style.setProperty("--brand-accent", t.accent);
    document.documentElement.style.setProperty("--font-display", f.css);
    applyTheme({ ...theme, primaryColor: t.primary, secondaryColor: t.secondary, accentColor: t.accent });
    setTheme({ ...theme, primaryColor: t.primary, secondaryColor: t.secondary, accentColor: t.accent });
    saveBranding({ primary_color: t.primary, secondary_color: t.secondary, accent_color: t.accent });
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
      } catch {}
    };
    reader.readAsText(file);
  }

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Admin" }, { label: "Personalização" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="afj-page-title">Personalização do Sistema</h1>
          <p className="text-afj-black/40 text-sm mt-0.5">Configure a identidade visual, cores, tipografia e temas do sistema.</p>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-afj-cream border border-afj-cream-dark rounded-sm p-1 overflow-x-auto">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setTab(id)}
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

          {/* ── Tab: Marca ── */}
          {tab === "marca" && (
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Identidade da Marca</p>
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
                </div>

                <div>
                  <label className="block text-[10px] font-semibold text-afj-black/55 mb-1.5 uppercase tracking-widest">
                    URL do Logo (opcional)
                  </label>
                  <input
                    type="url"
                    value={logoUrl}
                    onChange={(e) => setLogoUrl(e.target.value)}
                    className="w-full bg-afj-cream border border-afj-cream-dark rounded-sm px-4 py-2.5 text-sm focus:outline-none focus:border-afj-gold focus:bg-white transition-colors"
                    placeholder="https://..."
                  />
                  {logoUrl && (
                    <div className="mt-3 p-3 border border-afj-cream-dark rounded-sm bg-afj-cream/50">
                      <p className="text-[10px] text-afj-black/40 uppercase tracking-widest mb-2">Preview</p>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img src={logoUrl} alt="Logo preview" className="h-10 object-contain" />
                    </div>
                  )}
                </div>
              </div>

              <button
                onClick={() => saveBranding({ app_name: appName, logo_url: logoUrl })}
                disabled={saving}
                className="btn-afj-primary py-2.5 rounded-sm flex items-center gap-2"
              >
                {saved ? <Check size={14} /> : null}
                {saving ? "Salvando..." : saved ? "Salvo!" : "Salvar Marca"}
              </button>
            </div>
          )}

          {/* ── Tab: Cores ── */}
          {tab === "cores" && (
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

              <button
                onClick={() => saveBranding({ primary_color: previewColor })}
                disabled={saving}
                className="btn-afj-primary py-2.5 rounded-sm flex items-center gap-2"
              >
                {saved ? <Check size={14} /> : null}
                {saving ? "Salvando..." : saved ? "Salvo!" : "Aplicar Cor"}
              </button>
            </div>
          )}

          {/* ── Tab: Tipografia ── */}
          {tab === "tipografia" && (
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
            </div>
          )}

          {/* ── Tab: Templates ── */}
          {tab === "templates" && (
            <div className="afj-card p-6 space-y-5">
              <div className="afj-section-header">
                <p className="afj-section-title">Temas Prontos</p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {TEMPLATES.map((t) => (
                  <button
                    key={t.id}
                    onClick={() => applyTemplate(t)}
                    className="text-left border border-afj-cream-dark rounded-sm overflow-hidden hover:border-afj-gold/50 hover:shadow-md transition-all group"
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
                Ao aplicar um template, a cor, fundo e tipografia são atualizados instantaneamente.
                As alterações são persistidas no banco de dados.
              </p>
            </div>
          )}

          {/* ── Tab: Exportar / Importar ── */}
          {tab === "exportar" && (
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
                    Carrega um arquivo JSON de tema exportado anteriormente e aplica as configurações.
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
          )}
        </div>

        {/* Preview lateral */}
        <div className="hidden lg:block">
          <LivePreview color={previewColor} font={previewFont} />
        </div>
      </div>
    </div>
  );
}
