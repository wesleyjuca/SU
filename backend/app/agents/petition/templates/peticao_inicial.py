"""Template expandido de Petição Inicial para o AFJ petition_agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PeticaoInicialTemplate:
    tipo: str = "PETICAO_INICIAL"
    titulo: str = "Petição Inicial"
    formality_level: str = "ALTA"

    secoes_obrigatorias: list[str] = field(default_factory=lambda: [
        "ENDERECAMENTO",
        "QUALIFICACAO_REQUERENTE",
        "QUALIFICACAO_REQUERIDO",
        "DOS_FATOS",
        "DO_DIREITO",
        "DOS_PEDIDOS",
        "DO_VALOR_DA_CAUSA",
        "DOS_REQUERIMENTOS_FINAIS",
    ])

    instrucoes_gerais: str = """
    Redija petição inicial de acordo com o art. 319 do CPC/2015.
    Use linguagem jurídica formal brasileira. Seja objetivo e preciso.
    Fundamente EXCLUSIVAMENTE em dispositivos legais e jurisprudência do contexto fornecido.
    Marque com [COMPLETAR] qualquer informação que precise ser fornecida pelo advogado.
    NUNCA fabrique jurisprudência, número de processo ou nome de ministro/relator.
    """

    template_estrutura: str = """
EXCELENTÍSSIMO(A) SENHOR(A) DOUTOR(A) JUIZ(A) DE DIREITO DA [COMPLETAR: VARA E COMARCA]

[NOME COMPLETO DO AUTOR/REQUERENTE], [qualificação completa: nacionalidade, estado civil,
profissão, portador do RG nº [COMPLETAR], inscrito no CPF/MF sob o nº [COMPLETAR],
residente e domiciliado à [COMPLETAR: endereço completo]], por seu advogado que esta subscreve
(procuração anexa), vem respeitosamente à presença de Vossa Excelência, com fundamento no(s)
art(s). [COMPLETAR: dispositivos legais], propor a presente

AÇÃO [COMPLETAR: TIPO DA AÇÃO]

em face de [NOME COMPLETO DO RÉU/REQUERIDO], [qualificação: nacionalidade, estado civil,
profissão, inscrito no CPF/CNPJ nº [COMPLETAR], sediado/residente à [COMPLETAR: endereço]],
pelos fatos e fundamentos a seguir expostos:

I — DOS FATOS

[Narrativa cronológica clara e objetiva dos fatos relevantes.
Apresente apenas fatos verídicos e comprováveis com os documentos que serão juntados.
Numere os fatos quando houver mais de três.]

II — DO DIREITO

[Fundamente juridicamente o pedido.
Cite apenas normas e precedentes do contexto fornecido pelo sistema RAG.
Estruture em subitens quando aplicável:

II.1 — [COMPLETAR: Subtítulo do primeiro fundamento jurídico]
II.2 — [COMPLETAR: Subtítulo do segundo fundamento jurídico]]

III — DOS PEDIDOS

Ante o exposto, requer a Vossa Excelência:

a) A citação do Requerido no endereço acima para, querendo, contestar a presente ação,
   sob pena de revelia;

b) A procedência dos pedidos para:
   i) [COMPLETAR: primeiro pedido principal];
   ii) [COMPLETAR: segundo pedido, se aplicável];

c) A condenação do Réu ao pagamento das custas processuais e honorários advocatícios,
   na forma do art. 85 do CPC/2015;

d) A produção de todas as provas admitidas em Direito, especialmente [COMPLETAR: tipos de prova:
   documental, testemunhal, pericial].

IV — DO VALOR DA CAUSA

Dá-se à causa o valor de R$ [COMPLETAR: valor] ([COMPLETAR: valor por extenso]), nos termos
do art. [COMPLETAR: artigo do CPC] do Código de Processo Civil.

Nesses termos,
Pede deferimento.

[COMPLETAR: Cidade/UF], [COMPLETAR: data por extenso].

_______________________________________
[COMPLETAR: Nome completo do advogado]
OAB/[COMPLETAR: UF] nº [COMPLETAR: número]
"""

    checklist_pre_envio: list[str] = field(default_factory=lambda: [
        "Procuração com poderes específicos para a ação",
        "Documentos de identificação do autor (RG, CPF)",
        "Documentos que comprovam os fatos narrados",
        "Guia de custas processuais (se aplicável)",
        "Endereço completo do réu para citação",
        "Prova do valor da causa (orçamentos, contratos, etc.)",
    ])

    def render(self, context: dict[str, Any]) -> str:
        """Renderiza o template substituindo variáveis do contexto."""
        output = self.template_estrutura

        substitutions: dict[str, str] = {
            "[COMPLETAR: VARA E COMARCA]": context.get("vara_comarca", "[COMPLETAR: VARA E COMARCA]"),
            "[COMPLETAR: TIPO DA AÇÃO]": context.get("tipo_acao", "[COMPLETAR: TIPO DA AÇÃO]"),
        }

        for placeholder, value in substitutions.items():
            if value and value != placeholder:
                output = output.replace(placeholder, value)

        return output

    def get_system_prompt(self) -> str:
        return f"""SISTEMA: Você é advogado especialista do escritório Almeida, Freire & Jucá Advogados (AFJ).

REGRAS ABSOLUTAS — NUNCA VIOLAR:
1. NUNCA fabrique jurisprudência, acórdãos, súmulas, número de processo ou nome de relator.
2. Use APENAS os precedentes e dispositivos legais fornecidos no contexto RAG abaixo.
3. Se a informação não estiver no contexto, escreva [COMPLETAR] — nunca invente.
4. Use linguagem jurídica formal brasileira (ABNT NBR 10520 para citações).
5. Siga EXATAMENTE a estrutura da Petição Inicial (art. 319, CPC/2015).
6. Seções obrigatórias: {', '.join(self.secoes_obrigatorias)}

{self.instrucoes_gerais}
"""


PETICAO_INICIAL_TEMPLATE = PeticaoInicialTemplate()
