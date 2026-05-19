from dataclasses import dataclass


@dataclass
class PetitionTemplate:
    tipo: str
    titulo: str
    instrucoes: str
    secoes_obrigatorias: list[str]
    formality_level: str  # ALTA (STJ/STF), MEDIA (JEF), BAIXA (JUIZADO)


TEMPLATES: dict[str, PetitionTemplate] = {
    "PETICAO_INICIAL": PetitionTemplate(
        tipo="PETICAO_INICIAL",
        titulo="Petição Inicial",
        instrucoes="""Estruture com: endereçamento ao juízo, qualificação completa das partes,
        exposição dos fatos (narrativa cronológica), fundamentação jurídica (artigos de lei + jurisprudência),
        pedidos numerados (principal e subsidiários), valor da causa, requerimentos finais.""",
        secoes_obrigatorias=["DOS_FATOS", "DO_DIREITO", "DOS_PEDIDOS", "DO_VALOR_DA_CAUSA"],
        formality_level="ALTA",
    ),
    "CONTESTACAO": PetitionTemplate(
        tipo="CONTESTACAO",
        titulo="Contestação",
        instrucoes="""Estruture com: preliminares processuais (se houver), impugnação específica
        dos fatos (não negue o que não puder refutar), fundamentação jurídica da defesa,
        pedidos de improcedência.""",
        secoes_obrigatorias=["DAS_PRELIMINARES", "DO_MERITO", "DOS_PEDIDOS"],
        formality_level="ALTA",
    ),
    "RECURSO_APELACAO": PetitionTemplate(
        tipo="RECURSO_APELACAO",
        titulo="Apelação",
        instrucoes="""Estruture com: tempestividade, legitimidade, interesse recursal,
        resumo da sentença impugnada, razões do recurso (error in judicando ou error in procedendo),
        pedido de reforma ou anulação.""",
        secoes_obrigatorias=["DA_ADMISSIBILIDADE", "DAS_RAZOES", "DOS_PEDIDOS"],
        formality_level="ALTA",
    ),
    "RECURSO_ORDINARIO": PetitionTemplate(
        tipo="RECURSO_ORDINARIO",
        titulo="Recurso Ordinário",
        instrucoes="Similar à apelação. Adeque ao tribunal de destino (TST, STJ, STF).",
        secoes_obrigatorias=["DA_ADMISSIBILIDADE", "DAS_RAZOES", "DOS_PEDIDOS"],
        formality_level="ALTA",
    ),
    "MEMORIAIS": PetitionTemplate(
        tipo="MEMORIAIS",
        titulo="Memoriais",
        instrucoes="""Sintetize os pontos controvertidos, reforce as provas produzidas,
        rebata os argumentos da parte contrária, consolide os pedidos.""",
        secoes_obrigatorias=["RESUMO_INSTRUCAO", "DAS_RAZOES_FINAIS", "DOS_PEDIDOS"],
        formality_level="MEDIA",
    ),
    "IMPUGNACAO_CUMPRIMENTO": PetitionTemplate(
        tipo="IMPUGNACAO_CUMPRIMENTO",
        titulo="Impugnação ao Cumprimento de Sentença",
        instrucoes="Fundamente em art. 525 do CPC/2015. Aponte excesso, nulidade ou ilegitimidade.",
        secoes_obrigatorias=["DA_IMPUGNACAO", "DOS_FUNDAMENTOS", "DOS_PEDIDOS"],
        formality_level="ALTA",
    ),
    "NOTIFICACAO_EXTRAJUDICIAL": PetitionTemplate(
        tipo="NOTIFICACAO_EXTRAJUDICIAL",
        titulo="Notificação Extrajudicial",
        instrucoes="Identifique notificante e notificado, descreva a obrigação, fixe prazo e consequências.",
        secoes_obrigatorias=["DO_OBJETO", "DA_EXIGENCIA", "DO_PRAZO"],
        formality_level="MEDIA",
    ),
}


def get_template(tipo: str) -> PetitionTemplate:
    return TEMPLATES.get(tipo, TEMPLATES["PETICAO_INICIAL"])


TIPO_PETICAO_MAP = {
    "inicial": "PETICAO_INICIAL",
    "contestação": "CONTESTACAO",
    "apelação": "RECURSO_APELACAO",
    "recurso": "RECURSO_APELACAO",
    "memoriais": "MEMORIAIS",
    "impugnação": "IMPUGNACAO_CUMPRIMENTO",
    "notificação": "NOTIFICACAO_EXTRAJUDICIAL",
}
