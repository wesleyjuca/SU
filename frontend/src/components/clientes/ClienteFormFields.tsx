"use client";
import { Check, AlertTriangle, RefreshCw } from "lucide-react";
import { maskCpf, maskCnpj, maskTelefone, maskCep } from "@/lib/masks";

export interface Endereco {
  cep?: string;
  logradouro?: string;
  /** Fase 257.4 — opcional; quando presente, refina a geocodificação via
   * Nominatim (precisão de endereço exato) em vez de só o centro do
   * CEP/quadra da BrasilAPI. */
  numero?: string;
  bairro?: string;
  cidade?: string;
  uf?: string;
  latitude?: number | null;
  longitude?: number | null;
  /** Fase 253 — presença de `geocode_source` distingue coordenada que já
   * passou pela validação de causa-raiz (CEP comparado contra o anterior
   * antes de decidir se re-geocodifica) de coordenada herdada de antes
   * desse fix, que não dá pra confiar sem revisão. */
  geocode_source?: string | null;
  geocoded_at?: string | null;
}

/** Fase 253 — status de geolocalização computado no frontend a partir do
 * que a API já devolve, sem endpoint dedicado: mesmo critério de
 * `_status_geolocalizacao` no backend (clients.py), mais um 5º estado
 * ("cep_alterado") que só faz sentido no meio de uma edição ainda não
 * salva. */
export type StatusLocalizacao = "nao_geocodificado" | "requer_revisao" | "validada" | "cep_alterado";

export function statusLocalizacaoDe(endereco: Endereco, enderecoMudouDesdeAbertura: boolean): StatusLocalizacao {
  if (enderecoMudouDesdeAbertura) return "cep_alterado";
  if (endereco.latitude == null || endereco.longitude == null) return "nao_geocodificado";
  if (!endereco.geocode_source) return "requer_revisao";
  return "validada";
}

export interface ClienteFormValues {
  tipo: string;
  nome_completo: string;
  razao_social: string;
  email: string;
  telefone: string;
  whatsapp: string;
  origem: string;
  cpf: string;
  cnpj: string;
  status: string;
  lgpd_consent: boolean;
  observacoes: string;
}

interface ClienteFormFieldsProps {
  mode: "create" | "edit";
  values: ClienteFormValues;
  onChange: (patch: Partial<ClienteFormValues>) => void;
  endereco: Endereco;
  onEnderecoChange: (e: Endereco) => void;
  docSugestao: string | null;
  onDocumentoBlur: (tipo: "cpf" | "cnpj", valor: string) => void;
  onCepBlur: (cep: string) => void;
  /** Fase 233/253 — status computado (ver `statusLocalizacaoDe` acima). */
  statusLocalizacao: StatusLocalizacao;
  /** Fase 253 — só em modo edição (precisa de um cliente já existente).
   * Força nova geocodificação mesmo sem o CEP ter mudado — útil pra
   * registros "requer revisão" (herdados de antes do fix de causa-raiz)
   * ou que ficaram sem coordenada por falha temporária da BrasilAPI. */
  onRecalcularLocalizacao?: () => void;
  recalculando?: boolean;
}

const inputCls = "w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold";

/** Campos compartilhados entre "Novo Cliente" e "Editar Cliente"
 * (clientes/page.tsx) — antes duplicados quase por completo entre os 2
 * modais. `mode` controla as poucas diferenças reais: seletor de `tipo`
 * só aparece na criação (o tipo é fixo depois que o cliente existe), e
 * o status ganha a opção INATIVO só na edição (um cliente não nasce
 * inativo). */
