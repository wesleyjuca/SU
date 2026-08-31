"""Fase 253 — investigação do marcador de cliente em local incompatível no
mapa confirmou que não havia nenhuma validação de sanidade de coordenada
em lugar nenhum do backend (nem faixa geográfica válida, nem rejeição de
`(0, 0)`, sentinela comum de "não encontrado" em geocodificadores).
`_extrair_coordenadas` ganhou essa checagem — ponto único, todo
consumidor de `consultar_cep()` (Cliente, Tenant, preview do form) fica
protegido de graça."""
from app.integrations.publicas.cep_lookup import _extrair_coordenadas


def test_coordenada_valida_e_aceita():
    data = {"location": {"coordinates": {"latitude": -23.5613, "longitude": -46.6564}}}
    assert _extrair_coordenadas(data) == (-23.5613, -46.6564)


def test_latitude_fora_de_faixa_e_rejeitada():
    data = {"location": {"coordinates": {"latitude": 200.0, "longitude": -46.6564}}}
    assert _extrair_coordenadas(data) == (None, None)


def test_longitude_fora_de_faixa_e_rejeitada():
    data = {"location": {"coordinates": {"latitude": -23.5613, "longitude": -300.0}}}
    assert _extrair_coordenadas(data) == (None, None)


def test_null_island_e_rejeitada():
    data = {"location": {"coordinates": {"latitude": 0, "longitude": 0}}}
    assert _extrair_coordenadas(data) == (None, None)


def test_limites_exatos_da_faixa_sao_aceitos():
    data = {"location": {"coordinates": {"latitude": -90.0, "longitude": 180.0}}}
    assert _extrair_coordenadas(data) == (-90.0, 180.0)


def test_sem_location_devolve_none_sem_lancar():
    assert _extrair_coordenadas({}) == (None, None)
    assert _extrair_coordenadas({"location": {}}) == (None, None)
    assert _extrair_coordenadas({"location": {"coordinates": {}}}) == (None, None)


def test_coordenada_nao_numerica_devolve_none_sem_lancar():
    data = {"location": {"coordinates": {"latitude": "não é número", "longitude": -46.6564}}}
    assert _extrair_coordenadas(data) == (None, None)
