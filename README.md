# AI Visibility POC

Pipeline de diagnostico de visibilidade de medicos em buscas de IA.

> Implementa **P0.2 (diagnostico gratuito) + P0.7 (monitor de prompts) + P0.8 (AI Visibility Score)** do PRD iMedicina AI Visibility — o slice que valida a tese tecnica central: "conseguimos medir programaticamente se um medico aparece quando pacientes perguntam a uma IA?"

## O que faz

Dado o nome, especialidade e cidade de um medico, o pipeline:

1. **Gera 10 prompts realistas** que pacientes fariam a uma IA buscando esse tipo de medico (10 personas distintas)
2. **Roda buscas web reais** via OpenAI `web_search_preview` — retorna medicos reais com fontes citadas
3. **Avalia cada resposta** com LLM-as-Judge decomposed: o medico foi citado? Como? Quem aparece no lugar?
4. **Calcula um score 0-100** com 2 dimensoes (Visibilidade 65% + Dominancia 35%) e recomendacoes acionaveis

---

## Screenshots

**Score alto (85/100) — Dra. Karina Zold, Dermatologia, Campinas:**

![Report - Score Alto](docs/screenshots/report-score-high.png)

**Score baixo (32/100) — Dra. Mariana Costa (ficticia), Dermatologia, Sao Paulo:**

![Report - Score Baixo](docs/screenshots/report-score-low.png)

**Tabela de vereditos — cada prompt avaliado individualmente:**

![Report - Vereditos](docs/screenshots/report-chat-simulation.png)

---

## Quick start

### Opcao 1: Docker (recomendado)

```bash
git clone <repo-url> && cd ai-visibility-poc
cp .env.example .env   # preencha OPENAI_API_KEY
docker compose up       # sobe app + postgres
```

Acesse http://localhost:8000 — dashboard web com cadastro de medicos e execucao de analises.

### Opcao 2: Local (CLI)

```bash
pip install -e ".[dev]"
cp .env.example .env   # preencha OPENAI_API_KEY
python -m ai_visibility run \
  --name "Dr. Fernando Lopes" \
  --crm "169135" --crm-state "SP" \
  --specialty "Dermatologia" \
  --city "Campinas" --state "SP" \
  --output ./output/dr_fernando_lopes
```

### Opcao 3: Makefile

```bash
make install   # pip install -e ".[dev]"
make example   # roda exemplo da Dra. Mariana Costa
make test      # pytest -v
```

---

## Arquitetura — 4 estagios

![Pipeline Architecture](docs/diagrams/pipeline-architecture.png)

<details>
<summary>Versao texto</summary>

```
Input (nome, especialidade, cidade)
         |
         v
  Stage 1: GERADOR
  gpt-4.1-mini . structured output
  10 prompts variados (10 personas)
  Cache: especialidade x cidade
         |
         v
  Stage 2: SIMULADOR
  gpt-4.1-mini + web_search_preview
  Busca web real . medicos reais + fontes
  10 chamadas em paralelo (asyncio.gather)
         |
         v
  Stage 3: JUDGE
  gpt-4.1-mini . temperature=0
  LLM-as-Judge decomposed (3 perguntas binarias)
  Classifica: mentioned_by_name | specialty | competitor | not_mentioned
  evidence_quote obrigatorio (reduz alucinacao)
  Retry com backoff exponencial
         |
         v
  Stage 4: SCORER
  Python puro . deterministico
  Score 0-100 . reproduzivel +/-0 pontos
  2 dimensoes ponderadas + 1 informativa + recomendacoes
         |
         v
  Outputs: report.html, report.md, report.json, trace.jsonl
```

</details>

---

## Arquitetura do sistema

![System Architecture](docs/diagrams/system-architecture.png)

---

## Web UI

Dashboard web completo em FastAPI + Jinja2 + HTMX + DaisyUI (Tailwind).

**Fluxos disponiveis:**

