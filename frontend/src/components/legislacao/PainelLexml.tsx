"use client";
/**
 * Pesquisa de legislação no acervo LexML.
 *
 * Regra de apresentação que dita o layout: o que a tela mostra de uma norma é
 * SEMPRE fonte oficial ou metadado derivado da URN — nunca texto produzido por
 * IA. Não há resumo automático aqui de propósito; se um dia houver, precisa vir
 * rotulado como sugestão, em bloco próprio, separado do texto da norma.
 */
import { useCallback, useEffect, useState } from "react";
import {
  AlertTriangle, BookMarked, Check, ChevronDown, ChevronUp, Copy,
  ExternalLink, Loader2, Scale, Search, Star, Trash2,
} from "lucide-react";
import { useToast } from "@/components/ui/Toast";

interface Norma {
  id: string;
  urn: string;
  titulo: string | null;
  ementa: string | null;
  tipo_norma: string | null;
  numero: string | null;
  ano: number | null;
  autoridade: string | null;
  localidade: string | null;
  url_fonte: string | null;
  tem_texto_integral: boolean;
  origem: string;
  vinculo?: {
    id: string;
    favorito: boolean;
    process_id: string | null;
    anotacao: string | null;
  };
}

interface RespostaBusca {
  total: number;
  resultados: Norma[];
  fonte_consultada: boolean;
  fonte_respondeu: boolean;
  fonte_desfecho?: string | null;
  fonte_detalhe?: {
    status_code: number | null;
    body_snippet: string | null;
    number_of_records: number | null;
    query: string | null;
  } | null;
}

/**
 * Uma mensagem por desfecho real da consulta ao portal.
 *
 * Antes havia uma frase só — "o portal não respondeu" — para cinco situações
 * diferentes, e ela era falsa em três delas: o portal pode ter respondido que
 * não achou nada, a consulta pode nem ter saído (disjuntor aberto), ou a
 * resposta pode ter vindo num formato que o sistema ainda não lê.
 *
 * `tom` separa o que é falha do que é resultado legítimo: "não encontrei" não
 * é erro e não deve aparecer em âmbar ao lado de "o portal recusou".
 */
const DESFECHOS: Record<string, { tom: "info" | "aviso"; texto: string }> = {
  vazio: {
    tom: "info",
    texto: "O portal do LexML respondeu, mas não encontrou nenhuma norma para esses termos.",
  },
  circuito_aberto: {
    tom: "aviso",
    texto:
      "As consultas ao portal estão suspensas por alguns minutos, após falhas seguidas. " +
      "O que aparece abaixo vem só do acervo já conhecido.",
  },
  http: {
    tom: "aviso",
    texto: "O portal do LexML recusou a consulta. O que aparece abaixo vem só do acervo já conhecido.",
  },
  rede: {
    tom: "aviso",
    texto: "Não foi possível alcançar o portal do LexML. O que aparece abaixo vem só do acervo já conhecido.",
  },
  xml_ilegivel: {
    tom: "aviso",
    texto: "O portal do LexML devolveu uma resposta ilegível. O que aparece abaixo vem só do acervo já conhecido.",
  },
  schema_inesperado: {
    tom: "aviso",
    texto:
      "O portal do LexML respondeu num formato que o sistema ainda não sabe ler — " +
      "os resultados dele não puderam ser aproveitados nesta consulta.",
  },
};

// Só os tipos que a sincronização diária de fato cobre hoje
// (`TIPOS_NORMA_SUPORTADOS` no cliente SRU). Listar mais sugeriria uma
// cobertura que o acervo não tem.
const TIPOS = ["Lei", "Decreto"];

function token() {
  return localStorage.getItem("afj_access_token");
}

