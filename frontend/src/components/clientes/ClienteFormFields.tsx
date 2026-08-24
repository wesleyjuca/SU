"use client";
import { Check } from "lucide-react";

export interface Endereco {
  cep?: string;
  logradouro?: string;
  bairro?: string;
  cidade?: string;
  uf?: string;
  latitude?: number | null;
  longitude?: number | null;
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
  /** Fase 233 — mesma confirmação visual já usada no endereço do
   * escritório (EscritorioZone.tsx): fica true depois que o backend
   * geocodifica o CEP com sucesso (populado a partir da resposta do
   * POST/PUT /clients, não do preview de autofill de CEP). */
  temCoordenadas: boolean;
}

const inputCls = "w-full border border-afj-cream-dark rounded-sm px-3 py-2 text-sm focus:outline-none focus:border-afj-gold";

/** Campos compartilhados entre "Novo Cliente" e "Editar Cliente"
 * (clientes/page.tsx) — antes duplicados quase por completo entre os 2
 * modais. `mode` controla as poucas diferenças reais: seletor de `tipo`
 * só aparece na criação (o tipo é fixo depois que o cliente existe), e
 * o status ganha a opção INATIVO só na edição (um cliente não nasce
 * inativo). */
export function ClienteFormFields({
  mode, values, onChange, endereco, onEnderecoChange, docSugestao, onDocumentoBlur, onCepBlur, temCoordenadas,
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
        <input type="tel" value={values.telefone} onChange={(e) => onChange({ telefone: e.target.value })} className={inputCls} />
      </div>
      <div>
        <label className="text-xs text-afj-black/60 block mb-1">WhatsApp</label>
        <input type="tel" value={values.whatsapp} onChange={(e) => onChange({ whatsapp: e.target.value })} className={inputCls} />
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
              type="text" value={values.cnpj} onChange={(e) => onChange({ cnpj: e.target.value })}
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
            type="text" value={values.cpf} onChange={(e) => onChange({ cpf: e.target.value })}
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
            type="text" value={endereco.cep ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, cep: e.target.value })}
            onBlur={(e) => onCepBlur(e.target.value)}
            placeholder="CEP" className={inputCls}
          />
          <input
            type="text" value={endereco.uf ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, uf: e.target.value.toUpperCase().slice(0, 2) })}
            placeholder="UF" maxLength={2} className={inputCls}
          />
          <input
            type="text" value={endereco.logradouro ?? ""} onChange={(e) => onEnderecoChange({ ...endereco, logradouro: e.target.value })}
            placeholder="Rua, número, complemento" className={`col-span-2 ${inputCls}`}
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
        {temCoordenadas && (
          <p className="text-[11px] text-green-700 flex items-center gap-1.5 mt-2">
            <Check size={12} /> Localização geográfica capturada.
          </p>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm cursor-pointer">
        <input type="checkbox" checked={values.lgpd_consent} onChange={(e) => onChange({ lgpd_consent: e.target.checked })} />
        <span className="text-afj-black/70">Consentimento LGPD coletado</span>
      </label>
    </>
  );
}