| Fluxo | Rota | Descricao |
|-------|------|-----------|
| Dashboard | `/` | Visao geral: medicos cadastrados, analises recentes, scores |
| Cadastrar medico | `/doctors/new` | Form com nome, especialidade, cidade, CRM |
| Detalhe do medico | `/doctors/{id}` | Historico de analises, melhor score, score recente |
| Iniciar analise | `/runs/new` | Seleciona medico, inicia pipeline em background |
| Resultado da analise | `/runs/{id}` | Polling HTMX em tempo real, relatorio interativo ao concluir |

**Progresso em tempo real:** enquanto o pipeline roda (~60-90s), a UI faz polling a cada 3s via HTMX e mostra mensagens de progresso por estagio.

### Iniciar o servidor

```bash
# Via Docker
docker compose up

# Ou diretamente
python -m ai_visibility serve --host 0.0.0.0 --port 8000
```

Acesse http://localhost:8000.

---

## API (JSON)

API REST completa para integracao com frontends. Documentacao interativa em `/docs` (Swagger UI auto-gerado pelo FastAPI).

### Doctors

| Metodo | Endpoint | Descricao | Response |
|--------|----------|-----------|----------|
| `GET` | `/api/doctors` | Lista medicos com contagem de runs e ultimo score | `DoctorSummary[]` |
| `GET` | `/api/doctors/{id}` | Detalhe do medico + historico de runs | `DoctorDetail` |
| `POST` | `/api/doctors` | Cria medico | `DoctorSummary` (201) |
| `DELETE` | `/api/doctors/{id}` | Remove medico e runs (CASCADE) | 204 |

### Runs (analises)

| Metodo | Endpoint | Descricao | Response |
|--------|----------|-----------|----------|
| `GET` | `/api/runs` | Ultimas 20 analises | `RunSummary[]` |
| `GET` | `/api/runs/{id}` | Detalhe com report completo + recomendacoes | `RunDetail` |
| `GET` | `/api/runs/{id}/status` | Polling leve (status + progresso) | `RunStatusResponse` |
| `POST` | `/api/runs` | Cria e inicia analise em background | `RunCreateResponse` (201) |

### Exemplo: criar medico e rodar analise

```bash
# Criar medico
curl -X POST http://localhost:8000/api/doctors \
  -H "Content-Type: application/json" \
  -d '{"name": "Dr. Fernando Lopes", "specialty": "Dermatologia", "city": "Campinas", "state": "SP", "crm": "169135", "crm_state": "SP"}'

# Iniciar analise
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"doctor_id": "<uuid-retornado>"}'

# Polling de status
curl http://localhost:8000/api/runs/<run-id>/status
```

### Seed de dados (importar exemplos pre-gerados)

```bash
curl -X POST http://localhost:8000/api/seed \
  -H "Content-Type: application/json" \
  -d @examples/dra_karina_zold/report.json
```

---

## CLI

```bash
# Rodar diagnostico completo
python -m ai_visibility run \
  --name "Dr. Fernando Lopes" \
  --specialty "Dermatologia" \
  --city "Campinas" \
  --output ./output/dr_fernando

# Re-renderizar relatorios sem reconsumir API
python -m ai_visibility report ./output/dr_fernando

# Inspecionar trace de chamadas LLM
python -m ai_visibility trace ./output/dr_fernando --stage judge

# Iniciar servidor web
python -m ai_visibility serve --host 0.0.0.0 --port 8000
```

---

## Exemplos pre-gerados

Tres diagnosticos prontos em `examples/` para teste sem gastar API:

| Medico | Tipo | Score | Presenca | Insight |
|--------|------|-------|----------|---------|
| Dra. Mariana Costa | Ficticia | **32/100** | 2/10 | Baixa visibilidade — aparece raramente |
| Dr. Fernando Lopes | Real (Campinas) | **18/100** | 2/10 | Aparece raramente, perde espaco para concorrentes |
| Dra. Karina Zold | Real (Campinas) | **85/100** | 8/10 | Domina as recomendacoes de IA na regiao |

