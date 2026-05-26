# AI Visibility POC — Especificação Técnica

> POC para processo seletivo iMedicina. Implementa um slice de **P0.2 (diagnóstico gratuito) + P0.7 (monitor de prompts) + P0.8 (AI Visibility Score)** do PRD.
>
> **Documento para servir como briefing inicial ao Claude Code.** Cole este arquivo inteiro como primeira mensagem de contexto antes de pedir qualquer código.

---

## 1. O que está sendo construído

Dado **nome, especialidade e cidade** de um médico, um pipeline que:

1. **Gera 10 prompts realistas** que um paciente faria a uma IA buscando esse tipo de médico nessa cidade
2. **Simula respostas** rodando esses prompts contra um LLM (OpenAI) configurado para se comportar como um assistente recomendando médicos
3. **Avalia cada resposta** classificando como o médico apareceu: nome direto, especialidade genérica, concorrente no lugar, ou nada — com nível de confiança e evidência citada
4. **Gera relatório** com score 0–100 e breakdown explicado por dimensão

**Entregáveis:**

- Código rodável (CLI Python)
- README claro
- Exemplo de output real para 1 médico fictício (pasta `examples/`)

---

## 2. Princípios de design (não negociáveis)

- **Não inventar roda**: OpenAI SDK direto, sem LangChain/CrewAI/LlamaIndex.
- **Structured outputs**: Pydantic + `response_format` em todas as chamadas. Zero regex no parsing.
- **Reprodutibilidade**: `temperature=0` no judge e no scorer, `seed` quando o modelo aceita. Mesmo input → mesmo output ±2 pontos (PRD pede isso explicitamente).
- **Observabilidade**: cada chamada LLM logada em `trace.jsonl` com tokens, latência, custo estimado.
- **Pluggability**: judge atrás de uma interface (`Judge`). Hoje OpenAI, amanhã Claude/Gemini — o PRD coloca isso como expansão em P2.
- **Cache em disco**: chave por `(specialty, city)` para reaproveitar prompts gerados (PRD menciona cache compartilhado por especialidade × cidade — implementar até em versão mínima sinaliza que você leu).
- **Determinismo no scorer**: o cálculo do score final é Python puro, sem LLM, sem ambiguidade. Testável com fixtures.

---

## 3. Não-escopo (decisões conscientes)

- **Sem scraping real** de ChatGPT, Perplexity ou Google AIO. O pedido é "simulando o que o ChatGPT responderia" — simulação via API basta.
- **Sem UI web**. Avaliação é de código. CLI é mais que suficiente.
- **Sem banco de dados**. Arquivos JSON e JSONL em disco.
- **Sem múltiplos providers ativos no MVP**. OpenAI default, interface preparada para estender.
- **Sem autenticação, deployment, CI**. É POC.
- **Sem dashboard, sem rotina recorrente, sem notificações**. Tudo fica explícito no `README` seção "What I'd do with more time".

---

## 4. Stack

| Dependência | Por quê |
|---|---|
| Python 3.11+ | Pattern matching, `asyncio.TaskGroup`, type hints modernos |
| `openai` (SDK oficial) | Cliente oficial, structured outputs nativos |
| `pydantic` v2 | Schemas tipados, validação, serialização |
| `pydantic-settings` | Config via `.env` sem boilerplate |
| `typer` | CLI declarativa, autohelp |
| `asyncio` (stdlib) | Paralelismo dos 10 prompts |
| `diskcache` | Cache em disco simples, thread-safe |
| `rich` | Output no terminal bonito (tabelas no relatório) |
| `pytest` + `pytest-asyncio` | Testes |
| `python-dotenv` | (via pydantic-settings) |

**Explicitamente fora:** LangChain, LlamaIndex, CrewAI, AutoGen, Haystack, Instructor, qualquer framework de agente.

---

## 5. Layout do projeto

```
ai-visibility-poc/
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── Makefile
├── ai_visibility/
│   ├── __init__.py
│   ├── __main__.py            # python -m ai_visibility
│   ├── cli.py                 # Typer app
│   ├── config.py              # Settings (BaseSettings)
│   ├── models.py              # Schemas Pydantic
│   ├── llm.py                 # Cliente OpenAI + protocolo Judge
│   ├── cache.py               # Wrapper diskcache
│   ├── pipeline.py            # Orquestra os 4 estágios
│   ├── stages/
│   │   ├── __init__.py
│   │   ├── prompts.py         # Stage 1
│   │   ├── simulator.py       # Stage 2
│   │   ├── judge.py           # Stage 3
│   │   └── scorer.py          # Stage 4
│   └── report/
│       ├── __init__.py
│       ├── markdown.py        # render Markdown
│       └── json_dump.py       # dump JSON
├── tests/
│   ├── conftest.py
│   ├── test_models.py
│   ├── test_scorer.py
│   └── fixtures/
│       └── verdicts_sample.json
└── examples/
    └── dra_mariana_costa/
        ├── report.md
        ├── report.json
        └── trace.jsonl
```

