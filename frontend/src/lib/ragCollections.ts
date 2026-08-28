// Fase 242 — rótulos amigáveis pras coleções RAG. O CONJUNTO válido vem
// sempre de GET /rag/collections (fonte única, backend/app/api/v1/rag.py::
// VALID_COLLECTIONS) — este mapa só fornece o label de exibição, nunca a
// lista de quais valores existem, pra não voltar a divergir do backend
// (mesma classe de achado já corrigido pra Área do Direito na Fase 240).
export const RAG_COLLECTION_LABELS: Record<string, string> = {
  jurisprudencia: "Jurisprudência",
  legislacao: "Legislação",
  doutrina: "Doutrina",
  doutrina_privada: "Doutrina (privada)",
  peticoes_afj: "Petições AFJ",
  memorias_afj: "Memórias AFJ",
  documentos_clientes: "Docs. Clientes",
};

export async function fetchValidRagCollections(): Promise<string[]> {
  try {
    const token = localStorage.getItem("afj_access_token");
    const res = await fetch("/api/v1/rag/collections", { headers: { Authorization: `Bearer ${token}` } });
    if (res.ok) {
      const d = await res.json();
      if (Array.isArray(d.collections)) return d.collections;
    }
  } catch {}
  // Fail-soft: se o endpoint não responder, cai pro conjunto conhecido no
  // momento desta fase — nunca trava a tela por causa disso.
  return Object.keys(RAG_COLLECTION_LABELS);
}