```bash
# Ver relatorio visual
open examples/dra_karina_zold/report.html

# Importar no dashboard web (com server rodando)
curl -X POST http://localhost:8000/api/seed \
  -H "Content-Type: application/json" \
  -d @examples/dra_karina_zold/report.json
```

---

## Database

PostgreSQL 16 com 3 tabelas:

```sql
-- Medicos cadastrados
CREATE TABLE doctors (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name         TEXT NOT NULL,
    specialty    TEXT NOT NULL,
    city         TEXT NOT NULL,
    state        TEXT,
    neighborhood TEXT,
    crm          TEXT,
    crm_state    TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Execucoes do pipeline
CREATE TABLE runs (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doctor_id    UUID NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    status       TEXT NOT NULL DEFAULT 'pending',  -- pending | running | completed | failed
    score        REAL,
    error        TEXT,
    report_json  JSONB,                            -- Report completo serializado
    progress     TEXT DEFAULT '',                   -- Mensagem de progresso em tempo real
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

-- Cache de prompts por especialidade x cidade
CREATE TABLE prompt_cache (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL,                     -- GeneratedPrompts serializado
    expires_at TIMESTAMPTZ NOT NULL               -- TTL configuravel (default 24h)
);
```

**Indices:** `idx_runs_doctor_id`, `idx_runs_created_at DESC`.

Schema aplicado automaticamente no boot via `init_pool()`. Em modo CLI (sem Postgres), o cache faz fallback para dicionario em memoria.

---

## Infraestrutura e deploy

### Docker

**Multi-stage build** para imagem minima:

```dockerfile
# Stage 1: builder (gcc, libpq-dev, pip install)
# Stage 2: runtime (libpq5 apenas, copia site-packages do builder)
# Imagem final: python:3.11-slim
```

```bash
docker compose up        # App (porta 8000) + Postgres (porta 5432)
docker compose down -v   # Para e remove volumes
```

### CI/CD (GitHub Actions)

Pipeline automatizado em `.github/workflows/ci-cd.yml`:

```
Push/PR para main
    |
    v
[Tests] pytest -v (ubuntu-latest, Python 3.11)
    |
    v (apenas push em main)
[Deploy] Build imagem -> Push ECR -> Update ECS task -> Deploy ECS -> Wait stable
```

### AWS (producao)

```
GitHub Actions
    |
    v
ECR (container registry)
    |
    v
ECS Fargate (serverless containers)
    |
    v
ALB (load balancer, porta 8000)
    |
    v
RDS PostgreSQL (managed)
```

| Recurso | Valor |
|---------|-------|
| Regiao | us-east-1 |
| ECR repository | ai-visibility |
| ECS cluster | ai-visibility |
| ECS service | ai-visibility |
| Task family | ai-visibility |

**Deploy manual** (sem CI):

```bash
./infra/deploy.sh   # build, push ECR, deploy ECS, wait stable
```

---

## Observabilidade

### Langfuse (LLM tracing)

Integracao drop-in — basta trocar o import de `openai.AsyncOpenAI` para `langfuse.openai.AsyncOpenAI`. Toda chamada LLM eh capturada automaticamente:

- Tokens (input/output)
- Custo estimado (USD)
- Latencia (ms)
- Inputs/outputs completos
- Stage do pipeline

Configuracao via variaveis de ambiente (opcionais — pipeline funciona sem Langfuse):

```env
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_BASE_URL=https://us.cloud.langfuse.com
```

### trace.jsonl (fallback local)

Cada execucao gera um `trace.jsonl` com uma linha por chamada LLM:

```json
{
  "timestamp": "2026-05-27T...",
  "stage": "judge",
  "prompt_id": "p3",
  "model": "gpt-4.1-mini-2025-04-14",
  "tokens_in": 1250,
  "tokens_out": 180,
  "latency_ms": 1842,
  "cost_usd": 0.000788,
  "status": "success"
}
```

Inspecionar via CLI:

```bash
python -m ai_visibility trace ./output/dr_fernando --stage judge
```

### Custo por diagnostico

