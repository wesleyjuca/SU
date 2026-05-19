"""Template expandido de Recurso de Apelação para o AFJ petition_agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecursoApelacaoTemplate:
    tipo: str = "RECURSO_APELACAO"
    titulo: str = "Apelação Cível"
    formality_level: str = "ALTA"

    secoes_obrigatorias: list[str] = field(default_factory=lambda: [
        "ENDERECAMENTO_TRIBUNAL",
        "QUALIFICACAO_APELANTE",
        "DA_ADMISSIBILIDADE",
        "DA_SINTESE_DA_SENTENCA",
        "DAS_RAZOES_RECURSAIS",
        "DOS_PEDIDOS",
    ])

    instrucoes_gerais: str = """
    Redija Recurso de Apelação nos termos dos arts. 1.009 a 1.021 do CPC/2015.
    Demonstre tempestividade (prazo de 15 dias úteis — art. 1.003 CPC).
    Identifique com precisão os vícios da sentença (error in judicando ou error in procedendo).
    Fundamente em lei e jurisprudência EXCLUSIVAMENTE do contexto RAG fornecido.
    Marque [COMPLETAR] para qualquer dado que precise ser verificado pelo advogado.
    NUNCA fabrique número de acórdão, nome de relator ou data de julgamento.
    """

    template_estrutura: str = """
EGRÉGIO TRIBUNAL DE JUSTIÇA DO ESTADO DE [COMPLETAR: UF]
[COMPLETAR: Câmara/Turma julgadora, se já definida]

[NOME COMPLETO DO APELANTE], já qualificado nos autos do processo em epígrafe
([COMPLETAR: número CNJ do processo]), por seu advogado que esta subscreve, vem
tempestivamente interpor o presente

RECURSO DE APELAÇÃO

contra a r. sentença proferida pelo(a) MM. Juiz(a) [COMPLETAR: nome do juiz, se disponível]
da [COMPLETAR: vara/juízo de origem], conforme os fundamentos a seguir:

I — DA ADMISSIBILIDADE

1.1 Da Tempestividade
A sentença foi publicada em [COMPLETAR: data de publicação], sendo o prazo recursal de
15 (quinze) dias úteis, na forma do art. 1.003, § 5º, do CPC/2015. A presente apelação é
interposta dentro do prazo legal. [COMPLETAR: confirmar datas e contagem de prazo]

1.2 Da Legitimidade e Interesse Recursal
O Apelante possui legitimidade (art. 996, caput, CPC) e interesse recursal, pois a sentença
lhe foi desfavorável no seguinte aspecto: [COMPLETAR: descrever prejuízo sofrido].

1.3 Do Preparo
O preparo será recolhido nos termos da tabela vigente do [COMPLETAR: tribunal].
[COMPLETAR: Se for caso de gratuidade ou isenção, incluir fundamento]

II — DA SÍNTESE DA SENTENÇA RECORRIDA

O Douto Juízo a quo julgou [COMPLETAR: procedente/improcedente] o pedido do(a)
[COMPLETAR: autor/réu], sob os seguintes fundamentos:

a) [COMPLETAR: Primeiro fundamento da sentença];
b) [COMPLETAR: Segundo fundamento da sentença, se houver].

[COMPLETAR: Transcrever, se necessário, o trecho decisório relevante da sentença]

III — DAS RAZÕES DO RECURSO

O Apelante sustenta que a sentença incidiu em:
[Escolher e desenvolver, conforme o caso:]

3.1 — Error in Judicando — Equívoco na aplicação do Direito
[Desenvolver apenas se a sentença aplicou incorretamente a lei ou jurisprudência.
Citar os dispositivos legais corretos do contexto RAG.
Citar apenas precedentes fornecidos pelo sistema RAG — NUNCA inventar.]

3.2 — Error in Judicando — Equívoco na apreciação da prova
[Desenvolver apenas se houve má apreciação das provas dos autos.
Indicar especificamente as provas equivocadas e como deveriam ter sido valoradas.]

3.3 — Error in Procedendo — Nulidade processual
[Desenvolver apenas se há vício processual.
Indicar o ato nulo, o dispositivo violado e o prejuízo (pas de nullité sans grief).]

IV — DOS PEDIDOS

Ante o exposto, requer o Apelante:

a) O conhecimento e provimento do presente Recurso de Apelação, para que seja:
   i) Reformada a r. sentença, julgando-se [procedente/improcedente] o pedido;
   [OU]
   ii) Anulada a sentença, determinando-se o retorno dos autos à origem para nova instrução;

b) A inversão do ônus de sucumbência, com condenação da parte contrária ao pagamento das
   custas processuais e honorários advocatícios de ambas as instâncias, na forma do
   art. 85 do CPC/2015.

Nesses termos,
Pede deferimento.

[COMPLETAR: Cidade/UF], [COMPLETAR: data por extenso].

_______________________________________
[COMPLETAR: Nome completo do advogado]
OAB/[COMPLETAR: UF] nº [COMPLETAR: número]
"""

    checklist_pre_envio: list[str] = field(default_factory=lambda: [
        "Certidão de publicação da sentença (para contar prazo)",
        "Sentença completa em cópia",
        "Comprovante de recolhimento do preparo (ou pedido de gratuidade)",
        "Procuração com poderes para recorrer",
        "Cópia das principais peças do processo",
        "Confirmação da tempestividade (15 dias úteis)",
    ])

    def render(self, context: dict[str, Any]) -> str:
        output = self.template_estrutura
        substitutions = {
            "[COMPLETAR: UF]": context.get("uf", "[COMPLETAR: UF]"),
            "[COMPLETAR: número CNJ do processo]": context.get("numero_cnj", "[COMPLETAR: número CNJ]"),
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
4. Demonstre tempestividade claramente (art. 1.003, § 5º, CPC/2015 — 15 dias úteis).
5. Identifique com precisão: error in judicando vs. error in procedendo.
6. Seções obrigatórias: {', '.join(self.secoes_obrigatorias)}

{self.instrucoes_gerais}
"""


RECURSO_APELACAO_TEMPLATE = RecursoApelacaoTemplate()
