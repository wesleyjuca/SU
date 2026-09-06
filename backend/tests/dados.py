"""Identificadores únicos por execução para os testes.

Por que existe: `LegalProcess` tem `UniqueConstraint("tenant_id","numero_cnj")`
(`models/process.py:14`) e vários testes criavam processos com CNJ escrito à
mão. Contra um banco limpo passavam; na segunda execução contra o MESMO banco
o INSERT violava a constraint. Pior: parte dos testes escondia isso com
`if res.status_code != 201: pytest.skip(...)`, então a suíte degradava para
skip silencioso em vez de acusar. Isso também mascarava o problema no CI, onde
o banco nasce novo a cada run e a colisão nunca acontece — os dois ambientes
davam respostas diferentes pela mesma causa.

Regra para testes novos: nunca escreva um identificador único à mão. Use estes
helpers, e limpe o que criar.
"""
import uuid


def cnj_unico(*, ano: int = 2026, tribunal: str = "8.26", origem: str = "0100") -> str:
    """CNJ no formato NNNNNNN-DD.AAAA.J.TR.OOOO, único a cada chamada.

    Os dígitos verificadores não são calculados de verdade — nenhum endpoint
    do projeto valida o DV do CNJ hoje; o que importa aqui é a unicidade.
    """
    n = uuid.uuid4().int
    sequencial = f"{n % 10_000_000:07d}"
    dv = f"{(n // 10_000_000) % 100:02d}"
    return f"{sequencial}-{dv}.{ano}.{tribunal}.{origem}"


def email_unico(prefixo: str = "teste", dominio: str = "afjadvogados.com.br") -> str:
    """E-mail único por chamada — `users.email` é UNIQUE, e convites de teste
    que reusavam um endereço fixo viravam skip permanente na 2ª execução."""
    return f"{prefixo}-{uuid.uuid4().hex[:10]}@{dominio}"


def cpf_unico() -> str:
    """CPF numérico único (sem DV real). Desde a Fase 240 o cadastro rejeita
    CPF/CNPJ duplicado com 409, então CPF fixo em teste colide na 2ª execução."""
    return f"{uuid.uuid4().int % 10**11:011d}"