~$0.12 por execucao (21 chamadas LLM):

| Stage | Chamadas | Custo |
|-------|----------|-------|
| Generator | 1 | ~$0.002 |
| Simulator (web search) | 10 | ~$0.11 |
| Judge | 10 | ~$0.006 |
| **Total** | **21** | **~$0.12** |

---

## Variaveis de ambiente

| Variavel | Obrigatoria | Default | Descricao |
|----------|-------------|---------|-----------|
| `OPENAI_API_KEY` | Sim (para rodar pipeline) | — | Chave da API OpenAI |
| `DATABASE_URL` | Nao (web UI) | `postgresql://app:dev@localhost:5432/ai_visibility` | Connection string PostgreSQL |
| `LANGFUSE_SECRET_KEY` | Nao | — | Chave secreta Langfuse |
| `LANGFUSE_PUBLIC_KEY` | Nao | — | Chave publica Langfuse |
| `LANGFUSE_BASE_URL` | Nao | `https://us.cloud.langfuse.com` | URL do servidor Langfuse |

**Configuracoes internas** (via `config.py`, editaveis por env var):

| Variavel | Default | Descricao |
|----------|---------|-----------|
| `MODEL_GENERATOR` | `gpt-4.1-mini-2025-04-14` | Modelo do Stage 1 |
| `MODEL_SIMULATOR` | `gpt-4.1-mini-2025-04-14` | Modelo do Stage 2 |
| `MODEL_JUDGE` | `gpt-4.1-mini-2025-04-14` | Modelo do Stage 3 |
| `TEMPERATURE_GENERATOR` | `0.7` | Temperatura do gerador (diversidade) |
| `TEMPERATURE_SIMULATOR` | `0.3` | Temperatura do simulador (estabilidade) |
| `TEMPERATURE_JUDGE` | `0.0` | Temperatura do judge (reprodutibilidade) |
| `SEMAPHORE_LIMIT` | `5` | Chamadas LLM concorrentes maximas |
| `MAX_RETRIES` | `5` | Retries do SDK (backoff exponencial em 429) |
| `LLM_TIMEOUT_SECONDS` | `60` | Timeout por chamada LLM |
| `CACHE_TTL_SECONDS` | `86400` | TTL do cache de prompts (24h) |

---

## Testes

```bash
pytest -v   # 72 testes, ~1s
```

| Arquivo | Testes | O que cobre |
|---------|--------|-------------|
| `test_models.py` | 12 | Validacao Pydantic, bounds, serializacao |
| `test_scorer.py` | 6 | Score deterministico, edge cases (0, 100, vazio) |
| `test_recommendations.py` | 5 | Logica de recomendacoes por faixa de score |
| `test_cfm.py` | 7 | Validacao CRM, parsing HTML, medico inativo |
| `test_llm.py` | 9 | Estimativa de custo, web search cost |
| `test_judge.py` | 7 | Judge decomposed, derive_verdict, retries |
| `test_reporters.py` | 9 | Roundtrip JSON, geracao HTML/Markdown |
| `test_integration.py` | 1 | Pipeline completo end-to-end (LLM mockado) |

**Estrategia:** testes deterministicos para logica pura (scorer, models, recommendations), mocks para chamadas LLM (sem gastar API no CI).

---

## Decisoes tecnicas

**Por que OpenAI SDK direto (sem LangChain)?**
O PRD pede extensibilidade para Claude/Gemini em P2. Um wrapper fino sobre o SDK eh mais simples de trocar do que desacoplar de um framework. A interface `BaseJudge` permite adicionar providers sem mudar o pipeline.

**Por que `web_search_preview` em vez de simulacao "fria"?**
A API padrao responde com conhecimento treinado e pode inventar nomes. Com `web_search_preview`, o modelo faz busca web real — retorna medicos reais com URLs de fonte. Isso eh exatamente o que o paciente ve no ChatGPT.

