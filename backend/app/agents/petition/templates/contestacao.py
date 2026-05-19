"""Template expandido de Contestação para o AFJ petition_agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ContestacaoTemplate:
    tipo: str = "CONTESTACAO"
    titulo: str = "Contestação"
    formality_level: str = "ALTA"

    secoes_obrigatorias: list[str] = field(default_factory=lambda: [
        "ENDERECAMENTO",
        "QUALIFICACAO_REU",
        "DAS_PRELIMINARES",
        "DO_MERITO",
        "DA_IMPUGNACAO_ESPECIFICA",
        "DOS_PEDIDOS",
    ])

    instrucoes_gerais: str = """
    Redija Contestação nos termos do art. 335 e seguintes do CPC/2015.
    Prazo: 15 dias úteis (arts. 335 e 219, CPC) — confirmar data de citação.
    ATENÇÃO: Toda matéria de defesa deve ser alegada na contestação (princípio da eventualidade — art. 336).
    Impugne ESPECIFICAMENTE cada fato alegado na inicial (art. 341, CPC) — não basta negativa genérica.
    Fundamente em lei e jurisprudência EXCLUSIVAMENTE do contexto RAG fornecido.
    NUNCA fabrique número de processo, acórdão ou nome de relator.
    Marque [COMPLETAR] para qualquer informação a ser verificada.
    """

    template_estrutura: str = """
EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA [COMPLETAR: VARA E COMARCA]

Autos nº [COMPLETAR: número CNJ do processo]

[NOME COMPLETO DO RÉU], já qualificado na petição inicial, por seu advogado (procuração
nos autos), vem tempestivamente, nos termos do art. 335 do CPC/2015, apresentar

CONTESTAÇÃO

aos termos da ação [COMPLETAR: tipo de ação] ajuizada por [NOME DO AUTOR], pelos fatos
e fundamentos a seguir:

I — DAS PRELIMINARES PROCESSUAIS

[Alegar APENAS as matérias de defesa processual cabíveis. Suprimir as que não se aplicam.]

1.1 — Inépcia da Petição Inicial
[Incluir apenas se a inicial não preencher os requisitos do art. 319 ou art. 330, CPC.]

1.2 — Ilegitimidade de Parte
[Incluir apenas se o Autor ou o Réu não for o titular do direito ou da obrigação discutida.]

1.3 — Falta de Interesse de Agir
[Incluir apenas se a via judicial for desnecessária ou inadequada.]

1.4 — Incompetência do Juízo
[Incluir apenas se outro juízo for competente em razão da matéria, pessoa ou território.]

[COMPLETAR: Outras preliminares, se houver — ex.: litispendência, coisa julgada, perempção]

Diante das preliminares suscitadas, requer-se a extinção do processo sem julgamento do
mérito, nos termos do art. 485 do CPC/2015.

II — DO MÉRITO

Sem prescindir das preliminares, passa-se à defesa do mérito.

2.1 — Da Impugnação Específica dos Fatos

Em atenção ao art. 341 do CPC/2015, o Réu impugna especificamente os fatos narrados
na inicial:

a) Quanto ao fato descrito no item [COMPLETAR: nº do item da inicial]:
   [COMPLETAR: Confirmar, negar ou esclarecer o fato com base em documentos]

b) Quanto ao fato descrito no item [COMPLETAR: nº do item da inicial]:
   [COMPLETAR: Confirmar, negar ou esclarecer o fato com base em documentos]

[COMPLETAR: Repetir para cada fato relevante da inicial]

2.2 — Da Inexistência do Direito Alegado

O direito invocado pelo Autor não procede pelos seguintes fundamentos:

[COMPLETAR: Desenvolver os fundamentos jurídicos da defesa.
Citar apenas dispositivos legais e precedentes do contexto RAG.
Nunca citar jurisprudência que não esteja no contexto fornecido.]

2.3 — [COMPLETAR: Subtítulo do segundo fundamento de mérito, se houver]

[COMPLETAR: Desenvolver]

III — DA IMPUGNAÇÃO AO VALOR DA CAUSA

[Incluir apenas se o valor da causa estiver incorreto — art. 293, CPC]
O valor atribuído à causa (R$ [COMPLETAR]) está incorreto, pois [COMPLETAR: razão].
Requer-se a retificação para R$ [COMPLETAR].

IV — DOS PEDIDOS

Ante o exposto, requer o Réu:

a) O acolhimento das preliminares suscitadas, extinguindo-se o processo sem resolução
   do mérito, nos termos do art. 485 do CPC/2015;

b) Subsidiariamente, caso superadas as preliminares, a total improcedência dos pedidos
   formulados na inicial;

c) A condenação do Autor ao pagamento das custas processuais e honorários advocatícios,
   fixados nos termos do art. 85 do CPC/2015;

d) A produção de todas as provas admitidas em Direito, especialmente:
   [COMPLETAR: tipos de prova: documental, testemunhal, pericial, etc.]

Nesses termos,
Pede deferimento.

[COMPLETAR: Cidade/UF], [COMPLETAR: data por extenso].

_______________________________________
[COMPLETAR: Nome completo do advogado]
OAB/[COMPLETAR: UF] nº [COMPLETAR: número]
"""

    checklist_pre_envio: list[str] = field(default_factory=lambda: [
        "Certidão/mandado de citação (para contar prazo — 15 dias úteis)",
        "Cópia da petição inicial com todos os documentos anexos",
        "Procuração com poderes para contestar",
        "Documentos que embasam a defesa de mérito",
        "Comprovantes para impugnar os fatos da inicial",
        "Verificar se há reconvenção a ser apresentada (art. 343, CPC)",
        "Confirmar todas as preliminares antes de incluir",
    ])

    def render(self, context: dict[str, Any]) -> str:
        output = self.template_estrutura
        substitutions = {
            "[COMPLETAR: VARA E COMARCA]": context.get("vara_comarca", "[COMPLETAR: VARA E COMARCA]"),
            "[COMPLETAR: número CNJ do processo]": context.get("numero_cnj", "[COMPLETAR: número CNJ]"),
            "[COMPLETAR: tipo de ação]": context.get("tipo_acao", "[COMPLETAR: tipo de ação]"),
        }
        for placeholder, value in substitutions.items():
            if value and value != placeholder:
                output = output.replace(placeholder, value)
        return output

    def get_system_prompt(self) -> str:
        return f"""SISTEMA: Você é advogado especialista do escritório Almeida, Freire & Jucá Advogados (AFJ).

REGRAS ABSOLUTAS — NUNCA VIOLAR:
1. NUNCA fabrique acórdão, súmula, número de processo ou nome de relator.
2. Use APENAS precedentes e dispositivos legais do contexto RAG fornecido abaixo.
3. Se a informação não estiver no contexto, escreva [COMPLETAR] — nunca invente.
4. Impugne ESPECIFICAMENTE cada fato da inicial (art. 341, CPC) — negativa genérica é ineficaz.
5. Alegue TODA matéria de defesa na contestação (princípio da eventualidade — art. 336, CPC).
6. Seções obrigatórias: {', '.join(self.secoes_obrigatorias)}

{self.instrucoes_gerais}
"""


CONTESTACAO_TEMPLATE = ContestacaoTemplate()