**Convenção:** código em inglês (identificadores, comentários), conteúdo gerado e relatórios em PT-BR.

---

## 6. Contratos de dados (Pydantic)

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional
from datetime import datetime

# --------- Entrada ---------

class DoctorInput(BaseModel):
    name: str
    specialty: str
    city: str
    state: Optional[str] = None
    neighborhood: Optional[str] = None

# --------- Stage 1 ---------

PersonaType = Literal[
    "leigo_ansioso",
    "informado_específico",
    "urgência",
    "segunda_opinião",
    "pediátrico",
    "convênio_vs_particular",
    "estético_eletivo",
    "crônico_acompanhamento",
    "preventivo",
    "pediu_indicação",
]

class GeneratedPrompt(BaseModel):
    id: str                          # "p1" .. "p10"
    text: str                        # o que o paciente "perguntaria"
    persona: PersonaType
    intent_summary: str              # 1 linha do que o paciente quer

# --------- Stage 2 ---------

class SimulatedResponse(BaseModel):
    prompt_id: str
    raw_text: str
    doctors_named: list[str]         # nomes próprios detectados
    model: str
    tokens_in: int
    tokens_out: int
    latency_ms: int

# --------- Stage 3 ---------

CitationType = Literal[
    "mentioned_by_name",             # nome do médico citado diretamente
    "mentioned_as_specialty",        # mencionado mas só como "um dermato"
    "competitor_in_place",           # outro médico nomeado no lugar
    "not_mentioned",                 # nada
]

class Verdict(BaseModel):
    prompt_id: str
    citation_type: CitationType
    confidence: float = Field(ge=0.0, le=1.0)
    position: Optional[int] = Field(
        None, ge=1,
        description="Ordem de aparição na resposta (1 = primeiro mencionado)",
    )
    evidence_quote: str              # trecho que justifica a classificação
    competitors_named: list[str] = []

# --------- Stage 4 ---------

class ScoreBreakdown(BaseModel):
    presence: float = Field(ge=0, le=100)       # taxa de menção (qualquer tipo)
    quality: float = Field(ge=0, le=100)        # qualidade ponderada da menção
    position: float = Field(ge=0, le=100)       # posição média quando citado
    competitive: float = Field(ge=0, le=100)    # inverso de "deslocado por concorrente"
    overall: float = Field(ge=0, le=100)

# --------- Saída final ---------

class ReportMetadata(BaseModel):
    generated_at: datetime
    model_generator: str
    model_simulator: str
    model_judge: str
    total_tokens_in: int
    total_tokens_out: int
    total_cost_usd: float
    seed: int

class Report(BaseModel):
    doctor: DoctorInput
    prompts: list[GeneratedPrompt]
    responses: list[SimulatedResponse]
    verdicts: list[Verdict]
    score: ScoreBreakdown
    metadata: ReportMetadata