**Por que LLM-as-Judge decomposed (3 perguntas binarias)?**
Regex para detectar nomes eh fragil (Dr./Dra., acentos, abreviacoes). Decomposicao em 3 perguntas binarias (nome encontrado? concorrentes? especialidade recomendada?) reduz erros vs. classificacao multi-classe direta. Baseado em [pesquisa de LLM-as-Judge](https://montecarlo.ai/blog-llm-as-judge/).

**Por que cache por especialidade x cidade?**
Se dois dermatologistas de Campinas rodam o diagnostico, os prompts do Stage 1 sao reutilizados. Em producao, isso escala para meta de <R$30/medico/mes (PRD P0.7).

**Por que Langfuse?**
Drop-in replacement do import `AsyncOpenAI` — zero mudanca de codigo. Toda chamada LLM aparece no dashboard com tokens, custo, latencia. O `trace.jsonl` local funciona como fallback offline.

**Por que Postgres (nao SQLite)?**
Connection pooling (`psycopg_pool`), JSONB nativo para reports, `gen_random_uuid()` server-side, e mesma stack em dev e prod. O cache faz fallback para dict in-memory no modo CLI.

---

## Score: POC vs. PRD

O PRD define o AI Visibility Score com **6 dimensoes**. Este POC implementa **1 dimensao (Citacao em IA)** com 2 sub-metricas ponderadas + 1 informativa:

| Sub-metrica | Peso | O que mede |
|-------------|------|------------|
| Visibilidade | 65% | Score medio por prompt: by_name=100→10 (por posicao), as_specialty=15, else=0 |
| Dominancia | 35% | Market share: citacoes por nome / (citacoes + concorrentes) |
| Presenca Indireta | informativo | % de prompts onde a IA recomendou a especialidade sem citar o medico |

```
overall = 0.65 * visibility + 0.35 * dominance
```

**Presenca Indireta** nao entra no calculo — serve como insight diagnostico ("a IA conhece sua especialidade mas nao seu nome").

As 5 dimensoes restantes dependem de infra nao-POC:

| Dimensao PRD | Requer |
|--------------|--------|
| Encontrabilidade | Audit de SEO, Google Business Profile |
| Entidade | Entity Builder completo (CRM, RQE, schema JSON-LD) |
| Conteudo | Engine de conteudo educativo + compliance pipeline |
| Reputacao | Google Reviews, Doctoralia, score medio |
| Conversao | Pixel de atribuicao + funil booking -> consulta |

**Pesos sao assumidos, nao calibrados.** Em producao seriam ajustados com sample de 50 medicos beta (PRD Epic 4).

---

## Limitacoes conhecidas

### Score
- **1 de 6 dimensoes implementada** — mede exclusivamente citacao em IA
- **Pesos assumidos (65/35)** — sem dados reais para calibrar
- **Benchmarks por especialidade estimados** — hardcoded (Dermatologia=25, Cardiologia=18, etc.)
- **Variancia entre runs ~+/-5 pontos** — web search retorna resultados diferentes a cada chamada; scorer eh deterministico (+/-0) mas input varia

### Judge
- **Accuracy ~80%** — confunde conselho generico com recomendacao concreta; mitigado no prompt v2
- **Confidence pouco granular** — varia entre 0.7-1.0; ideal seria 0.3-1.0

### Pipeline
- **10 prompts por diagnostico** — producao seria 50+ (PRD P0.7)
- **1 fonte (OpenAI)** — producao incluiria Perplexity e Google AI Overviews

---

## Proximos passos (com mais tempo)

- Implementar as 5 dimensoes restantes do score
- Calibracao de pesos com 50 medicos beta + correlacao com pacientes atribuiveis
- Scraping de Perplexity e Google AI Overviews (PRD P0.7 pede 3 fontes)
- Multiplos providers de judge (Claude, Gemini) com majority voting
- Pipeline de avaliacao humana (Cohen's Kappa) para validar accuracy do judge
- 50 prompts/medico com cache agressivo
- Versionamento de prompts (prompt registry) para rastrear impacto de mudancas
- Alembic para migracao de schema
- Task queue persistente (Celery/RQ) para substituir daemon threads

---

## Estrutura do projeto

```
ai_doctor_visibility/
|-- ai_visibility/              # Core do pipeline (Python)
|   |-- __main__.py             # Entrypoint: python -m ai_visibility
|   |-- cli.py                  # CLI (Typer): run, report, trace, serve
|   |-- config.py               # Settings (pydantic-settings, .env)
|   |-- models.py               # Todos os modelos Pydantic (~164 linhas)
|   |-- llm.py                  # OpenAI client wrapper + tracing + rate limiting
|   |-- pipeline.py             # Orquestrador dos 4 estagios
|   |-- cache.py                # Cache Postgres/in-memory por especialidade x cidade
|   |-- cfm.py                  # Validacao CRM contra portal CFM (desabilitado no pipeline)
|   |-- stages/
|   |   |-- prompts.py          # Stage 1: gera 10 prompts (structured output)
|   |   |-- simulator.py        # Stage 2: busca web real (web_search_preview)
|   |   |-- judge.py            # Stage 3: LLM-as-Judge decomposed (BaseJudge ABC)
|   |   |-- scorer.py           # Stage 4: score deterministico + recomendacoes
|   |-- report/
|   |   |-- html.py             # Relatorio HTML standalone (Tailwind inline)
|   |   |-- markdown.py         # Relatorio Markdown
|   |   |-- json_dump.py        # Serializacao JSON
|   |-- web/
|       |-- app.py              # FastAPI factory + lifespan + CORS
|       |-- routes.py           # Rotas HTML (SSR com Jinja2 + HTMX)
|       |-- api_routes.py       # API JSON (/api/*)
|       |-- db.py               # PostgreSQL: pool, schema, CRUD
|       |-- background.py       # Runner async em thread separada
|       |-- templates/          # Templates Jinja2 (DaisyUI + HTMX)
|-- frontend/                   # Next.js frontend (experimental, nao principal)
|-- tests/                      # 72 testes
|-- examples/                   # 3 diagnosticos pre-gerados
|-- infra/
|   |-- deploy.sh               # Deploy manual: build + push ECR + deploy ECS
|-- docs/
|   |-- screenshots/            # Screenshots para este README
|-- .github/
|   |-- workflows/ci-cd.yml     # CI (tests) + CD (deploy ECS)
|-- Dockerfile                  # Multi-stage build (builder + runtime)
|-- docker-compose.yml          # Dev local: app + postgres
|-- pyproject.toml              # Dependencias + config
|-- Makefile                    # Atalhos: install, test, example, clean
|-- PRACTICES.md                # Decisoes de engenharia LLM documentadas
|-- SPEC.md                     # Especificacao tecnica do pipeline
|-- .env.example                # Template de variaveis de ambiente
```

---

## Tech stack

| Camada | Tecnologia | Justificativa |
|--------|------------|---------------|
| **LLM** | OpenAI SDK (`gpt-4.1-mini`) | Structured outputs + web_search_preview nativo |
| **Modelos** | Pydantic v2 | Type safety, validacao, serializacao JSON |
| **Web** | FastAPI + Jinja2 + HTMX | SSR rapido, polling nativo, sem build frontend |
| **UI** | DaisyUI (Tailwind) | Componentes prontos, tema corporativo |
| **Database** | PostgreSQL 16 | JSONB, UUID nativo, pool de conexoes |
| **CLI** | Typer + Rich | Interface amigavel, tabelas formatadas |
| **Observabilidade** | Langfuse + trace.jsonl | Drop-in, dual (cloud + local) |
| **HTTP** | httpx (async) | Requests async |
| **Container** | Docker multi-stage | Imagem slim, build reproducivel |
| **CI/CD** | GitHub Actions | Test -> Build -> Deploy automatico |
| **Cloud** | AWS ECS Fargate + ECR + ALB | Serverless containers, zero gerenciamento |
| **Testes** | pytest + pytest-asyncio | Async nativo, fixtures leves |