export function ClienteFormFields({
  mode, values, onChange, endereco, onEnderecoChange, docSugestao, onDocumentoBlur, onCepBlur,
  statusLocalizacao, onRecalcularLocalizacao, recalculando,
}: ClienteFormFieldsProps) {
  return (
    <>
      <div className="grid grid-cols-2 gap-3">
        {mode === "create" ? (
          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Tipo *</label>
            <select value={values.tipo} onChange={(e) => onChange({ tipo: e.target.value })} className={inputCls}>
              <option value="PF">Pessoa Física</option>
              <option value="PJ">Pessoa Jurídica</option>
            </select>
          </div>
        ) : (
          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Tipo</label>
            <p className="text-sm text-afj-black/70 py-2">{values.tipo === "PJ" ? "Pessoa Jurídica" : "Pessoa Física"}</p>
          </div>
        )}
        <div>
          <label className="text-xs text-afj-black/60 block mb-1">Status</label>
          <select value={values.status} onChange={(e) => onChange({ status: e.target.value })} className={inputCls}>
            <option value="PROSPECTO">Prospecto</option>
            <option value="ATIVO">Ativo</option>
            {mode === "edit" && <option value="INATIVO">Inativo</option>}
          </select>
        </div>
      </div>

      <div>
        <label className="text-xs text-afj-black/60 block mb-1">Nome Completo *</label>
        <input type="text" value={values.nome_completo} onChange={(e) => onChange({ nome_completo: e.target.value })} className={inputCls} required />
      </div>
      <div>
        <label className="text-xs text-afj-black/60 block mb-1">E-mail</label>
        <input type="email" value={values.email} onChange={(e) => onChange({ email: e.target.value })} className={inputCls} />
      </div>
      <div>
        <label className="text-xs text-afj-black/60 block mb-1">Telefone</label>
        <input type="tel" value={values.telefone} onChange={(e) => onChange({ telefone: maskTelefone(e.target.value) })} className={inputCls} />
      </div>
      <div>
        <label className="text-xs text-afj-black/60 block mb-1">WhatsApp</label>
        <input type="tel" value={values.whatsapp} onChange={(e) => onChange({ whatsapp: maskTelefone(e.target.value) })} className={inputCls} />
      </div>
      <div>
        <label className="text-xs text-afj-black/60 block mb-1">Origem</label>
        <input type="text" value={values.origem} onChange={(e) => onChange({ origem: e.target.value })} className={inputCls} />
      </div>

      {values.tipo === "PJ" ? (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-afj-black/60 block mb-1">Razão Social</label>
            <input type="text" value={values.razao_social} onChange={(e) => onChange({ razao_social: e.target.value })} className={inputCls} />
          </div>
          <div>
            <label className="text-xs text-afj-black/60 block mb-1">CNPJ</label>
            <input
              type="text" value={values.cnpj} onChange={(e) => onChange({ cnpj: maskCnpj(e.target.value) })}
              onBlur={(e) => onDocumentoBlur("cnpj", e.target.value)}
              placeholder="00.000.000/0000-00" className={inputCls}
            />
            {docSugestao && <p className="text-xs text-afj-gold mt-1">{docSugestao}</p>}
          </div>
        </div>
      ) : (
        <div>
          <label className="text-xs text-afj-black/60 block mb-1">CPF</label>
          <input
            type="text" value={values.cpf} onChange={(e) => onChange({ cpf: maskCpf(e.target.value) })}
            onBlur={(e) => onDocumentoBlur("cpf", e.target.value)}
            placeholder="000.000.000-00" className={inputCls}
          />
          {docSugestao && <p className="text-xs text-afj-gold mt-1">{docSugestao}</p>}
        </div>
      )}

      <div>
        <label className="text-xs text-afj-black/60 block mb-2">Endereço</label>
        <div className="grid grid-cols-2 gap-2">
          <input
            type="text" value={endereco.cep ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, cep: maskCep(e.target.value) })}
            onBlur={(e) => onCepBlur(e.target.value)}
            placeholder="CEP" className={inputCls}
          />
          <input
            type="text" value={endereco.uf ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, uf: e.target.value.toUpperCase().slice(0, 2) })}
            placeholder="UF" maxLength={2} className={inputCls}
          />
          <input
            type="text" value={endereco.logradouro ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, logradouro: e.target.value })}
            placeholder="Rua, complemento" className={inputCls}
          />
          <input
            type="text" value={endereco.numero ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, numero: e.target.value })}
            placeholder="Número" className={inputCls}
          />
          <input
            type="text" value={endereco.bairro ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, bairro: e.target.value })}
            placeholder="Bairro" className={inputCls}
          />
          <input
            type="text" value={endereco.cidade ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, cidade: e.target.value })}
            placeholder="Cidade" className={inputCls}
          />
        </div>
        {endereco.numero && (
          <p className="text-[10px] text-afj-black/35 mt-1.5">
            Com o número preenchido, a localização é refinada por endereço exato (não só o centro do CEP).
          </p>
        )}
        <div className="flex items-center justify-between gap-2 mt-2">
          {statusLocalizacao === "validada" && (
            <p className="text-[11px] text-green-700 flex items-center gap-1.5">
              <Check size={12} /> Localização geográfica capturada{endereco.geocode_source === "nominatim" ? " (endereço exato)" : ""}.
            </p>
          )}
          {statusLocalizacao === "requer_revisao" && (
            <p className="text-[11px] text-amber-700 flex items-center gap-1.5">
              <AlertTriangle size={12} /> Localização requer revisão (capturada antes de uma verificação mais recente).
            </p>
          )}
          {statusLocalizacao === "cep_alterado" && (
            <p className="text-[11px] text-afj-black/60 flex items-center gap-1.5">
              CEP ou número alterado — a localização será recalculada ao salvar.
            </p>
          )}
          {statusLocalizacao === "nao_geocodificado" && <span />}
          {mode === "edit" && onRecalcularLocalizacao && endereco.cep && (
            <button
              type="button" onClick={onRecalcularLocalizacao} disabled={recalculando}
              className="text-[11px] text-afj-gold hover:underline flex items-center gap-1 disabled:opacity-50 shrink-0"
            >
              <RefreshCw size={11} className={recalculando ? "animate-spin" : ""} /> Recalcular localização
            </button>
          )}
        </div>
      </div>

      <div>
        <label className="text-xs text-afj-black/60 block mb-1">Observações</label>
        <textarea
          rows={3} value={values.observacoes} onChange={(e) => onChange({ observacoes: e.target.value })}
          className={inputCls}
        />
      </div>

      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={values.lgpd_consent} onChange={(e) => onChange({ lgpd_consent: e.target.checked })} />
        <span className="text-afj-black/70">Consentimento LGPD coletado</span>
      </label>
    </>
  );
}
