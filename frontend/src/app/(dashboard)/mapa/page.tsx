"use client";
import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { MapPin, RefreshCw, Loader2 } from "lucide-react";
import { Breadcrumb } from "@/components/layout/Breadcrumb";
import type { PontoEscritorio, PontoCliente } from "@/components/mapa/EscritorioClientesMap";

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

function enderecoTexto(e: EnderecoResponse): string {
  return [e.logradouro, e.bairro, [e.cidade, e.uf].filter(Boolean).join("/")].filter(Boolean).join(" — ") || "Endereço não informado";
}

export default function MapaPage() {
  const [escritorio, setEscritorio] = useState<PontoEscritorio | null>(null);
  const [clientes, setClientes] = useState<PontoCliente[]>([]);
  const [totalClientesComEndereco, setTotalClientesComEndereco] = useState(0);
  const [loading, setLoading] = useState(true);

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
        fetch("/api/v1/clients", { headers: headers() }),
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
        setClientes(
          comEndereco.map((c: any) => ({
            id: c.id,
            nome: c.nome_completo,
            latitude: c.endereco_json.latitude,
            longitude: c.endereco_json.longitude,
            enderecoTexto: enderecoTexto(c.endereco_json),
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

  const semMarcadores = !loading && !escritorio && clientes.length === 0;

  return (
    <div className="max-w-7xl mx-auto space-y-5">
      <Breadcrumb crumbs={[{ label: "Dashboard", href: "/dashboard" }, { label: "Mapa" }]} />

      <div className="afj-page-header">
        <div>
          <h1 className="font-display text-2xl font-semibold text-afj-black">Mapa</h1>
          <p className="text-afj-black/50 text-sm">
            Localização do escritório{clientes.length > 0 || totalClientesComEndereco > 0 ? ` e ${totalClientesComEndereco} cliente(s) geocodificado(s)` : ""}
          </p>
        </div>
        <button
          onClick={carregar}
          disabled={loading}
          className="btn-afj-outline rounded-sm flex items-center gap-2 disabled:opacity-50"
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : <RefreshCw size={14} />}
          Atualizar
        </button>
      </div>

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
      ) : (
        <div className="afj-card p-2 overflow-hidden">
          <EscritorioClientesMap escritorio={escritorio} clientes={clientes} />
        </div>
      )}
    </div>
  );
}

function MapSkeleton() {
  return <div className="afj-card h-[560px] animate-pulse bg-afj-cream-dark/40" />;
}
