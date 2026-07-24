"use client";
import { useState, useEffect, useCallback } from "react";
import { Cpu, Database, Boxes, Server, ListChecks, Network, Clock } from "lucide-react";
import { fetchBrain, type Infra } from "./types";

function Estado({ ok, configured }: { ok: boolean; configured?: boolean }) {
  const label = configured === false ? "não configurado" : ok ? "ok" : "indisponível";
  const cls = configured === false ? "bg-gray-100 text-gray-500" : ok ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700";
  return <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full ${cls}`}>{label}</span>;
}

function Card({ icon: Icon, titulo, ok, configured, children }: {
  icon: React.ElementType; titulo: string; ok: boolean; configured?: boolean; children: React.ReactNode;
}) {
  return (
    <div className="afj-card p-4">
      <div className="flex items-center justify-between mb-2.5">
        <h3 className="font-semibold text-afj-black text-sm flex items-center gap-2">
          <Icon size={15} className="text-afj-gold" /> {titulo}
        </h3>
        <Estado ok={ok} configured={configured} />
      </div>
      {children}
    </div>
  );
}

function Linha({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between gap-2 text-xs">
      <span className="text-afj-black/45">{label}</span>
      <span className="text-afj-black font-medium text-right">{value ?? "—"}</span>
    </div>
  );
}

export function BrainInfra() {
  const [infra, setInfra] = useState<Infra | null>(null);
  const [carregado, setCarregado] = useState(false);

  const carregar = useCallback(async () => {
    const inf = await fetchBrain<Infra>("infra");
    setInfra(inf); setCarregado(true);
  }, []);
  useEffect(() => { carregar(); }, [carregar]);
  useEffect(() => { const i = setInterval(carregar, 15000); return () => clearInterval(i); }, [carregar]);

  if (carregado && !infra) return <div className="afj-card p-6 text-center text-sm text-afj-black/50">Infraestrutura indisponível no momento.</div>;
  if (!infra) return <div className="afj-card p-6 text-center text-sm text-afj-black/40">Carregando…</div>;

  const c = infra.celery, r = infra.redis, q = infra.qdrant, pg = infra.postgres_pool;
  const jobs = infra.jobs, fontes = infra.fontes;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        {/* Celery */}
        <Card icon={Cpu} titulo="Celery (workers)" ok={c.ok}>
          <div className="space-y-1">
            <Linha label="Workers" value={c.workers} />
            <Linha label="Tarefas ativas" value={c.total_ativas ?? 0} />
          </div>
          {(c.workers_detail?.length ?? 0) > 0 && (
            <div className="mt-2 space-y-1">
              {c.workers_detail!.map((w) => (
                <div key={w.nome} className="text-[11px] text-afj-black/60 flex justify-between border-t border-afj-cream-dark pt-1">
                  <span className="truncate max-w-[60%]">{w.nome}</span>
                  <span>{w.ativas} ativas · {w.agendadas} agend. · conc. {w.concorrencia ?? "—"}</span>
                </div>
              ))}
            </div>
          )}
          {(c.beat_schedule?.length ?? 0) > 0 && (
            <div className="mt-2">
              <p className="text-[10px] uppercase tracking-wider text-afj-black/40 mb-1 flex items-center gap-1"><Clock size={10} /> Tarefas agendadas (beat)</p>
              <div className="space-y-0.5">
                {c.beat_schedule!.map((b) => (
                  <div key={b.nome} className="text-[11px] text-afj-black/55 flex justify-between gap-2">
                    <span className="truncate max-w-[55%]">{b.nome}</span>
                    <span className="text-afj-black/35 truncate">{b.schedule}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {!c.ok && c.detail && <p className="text-[11px] text-red-500 mt-1">{c.detail}</p>}
        </Card>

        {/* Redis */}
        <Card icon={Database} titulo="Redis" ok={r.ok} configured={r.configured}>
          <div className="space-y-1">
            <Linha label="Memória usada" value={r.memoria_usada} />
            <Linha label="Clientes conectados" value={r.clientes_conectados} />
            <Linha label="Uptime (dias)" value={r.uptime_dias} />
            <Linha label="Total de chaves" value={r.total_chaves} />
            <Linha label="Fila Celery" value={r.fila_celery} />
          </div>
        </Card>

        {/* Qdrant */}
        <Card icon={Boxes} titulo="Qdrant (RAG)" ok={q.ok} configured={q.configured}>
          <Linha label="Coleções" value={q.total_colecoes ?? 0} />
          {(q.colecoes?.length ?? 0) > 0 && (
            <div className="mt-1.5 space-y-0.5">
              {q.colecoes!.map((col) => (
                <div key={col.nome} className="text-[11px] text-afj-black/60 flex justify-between border-t border-afj-cream-dark pt-1">
                  <span className="truncate max-w-[65%]">{col.nome}</span>
                  <span>{col.pontos ?? "—"} pts</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        {/* Postgres */}
        <Card icon={Server} titulo="PostgreSQL (pool)" ok={pg.ok}>
          <div className="space-y-1">
            <Linha label="Tamanho do pool" value={pg.tamanho} />
            <Linha label="Em uso" value={pg.em_uso} />
            <Linha label="Overflow" value={pg.overflow} />
          </div>
        </Card>
      </div>

      {/* Jobs: AgentRun por status + SyncRun recentes */}
      {jobs && (
        <Card icon={ListChecks} titulo="Execuções (24h) & sincronizações" ok={jobs.ok}>
          <div className="flex flex-wrap gap-2 mb-2">
            {Object.entries(jobs.agent_runs_24h_por_status ?? {}).length > 0
              ? Object.entries(jobs.agent_runs_24h_por_status ?? {}).map(([s, n]) => (
                  <span key={s} className="text-[11px] px-2 py-0.5 rounded-full bg-afj-cream border border-afj-cream-dark text-afj-black/70">
                    {s}: <b>{n}</b>
                  </span>
                ))
              : <span className="text-[11px] text-afj-black/40">Nenhuma execução de agente nas últimas 24h.</span>}
          </div>
          {(jobs.sync_runs_recentes?.length ?? 0) > 0 && (
            <div className="space-y-0.5">
              {jobs.sync_runs_recentes!.map((s, i) => (
                <div key={i} className="text-[11px] flex justify-between gap-2 border-t border-afj-cream-dark pt-1">
                  <span className="text-afj-black/60">{s.fonte} · {s.tipo}</span>
                  <span className={s.status === "ERRO" ? "text-red-600" : s.status === "OK" ? "text-green-600" : "text-afj-black/50"}>
                    {s.status}{s.started_at ? ` · ${new Date(s.started_at).toLocaleString("pt-BR")}` : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Fontes da captura */}
      {fontes && (
        <Card icon={Network} titulo="Fontes da Captura" ok={fontes.ok}>
          {typeof fontes.tribunais === "number" && (
            <p className="text-[11px] text-afj-black/45 mb-2">{fontes.tribunais} tribunais na tabela de referência</p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
            {fontes.fontes.map((f) => {
              const aberto = f.breaker === "open", meio = f.breaker === "half_open";
              return (
                <div key={f.nome} className="border border-afj-cream-dark rounded-sm p-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-semibold text-afj-black">{f.nome}</span>
                    <span className={`text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full ${
                      aberto ? "bg-red-100 text-red-700" : meio ? "bg-amber-100 text-amber-700" : "bg-green-100 text-green-700"}`}>
                      {aberto ? "aberto" : meio ? "meio-aberto" : "ok"}
                    </span>
                  </div>
                  <p className="text-[11px] text-afj-black/45 mt-1">{f.capabilities.join(" · ")}</p>
                </div>
              );
            })}
            <div className="border border-dashed border-afj-cream-dark rounded-sm p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-sm font-semibold text-afj-black">pdpj</span>
                <span className="text-[10px] font-semibold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-afj-gold/15 text-afj-gold">credenciado</span>
              </div>
              <p className="text-[11px] text-afj-black/45 mt-1">detalhar · partes · por escritório</p>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}
