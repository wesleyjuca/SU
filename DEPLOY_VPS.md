# Deploy em VPS (HostGator VPS/Cloud ou qualquer VPS com Docker)

Guia passo-a-passo para publicar o AFJ CORE SYSTEM num servidor próprio.
Vale para **HostGator VPS/Cloud**, Hetzner, DigitalOcean, Contabo, etc.

> ⚠️ **Hospedagem compartilhada (cPanel) NÃO serve.** O plano shared da
> HostGator oferece apenas PHP/MySQL — o sistema exige PostgreSQL, Redis,
> Qdrant, workers Celery e bibliotecas de sistema (Tesseract OCR, WeasyPrint),
> que só funcionam com acesso root/Docker. Contrate **VPS ou Cloud** (com root).

## O que o `docker-compose.prod.yml` sobe

| Serviço     | Função                                                        |
|-------------|---------------------------------------------------------------|
| `caddy`     | Reverse-proxy público (portas 80/443) + **HTTPS automático**  |
| `frontend`  | Next.js (build standalone)                                    |
| `backend`   | API FastAPI (com auto-migração no boot)                       |
| `worker`    | Celery worker (agentes IA, OCR, emails)                       |
| `scheduler` | Celery beat (polling de andamentos, alertas de prazo, DJe)    |
| `db`        | PostgreSQL 16 (volume persistente)                            |
| `redis`     | Fila Celery + cache/rate-limit                                |
| `qdrant`    | Busca vetorial (RAG de jurisprudência/documentos)             |
| `pgbackup`  | Backup diário do banco (02:00, retenção 30 dias)              |

Só o Caddy expõe portas públicas; ele roteia `/api/*` e `/health` para o
backend e todo o resto para o frontend — tudo same-origin, sem CORS no navegador.

## Requisitos

- VPS com **root**, ≥ 4 GB RAM (8 GB recomendado) e ≥ 40 GB de disco
- **Docker Engine + plugin compose** ([instalação](https://docs.docker.com/engine/install/))
- Um **domínio** (ex.: `sistema.seuescritorio.com.br`) com registro **A**
  apontando para o IP do VPS
- Portas **80 e 443** liberadas no firewall

## Passo a passo

### 1. Clonar o repositório

```bash
git clone https://github.com/wesleyjuca/SU.git
cd SU
```

### 2. Criar e preencher o `.env.prod`

```bash
cp .env.prod.example .env.prod
nano .env.prod
```

Preencha no mínimo:

```bash
# Senhas dos serviços (invente valores fortes)
POSTGRES_PASSWORD=<senha-forte>
REDIS_PASSWORD=<senha-forte>

# Chaves fixas de segurança — gere UMA vez no terminal e cole o valor
# (NUNCA troque depois; invalidaria sessões e credenciais cifradas):
#   python3 -c "import secrets; print(secrets.token_urlsafe(48))"   # SECRET_KEY
#   python3 -c "import secrets; print(secrets.token_urlsafe(32))"   # ENCRYPTION_KEY
SECRET_KEY=<cole-o-valor-gerado>
ENCRYPTION_KEY=<cole-o-valor-gerado>

# Domínio + TLS
DOMAIN=sistema.seuescritorio.com.br
ACME_EMAIL=voce@seuescritorio.com.br
CORS_ORIGINS=["https://sistema.seuescritorio.com.br"]

# IA (necessário para os agentes)
ANTHROPIC_API_KEY=sk-ant-...
# RAG/busca jurídica (embeddings)
OPENAI_API_KEY=sk-...
```

> `DATABASE_URL`/`REDIS_URL` **não precisam** ser alterados — o compose já
> injeta as URLs internas (`db:5432` / `redis:6379`) nos serviços.

### 3. Subir tudo

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

O primeiro build leva alguns minutos (frontend + backend). O backend roda
`alembic upgrade head` automaticamente no boot (e o startup do app aplica
`create_all`/ALTERs como rede de segurança).

### 4. Verificar

```bash
docker compose -f docker-compose.prod.yml ps           # tudo "running"?
curl -fsS https://sistema.seuescritorio.com.br/health   # backend ok?
```

Abra `https://sistema.seuescritorio.com.br` no navegador — o certificado
Let's Encrypt é emitido automaticamente na primeira visita (aguarde ~30 s).

### 5. Primeiro acesso

O seed de dados-base (tenant + usuários iniciais) roda **automaticamente** no
primeiro boot do backend. Credenciais iniciais: ver `CLAUDE.md` /
documentação interna — **troque as senhas no primeiro login**.

## Operação

| Tarefa                | Comando                                                                 |
|-----------------------|-------------------------------------------------------------------------|
| Ver logs              | `docker compose -f docker-compose.prod.yml logs -f backend`             |
| Atualizar o sistema   | `git pull && docker compose -f docker-compose.prod.yml up -d --build`   |
| Reiniciar um serviço  | `docker compose -f docker-compose.prod.yml restart worker`              |
| Backup manual do banco| `docker compose -f docker-compose.prod.yml exec db pg_dump -U afj afj_core > backup.sql` |
| Backups automáticos   | volume `backups` (diário às 02:00, retenção 30 dias — serviço `pgbackup`)|

## Solução de problemas

- **Certificado não emite**: confirme que o DNS (registro A) já propagou para
  o IP do VPS e que as portas 80/443 estão abertas (`ufw allow 80,443/tcp`).
- **Worker não processa tarefas**: `docker compose ... logs worker` — confira
  `REDIS_PASSWORD` idêntico no `.env.prod` e se o serviço `redis` está saudável.
- **Captura por OAB retorna "fonte não respondeu"**: o VPS precisa de saída
  para a internet (hosts `comunicaapi.pje.jus.br` e
  `api-publica.datajud.cnj.jus.br`); teste com
  `docker compose ... exec backend curl -sI https://comunicaapi.pje.jus.br`.
- **Banco legado (migrado do Railway)**: se o alembic reclamar de tabelas
  existentes, rode uma única vez
  `docker compose ... exec backend alembic stamp head`.

## Migrando do Railway/Vercel para o VPS

1. Exporte o banco no Railway: `pg_dump $DATABASE_URL > afj.sql`
2. Importe no VPS: `docker compose ... exec -T db psql -U afj afj_core < afj.sql`
3. Copie os MESMOS `SECRET_KEY`/`ENCRYPTION_KEY` do Railway para o `.env.prod`
   (senão tokens BYOK/Google cifrados ficam indecifráveis).
4. Aponte o DNS para o VPS.
