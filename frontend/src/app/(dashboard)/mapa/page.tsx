"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { MapPin, RefreshCw, Loader2, Search, MousePointer2, ClipboardList, ChevronDown, ChevronUp } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import { useToast } from "@/components/ui/Toast";
import { useUserStore } from "@/store";
import { useConfirmDialog } from "@/hooks/useConfirmDialog";
import type { PontoEscritorio, PontoCliente, ResumoOperacional } from "@/components/mapa/EscritorioClientesMap";

// Leaflet acessa window/document no import — precisa ser client-only
// (mesmo padrão de GestaoCharts/ProcessosCharts em relatorios/page.tsx).
const EscritorioClientesMap = dynamic(() => import("@/components/mapa/EscritorioClientesMap"), {
  ssr: false,
  loading: () => <MapSkeleton />,
});

type EnderecoResponse = {
  cep?: string; logradouro?: string; bairro?: string; cidade?: string; uf?: string;
  latitude?: number | null; longitude?: number | null;
  geocode_source?: string | null;
};

// Fase 254 — versão "crua" do cliente, com cidade/UF preservados pra
// alimentar os filtros (o tipo que o mapa consome, PontoCliente, não
// carrega esses 2 campos separados — só o enderecoTexto já formatado).
type ClienteRaw = PontoCliente & { cidade: string; uf: string };

// Fase 255 — shape de GET /clients/geolocalizacao/auditoria.
type ItemAuditoria = {
  id: string; nome: string; cidade: string | null; uf: string | null; cep: string | null;
  status: "NAO_GEOCODIFICADO" | "REQUER_REVISAO" | "VALIDADA";
};
type Auditoria = {
  total: number;
  contagem: { NAO_GEOCODIFICADO: number; REQUER_REVISAO: number; VALIDADA: number };
  clientes: ItemAuditoria[];
};

function enderecoTexto(e: EnderecoResponse): string {
  return [e.logradouro, e.bairro, [e.cidade, e.uf].filter(Boolean).join("/")].filter(Boolean).join(" — ") || "Endereço não informado";
}

// Fase 254 — mesmo gate de "ação de gestão" já usado no endpoint de
// auditoria (`GET /clients/geolocalizacao/auditoria`, ADMIN/SOCIO/GESTOR)
// e no novo `PUT /clients/{id}/localizacao-manual` — inclui SUPERADMIN
// explicitamente (lição da Fase 236: nunca confiar só em "ADMIN" sem
// incluir o superconjunto).
const PODE_AJUSTAR = ["ADMIN", "SOCIO", "GESTOR", "SUPERADMIN"];

