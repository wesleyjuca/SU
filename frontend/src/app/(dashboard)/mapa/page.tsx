"use client";
import { useEffect, useMemo, useState } from "react";
import dynamic from "next/dynamic";
import { MapPin, RefreshCw, Loader2, Search, ClipboardList, ChevronDown, ChevronUp, RotateCw, Pencil } from "lucide-react";
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
// Fase pós-260.2 — ganha tipo/status/segmento (já vinham em GET /clients,
// só eram descartados aqui) pra alimentar os filtros de carteira novos.
type ClienteRaw = PontoCliente & {
  cidade: string;
  uf: string;
  tipo: string;
  status: string;
  segmento: string;
};

// Fase 255 — shape de GET /clients/geolocalizacao/auditoria. Fase pós-260.2
// — ganha geocode_source (já vinha na resposta do backend, só não estava
// tipado aqui) pra derivar o rótulo de precisão aproximada/precisa.
type ItemAuditoria = {
  id: string; nome: string; cidade: string | null; uf: string | null; cep: string | null;
  geocode_source: string | null;
  status: "NAO_GEOCODIFICADO" | "REQUER_REVISAO" | "VALIDADA";
};
type Auditoria = {
  total: number;
  contagem: { NAO_GEOCODIFICADO: number; REQUER_REVISAO: number; VALIDADA: number };
  clientes: ItemAuditoria[];
};

const TIPO_LABEL: Record<string, string> = { PF: "Pessoa Física", PJ: "Pessoa Jurídica" };
const STATUS_LABEL: Record<string, string> = { PROSPECTO: "Prospecto", ATIVO: "Ativo", INATIVO: "Inativo" };
const SEGMENTO_LABEL: Record<string, string> = {
  PLATINUM: "Platinum", GOLD: "Gold", SILVER: "Silver", REGULAR: "Regular",
};

function enderecoTexto(e: EnderecoResponse): string {
  return [e.logradouro, e.bairro, [e.cidade, e.uf].filter(Boolean).join("/")].filter(Boolean).join(" — ") || "Endereço não informado";
}

// Fase 254 — mesmo gate de "ação de gestão" já usado no endpoint de
// auditoria (`GET /clients/geolocalizacao/auditoria`, ADMIN/SOCIO/GESTOR)
// — inclui SUPERADMIN explicitamente (lição da Fase 236: nunca confiar só
// em "ADMIN" sem incluir o superconjunto). Coincide com o gate de nav
// pra /mapa (GESTAO) — todo papel que vê esta tela já pode auditar.
const PODE_AJUSTAR = ["ADMIN", "SOCIO", "GESTOR", "SUPERADMIN"];

