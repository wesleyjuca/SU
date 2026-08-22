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

## Provisionar de graça: Oracle Cloud "Always Free"

Cobre a única lacuna real do restante deste guia: como conseguir a VPS em
si sem custo. Vale só pra esse passo — a partir de "Passo a passo" abaixo,
segue o fluxo genérico normalmente (SSH na VM criada aqui). Não se aplica
a nenhum outro provedor da lista do topo (Hetzner/DigitalOcean/Contabo são
sempre pagos, mesmo no menor plano).

> ⚠️ Em 15/jun/2026 a Oracle cortou pela metade a cota Ampere A1 "Always
> Free" (de 4 OCPU/24GB para **2 OCPU/12GB**), sem aviso público — só
> descoberta quando instâncias começaram a ser encerradas. Contas novas já
> nascem só com a cota reduzida. Mesmo assim, 2 OCPU/12GB continua acima
> do mínimo pedido neste guia (≥4GB, 8GB recomendado) — só não conte com
> a cota antiga, e não trate "grátis pra sempre" como garantia contratual:
> a Oracle já demonstrou que muda os termos sem aviso.

1. **Criar conta** em [cloud.oracle.com](https://cloud.oracle.com) — cartão
   de crédito é exigido só pra verificação de identidade; os recursos
   "Always Free" não são cobrados.
2. **Criar a instância** (Menu → Compute → Instances → Create Instance):
   - Shape: clique em "Change Shape" → aba **Ampere** → `VM.Standard.A1.Flex`
     (o shape ARM elegível pro tier grátis — **não** use os "2 VMs Micro
     AMD", que só têm 1GB RAM cada, insuficiente pra esse stack).
   - Configure **2 OCPU / 12 GB RAM** (a cota Always Free inteira numa
     única instância, em vez de dividir em várias menores).
   - Boot volume: pode ir até ~200GB dentro da cota grátis agregada — deixe
     bem acima dos 40GB mínimos.
   - Imagem: Ubuntu (mais comum, mesma base dos passos de Docker abaixo).
3. **Se aparecer "Out of host capacity"**: não é erro de configuração, é
   disponibilidade da região — troque de Availability Domain (se a região
   tiver mais de uma) ou tente de novo mais tarde/em outra região.
4. **Abrir as portas 80/443 — duas vezes** (essa é a armadilha mais comum
   de quem já tem experiência com VPS "normal" e assume que só a regra de
   rede basta):
   - **Nível de rede (VCN)**: Networking → Virtual Cloud Networks → sua
     VCN → Security Lists → Default Security List → Add Ingress Rules →
     `0.0.0.0/0`, TCP, portas `80` e `443`.
   - **Nível do SO**: as imagens da Oracle já vêm com `iptables`
     bloqueando tráfego não-SSH por padrão — sem isso, o Caddy nunca
     recebe conexão mesmo com a Security List certa:
     ```bash
     # Ubuntu (iptables-persistent)
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
     sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
     sudo netfilter-persistent save

     # Oracle Linux (firewalld, se usar essa imagem em vez de Ubuntu)
     sudo firewall-cmd --permanent --add-port=80/tcp
     sudo firewall-cmd --permanent --add-port=443/tcp
     sudo firewall-cmd --reload
     ```
5. **Instalar Docker** na VM ([guia oficial](https://docs.docker.com/engine/install/ubuntu/)),
   depois seguir o "Passo a passo" abaixo normalmente.
6. **De quebra**: como o `docker-compose.prod.yml` já sobe `frontend` +
   `backend` + `worker` + `scheduler` + `db` + `redis` + `qdrant` + `caddy`
   nessa mesma VM, esse caminho substitui **tanto o backend hospedado
   quanto o frontend hospedado** de uma vez — não é preciso nenhum outro
   provedor pago pra nada além do domínio.
7. **Object storage sem custo**: aproveite pra configurar `S3_BUCKET`/
   `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`/`S3_ENDPOINT_URL` no
   `.env.prod` apontando pro [Cloudflare R2](https://developers.cloudflare.com/r2/)
   (10GB grátis, egress sempre grátis, já é S3-compatível — sem isso,
   documentos ficam em base64 dentro do próprio Postgres, inflando o
   volume da VM à toa).
8. **Backup do serviço `pgbackup`**: a imagem `prodrigorocha/pgbackup` não
   tem build ARM64 confirmado — no primeiro `docker compose up`, confirme
   com `docker compose -f docker-compose.prod.yml ps pgbackup` que o
   container subiu; se falhar por arquitetura, substitua por um cron
   simples na própria VM chamando o comando de backup manual da tabela de
   Operação abaixo.

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
