"use client";
import "leaflet/dist/leaflet.css";
import "leaflet.markercluster/dist/MarkerCluster.css";
import "leaflet.markercluster/dist/MarkerCluster.Default.css";
import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";
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

/** Fase 254 — marcador de cliente com suporte a ajuste manual (arrastar).
 * Extraído num componente próprio porque cada marcador precisa da sua
 * própria referência do Leaflet (pra reverter a posição se o usuário
 * cancelar) e do seu próprio estado de "aguardando confirmação" — nunca
 * salva direto no dragend, só depois de o usuário confirmar
 * explicitamente (mesmo fluxo pedido: arrastar → confirmar → salvar,
 * nunca sobrescreve a geolocalização automática silenciosamente). */
function ClienteMarker({
  cliente,
  icon,
  ajusteAtivo,
  onAjustarLocalizacao,
}: {
  cliente: PontoCliente;
  icon: L.DivIcon;
  ajusteAtivo: boolean;
  onAjustarLocalizacao?: (id: string, lat: number, lng: number) => Promise<void>;
}) {
  const markerRef = useRef<L.Marker>(null);
  const posOriginal: [number, number] = [cliente.latitude, cliente.longitude];
  const [pendente, setPendente] = useState<{ lat: number; lng: number } | null>(null);
  const [salvando, setSalvando] = useState(false);

  // Se o modo de ajuste for desativado (ou a coordenada mudar por baixo,
  // ex. depois de salvar) com uma alteração ainda não confirmada, reverte
  // — nunca deixa um arrasto pendurado sem decisão explícita do usuário.
  useEffect(() => {
    if (!ajusteAtivo && pendente) {
      markerRef.current?.setLatLng(posOriginal);
      setPendente(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ajusteAtivo]);

  function handleDragEnd() {
    const marker = markerRef.current;
    if (!marker) return;
    const { lat, lng } = marker.getLatLng();
    setPendente({ lat, lng });
    marker.openPopup();
  }

  function cancelar() {
    markerRef.current?.setLatLng(posOriginal);
    setPendente(null);
  }

  async function confirmar() {
    if (!pendente || !onAjustarLocalizacao) return;
    setSalvando(true);
    try {
      await onAjustarLocalizacao(cliente.id, pendente.lat, pendente.lng);
      setPendente(null);
    } finally {
      setSalvando(false);
    }
  }

  return (
    <Marker
      ref={markerRef}
      position={posOriginal}
      icon={icon}
      draggable={ajusteAtivo}
      eventHandlers={ajusteAtivo ? { dragend: handleDragEnd } : {}}
    >
      <Popup>
        {pendente ? (
          <div className="space-y-1.5 min-w-[160px]">
            <p className="font-semibold text-sm">Confirmar nova localização?</p>
            <p className="text-xs text-afj-black/60">{cliente.nome}</p>
            <p className="text-[10px] text-afj-black/40">{pendente.lat.toFixed(5)}, {pendente.lng.toFixed(5)}</p>
            <div className="flex gap-2 pt-1">
              <button
                type="button" onClick={confirmar} disabled={salvando}
                className="text-xs px-2 py-1 bg-afj-gold text-white rounded-sm disabled:opacity-50"
              >
                {salvando ? "Salvando..." : "Confirmar"}
              </button>
              <button
                type="button" onClick={cancelar} disabled={salvando}
                className="text-xs px-2 py-1 border border-afj-cream-dark rounded-sm"
              >
                Cancelar
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="font-semibold text-sm">{cliente.nome}</p>
            <p className="text-xs text-afj-black/60">{cliente.enderecoTexto}</p>
            {cliente.statusGeo === "requer_revisao" && (
              <p className="text-[10px] text-amber-700 mt-1">⚠ Localização requer revisão</p>
            )}
            {ajusteAtivo && (
              <p className="text-[10px] text-afj-black/40 mt-1">Arraste o marcador pra ajustar a localização.</p>
            )}
          </>
        )}
      </Popup>
    </Marker>
  );
}

export default function EscritorioClientesMap({
  escritorio,
  clientes,
  ajusteAtivo = false,
  onAjustarLocalizacao,
}: {
  escritorio: PontoEscritorio | null;
  clientes: PontoCliente[];
  /** Fase 254 — modo de ajuste manual (arrastar marcador de cliente),
   * role-gated no chamador (mapa/page.tsx). */
  ajusteAtivo?: boolean;
  onAjustarLocalizacao?: (id: string, lat: number, lng: number) => Promise<void>;
}) {
  const iconeEscritorio = useMemo(() => pinIcon(corMarca("--brand-primary", "184 149 74"), 34), []);
  const iconeCliente = useMemo(() => pinIcon(corMarca("--brand-secondary", "30 34 41"), 26), []);

  const pontos: [number, number][] = [
    ...(escritorio ? [[escritorio.latitude, escritorio.longitude] as [number, number]] : []),
    ...clientes.map((c) => [c.latitude, c.longitude] as [number, number]),
  ];

  if (pontos.length === 0) return null;

  return (
    <MapContainer
      center={pontos[0]}
      zoom={13}
      scrollWheelZoom
      style={{ height: "560px", width: "100%", borderRadius: "2px" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <AjustarEnquadramento pontos={pontos} />
      {escritorio && (
        <Marker position={[escritorio.latitude, escritorio.longitude]} icon={iconeEscritorio}>
          <Popup>
            <p className="font-semibold text-sm">{escritorio.nome}</p>
            <p className="text-xs text-afj-black/60">{escritorio.enderecoTexto}</p>
            <p className="text-[10px] text-afj-gold uppercase tracking-widest mt-1">Escritório</p>
          </Popup>
        </Marker>
      )}
      {/* Fase 254 — clustering só nos marcadores de cliente (o do escritório
          é único, não faz sentido agrupar). leaflet.markercluster já
          separa um marcador draggable do cluster automaticamente durante
          o arrasto, sem trabalho extra aqui. */}
      <MarkerClusterGroup chunkedLoading>
        {clientes.map((c) => (
          <ClienteMarker
            key={c.id}
            cliente={c}
            icon={iconeCliente}
            ajusteAtivo={ajusteAtivo}
            onAjustarLocalizacao={onAjustarLocalizacao}
          />
        ))}
      </MarkerClusterGroup>
    </MapContainer>
  );
}