export default function MapaPage() {
  const toast = useToast();
  const userRole = useUserStore((s) => s.user?.role);
  const podeAjustar = PODE_AJUSTAR.includes(userRole ?? "");
  const { ask, confirmDialog } = useConfirmDialog();

  const [escritorio, setEscritorio] = useState<PontoEscritorio | null>(null);
  const [clientesRaw, setClientesRaw] = useState<ClienteRaw[]>([]);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  const [filtroCidade, setFiltroCidade] = useState("");
  const [filtroUf, setFiltroUf] = useState("");
  const [filtroTipo, setFiltroTipo] = useState("");
  const [filtroStatus, setFiltroStatus] = useState("");
  const [filtroSegmento, setFiltroSegmento] = useState("");

  // Fase 255 — painel de auditoria de geolocalização + correção em lote.
  // Fase pós-260.2 — buscada de forma eager no mount (não mais só ao abrir
  // o painel), pra alimentar os indicadores de topo com uma única fonte de
  // verdade (cobre a carteira inteira, não só quem já tem pino no mapa).
  const [auditoriaAberta, setAuditoriaAberta] = useState(false);
  const [auditoria, setAuditoria] = useState<Auditoria | null>(null);
  const [carregandoAuditoria, setCarregandoAuditoria] = useState(false);
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [corrigindo, setCorrigindo] = useState(false);
  const [recalculandoIds, setRecalculandoIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    carregar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Fase pós-260.2 — `userRole`/`podeAjustar` só resolvem depois que o
  // Zustand store de usuário hidrata (user começa null) — buscar a
  // auditoria já no efeito de mount (deps []) capturaria `podeAjustar`
  // ainda false na maioria das vezes e nunca mais tentaria de novo. Efeito
  // separado, reagindo a `podeAjustar`, garante que a busca dispara assim
  // que o papel do usuário for conhecido.
  useEffect(() => {
    if (podeAjustar) carregarAuditoria();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [podeAjustar]);

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
        setClientesRaw(
          comEndereco.map((c: any) => ({
            id: c.id,
            nome: c.nome_completo,
            latitude: c.endereco_json.latitude,
            longitude: c.endereco_json.longitude,
            enderecoTexto: enderecoTexto(c.endereco_json),
            cidade: c.endereco_json.cidade || "",
            uf: c.endereco_json.uf || "",
            tipo: c.tipo || "",
            status: c.status || "",
            segmento: c.segmento || "",
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

  // Fase 255 — só relatório (GET /clients/geolocalizacao/auditoria já é
  // read-only); a correção em lote ou individual pede seleção/ação
  // explícita, nunca "corrige tudo" sozinho.
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
    setAuditoriaAberta((v) => !v);
  }

  const pendentes = useMemo(
    () => (auditoria?.clientes ?? []).filter((c) => c.status !== "VALIDADA"),
    [auditoria]
  );

  // Fase pós-260.2 — "baixa/aproximada precisão" pedida na melhoria da
  // Auditoria: sem nenhum campo novo de precisão no backend, deriva só de
  // reinterpretar `geocode_source` já existente — "brasilapi" só localiza
  // por CEP (nível de quadra), "nominatim" localiza por endereço+número
  // (mais preciso). Informativo, não bloqueia nada.
  const aproximados = useMemo(
    () => (auditoria?.clientes ?? []).filter((c) => c.status === "VALIDADA" && c.geocode_source === "brasilapi").length,
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

  // Fase pós-260.2 — correção contextual individual, direto na linha da
  // Auditoria (substitui o antigo botão global "Ajustar manualmente").
  // Reaproveita o endpoint single já existente (POST .../recalcular-
  // localizacao) — útil quando o CEP já está certo mas a geocodificação
  // falhou/está desatualizada (cobre principalmente REQUER_REVISAO).
  async function recalcularUm(clienteId: string) {
    setRecalculandoIds((prev) => new Set(prev).add(clienteId));
    try {
      const res = await fetch(`/api/v1/clients/${clienteId}/recalcular-localizacao`, {
        method: "POST",
        headers: headers(),
      });
      if (res.ok) {
        toast.success("Localização recalculada.");
        await Promise.all([carregar(), carregarAuditoria()]);
      } else {
        const d = await res.json().catch(() => ({}));
        toast.error(d.detail || "Erro ao recalcular localização.");
      }
    } catch {
      toast.error("Erro de conexão.");
    } finally {
      setRecalculandoIds((prev) => {
        const next = new Set(prev);
        next.delete(clienteId);
        return next;
      });
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
  const tiposDisponiveis = useMemo(
    () => Array.from(new Set(clientesRaw.map((c) => c.tipo).filter(Boolean))).sort(),
    [clientesRaw]
  );
  const statusDisponiveis = useMemo(
    () => Array.from(new Set(clientesRaw.map((c) => c.status).filter(Boolean))).sort(),
    [clientesRaw]
  );
  const segmentosDisponiveis = useMemo(
    () => Array.from(new Set(clientesRaw.map((c) => c.segmento).filter(Boolean))).sort(),
    [clientesRaw]
  );

  const clientesFiltrados: PontoCliente[] = useMemo(() => {
    const buscaNorm = busca.trim().toLowerCase();
    return clientesRaw.filter((c) => {
      if (buscaNorm && !c.nome.toLowerCase().includes(buscaNorm)) return false;
      if (filtroCidade && c.cidade !== filtroCidade) return false;
      if (filtroUf && c.uf !== filtroUf) return false;
      if (filtroTipo && c.tipo !== filtroTipo) return false;
      if (filtroStatus && c.status !== filtroStatus) return false;
      if (filtroSegmento && c.segmento !== filtroSegmento) return false;
      return true;
    });
  }, [clientesRaw, busca, filtroCidade, filtroUf, filtroTipo, filtroStatus, filtroSegmento]);

  const filtroAtivo = !!(busca || filtroCidade || filtroUf || filtroTipo || filtroStatus || filtroSegmento);
  const semMarcadores = !loading && !escritorio && clientesRaw.length === 0;
  const semResultadoFiltro = !loading && !semMarcadores && filtroAtivo && !escritorio && clientesFiltrados.length === 0;

  // Fase pós-260.2 — indicadores de topo, fonte única (auditoria, cobre a
  // carteira inteira — sem o cap de 200 do GET /clients usado pro mapa em
  // si). "—" enquanto carrega, nunca "0" antes de resolver.
  const geocodificados = auditoria ? auditoria.contagem.VALIDADA + auditoria.contagem.REQUER_REVISAO : null;
  const semLocalizacao = auditoria ? auditoria.contagem.NAO_GEOCODIFICADO : null;
  const cidadesCarteira = auditoria
    ? new Set(auditoria.clientes.map((c) => c.cidade).filter(Boolean)).size
    : null;
  const ufsCarteira = auditoria ? new Set(auditoria.clientes.map((c) => c.uf).filter(Boolean)).size : null;
  const capAtingido = clientesRaw.length >= 200;

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Mapa" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Mapa</h1>
          <p className="text-afj-black/50 text-sm">Localização do escritório e da carteira de clientes.</p>
        </div>
        <div className="flex items-center gap-2">
          {podeAjustar && (
            <button
              onClick={toggleAuditoria}
              className={`rounded-sm flex items-center gap-2 px-3 py-2 text-sm border ${
                auditoriaAberta ? "bg-afj-gold text-white border-afj-gold" : "btn-afj-outline"
              }`}
              title="Ver relatório de geolocalização e corrigir clientes pendentes"
            >
              <ClipboardList size={14} />
              Auditoria de Geolocalização
              {auditoriaAberta ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
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

      {/* Fase pós-260.2 — indicadores de topo (painel geográfico da
          carteira, não só visualização de pinos). */}
      <div className="afj-card p-3 flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <Indicador label="Geocodificados" valor={geocodificados} />
        <Indicador label="Sem localização" valor={semLocalizacao} />
        <Indicador label="Cidades" valor={cidadesCarteira} />
        <Indicador label="UFs" valor={ufsCarteira} />
        {capAtingido && (
          <span
            className="text-[11px] text-afj-black/40 ml-auto self-center"
            title="O mapa mostra no máximo 200 clientes por vez — os indicadores acima cobrem a carteira inteira, mas o mapa e os filtros abaixo podem mostrar menos pinos do que o total geocodificado."
          >
            ⓘ mapa limitado a 200 clientes
          </span>
        )}
      </div>

      {auditoriaAberta && podeAjustar && (
        <div className="afj-card p-4 space-y-3">
          <h2 className="text-sm font-semibold text-afj-black">Auditoria de Geolocalização</h2>
          {carregandoAuditoria && !auditoria ? (
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
                <span
                  className="text-afj-black/50"
                  title="Validados, mas localizados só pelo CEP (nível de quadra) — considere corrigir o número do endereço pra uma localização mais precisa."
                >
                  📍 Precisão aproximada: {aproximados}
                </span>
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
                  <div className="max-h-80 overflow-y-auto border border-afj-cream-dark rounded-sm">
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
                            <td className="px-2 py-1.5 whitespace-nowrap">
                              <div className="flex items-center gap-2">
                                <button
                                  onClick={() => recalcularUm(c.id)}
                                  disabled={recalculandoIds.has(c.id)}
                                  className="flex items-center gap-1 text-afj-gold hover:underline disabled:opacity-50"
                                  title="Refazer a geocodificação a partir do CEP já cadastrado"
                                >
                                  <RotateCw size={11} className={recalculandoIds.has(c.id) ? "animate-spin" : ""} />
                                  Recalcular
                                </button>
                                <a
                                  href={`/clientes?editar=${c.id}`}
                                  target="_blank"
                                  rel="noopener noreferrer"
                                  className="flex items-center gap-1 text-afj-black/60 hover:text-afj-gold hover:underline"
                                  title="Corrigir o endereço cadastrado (abre em nova aba) — a geocodificação já é refeita automaticamente ao salvar"
                                >
                                  <Pencil size={11} />
                                  Corrigir endereço
                                </a>
                              </div>
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
          <select
            value={filtroTipo} onChange={(e) => setFiltroTipo(e.target.value)}
            className="px-3 py-2 text-sm border border-afj-cream-dark rounded-sm"
          >
            <option value="">Todos os tipos</option>
            {tiposDisponiveis.map((t) => <option key={t} value={t}>{TIPO_LABEL[t] || t}</option>)}
          </select>
          <select
            value={filtroStatus} onChange={(e) => setFiltroStatus(e.target.value)}
            className="px-3 py-2 text-sm border border-afj-cream-dark rounded-sm"
          >
            <option value="">Todos os status</option>
            {statusDisponiveis.map((s) => <option key={s} value={s}>{STATUS_LABEL[s] || s}</option>)}
          </select>
          <select
            value={filtroSegmento} onChange={(e) => setFiltroSegmento(e.target.value)}
            className="px-3 py-2 text-sm border border-afj-cream-dark rounded-sm"
          >
            <option value="">Todos os segmentos</option>
            {segmentosDisponiveis.map((s) => <option key={s} value={s}>{SEGMENTO_LABEL[s] || s}</option>)}
          </select>
          {filtroAtivo && (
            <button
              onClick={() => {
                setBusca(""); setFiltroCidade(""); setFiltroUf("");
                setFiltroTipo(""); setFiltroStatus(""); setFiltroSegmento("");
              }}
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
            carregarResumo={carregarResumoCliente}
          />
          <Legenda temEscritorio={!!escritorio} temRequerRevisao={clientesFiltrados.some((c) => c.statusGeo === "requer_revisao")} />
        </div>
      )}
      {confirmDialog}
    </div>
  );
}

function Indicador({ label, valor }: { label: string; valor: number | null }) {
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="font-display text-lg font-semibold text-afj-black">{valor ?? "—"}</span>
      <span className="text-afj-black/50 text-xs">{label}</span>
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