```

---

## 7. Os 4 estágios em detalhe

### Stage 1 — PromptGenerator (`stages/prompts.py`)

**Função:** dado `DoctorInput`, gera 10 prompts realistas em PT-BR de pacientes buscando esse tipo de médico nessa cidade.

**Prompt engineering crítico:**

- System prompt instrui: gere 10 prompts **diversos**, cada um com persona diferente da lista enumerada acima.
- Inclua few-shot: 2-3 exemplos curtos do que NÃO é diverso (todos começando com "preciso de") e do que É diverso (variação de tom, contexto, urgência).
- Não mencione o nome do médico-alvo aos prompts — o paciente não sabe quem ele é, está procurando.
- Output via `response_format` com schema `list[GeneratedPrompt]`.

**Modelo:** `gpt-4o-mini`, `temperature=0.7` (queremos diversidade aqui, não determinismo).

**Cache:** chave = `(specialty, city, neighborhood)`. Reaproveita prompts entre médicos da mesma especialidade × cidade (alinhamento com PRD P0.7).

### Stage 2 — SearchSimulator (`stages/simulator.py`)

**Função:** para cada prompt, simula o que um assistente IA responderia ao paciente brasileiro.

**System prompt do simulador (esboço):**

> "Você é um assistente de IA conversacional ajudando um paciente brasileiro a encontrar atendimento médico. Quando faz sentido, sugira 2-4 nomes de médicos com breve justificativa. Se não tiver informação suficiente, oriente o paciente sem inventar. Mantenha tom natural e útil."

**Importante:** o simulador **não recebe** o nome do médico-alvo. Ele responde "frio", igual o ChatGPT real responderia a um paciente qualquer. Esse é o teste real de visibilidade.

**Modelo:** `gpt-4o-mini`, `temperature=0.3` (consistência com naturalidade).

**Paralelismo:** `asyncio.gather` com semáforo de 5 para não estourar rate limit.

### Stage 3 — Judge (`stages/judge.py`)

**Função:** dado `(DoctorInput, GeneratedPrompt, SimulatedResponse)`, classifica como o médico aparece.

**Prompt engineering crítico:**

- Define rigorosamente cada categoria de `CitationType` com exemplos.
- **Exige `evidence_quote`** — trecho literal da resposta que justifica a classificação. Força a LLM a se fundamentar, reduz alucinação.
- Pede `position` (ordem 1-N de aparição) só quando `mentioned_by_name`.
- Pede `competitors_named`: lista de outros nomes próprios de médicos citados.
- Confiança `0.0–1.0` calibrada explicitamente: 1.0 = inequívoco, 0.5 = ambíguo, <0.3 = palpite.

**Modelo:** `gpt-4o-mini` para custo; `gpt-4o` se quiser robustez extra. `temperature=0`, `seed=42`.

**Output:** `Verdict` via structured output.

### Stage 4 — Scorer (`stages/scorer.py`)

**Função:** agrega `list[Verdict]` num `ScoreBreakdown` determinístico. **Sem LLM aqui.**

**Fórmula:**

```python
QUALITY_VALUE = {
    "mentioned_by_name":     100,
    "mentioned_as_specialty": 30,
    "competitor_in_place":    10,
    "not_mentioned":           0,
}

def score(verdicts: list[Verdict]) -> ScoreBreakdown:
    n = len(verdicts)
    mentioned = [v for v in verdicts
                 if v.citation_type in ("mentioned_by_name", "mentioned_as_specialty")]
    
    # Presença: % de prompts em que apareceu (de qualquer forma)
    presence = 100 * len(mentioned) / n
    
    # Qualidade: média ponderada pela confiança
    quality = sum(
        QUALITY_VALUE[v.citation_type] * v.confidence
        for v in verdicts
    ) / n
    
    # Posição: quando citado por nome, posição mais alta vale mais
    by_name = [v for v in verdicts if v.citation_type == "mentioned_by_name" and v.position]
    if by_name:
        position = sum(max(0, (11 - v.position) * 10) for v in by_name) / len(by_name)
    else:
        position = 0.0
    
    # Competitivo: inverso da taxa em que o concorrente tomou a vaga
    competitor_count = sum(1 for v in verdicts if v.citation_type == "competitor_in_place")
    competitive = 100 - (100 * competitor_count / n)
    
    # Overall: pesos refletem hipótese de produto
    # - qualidade da menção é o mais importante
    # - presença vem em seguida (estar lá > como)
    # - posição importa quando se está lá
    # - competitivo é o último ajuste (contexto, não core)
    overall = 0.40*quality + 0.30*presence + 0.20*position + 0.10*competitive
    
    return ScoreBreakdown(
        presence=round(presence, 1),
        quality=round(quality, 1),
        position=round(position, 1),
        competitive=round(competitive, 1),
        overall=round(overall, 1),
    )
```

**Testes obrigatórios neste módulo** — é o único lugar onde a matemática do score vive.

---

## 8. CLI

```bash
# Comando principal (campos via flag)
python -m ai_visibility run \
  --name "Dra. Mariana Costa" \
  --specialty "Dermatologia" \
  --city "São Paulo" \
  --state "SP" \
  --neighborhood "Moema" \
  --output ./examples/dra_mariana_costa

# Comando via JSON (mais limpo)
python -m ai_visibility run \
  --doctor ./examples/doctors/dra_mariana.json \
  --output ./examples/dra_mariana_costa

# Re-renderizar relatório de dados já gerados (sem reconsumir API)
python -m ai_visibility report ./examples/dra_mariana_costa

# Inspecionar trace
python -m ai_visibility trace ./examples/dra_mariana_costa --stage judge
```

---

## 9. Relatório (saída)

Pasta de output sempre contém **três arquivos**:

### `report.md` — humano

```markdown
# AI Visibility Report — Dra. Mariana Costa

**Especialidade:** Dermatologia  
**Cidade:** São Paulo - SP (Moema)  
**Gerado em:** 2026-05-27 10:42

