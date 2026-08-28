// Fase 240 (achado do diagnóstico de cadastros) — lista de Área do Direito
// estava duplicada e divergente em 5 lugares do frontend (algumas com só 6
// dos 10 valores que o backend aceita, `AREAS_DIREITO` em
// backend/app/schemas/process.py, uma delas com "EMPRESARIAL", que nem
// existe no backend e quebraria o save com 422). Fonte única aqui,
// mantida em sincronia manual com o enum do backend.
export const AREAS_DIREITO = [
  "CIVIL",
  "TRABALHISTA",
  "PENAL",
  "TRIBUTARIO",
  "AMBIENTAL",
  "ADMINISTRATIVO",
  "PREVIDENCIARIO",
  "CONSUMIDOR",
  "FAMILIA",
  "IMOBILIARIO",
] as const;
