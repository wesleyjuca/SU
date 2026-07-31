"""agents/orchestration — adaptador de entrada fino, não motor.

`orchestration_agent.py` é o ponto de entrada padrão pra disparar qualquer
agente a partir de fora (API `/agents/trigger`, worker Celery): monta o
`AgentContext` (`agents/brain/context.py`) e delega a execução real pro grafo
LangGraph em `agents/brain/orchestrator.py`. Não contém lógica de
orquestração própria — é intencionalmente magro.
"""
