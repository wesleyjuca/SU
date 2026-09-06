"""Guarda contra a deriva que deixou o alembic inutilizável por 182 commits.

Contexto (fase pós-260.7): `app/models/__init__.py` importava 24 módulos de
model, mas `push_subscription` e `ai_call_log` não estavam entre eles. As duas
tabelas só entravam no `Base.metadata` porque routers/services as importam em
runtime — o que basta pro `create_all` do boot, mas NÃO pro
`alembic/env.py`, que faz apenas `import app.models`.

Consequências reais, medidas antes do fix:
  - `alembic revision --autogenerate` propunha `DROP TABLE ai_call_logs` e
    `DROP TABLE push_subscriptions` — armadilha armada pra quem escrevesse a
    primeira migração de verdade;
  - o passo de schema do CI (que também faz `import app.models`) montava 56
    tabelas em vez de 58.

O 1º teste é estático e barato: qualquer model novo que alguém esqueça de
registrar no `__init__` reprova aqui, sem precisar de banco.
"""
import json
import pathlib
import re
import subprocess
import sys

import pytest

import app.models  # noqa: F401
from app.db.base import Base

_MODELS_DIR = pathlib.Path(app.models.__file__).parent
_BACKEND = _MODELS_DIR.parent.parent


def _tabelas_de_um_import_puro() -> set[str]:
    """Metadata visto por quem faz SÓ `import app.models` — o que o alembic faz.

    Precisa ser um interpretador separado: neste processo o `conftest` já
    importou `app.main`, que puxa os routers, que importam os models avulsos —
    então medir aqui daria sempre "tudo presente" e o teste passaria mesmo com
    o `__init__.py` quebrado (verificado: foi o que aconteceu no 1º desenho).
    """
    saida = subprocess.run(
        [sys.executable, "-c",
         "import app.models; from app.db.base import Base; "
         "import json; print(json.dumps(sorted(Base.metadata.tables)))"],
        cwd=str(_BACKEND), capture_output=True, text=True, timeout=120,
    )
    assert saida.returncode == 0, f"import app.models falhou:\n{saida.stderr[-2000:]}"
    return set(json.loads(saida.stdout.strip().splitlines()[-1]))


def test_todo_model_do_pacote_esta_no_metadata():
    """Todo `__tablename__` de `app/models/*.py` tem que estar no metadata
    depois de um `import app.models` puro."""
    declaradas: dict[str, str] = {}
    for arquivo in sorted(_MODELS_DIR.glob("*.py")):
        if arquivo.name == "__init__.py":
            continue
        for tabela in re.findall(r'^\s*__tablename__\s*=\s*["\'](\w+)["\']',
                                 arquivo.read_text(), re.MULTILINE):
            declaradas[tabela] = arquivo.name

    registradas = _tabelas_de_um_import_puro()
    ausentes = {t: f for t, f in declaradas.items() if t not in registradas}
    assert not ausentes, (
        "model(s) fora do metadata — `app/models/__init__.py` não os importa, "
        "então o alembic não os enxerga e o autogenerate proporia DROP TABLE: "
        + ", ".join(f"{t} ({f})" for t, f in sorted(ausentes.items()))
    )


@pytest.mark.asyncio
async def test_banco_real_cobre_todo_o_metadata():
    """Nenhuma tabela/coluna do metadata pode faltar no banco de verdade.

    É a deriva que importa na prática: o que o código espera e o banco não tem.
    A direção oposta (índices que o `events.py` cria e os models não declaram)
    é deliberada e não é checada aqui.
    """
    from sqlalchemy import text

    from tests.db_isolada import sessao_isolada

    async with sessao_isolada() as db:
        linhas = (await db.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public'"
        ))).all()

    if not linhas:
        pytest.skip("banco sem schema público — nada a comparar")

    reais: dict[str, set[str]] = {}
    for tabela, coluna in linhas:
        reais.setdefault(tabela, set()).add(coluna)

    faltando: list[str] = []
    for nome, tabela in sorted(Base.metadata.tables.items()):
        if nome not in reais:
            faltando.append(f"tabela ausente: {nome}")
            continue
        for coluna in tabela.columns:
            if coluna.name not in reais[nome]:
                faltando.append(f"coluna ausente: {nome}.{coluna.name}")

    assert not faltando, "banco atrás do metadata:\n  " + "\n  ".join(faltando)
