"""Fase 249 — invocado pelo watchdog de `start.sh` quando o Celery entra em
crash-loop (mortes rápidas seguidas — ver `maybe_alert_crashloop` no
próprio start.sh). Roda como processo Python independente, fora do Celery
e do FastAPI de propósito: é o único canal de alerta que não depende do
que está quebrado. Cada passo é isolado em try/except — uma falha aqui
vira uma linha em stderr, nunca um traceback nem um hang que travaria o
loop do watchdog (que chama este script com `timeout 20` por precaução
extra).

Não diagnostica QUAL variável (REDIS_URL/CELERY_BROKER_URL/
CELERY_RESULT_BACKEND) está quebrada — isso já aparece no traceback do
próprio Celery nos logs. O trabalho deste script é só avisar um humano
que existe um crash-loop real, rápido o suficiente pra não passar
despercebido por horas."""
import asyncio
import sys


async def _main(death_count: str) -> None:
    from sqlalchemy import select

    from app.db.base import AsyncSessionLocal
    from app.models.user import User
    from app.services.email import send_email
    from app.services.notification import create_batch

    detalhe = (
        f"O processo Celery caiu e foi religado {death_count} vezes seguidas "
        "em menos de tempo saudável — indício de configuração quebrada (ex.: "
        "REDIS_URL/CELERY_BROKER_URL/CELERY_RESULT_BACKEND) que reinicia "
        "sozinha sem nunca ficar de pé. Tarefas em background (agentes de "
        "IA, alertas de prazo, sync de jurisprudência, captura de "
        "publicações, descoberta por OAB) não estão sendo processadas. "
        "Verifique os logs do Celery no Railway para o traceback exato."
    )

    async with AsyncSessionLocal() as db:
        try:
            admins = (await db.execute(
                select(User.id, User.email).where(
                    User.role == "SUPERADMIN",
                    User.is_active.is_(True),
                )
            )).all()
        except Exception as exc:
            print(f"[AFJ][ALERT] falha ao consultar SUPERADMIN: {exc}", file=sys.stderr)
            return

        if not admins:
            print("[AFJ][ALERT] nenhum SUPERADMIN ativo encontrado", file=sys.stderr)
            return

        try:
            await create_batch(
                db, [a.id for a in admins],
                titulo="Celery em crash-loop — tarefas em background paradas",
                tipo="INFRA_ALERTA",
                corpo=detalhe,
                priority="ALTA",
                link="/admin/cerebro?aba=infra",
            )
        except Exception as exc:
            print(f"[AFJ][ALERT] falha ao criar notificação in-app: {exc}", file=sys.stderr)

        for admin in admins:
            try:
                await send_email(
                    admin.email,
                    "[AFJ CORE] URGENTE — Celery em crash-loop em produção",
                    f"<p>{detalhe}</p>",
                    detalhe,
                    db=db,
                    tenant_id=None,
                )
            except Exception as exc:
                print(f"[AFJ][ALERT] falha ao enviar e-mail pra {admin.email}: {exc}", file=sys.stderr)


def main() -> None:
    death_count = sys.argv[1] if len(sys.argv) > 1 else "?"
    try:
        asyncio.run(asyncio.wait_for(_main(death_count), timeout=15))
    except Exception as exc:
        print(f"[AFJ][ALERT] falha geral ao alertar crash-loop: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
