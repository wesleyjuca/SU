"""Fase 84 — classificação de camadas/pesos do Mapa Neural (lógica pura)."""
from app.services import system_map as sm


def test_ids_conhecidos_tem_camada_fixa():
    assert sm._classificar_camada({"id": "api"}) == "nucleo"
    assert sm._classificar_camada({"id": "orchestrator"}) == "inteligencia"
    assert sm._classificar_camada({"id": "llm"}) == "inteligencia"
    assert sm._classificar_camada({"id": "qdrant"}) == "inteligencia"
    assert sm._classificar_camada({"id": "postgres"}) == "memoria"
    assert sm._classificar_camada({"id": "redis"}) == "memoria"
    assert sm._classificar_camada({"id": "celery"}) == "execucao"
    assert sm._classificar_camada({"id": "captura"}) == "execucao"


def test_padroes_de_prefixo_sufixo_auto_crescem():
    # qualquer agente novo (xxx_agent) cai em inteligencia, sem hardcode de nome
    assert sm._classificar_camada({"id": "escavador_agent", "grupo": "agentes"}) == "inteligencia"
    assert sm._classificar_camada({"id": "novo_conector_agent"}) == "inteligencia"
    # qualquer provider/fonte novo cai em integracoes
    assert sm._classificar_camada({"id": "prov_novopagamento"}) == "integracoes"
    assert sm._classificar_camada({"id": "fonte_jusbrasil"}) == "integracoes"


def test_fallback_por_grupo_para_id_desconhecido():
    assert sm._classificar_camada({"id": "modulo_x", "grupo": "infra"}) == "memoria"
    assert sm._classificar_camada({"id": "modulo_y", "grupo": "agentes"}) == "inteligencia"
    assert sm._classificar_camada({"id": "modulo_z", "grupo": "integracoes"}) == "integracoes"
    assert sm._classificar_camada({"id": "modulo_w", "grupo": "desconhecido"}) == "integracoes"


def test_peso_no_nucleo_maior_que_servico_central_maior_que_folha():
    assert sm._peso_no({"id": "api"}) == 5
    assert sm._peso_no({"id": "celery"}) == 3
    assert sm._peso_no({"id": "algum_agent"}) == 1
    assert sm._peso_no({"id": "api"}) > sm._peso_no({"id": "celery"}) > sm._peso_no({"id": "algum_agent"})


def test_peso_aresta_estrutural_maior_que_folha():
    assert sm._peso_aresta("dados") == 3
    assert sm._peso_aresta("ia") == 3
    assert sm._peso_aresta("roteia") == 1
    assert sm._peso_aresta("conecta") == 1
    assert sm._peso_aresta("fonte") == 1


def test_construir_mapa_aplica_camada_e_peso_em_todos_os_nos():
    mapa = sm.construir_mapa()
    for no in mapa["nos"]:
        assert "camada" in no and no["camada"] in {"nucleo", "inteligencia", "memoria", "execucao", "integracoes"}
        assert "peso" in no and no["peso"] > 0
    for a in mapa["arestas"]:
        assert "peso" in a and a["peso"] > 0
    # o núcleo continua único e com o maior peso
    api = next(n for n in mapa["nos"] if n["id"] == "api")
    assert api["camada"] == "nucleo"
    assert all(n["peso"] <= api["peso"] for n in mapa["nos"])