export default function MapaPage() {
  const toast = useToast();
  const userRole = useUserStore((s) => s.user?.role);
  const podeAjustar = PODE_AJUSTAR.includes(userRole ?? "");
  const { ask, confirmDialog } = useConfirmDialog();

  const [escritorio, setEscritorio] = useState<PontoEscritorio | null>(null);
  const [clientesRaw, setClientesRaw] = useState<ClienteRaw[]>([]);
  const [totalClientesComEndereco, setTotalClientesComEndereco] = useState(0);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  const [filtroCidade, setFiltroCidade] = useState("");
  const [filtroUf, setFiltroUf] = useState("");
  const [ajusteAtivo, setAjusteAtivo] = useState(false);

  // Fase 255 — painel de auditoria de geolocalização + correção em lote.
  const [auditoriaAberta, setAuditoriaAberta] = useState(false);
  const [auditoria, setAuditoria] = useState<Auditoria | null>(null);
  const [carregandoAuditoria, setCarregandoAuditoria] = useState(false);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [corrigindo, setCorrigindo] = useState(false);

  useEffect(() => {
    carregar();
  }, []);

  const headers = () => ({
    Authorization: `Bearer ${typeof window !== "undefined" ? localStorage.getItem("afj_access_token") : ""}`,
  });

  async function carregar() {
    setLoading(true);
    try {
      const [resEndereco, resClientes] = await Promise.all([
        fetch("/api/v1/tenant/endereco", { headers: headers() }),
        fetch("/api/v1/clients?limit=200", { headers: headers() }),
      ]);

      if (resEndereco.ok) {
        const e: EnderecoResponse = await resEndereco.json();
        setEscritorio(
          e.latitude != null && e.longitude != null
            ? { nome: "Escritório", latitude: e.latitude, longitude: e.longitude, enderecoTexto: enderecoTexto(e) }
            : null
        );
      }

      if (resClientes.ok) {
        const lista = await resClientes.json();
        const comEndereco = (Array.isArray(lista) ? lista : []).filter(
          (c: any) => c.endereco_json?.latitude != null && c.endereco_json?.longitude != null
        );
        setTotalClientesComEndereco(comEndereco.length);
        setClientesRaw(
          comEndereco.map((c: any) => ({
            id: c.id,
            nome: c.nome_completo,
            latitude: c.endereco_json.latitude,
            longitude: c.endereco_json.longitude,
            enderecoTexto: enderecoTexto(c.endereco_json),
            cidade: c.endereco_json.cidade || "",
            uf: c.endereco_json.uf || "",
            // Fase 253 — sem `geocode_source` = coordenada herdada de
            // antes do fix de causa-raiz (endereço mudou sem re-geocodificar).
            statusGeo: c.endereco_json.geocode_source ? "validada" : "requer_revisao",
          }))
        );
      }
    } finally {
      setLoading(false);
    }
  }

  // Fase 257.1 — resumo operacional pro popup do marcador, buscado sob
  // demanda no 1º popupopen de cada cliente (nunca pré-carregado pros
  // até 200 clientes de uma vez).
  async function carregarResumoCliente(clienteId: string): Promise<ResumoOperacional | null> {
    try {
      const res = await fetch(`/api/v1/clients/${clienteId}/mapa-resumo`, { headers: headers() });
      return res.ok ? await res.json() : null;
    } catch {
      return null;
    }
  }

  // Fase 254 — ajuste manual: nunca sobrescreve silenciosamente, só
  // depois do usuário confirmar no popup do marcador (EscritorioClientesMap).
  async function ajustarLocalizacao(clienteId: string, lat: number, lng: number) {
    try {
      const res = await fetch(`/api/v1/clients/${clienteId}/localizacao-manual`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ latitude: lat, longitude: lng }),
      });
      if (res.ok) {
        toast.success("Localização ajustada manualmente.");
        await carregar();
      } else {
        const d = await res.json().catch(() => ({}));
        toast.error(d.detail || "Erro ao ajustar localização.");
      }
    } catch {
      toast.error("Erro de conexão.");
    }
  }

  // Fase 255 — só relatório inicialmente (GET /clients/geolocalizacao/
  // auditoria já é read-only); a correção em lote pede seleção explícita
  // + confirmação, nunca "corrige tudo" sozinho.
  async function carregarAuditoria() {
    setCarregandoAuditoria(true);
    try {
      const res = await fetch("/api/v1/clients/geolocalizacao/auditoria", { headers: headers() });
      if (res.ok) {
        const d: Auditoria = await res.json();
        setAuditoria(d);
        setSelecionados(new Set());
      } else {
        toast.error("Não foi possível carregar a auditoria de geolocalização.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setCarregandoAuditoria(false);
    }
  }

  function toggleAuditoria() {
    const abrir = !auditoriaAberta;
    setAuditoriaAberta(abrir);
    if (abrir && !auditoria) carregarAuditoria();
  }

  const pendentes = useMemo(
    () => (auditoria?.clientes ?? []).filter((c) => c.status !== "VALIDADA"),
    [auditoria]
  );

  function toggleSelecionado(id: string) {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function selecionarTodosPendentes() {
    setSelecionados(new Set(pendentes.map((c) => c.id)));
  }

  async function corrigirSelecionados() {
    if (selecionados.size === 0) return;
    const confirmado = await ask({
      title: "Corrigir localização em lote",
      message: `Recalcular a localização de ${selecionados.size} cliente(s) selecionado(s)? Cada um será reconsultado na BrasilAPI — clientes sem CEP cadastrado são ignorados.`,
      confirmLabel: "Corrigir selecionados",
    });
    if (confirmado === null) return;

    setCorrigindo(true);
    try {
      const res = await fetch("/api/v1/clients/geolocalizacao/recalcular-lote", {
        method: "POST",
        headers: { "Content-Type": "application/json", ...headers() },
        body: JSON.stringify({ client_ids: Array.from(selecionados) }),
      });
      if (res.ok) {
        const d = await res.json();
        const ok = (d.processados || []).filter((p: any) => p.status === "ok").length;
        toast.success(`${ok} de ${d.solicitados} cliente(s) corrigido(s).`);
        await Promise.all([carregar(), carregarAuditoria()]);
      } else {
        const d = await res.json().catch(() => ({}));
        toast.error(d.detail || "Erro ao corrigir em lote.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setCorrigindo(false);
    }
  }

  const cidadesDisponiveis = useMemo(
    () => Array.from(new Set(clientesRaw.map((c) => c.cidade).filter(Boolean))).sort(),
    [clientesRaw]
  );
  const ufsDisponiveis = useMemo(
    () => Array.from(new Set(clientesRaw.map((c) => c.uf).filter(Boolean))).sort(),
    [clientesRaw]
  );

  const clientesFiltrados: PontoCliente[] = useMemo(() => {
    const buscaNorm = busca.trim().toLowerCase();
    return clientesRaw.filter((c) => {
      if (buscaNorm && !c.nome.toLowerCase().includes(buscaNorm)) return false;
      if (filtroCidade && c.cidade !== filtroCidade) return false;
      if (filtroUf && c.uf !== filtroUf) return false;
      return true;
    });
  }, [clientesRaw, busca, filtroCidade, filtroUf]);

  const filtroAtivo = !!(busca || filtroCidade || filtroUf);
  const semMarcadores = !loading && !escritorio && clientesRaw.length === 0;
  const semResultadoFiltro = !loading && !semMarcadores && filtroAtivo && !escritorio && clientesFiltrados.length === 0;

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Mapa" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Mapa</h1>
          <p className="text-afj-black/50 text-sm">
            Localização do escritório{clientesRaw.length > 0 || totalClientesComEndereco > 0 ? ` e ${totalClientesComEndereco} cliente(s) geocodificado(s)` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {podeAjustar && (
            <button
              onClick={toggleAuditoria}
              className={`rounded-sm flex items-center gap-2 px-3 py-2 text-sm border ${
                auditoriaAberta ? "bg-afj-gold text-white border-afj-gold" : "btn-afj-outline"
              }`}
              title="Ver relatório de geolocalização e corrigir clientes pendentes em lote"
            >
              <ClipboardList size={14} />
              Auditoria de Geolocalização
              {auditoriaAberta ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
            </button>
          )}
          {podeAjustar && !semMarcadores && (
            <button
              onClick={() => setAjusteAtivo((v) => !v)}
              className={`rounded-sm flex items-center gap-2 px-3 py-2 text-sm border ${
                ajusteAtivo
                  ? "bg-afj-gold text-white border-afj-gold"
                  : "btn-afj-outline"
              }`}
              title="Arrastar marcadores de cliente para corrigir manualmente a localização"
            >
              <MousePointer2 size={14} />
              {ajusteAtivo ? "Ajuste manual ativo" : "Ajustar manualmente"}
            </button>
          )}
          <button
            onClick={carregar}
            disabled={loading}
            className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50"
          >
            {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
            Atualizar
          </button>
        </div>
      </div>

      {ajusteAtivo && (
        <div className="afj-card p-3 text-xs text-afj-black/60 bg-afj-cream/40 border-l-2 border-afj-gold">
          Modo de ajuste manual ativo — arraste um marcador de cliente pra corrigir a localização e confirme
          no popup que abre. A alteração fica marcada como ajuste manual e não é sobrescrita automaticamente depois.
        </div>
      )}

      {auditoriaAberta && podeAjustar && (
        <div className="afj-card p-4 space-y-3">
          <h2 className="text-sm font-semibold text-afj-black">Auditoria de Geolocalização</h2>
          {carregandoAuditoria ? (
            <div className="flex items-center gap-2 text-sm text-afj-black/50">
              <Loader2 size={14} className="animate-spin" /> Carregando...
            </div>
          ) : !auditoria ? (
            <p className="text-sm text-afj-black/40">Nenhum dado carregado.</p>
          ) : (
            <>
              <div className="flex flex-wrap gap-4 text-sm">
                <span className="text-emerald-700">✓ Validada: {auditoria.contagem.VALIDADA}</span>
                <span className="text-amber-700">⚠ Requer revisão: {auditoria.contagem.REQUER_REVISAO}</span>
                <span className="text-afj-black/50">○ Não geocodificado: {auditoria.contagem.NAO_GEOCODIFICADO}</span>
              </div>
              {pendentes.length === 0 ? (
                <p className="text-sm text-afj-black/40">Nenhum cliente pendente — tudo validado.</p>
              ) : (
                <>
                  <div className="flex items-center gap-3 text-xs">
                    <button onClick={selecionarTodosPendentes} className="text-afj-gold hover:underline">
                      Selecionar todos os pendentes ({pendentes.length})
                    </button>
                    {selecionados.size > 0 && (
                      <button onClick={() => setSelecionados(new Set())} className="text-afj-black/50 hover:underline">
                        Limpar seleção
                      </button>
                    )}
                    <button
                      onClick={corrigirSelecionados}
                      disabled={selecionados.size === 0 || corrigindo}
                      className="btn-afj-primary text-xs py-1.5 px-3 rounded-sm disabled:opacity-50 ml-auto"
                    >
                      {corrigindo ? "Corrigindo..." : `Corrigir selecionados (${selecionados.size})`}
                    </button>
                  </div>
                  <div className="max-h-64 overflow-y-auto border border-afj-cream-dark rounded-sm">
                    <table className="w-full text-xs">
                      <tbody>
                        {pendentes.map((c) => (
                          <tr key={c.id} className="border-b border-afj-cream-dark last:border-0">
                            <td className="w-8 px-2 py-1.5">
                              <input
                                type="checkbox"
                                checked={selecionados.has(c.id)}
                                onChange={() => toggleSelecionado(c.id)}
                              />
                            </td>
                            <td className="px-2 py-1.5">{c.nome}</td>
                            <td className="px-2 py-1.5 text-afj-black/50">{[c.cidade, c.uf].filter(Boolean).join("/") || "—"}</td>
                            <td className="px-2 py-1.5">
                              {c.status === "REQUER_REVISAO" ? (
                                <span className="text-amber-700">⚠ Requer revisão</span>
                              ) : (
                                <span className="text-afj-black/50">○ Não geocodificado</span>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}

      {!semMarcadores && !loading && clientesRaw.length > 0 && (
        <div className="afj-card p-3 flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[180px]">
            <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-afj-black/30" />
            <input
              type="text" value={busca} onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar cliente por nome..."
              className="w-full pl-8 pr-3 py-2 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
            />
          </div>
          <select
            value={filtroCidade} onChange={(e) => setFiltroCidade(e.target.value)}
            className="px-3 py-2 text-sm border border-afj-cream-dark rounded-sm"
          >
            <option value="">Todas as cidades</option>
            {cidadesDisponiveis.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <select
            value={filtroUf} onChange={(e) => setFiltroUf(e.target.value)}
            className="px-3 py-2 text-sm border border-afj-cream-dark rounded-sm"
          >
            <option value="">Todas as UFs</option>
            {ufsDisponiveis.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
          {filtroAtivo && (
            <button
              onClick={() => { setBusca(""); setFiltroCidade(""); setFiltroUf(""); }}
              className="text-xs text-afj-black/50 hover:text-afj-black underline"
            >
              Limpar filtros
            </button>
          )}
          {filtroAtivo && (
            <span className="text-xs text-afj-black/40 ml-auto">
              {clientesFiltrados.length} de {clientesRaw.length} cliente(s)
            </span>
          )}
        </div>
      )}

      {loading ? (
        <MapSkeleton />
      ) : semMarcadores ? (
        <div className="afj-card p-12 text-center">
          <div className="mx-auto mb-3 flex justify-center">
            <MapPin size={28} className="text-afj-black/20" />
          </div>
          <p className="text-afj-black/40 text-sm">Nenhum endereço geocodificado ainda.</p>
          <p className="text-afj-black/30 text-xs mt-1">
            Cadastre o endereço do escritório em Configurações → Escritório, ou o endereço de um cliente
            com CEP — a localização é capturada automaticamente ao salvar.
          </p>
        </div>
      ) : semResultadoFiltro ? (
        <div className="afj-card p-12 text-center">
          <p className="text-afj-black/40 text-sm">Nenhum cliente encontrado com esse filtro.</p>
        </div>
      ) : (
        <div className="afj-card p-2 overflow-hidden relative">
          <EscritorioClientesMap
            escritorio={escritorio}
            clientes={clientesFiltrados}
            ajusteAtivo={ajusteAtivo}
            onAjustarLocalizacao={ajustarLocalizacao}
            carregarResumo={carregarResumoCliente}
          />
          <Legenda temEscritorio={!!escritorio} temRequerRevisao={clientesFiltrados.some((c) => c.statusGeo === "requer_revisao")} />
        </div>
      )}
      {confirmDialog}
    </div>
  );
}

function Legenda({ temEscritorio, temRequerRevisao }: { temEscritorio: boolean; temRequerRevisao: boolean }) {
  return (
    <div className="absolute bottom-4 left-4 z-[1000] bg-white/95 rounded-sm shadow-md px-3 py-2 text-[11px] text-afj-black/70 space-y-1 pointer-events-none">
      {temEscritorio && (
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: "rgb(var(--brand-primary))" }} />
          Escritório
        </div>
      )}
      <div className="flex items-center gap-1.5">
        <span className="inline-block w-2.5 h-2.5 rounded-full" style={{ backgroundColor: "rgb(var(--brand-secondary))" }} />
        Cliente
      </div>
      {temRequerRevisao && (
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-600" />
          Requer revisão
        </div>
      )}
    </div>
  );
}

function MapSkeleton() {
  return <div className="afj-card h-[560px] animate-pulse bg-afj-cream-dark/40" />;
}
