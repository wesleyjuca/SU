"use client";
import "leaflet/dist/leaflet.css";
import { useMemo } from "react";
import L from "leaflet";
import { MapContainer, TileLayer, Marker, Popup, useMap } from "react-leaflet";

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

export default function EscritorioClientesMap({
  escritorio,
  clientes,
}: {
  escritorio: PontoEscritorio | null;
  clientes: PontoCliente[];
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
      {clientes.map((c) => (
        <Marker key={c.id} position={[c.latitude, c.longitude]} icon={iconeCliente}>
          <Popup>
            <p className="font-semibold text-sm">{c.nome}</p>
            <p className="text-xs text-afj-black/60">{c.enderecoTexto}</p>
            {c.statusGeo === "requer_revisao" && (
              <p className="text-[10px] text-amber-700 mt-1">⚠ Localização requer revisão</p>
            )}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}
