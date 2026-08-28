// Fase 243 — máscaras de digitação (CPF/CNPJ/telefone/CEP). Puramente
// cosmético: formata o que o usuário já digitou, nunca valida dígito
// verificador (isso já existe no backend, `_documento_ja_cadastrado`/
// `POST /clients/validar-documento`, Fase 217/220/240) nem impede colar um
// valor com formatação diferente — sempre trabalha só com os dígitos.

export function maskCpf(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  return d
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
}

export function maskCnpj(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 14);
  return d
    .replace(/(\d{2})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1.$2")
    .replace(/(\d{3})(\d)/, "$1/$2")
    .replace(/(\d{4})(\d{1,2})$/, "$1-$2");
}

// Telefone brasileiro — detecta celular (9 dígitos) vs. fixo (8) pelo que
// já foi digitado, sem forçar um formato antes da hora.
export function maskTelefone(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 11);
  if (d.length <= 2) return d.replace(/(\d{0,2})/, "($1");
  if (d.length <= 6) return d.replace(/(\d{2})(\d{0,4})/, "($1) $2");
  if (d.length <= 10) return d.replace(/(\d{2})(\d{4})(\d{0,4})/, "($1) $2-$3");
  return d.replace(/(\d{2})(\d{5})(\d{0,4})/, "($1) $2-$3");
}

export function maskCep(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8);
  return d.replace(/(\d{5})(\d{1,3})$/, "$1-$2");
}
