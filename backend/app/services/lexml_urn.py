"""URN LexML — normalização, validação e extração de campos.

A URN é o identificador jurídico externo de uma norma: persistente, citável e
estável ("sem link quebrado"). No AFJ ela é a **chave natural** de
`lexml_normas`, não um id interno.

Forma geral (confirmada na documentação oficial do LexML, Parte 2):

    urn:lex:<localidade>:<autoridade>:<tipo>:<descritor>

onde `<descritor>` é composto por data e um identificador alfanumérico.
Exemplo real, já usado nos testes deste projeto:

    urn:lex:br:federal:lei:1990-09-11;8078

**Princípio de desenho:** uma URN que não casa a forma esperada é PRESERVADA
COMO VEIO e apenas não rende campos derivados. Nunca é "consertada" por
heurística — inventar estrutura num identificador jurídico é pior do que
admitir que não foi possível interpretá-lo.
"""
from __future__ import annotations

import re

_PREFIXO = "urn:lex:"

# Data no descritor: YYYY-MM-DD (o que a especificação usa). Aceita também
# só o ano, que aparece em parte do acervo.
_DATA_COMPLETA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_SO_ANO = re.compile(r"^(\d{4})$")


def normalizar_urn(urn: str | None) -> str | None:
    """Minúsculas e sem espaço nas bordas — só isso.

    Deliberadamente conservador: não reescreve separador, não completa data,
    não expande abreviação. O objetivo é que duas grafias triviais da MESMA
    urn colidam na constraint unique, não transformar o identificador.
    """
    if not urn:
        return None
    limpa = " ".join(urn.split()).strip().lower()
    return limpa or None


def validar_urn(urn: str | None) -> bool:
    """`True` se parece uma URN LexML utilizável como chave.

    Permissiva de propósito: exige o prefixo e um mínimo de estrutura, mas não
    valida contra lista fechada de autoridades ou tipos — quais existem é
    informação NÃO VERIFICADA (o portal não é alcançável do ambiente de
    desenvolvimento), e uma lista fechada errada rejeitaria norma legítima.
    """
    normalizada = normalizar_urn(urn)
    if not normalizada or not normalizada.startswith(_PREFIXO):
        return False
    resto = normalizada[len(_PREFIXO):]
    # localidade:autoridade:tipo:descritor → ao menos 4 segmentos não vazios
    partes = resto.split(":")
    return len(partes) >= 4 and all(p.strip() for p in partes[:4])


def derivar_campos_da_urn(urn: str | None) -> dict:
    """Extrai o que a URN carrega estruturalmente.

    Devolve sempre um dict com as mesmas chaves; valores são `None` quando não
    foi possível derivar — o chamador grava nulo em vez de adivinhar. Nunca
    lança.
    """
    vazio = {
        "localidade": None, "autoridade": None, "tipo_norma": None,
        "numero": None, "ano": None, "data_publicacao": None,
    }
    if not validar_urn(urn):
        return vazio

    partes = normalizar_urn(urn)[len(_PREFIXO):].split(":")
    localidade, autoridade, tipo = partes[0], partes[1], partes[2]
    descritor = ":".join(partes[3:])  # o descritor pode conter ':' em versões

    numero: str | None = None
    ano: int | None = None
    data_publicacao: str | None = None

    # Descritor típico: "1990-09-11;8078" (data;numero)
    if ";" in descritor:
        parte_data, _, parte_numero = descritor.partition(";")
        numero = parte_numero.split(";")[0].strip() or None
    else:
        parte_data = descritor

    parte_data = parte_data.strip()
    if m := _DATA_COMPLETA.match(parte_data):
        ano = int(m.group(1))
        data_publicacao = parte_data
    elif m := _SO_ANO.match(parte_data):
        ano = int(m.group(1))

    return {
        "localidade": localidade or None,
        "autoridade": autoridade or None,
        # A URN usa o tipo em minúsculas ("lei"); o acervo e o Qdrant usam a
        # forma de exibição ("Lei"). Normalizamos para a de exibição aqui,
        # que é a que o usuário vê e filtra.
        "tipo_norma": tipo.capitalize() if tipo else None,
        "numero": numero,
        "ano": ano,
        "data_publicacao": data_publicacao,
    }
