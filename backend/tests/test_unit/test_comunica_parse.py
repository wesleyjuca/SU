"""Fase 76 — robustez do parsing da Comunica/DJEN (helpers puros)."""
from app.integrations.dje.comunica import _extrai_itens, _extrai_total, _normalize


def test_extrai_itens_variantes_de_envelope():
    assert _extrai_itens([{"a": 1}]) == [{"a": 1}]
    assert _extrai_itens({"items": [1, 2]}) == [1, 2]
    assert _extrai_itens({"content": [3]}) == [3]
    assert _extrai_itens({"comunicacoes": [4]}) == [4]
    assert _extrai_itens({"results": [5]}) == [5]
    # envelope aninhado {"data": {"items": [...]}}
    assert _extrai_itens({"data": {"items": [6]}}) == [6]
    # data como lista direta
    assert _extrai_itens({"data": [7]}) == [7]
    # nada reconhecível
    assert _extrai_itens({"foo": "bar"}) == []
    assert _extrai_itens("lixo") == []


def test_extrai_total_variantes():
    assert _extrai_total({"total": 42}) == 42
    assert _extrai_total({"count": 3}) == 3
    assert _extrai_total({"totalElements": 10}) == 10
    assert _extrai_total({"data": {"totalRegistros": 7}}) == 7
    assert _extrai_total({"sem": "total"}) is None
    assert _extrai_total([1, 2, 3]) is None


def test_normalize_tolera_grafias():
    # campos com casing/nomes diferentes (a Comunica varia por edição)
    item = {
        "numeroProcessoComMascara": "0001234-56.2026.8.06.0001",
        "texto": "Intimação para manifestar",
        "dataDisponibilizacao": "2026-07-20",
        "siglaTribunal": "TJCE",
        "id": 99,
    }
    c = _normalize(item)
    assert c.numero_cnj == "00012345620268060001"   # só dígitos
    assert c.numero_cnj_fmt == "0001234-56.2026.8.06.0001"
    assert c.tribunal == "TJCE" and c.id_externo == "99"