function CardNorma({
  norma, onFavoritar, onRemover,
}: {
  norma: Norma;
  onFavoritar: (n: Norma) => void;
  onRemover?: (n: Norma) => void;
}) {
  const toast = useToast();
  const [texto, setTexto] = useState<string | null>(null);
  const [origemTexto, setOrigemTexto] = useState<string | null>(null);
  const [carregandoTexto, setCarregandoTexto] = useState(false);
  const [aberto, setAberto] = useState(false);
  const [copiado, setCopiado] = useState(false);

  async function alternarTexto() {
    if (aberto) { setAberto(false); return; }
    setAberto(true);
    if (texto !== null || origemTexto === "indisponivel") return;
    setCarregandoTexto(true);
    try {
      const res = await fetch(`/api/v1/lexml/normas/${norma.id}/texto`, {
        headers: { Authorization: `Bearer ${token()}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(typeof data.detail === "string" ? data.detail : "Não foi possível obter o texto.");
        setOrigemTexto("indisponivel");
        return;
      }
      setTexto(data.texto ?? null);
      setOrigemTexto(data.origem ?? null);
    } catch {
      toast.error("Erro de conexão ao buscar o texto da norma.");
      setOrigemTexto("indisponivel");
    } finally {
      setCarregandoTexto(false);
    }
  }

  async function copiarUrn() {
    await navigator.clipboard.writeText(norma.urn);
    setCopiado(true);
    setTimeout(() => setCopiado(false), 1500);
  }

  const identificacao = [norma.tipo_norma, norma.numero, norma.ano]
    .filter(Boolean)
    .join(" ");

  return (
    <div className="afj-card p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-sm font-medium text-afj-black">
            {norma.titulo || identificacao || norma.urn}
          </h3>
          <p className="text-xs text-afj-black/50 mt-0.5">
            {identificacao || "Identificação não derivável da URN"}
            {norma.autoridade ? ` · ${norma.autoridade}` : ""}
          </p>
        </div>
        <span
          className={`text-[10px] px-2 py-0.5 rounded-sm whitespace-nowrap ${
            norma.origem === "lexml"
              ? "bg-green-100 text-green-700"
              : "bg-afj-cream text-afj-black/60"
          }`}
          title={
            norma.origem === "lexml"
              ? "Recém-obtida do portal oficial do LexML nesta busca"
              : "Já conhecida pelo acervo do sistema"
          }
        >
          {norma.origem === "lexml" ? "LexML (agora)" : "Acervo"}
        </span>
      </div>

      {norma.ementa && <p className="text-xs text-afj-black/70 leading-relaxed">{norma.ementa}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <code className="text-[11px] bg-afj-cream px-2 py-1 rounded-sm text-afj-black/70 break-all">
          {norma.urn}
        </code>
        <button
          type="button"
          onClick={copiarUrn}
          className="text-xs text-afj-black/50 hover:text-afj-gold flex items-center gap-1"
        >
          {copiado ? <Check size={12} /> : <Copy size={12} />}
          {copiado ? "Copiado" : "Copiar URN"}
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-3 pt-1">
        {norma.url_fonte && (
          <a
            href={norma.url_fonte}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-afj-gold hover:underline flex items-center gap-1"
          >
            <ExternalLink size={12} /> Abrir fonte oficial
          </a>
        )}
        <button
          type="button"
          onClick={alternarTexto}
          className="text-xs text-afj-black/60 hover:text-afj-gold flex items-center gap-1"
        >
          {aberto ? <ChevronUp size={12} /> : <ChevronDown size={12} />} Ver texto
        </button>
        <button
          type="button"
          onClick={() => onFavoritar(norma)}
          className="text-xs text-afj-black/60 hover:text-afj-gold flex items-center gap-1"
        >
          <Star size={12} className={norma.vinculo?.favorito ? "fill-afj-gold text-afj-gold" : ""} />
          {norma.vinculo?.favorito ? "Favoritada" : "Favoritar"}
        </button>
        {onRemover && (
          <button
            type="button"
            onClick={() => onRemover(norma)}
            className="text-xs text-red-600/70 hover:text-red-700 flex items-center gap-1"
          >
            <Trash2 size={12} /> Remover do acervo
          </button>
        )}
      </div>

      {aberto && (
        <div className="border-t border-afj-cream-dark pt-3">
          {carregandoTexto ? (
            <p className="text-xs text-afj-black/50 flex items-center gap-2">
              <Loader2 size={12} className="animate-spin" /> Buscando na fonte oficial...
            </p>
          ) : texto ? (
            <>
              <p className="text-[11px] text-afj-black/45 mb-2">
                Texto obtido do portal oficial da norma
                {origemTexto === "cache" ? " (armazenado em consulta anterior)" : " agora"} — sem
                nenhuma edição ou resumo por IA.
              </p>
              <pre className="text-xs text-afj-black/80 whitespace-pre-wrap max-h-80 overflow-y-auto leading-relaxed">
                {texto}
              </pre>
            </>
          ) : (
            <p className="text-xs text-amber-700 flex items-start gap-2">
              <AlertTriangle size={12} className="mt-0.5 flex-shrink-0" />
              Não foi possível obter o texto integral nesta consulta. Use o link da fonte oficial acima.
            </p>
          )}
        </div>
      )}
    </div>
  );
}

export function PainelLexml() {
  const toast = useToast();
  const [aba, setAba] = useState<"busca" | "acervo">("busca");

  const [texto, setTexto] = useState("");
  const [tipo, setTipo] = useState("");
  const [ano, setAno] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [resposta, setResposta] = useState<RespostaBusca | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  const [acervo, setAcervo] = useState<Norma[] | null>(null);
  const [carregandoAcervo, setCarregandoAcervo] = useState(false);

  const carregarAcervo = useCallback(async () => {
    setCarregandoAcervo(true);
    try {
      const res = await fetch("/api/v1/lexml/acervo", {
        headers: { Authorization: `Bearer ${token()}` },
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) { toast.error("Não foi possível carregar o acervo."); return; }
      setAcervo(
        (data.resultados ?? []).map((r: Norma & { vinculo?: Norma["vinculo"] }) => ({
          ...r, vinculo: r.vinculo,
        }))
      );
    } catch {
      toast.error("Erro de conexão ao carregar o acervo.");
    } finally {
      setCarregandoAcervo(false);
    }
  }, [toast]);

  useEffect(() => {
    if (aba === "acervo" && acervo === null) carregarAcervo();
  }, [aba, acervo, carregarAcervo]);

  async function buscar(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!texto.trim() && !tipo && !ano) return;
    setBuscando(true);
    setErro(null);
    setResposta(null);
    try {
      const res = await fetch("/api/v1/lexml/buscar", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({
          texto: texto.trim() || null,
          tipo_norma: tipo || null,
          ano: ano ? Number(ano) : null,
          limite: 20,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErro(typeof data.detail === "string" ? data.detail : "Erro ao buscar legislação.");
        return;
      }
      setResposta(data);
    } catch {
      setErro("Erro de conexão com o serviço de legislação.");
    } finally {
      setBuscando(false);
    }
  }

  async function favoritar(norma: Norma) {
    try {
      const res = await fetch("/api/v1/lexml/acervo", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token()}` },
        body: JSON.stringify({ norma_id: norma.id, favorito: !norma.vinculo?.favorito }),
      });
      if (!res.ok) { toast.error("Não foi possível salvar no acervo."); return; }
      toast.success(norma.vinculo?.favorito ? "Favorito removido." : "Norma salva no acervo.");
      setAcervo(null);
      setResposta((atual) =>
        atual
          ? {
              ...atual,
              resultados: atual.resultados.map((r) =>
                r.id === norma.id
                  ? { ...r, vinculo: { id: r.vinculo?.id ?? "", favorito: !norma.vinculo?.favorito, process_id: null, anotacao: r.vinculo?.anotacao ?? null } }
                  : r
              ),
            }
          : atual
      );
      if (aba === "acervo") carregarAcervo();
    } catch {
      toast.error("Erro de conexão ao salvar no acervo.");
    }
  }

  async function remover(norma: Norma) {
    try {
      const res = await fetch(`/api/v1/lexml/acervo/${norma.id}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token()}` },
      });
      if (!res.ok) { toast.error("Não foi possível remover do acervo."); return; }
      toast.success("Removida do acervo.");
      carregarAcervo();
    } catch {
      toast.error("Erro de conexão ao remover do acervo.");
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {([["busca", "Pesquisar", Search], ["acervo", "Meu acervo", BookMarked]] as const).map(
          ([valor, rotulo, Icone]) => (
            <button
              key={valor}
              type="button"
              onClick={() => setAba(valor)}
              className={`text-xs px-3 py-1.5 rounded-sm border transition-colors flex items-center gap-1.5 ${
                aba === valor
                  ? "border-afj-gold bg-afj-gold/5 text-afj-gold font-medium"
                  : "border-afj-cream-dark text-afj-black/50 hover:border-afj-gold/50"
              }`}
            >
              <Icone size={13} /> {rotulo}
            </button>
          )
        )}
      </div>

      {aba === "busca" && (
        <>
          <form onSubmit={buscar} className="afj-card p-5 space-y-4">
            <div className="relative">
              <Scale size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-afj-black/30" />
              <input
                value={texto}
                onChange={(e) => setTexto(e.target.value)}
                placeholder="Ex: Lei 14.133, licitações, Código de Defesa do Consumidor..."
                className="w-full pl-9 pr-4 py-2.5 text-sm border border-afj-cream-dark rounded-sm focus:outline-none focus:border-afj-gold"
              />
            </div>

            <div className="flex flex-wrap gap-3">
              <select
                value={tipo}
                onChange={(e) => setTipo(e.target.value)}
                className="text-sm border border-afj-cream-dark rounded-sm px-3 py-2 focus:outline-none focus:border-afj-gold"
              >
                <option value="">Todos os tipos</option>
                {TIPOS.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <input
                value={ano}
                onChange={(e) => setAno(e.target.value.replace(/\D/g, "").slice(0, 4))}
                placeholder="Ano"
                inputMode="numeric"
                className="w-24 text-sm border border-afj-cream-dark rounded-sm px-3 py-2 focus:outline-none focus:border-afj-gold"
              />
              <button
                type="submit"
                disabled={buscando || (!texto.trim() && !tipo && !ano)}
                className="btn-afj-primary text-sm px-5 disabled:opacity-40 flex items-center gap-2"
              >
                {buscando ? <Loader2 size={14} className="animate-spin" /> : <Search size={14} />}
                Pesquisar
              </button>
            </div>

            <p className="text-[11px] text-afj-black/45">
              O filtro por ano é aplicado sobre o acervo do sistema — o portal do LexML não confirma
              um índice de busca por ano, e enviá-lo às cegas poderia derrubar a consulta inteira.
            </p>
          </form>

          {erro && (
            <div className="afj-card p-4 border-l-2 border-red-400">
              <p className="text-sm text-red-700">{erro}</p>
            </div>
          )}

          {resposta && (
            <div className="space-y-3">
              <div className="flex items-center justify-between text-xs text-afj-black/50">
                <span>{resposta.total} norma(s)</span>
                {resposta.fonte_consultada && (() => {
                  const info = DESFECHOS[resposta.fonte_desfecho ?? ""];
                  if (!info) return null;
                  // O técnico (status HTTP / trecho da resposta) fica no
                  // tooltip: serve ao suporte sem poluir a tela do advogado —
                  // mesmo princípio de `erro_amigavel` em Integrações.
                  const tecnico = [
                    resposta.fonte_detalhe?.status_code
                      ? `HTTP ${resposta.fonte_detalhe.status_code}`
                      : null,
                    resposta.fonte_detalhe?.query
                      ? `consulta enviada: ${resposta.fonte_detalhe.query}`
                      : null,
                    resposta.fonte_detalhe?.body_snippet,
                  ]
                    .filter(Boolean)
                    .join(" — ");
                  return (
                    <span
                      title={tecnico || undefined}
                      className={`flex items-center gap-1 ${
                        info.tom === "aviso" ? "text-amber-700" : "text-afj-black/50"
                      }`}
                    >
                      {info.tom === "aviso" && <AlertTriangle size={12} />}
                      {info.texto}
                    </span>
                  );
                })()}
              </div>
              {resposta.resultados.length === 0 ? (
                <div className="afj-card p-6 text-center">
                  <p className="text-sm text-afj-black/50">Nenhuma norma encontrada para esses critérios.</p>
                </div>
              ) : (
                resposta.resultados.map((n) => (
                  <CardNorma key={n.id} norma={n} onFavoritar={favoritar} />
                ))
              )}
              <div className="bg-amber-50 border border-amber-200 rounded-sm p-3 flex items-start gap-2">
                <AlertTriangle size={14} className="text-amber-600 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-amber-800">
                  Confira a vigência da norma na fonte oficial antes de citá-la: o acervo reflete o
                  que foi publicado, não se o texto segue em vigor ou foi alterado depois.
                </p>
              </div>
            </div>
          )}
        </>
      )}

      {aba === "acervo" && (
        <div className="space-y-3">
          {carregandoAcervo ? (
            <p className="text-sm text-afj-black/50 flex items-center gap-2">
              <Loader2 size={14} className="animate-spin" /> Carregando acervo...
            </p>
          ) : !acervo || acervo.length === 0 ? (
            <div className="afj-card p-6 text-center">
              <p className="text-sm text-afj-black/50">
                Nenhuma norma no acervo do escritório ainda. Favorite uma norma na aba Pesquisar.
              </p>
            </div>
          ) : (
            acervo.map((n) => (
              <CardNorma key={n.vinculo?.id ?? n.id} norma={n} onFavoritar={favoritar} onRemover={remover} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
