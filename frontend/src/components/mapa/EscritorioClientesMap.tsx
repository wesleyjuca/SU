"use client";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import L from "leaflet";
import "leaflet.heat";
import { LayersControl, MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
import MarkerClusterGroup from "react-leaflet-cluster";

export type PontoEscritorio = {
  nome: string;
  latitude: number;
  longitude: number;
  enderecoTexto: string;
};

export type PontoCliente = {
  id: string;
  nome: string;
  latitude: number;
  longitude: number;
  enderecoTexto: string;
  /** Fase 253 — "validada" (passou pelo fix de causa-raiz que compara CEP
   * novo x anterior antes de reutilizar coordenada) ou "requer_revisao"
   * (herdada de antes do fix — mesma classe de registro que pode ter
   * ficado com endereço novo + coordenada antiga). */
  statusGeo: "validada" | "requer_revisao";
};

/** Fase 257.1 — shape de `GET /clients/{id}/mapa-resumo`, buscado sob
 * demanda quando o popup de um marcador de cliente abre. */
export type ResumoOperacional = {
  score: number;
  banda: "saudavel" | "atencao" | "risco";
  processos_ativos: number;
  proximo_prazo: { descricao: string; data_prazo: string | null; data_fatal: string | null } | null;
};

const BANDA_LABEL: Record<ResumoOperacional["banda"], { texto: string; cor: string }> = {
  saudavel: { texto: "Saudável", cor: "text-emerald-700" },
  atencao: { texto: "Atenção", cor: "text-amber-700" },
  risco: { texto: "Risco", cor: "text-red-700" },
};

/** Fase 257.2 — distância em linha reta (haversine), sem custo/credencial
 * nova — não é rota real (evitaria depender de um serviço de roteamento
 * externo só pra essa métrica secundária), mas já dá uma noção útil de
 * proximidade pro advogado que está olhando o mapa. */
function distanciaKm(lat1: number, lng1: number, lat2: number, lng2: number): number {
  const R = 6371;
  const toRad = (v: number) => (v * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLng = toRad(lng2 - lng1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLng / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

/** Fase 231 — ícone de pin custom (evita o bug clássico do Leaflet com
 * bundlers: os paths das imagens padrão do marcador quebram sob webpack).
 * Lê a cor da marca em runtime via CSS var (--brand-primary/--brand-secondary,
 * canais RGB "R G B") pra ficar theme-aware — tenant pode ter cor própria. */
function corMarca(varName: string, fallbackRgb: string): string {
  if (typeof window === "undefined") return `rgb(${fallbackRgb})`;
  const canais = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return canais ? `rgb(${canais})` : `rgb(${fallbackRgb})`;
}

function pinIcon(cor: string, tamanho = 30) {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="${tamanho}" height="${tamanho}" viewBox="0 0 24 24" fill="${cor}" stroke="white" stroke-width="1.2">
      <path d="M12 0C7.6 0 4 3.6 4 8c0 6 8 16 8 16s8-10 8-16c0-4.4-3.6-8-8-8z"/>
      <circle cx="12" cy="8" r="3" fill="white"/>
    </svg>`;
  return L.divIcon({
    html: svg,
    className: "",
    iconSize: [tamanho, tamanho],
    iconAnchor: [tamanho / 2, tamanho],
    popupAnchor: [0, -tamanho],
  });
}

/** Enquadra automaticamente todos os marcadores — nunca um centro fixo
 * hardcoded, já que o escritório pode ficar em qualquer lugar do Brasil. */
function AjustarEnquadramento({ pontos }: { pontos: [number, number][] }) {
  const map = useMap();
  useMemo(() => {
    if (pontos.length === 1) {
      map.setView(pontos[0], 14);
    } else if (pontos.length > 1) {
      map.fitBounds(pontos, { padding: [40, 40], maxZoom: 15 });
    }
  }, [map, pontos]);
  return null;
}

/** Mapa de calor — camada alternativa aos marcadores de cliente
 * (`leaflet.heat`, única dependência nova; sem custo/chave de API,
 * puramente client-side). Substitui o cluster de pinos quando ativo, não
 * soma em cima — as duas visualizações juntas ficariam poluídas. */
function CamadaCalor({ pontos }: { pontos: [number, number][] }) {
  const map = useMap();
  useEffect(() => {
    if (pontos.length === 0) return;
    // leaflet.heat espera [lat, lng, intensidade] — peso uniforme (1) por
    // cliente, sem nenhuma métrica de ponderação real neste momento.
    const pontosComIntensidade: [number, number, number][] = pontos.map(([lat, lng]) => [lat, lng, 1]);
    const camada = L.heatLayer(pontosComIntensidade, { radius: 22, blur: 18, maxZoom: 16 }).addTo(map);
    return () => {
      map.removeLayer(camada);
    };
  }, [map, pontos]);
  return null;
}

/** Tela cheia (Fullscreen API nativa do navegador, sem plugin) muda o
 * tamanho do container do mapa via CSS, mas o Leaflet não recalcula o
 * canvas sozinho nessa transição — precisa de `invalidateSize()`
 * explícito, com um pequeno atraso pra a mudança de layout assentar. */
function InvalidarAoRedimensionar({ gatilho }: { gatilho: boolean }) {
  const map = useMap();
  useEffect(() => {
    const id = setTimeout(() => map.invalidateSize(), 150);
    return () => clearTimeout(id);
  }, [map, gatilho]);
  return null;
}

/** Marcador de cliente — mostra nome/endereço/distância/status +, sob
 * demanda, o resumo operacional. Correção de localização deslocada pra
 * dentro da Auditoria de Geolocalização (mapa/page.tsx) — este marcador
 * não é mais arrastável (o antigo "Ajustar manualmente" foi removido:
 * edição de coordenada crua era considerada desnecessária como ação
 * principal do mapa; correções agora passam por corrigir o ENDEREÇO
 * cadastrado, que já re-geocodifica sozinho ao salvar). */
function ClienteMarker({
  cliente,
  icon,
  escritorio,
  carregarResumo,
}: {
  cliente: PontoCliente;
  icon: L.DivIcon;
  /** Fase 257.2 — pra calcular a distância em linha reta até o escritório. */
  escritorio?: PontoEscritorio | null;
  /** Fase 257.1 — buscado sob demanda no 1º popupopen do marcador, nunca
   * pré-carregado pra todos os clientes de uma vez. */
  carregarResumo?: (id: string) => Promise<ResumoOperacional | null>;
}) {
  const [resumo, setResumo] = useState<ResumoOperacional | null | "carregando" | "erro">(null);

  function handlePopupOpen() {
    if (!carregarResumo || resumo !== null) return;
    setResumo("carregando");
    carregarResumo(cliente.id)
      .then((r) => setResumo(r ?? "erro"))
      .catch(() => setResumo("erro"));
  }

  const distancia = escritorio
    ? distanciaKm(escritorio.latitude, escritorio.longitude, cliente.latitude, cliente.longitude)
    : null;

  return (
    <Marker
      position={[cliente.latitude, cliente.longitude]}
      icon={icon}
      eventHandlers={{ popupopen: handlePopupOpen }}
    >
      <Popup minWidth={200} maxWidth={280}>
        <div className="space-y-1">
          <p className="font-semibold text-sm">{cliente.nome}</p>
          <p className="text-xs text-afj-black/60">{cliente.enderecoTexto}</p>
          {distancia != null && (
            <p className="text-[10px] text-afj-black/40">
              ≈ {distancia < 1 ? `${Math.round(distancia * 1000)} m` : `${distancia.toFixed(1)} km`} do escritório (linha reta)
            </p>
          )}
          {cliente.statusGeo === "requer_revisao" && (
            <p className="text-[10px] text-amber-700 mt-1">⚠ Localização requer revisão</p>
          )}

          {/* Fase 257.1 — resumo operacional, buscado sob demanda */}
          {resumo === "carregando" && (
            <p className="text-[10px] text-afj-black/35 pt-1">Carregando resumo...</p>
          )}
          {resumo === "erro" && (
            <p className="text-[10px] text-afj-black/35 pt-1">Não foi possível carregar o resumo.</p>
          )}
          {resumo && resumo !== "carregando" && resumo !== "erro" && (
            <div className="pt-1.5 mt-1.5 border-t border-afj-cream-dark space-y-1">
              <p className={`text-[11px] font-semibold ${BANDA_LABEL[resumo.banda].cor}`}>
                Saúde: {resumo.score}/100 ({BANDA_LABEL[resumo.banda].texto})
              </p>
              <p className="text-[11px] text-afj-black/60">
                {resumo.processos_ativos} processo(s) ativo(s)
              </p>
              {resumo.proximo_prazo ? (
                <p className="text-[11px] text-afj-black/60">
                  Próximo prazo: {formatarData(resumo.proximo_prazo.data_fatal || resumo.proximo_prazo.data_prazo)}
                  {resumo.proximo_prazo.data_fatal && <span className="text-red-700 font-semibold"> (FATAL)</span>}
                </p>
              ) : (
                <p className="text-[11px] text-afj-black/40">Sem prazo pendente</p>
              )}
            </div>
          )}

          <Link
            href={`/clientes/${cliente.id}`}
            className="block pt-1.5 mt-1.5 border-t border-afj-cream-dark text-[11px] font-semibold text-afj-gold hover:underline"
          >
            Ver cliente completo →
          </Link>
        </div>
      </Popup>
    </Marker>
  );
}

function formatarData(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("pt-BR");
}

export default function EscritorioClientesMap({
  escritorio,
  clientes,
  carregarResumo,
  mostrarCalor = false,
  emTelaCheia = false,
}: {
  escritorio: PontoEscritorio | null;
  clientes: PontoCliente[];
  /** Fase 257.1 — resumo operacional (score/processos/próximo prazo) do
   * popup de cliente, buscado sob demanda no chamador. */
  carregarResumo?: (id: string) => Promise<ResumoOperacional | null>;
  /** Alterna cluster de pinos ⇄ mapa de calor dos clientes. */
  mostrarCalor?: boolean;
  /** Só usado pra disparar `invalidateSize()` do Leaflet quando o
   * container entra/sai da Fullscreen API (controlada pelo chamador). */
  emTelaCheia?: boolean;
}) {
  const iconeEscritorio = useMemo(() => pinIcon(corMarca("--brand-primary", "184 149 74"), 34), []);
  const iconeCliente = useMemo(() => pinIcon(corMarca("--brand-secondary", "30 34 41"), 26), []);

  const pontos: [number, number][] = [
    ...(escritorio ? [[escritorio.latitude, escritorio.longitude] as [number, number]] : []),
    ...clientes.map((c) => [c.latitude, c.longitude] as [number, number]),
  ];
  const pontosClientes: [number, number][] = clientes.map((c) => [c.latitude, c.longitude]);

  if (pontos.length === 0) return null;

  return (
    <MapContainer
      center={pontos[0]}
      zoom={13}
      scrollWheelZoom
      style={{ height: emTelaCheia ? "100%" : "560px", width: "100%", borderRadius: "2px" }}
    >
      {/* Camadas — Padrão (OSM, sem chave) já era a única opção; Satélite
          (Esri World Imagery) e Terreno (OpenTopoMap) são igualmente
          gratuitas/sem credencial, mesmo espírito da camada já existente.
          `LayersControl` é nativo do react-leaflet — sem UI customizada. */}
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name="Padrão">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Satélite">
          <TileLayer
            attribution="Tiles &copy; Esri &mdash; Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
            url="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
          />
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="Terreno">
          <TileLayer
            attribution='Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, SRTM | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (CC-BY-SA)'
            url="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png"
          />
        </LayersControl.BaseLayer>
      </LayersControl>
      <AjustarEnquadramento pontos={pontos} />
      <InvalidarAoRedimensionar gatilho={emTelaCheia} />
      {escritorio && (
        <Marker position={[escritorio.latitude, escritorio.longitude]} icon={iconeEscritorio}>
          <Popup>
            <p className="font-semibold text-sm">{escritorio.nome}</p>
            <p className="text-xs text-afj-black/60">{escritorio.enderecoTexto}</p>
            <p className="text-[10px] text-afj-gold uppercase tracking-widest mt-1">Escritório</p>
          </Popup>
        </Marker>
      )}
      {mostrarCalor ? (
        <CamadaCalor pontos={pontosClientes} />
      ) : (
        // Fase 254 — clustering só nos marcadores de cliente (o do
        // escritório é único, não faz sentido agrupar).
        <MarkerClusterGroup chunkedLoading>
          {clientes.map((c) => (
            <ClienteMarker
              key={c.id}
              cliente={c}
              icon={iconeCliente}
              escritorio={escritorio}
              carregarResumo={carregarResumo}
            />
          ))}
        </MarkerClusterGroup>
      )}
    </MapContainer>
  );
}