## Score Geral: 23 / 100

| Dimensão     | Score | O que mede                                          |
|--------------|-------|-----------------------------------------------------|
| Presença     | 20.0  | Em quantos prompts a médica apareceu (qualquer forma) |
| Qualidade    | 18.5  | Tipo de menção ponderado pela confiança             |
| Posição      | 0.0   | Posição média quando citada por nome                |
| Competitivo  | 70.0  | Inverso de "concorrente tomou a vaga"               |

## Diagnóstico em uma frase

A médica não aparece nas recomendações de IA para sua especialidade na sua cidade.
Em 8 de 10 prompts de pacientes simulados, outros nomes foram citados no lugar.

## Detalhe por prompt

### p1 — leigo_ansioso
> "Tenho uma mancha estranha que apareceu no rosto, com quem devo me consultar em SP?"

**Veredicto:** competitor_in_place (confiança 0.92)  
**Evidência:** "Recomendo procurar a Dra. Carla Mendes ou o Dr. Paulo Veiga..."  
**Concorrentes citados:** Dra. Carla Mendes, Dr. Paulo Veiga

[... p2 a p10 ...]

## Plano de ação

1. Construir entidade verificada (CRM/RQE) — você não existe na camada de IA.
2. Publicar conteúdo educativo em derma estética com schema correto.
3. Otimizar Google Business Profile para captura de "dermatologista em Moema".
```

### `report.json` — máquina

Dump completo do `Report` (Pydantic `.model_dump_json(indent=2)`).

### `trace.jsonl` — observability

Uma linha JSON por chamada LLM:

```jsonl
{"stage":"generator","model":"gpt-4o-mini","tokens_in":312,"tokens_out":1024,"latency_ms":2840,"cost_usd":0.00063,"timestamp":"2026-05-27T10:42:01Z"}
{"stage":"simulator","prompt_id":"p1","model":"gpt-4o-mini","tokens_in":189,"tokens_out":423,"latency_ms":1820,"cost_usd":0.00031,"timestamp":"..."}
{"stage":"judge","prompt_id":"p1","model":"gpt-4o-mini","tokens_in":612,"tokens_out":187,"latency_ms":1340,"cost_usd":0.00021,"timestamp":"..."}
```

---

## 10. README — estrutura

1. **One-liner** do que o projeto faz
2. **Callout de contexto**: "Este POC implementa um slice de P0.2 / P0.7 / P0.8 do PRD iMedicina AI Visibility."
3. **Quick start**:
   ```bash
   git clone ...
   cd ai-visibility-poc
   pip install -e .
   cp .env.example .env  # preencha OPENAI_API_KEY
   make example          # roda a Dra. Mariana fictícia
   ```
4. **Visão de pipeline** — 1 parágrafo por estágio.
5. **Decisões de arquitetura** — curtas, ~3-5 bullets:
   - Por que sem LangChain
   - Por que Pydantic + structured outputs
   - Por que cache local
   - Por que judge separado do simulator
6. **Reprodutibilidade** — explica `temperature=0`, `seed`, e o ±2 pontos do PRD.
7. **Preview do exemplo** — cole o cabeçalho do `report.md` da pasta `examples/`.
8. **Custo estimado** — ~$0.005 por run com gpt-4o-mini.
9. **Limitações conhecidas**:
   - Simulação "fria" — o simulator é um proxy para ChatGPT real, não substitui scraping.
   - Médico fictício esperado pontuar baixo (LLM não conhece — esse é o ponto).
   - 10 prompts é amostra pequena; em produção seriam 50+ (PRD P0.7).
   - Sem scraping de Perplexity ou Google AIO neste POC.
10. **What I'd do with more time** — 5-7 bullets honestos:
    - Scraping real de ChatGPT/Perplexity/AIO
    - Múltiplos providers (Claude, Gemini)
    - Calibração ex-post com pacientes atribuíveis reais (Anexo A do plano)
    - Dashboard web simples (Streamlit)
    - Cache compartilhado por (specialty × city) entre médicos
    - Sample maior (50 prompts/médico)
    - Pipeline de avaliação humana (Kappa entre judges humanos vs LLM)

---

## 11. Testes

**Mínimo obrigatório:**

- `test_models.py` — Pydantic: limites (`confidence ∈ [0,1]`), enums, campos obrigatórios.
- `test_scorer.py` — fixtures de `list[Verdict]` pré-definidas → `ScoreBreakdown` esperado. Casos:
  - Todos `mentioned_by_name` com confiança 1.0 → score ~100
  - Todos `not_mentioned` → score 0
  - Todos `competitor_in_place` → presença 0, competitivo 0, quality 10, overall baixo
  - Mix realista → score intermediário esperado (calculado à mão e fixado no teste)

**Bom ter (se sobrar tempo):**

- `test_pipeline.py` — integração com `respx` mockando OpenAI ou `vcr.py` com cassetes.

---

## 12. Plano de execução (2 dias)

### Dia 1 — segunda 25/05

| Hora | Bloco |
|------|-------|
| H1 | Scaffolding: `pyproject.toml`, `.gitignore`, `.env.example`, estrutura de pastas, `__init__.py`'s |
| H2 | `models.py` completo + `test_models.py` |
| H3 | `config.py` (Settings) + `llm.py` (client OpenAI + protocolo) |
| H4 | `cache.py` + decorator simples para cache de prompts |
| H5-6 | `stages/prompts.py` — iteração até o gerador produzir prompts genuinamente diversos. **Manual review do prompt.** |
| H7-8 | `stages/simulator.py` com `asyncio.gather` + semáforo. Rodar com 1 prompt manual pra ver output. |

### Dia 2 — terça 26/05

| Hora | Bloco |
|------|-------|
| H1-2 | `stages/judge.py` — iteração até o judge classificar de forma consistente em 3 runs. **Manual review do prompt.** |
| H3 | `stages/scorer.py` + `test_scorer.py` completo |
| H4 | `pipeline.py` — orquestração + tratamento de erros + agregação do trace |
| H5 | `report/markdown.py` + `report/json_dump.py` |
| H6 | `cli.py` (Typer) + `__main__.py` + `Makefile` |
| H7 | Rodar exemplo end-to-end com Dra. Mariana, polir output |
| H8 | Escrever `README.md` final |

### Quarta manhã 27/05 — buffer

- Revisão final do código (typing, docstrings nos pontos críticos)
- Mais 1-2 testes se faltar cobertura
- Commit history limpo no Git
- Tag `v0.1.0`

---

## 13. Médico fictício do exemplo (sugestão)

```json
{
  "name": "Dra. Mariana Costa",
  "specialty": "Dermatologia",
  "city": "São Paulo",
  "state": "SP",
  "neighborhood": "Moema"
}
```

**Justificativa:** o Anexo A do plano estratégico lista "dermato estética" como uma das 4 especialidades-alvo para validação inicial. Usar dermato no exemplo mostra que você leu e está alinhado.

---

## 14. Dicas para usar com Claude Code

1. **Cole este spec inteiro como contexto inicial.** Não peça pro Claude Code inferir — dê o contrato exato.
2. **Vá módulo por módulo**, na ordem do layout (seção 5). Nunca peça "build the whole thing".
3. **Revise os 3 prompts críticos manualmente** (generator, simulator, judge). É onde Claude Code pode acelerar mas é também onde a qualidade do POC vai aparecer. Garanta:
   - Generator **pede diversidade explícita** (varia persona/urgência/contexto)
   - Simulator **não conhece** o médico-alvo
   - Judge **exige `evidence_quote`** literal
4. **Cada `stages/*.py` deve ter um `if __name__ == "__main__":`** com exemplo mínimo. Roda o módulo isolado antes de integrar.
5. **Não aceite testes que não falham** quando você quebra a regra. Peça fixtures concretas com score esperado calculado à mão.
6. **Commits granulares** mostram processo. Um commit por módulo concluído. Mensagens claras (`feat: stage 1 prompt generator`, `test: scorer determinism`, etc.).
7. **Dry run final** com a opção fictícia, screenshots do output ou bloco de texto direto no README.

---

## 15. Checklist de "estou pronto pra entregar"

- [ ] `pip install -e .` funciona em ambiente limpo
- [ ] `make example` roda end-to-end sem erro com `OPENAI_API_KEY` válida
- [ ] `pytest` passa (≥ `test_models.py` + `test_scorer.py`)
- [ ] `examples/dra_mariana_costa/` tem os 3 arquivos (`.md`, `.json`, `.jsonl`)
- [ ] README está completo (todas as seções da §10)
- [ ] Sem `print()` de debug no código
- [ ] Sem chaves de API commitadas (cheque `.env` no `.gitignore`)
- [ ] `temperature=0` e `seed` no judge confirmados
- [ ] Repo no Git com history limpo (pelo menos 8-10 commits descritivos)
- [ ] Rodou 2x a mesma input e os scores ficaram dentro de ±2 pontos

---

**Status:** spec pronto.  
**Próxima ação:** abrir Claude Code com este arquivo como contexto e atacar o Dia 1.
