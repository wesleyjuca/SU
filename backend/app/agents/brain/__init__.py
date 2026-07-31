"""agents/brain — motor de orquestração real (LangGraph).

- `orchestrator.py` executa o grafo (classify_intent → retrieve_memory →
  execute_agent → check_approval).
- `router.py` classifica a intenção da tarefa e roteia pro(s) agente(s) certo(s).
- `context.py` define `AgentContext`, o estado compartilhado lido/escrito por
  todos os 19 agentes durante um run.

Quem chama esse motor de fora (API `/agents/trigger`, worker Celery) não usa
este pacote diretamente — passa por `agents/orchestration/orchestration_agent.py`,
um adaptador fino que só monta o `AgentContext` e delega pra cá.
"""
