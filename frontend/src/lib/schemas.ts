import { z } from "zod";

export const ProcessoSchema = z.object({
  numero_cnj: z
    .string()
    .regex(
      /^\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}$/,
      "Formato CNJ inválido (0000000-00.0000.0.00.0000)"
    )
    .optional()
    .or(z.literal("")),
  tribunal: z.string().min(2, "Tribunal obrigatório"),
  area_direito: z.string().optional(),
  tipo_acao: z.string().optional(),
  descricao: z.string().optional(),
  valor_causa: z.coerce.number().nonnegative("Valor não pode ser negativo").optional(),
  client_id: z.string().optional(),
});

export const ClienteSchema = z.object({
  tipo: z.enum(["PF", "PJ"], { message: "Tipo obrigatório" }),
  nome_completo: z.string().min(3, "Nome deve ter ao menos 3 caracteres"),
  email: z.string().email("E-mail inválido").optional().or(z.literal("")),
  telefone: z
    .string()
    .regex(/^[\d\s()\-+]{8,}$/, "Telefone inválido (mín. 8 dígitos)")
    .optional()
    .or(z.literal("")),
  whatsapp: z.string().optional().or(z.literal("")),
  cpf: z
    .string()
    .regex(/^\d{3}\.\d{3}\.\d{3}-\d{2}$/, "CPF no formato 000.000.000-00")
    .optional()
    .or(z.literal("")),
  cnpj: z
    .string()
    .regex(/^\d{2}\.\d{3}\.\d{3}\/\d{4}-\d{2}$/, "CNPJ no formato 00.000.000/0000-00")
    .optional()
    .or(z.literal("")),
  origem: z.string().optional(),
  status: z.string().optional(),
  observacoes: z.string().optional(),
  lgpd_consent: z.boolean().default(false),
});

export const FinanceiroSchema = z.object({
  tipo: z.enum(["RECEITA", "DESPESA"], { message: "Tipo obrigatório" }),
  descricao: z.string().min(3, "Descrição obrigatória"),
  valor: z.coerce.number().positive("Valor deve ser maior que zero"),
  categoria: z.string().optional(),
  status: z.string().optional(),
  vencimento: z.string().optional(),
  data_pagamento: z.string().optional(),
  processo_id: z.string().optional(),
  client_id: z.string().optional(),
});

export const PrazoSchema = z.object({
  descricao: z.string().min(3, "Descrição obrigatória"),
  tipo: z.string().optional(),
  data_prazo: z.string().min(1, "Data do prazo obrigatória"),
  data_fatal: z.string().optional(),
  observacoes: z.string().optional(),
});

export const MovimentacaoSchema = z.object({
  descricao: z.string().min(3, "Descrição obrigatória"),
  tipo: z.string().optional(),
  data_movimento: z.string().optional(),
});

export const ContatoSchema = z.object({
  nome: z.string().min(2, "Nome obrigatório"),
  cargo: z.string().optional(),
  email: z.string().email("E-mail inválido").optional().or(z.literal("")),
  telefone: z.string().optional(),
  whatsapp: z.string().optional(),
  is_primary: z.boolean().default(false),
});

export type ProcessoInput = z.infer<typeof ProcessoSchema>;
export type ClienteInput = z.infer<typeof ClienteSchema>;
export type FinanceiroInput = z.infer<typeof FinanceiroSchema>;
export type PrazoInput = z.infer<typeof PrazoSchema>;
export type MovimentacaoInput = z.infer<typeof MovimentacaoSchema>;
export type ContatoInput = z.infer<typeof ContatoSchema>;
