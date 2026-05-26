# AI Visibility POC

Pipeline de diagnóstico de visibilidade de médicos em buscas de IA.

> Este POC implementa um slice de **P0.2 (diagnóstico gratuito) + P0.7 (monitor de prompts) + P0.8 (AI Visibility Score)** do PRD iMedicina AI Visibility.

## O que faz

Dado o nome, especialidade e cidade de um médico, o pipeline:

1. **Gera 10 prompts realistas** que pacientes fariam a uma IA buscando esse tipo de médico
2. **Roda buscas web reais** via OpenAI `web_search_preview` — retorna médicos reais com fontes citadas
3. **Avalia cada resposta** com LLM-as-Judge: o médico foi citado? Como? Quem aparece no lugar?
4. **Calcula um score 0–100** com breakdown por dimensão e recomendações acionáveis

## Quick start

```bash
git clone <repo-url> && cd ai-visibility-poc
pip install -e ".[dev]"
cp .env.example .env  # preencha OPENAI_API_KEY (e opcionalmente Langfuse keys)
make example           # roda o exemplo da Dra. Mariana Costa
```

Ou diretamente:

```bash
python -m ai_visibility run \
  --name "Dr. Fernando Lopes" \
  --crm "169135" \
  --crm-state "SP" \
  --specialty "Dermatologia" \
  --city "Campinas" \
  --state "SP" \
  --output ./output/dr_fernando_lopes
```

## Arquitetura — 4 estágios

```
Input (nome, CRM, UF, especialidade, cidade)
         │
         ├──────────────────────┐
         ▼                      ▼
  CFM Validation         Stage 1: GERADOR
  (paralelo)             gpt-4.1-mini · structured output
                         10 prompts variados (10 personas)
                                │
                                ▼
                         Stage 2: SIMULADOR
                         gpt-4.1-mini + web_search_preview
                         Busca web real · médicos reais + fontes
                                │
                                ▼
                         Stage 3: JUDGE
                         gpt-4.1-mini · temperature=0
                         LLM-as-judge · structured output
                         Classifica: mentioned_by_name | specialty | competitor | not_mentioned
                                │
                                ▼
                         Stage 4: SCORER
                         Python puro · determinístico
                         Score 0-100 · reproduzível ±0 pontos
                                │
                                ▼
                         report.html · report.md · report.json · trace.jsonl
```

## Exemplo de output

Três exemplos pré-gerados em `examples/`:

| Médico | Tipo | Score | Presença | Insight |
|---|---|---|---|---|
| Dra. Mariana Costa | Fictícia | **4/100** | 0/10 | Invisível — nenhuma IA a cita |
| Dr. Fernando Lopes | Real (Campinas) | **18/100** | 2/10 | Aparece raramente, perde espaço para concorrentes |
| Dra. Karina Zold | Real (Campinas) | **92/100** | 9/10 | Domina as recomendações de IA na região |

Para ver o relatório visual: `open examples/dra_karina_zold/report.html`

## Decisões técnicas

**Por que OpenAI SDK direto (sem LangChain)?**
O PRD pede extensibilidade para Claude/Gemini em P2. Um wrapper fino sobre o SDK é mais simples de trocar do que desacoplar de um framework. "Não inventa roda" corta dos dois lados — também corta quem importa biblioteca que não precisa.

**Por que `web_search_preview` em vez de simulação "fria"?**
A API padrão responde com conhecimento treinado e pode inventar nomes. Com `web_search_preview`, o modelo faz busca web real — retorna médicos reais com URLs de fonte e `utm_source=openai`. Isso é exatamente o que o paciente vê no ChatGPT.

**Por que LLM-as-Judge (Stage 3 separado)?**
Regex para detectar nomes é frágil (Dr./Dra., acentos, abreviações). O judge usa structured output com Pydantic para classificar cada resposta em categorias tipadas, com `evidence_quote` literal obrigatório que reduz alucinação. Interface plugável (`BaseJudge` → `OpenAIJudge`) permite trocar o provider.

**Por que cache por especialidade × cidade?**
O PRD menciona cache compartilhado (P0.7) para reduzir custo. Se dois médicos dermatologistas de Campinas rodam o diagnóstico, os prompts do Stage 1 são reutilizados. Em produção, isso escala para meta de <R$30/médico/mês.

**Por que Langfuse?**
Observabilidade é requisito implícito para qualquer pipeline LLM em produção. A integração é um drop-in replacement do `AsyncOpenAI` import — zero mudança de código. Toda chamada aparece no dashboard com tokens, custo, latência e inputs/outputs. O `trace.jsonl` local funciona como fallback offline.

## Reprodutibilidade

- `temperature=0` no Judge (não no Generator — lá queremos diversidade)
- Scorer é Python puro, determinístico: mesmo input → mesmo output (±0 pontos)
- PRD pede reprodutibilidade ±2 pontos (SPEC §2) — cumprido

## Custo

~$0.12 por diagnóstico (10 buscas web + 10 avaliações + 1 geração de prompts).

| Stage | Chamadas | Custo |
|---|---|---|
| Generator | 1 | ~$0.002 |
| Simulator (web search) | 10 | ~$0.11 |
| Judge | 10 | ~$0.006 |
| **Total** | **21** | **~$0.12** |

## CLI

```bash
# Rodar diagnóstico
python -m ai_visibility run --name "..." --specialty "..." --city "..." --output ./output

# Re-renderizar relatórios sem reconsumir API
python -m ai_visibility report ./output

# Inspecionar trace de chamadas LLM
python -m ai_visibility trace ./output --stage judge
```

## Testes

```bash
pytest -v   # 51 testes
```

Cobertura: models, scorer (6 cenários determinísticos), recommendations, cache, CFM parser, cost estimation, reporters (JSON roundtrip, markdown, HTML).

## Score: o que implementamos vs. o que o PRD define

O PRD define o AI Visibility Score com **6 dimensões**: Encontrabilidade, Entidade, Conteúdo, Reputação, Citação em IA e Conversão. Este POC implementa **1 dessas 6 dimensões — Citação em IA** — subdividida em 4 sub-métricas:

| Sub-métrica POC | Peso | O que mede | Dimensão PRD |
|---|---|---|---|
| Quality | 40% | Tipo de menção × confiança do judge | Citação em IA |
| Presence | 30% | % de prompts onde o médico apareceu | Citação em IA |
| Position | 20% | Posição quando citado por nome | Citação em IA |
| Competitive | 10% | Inverso de deslocamento por concorrente | Citação em IA |

As outras 5 dimensões dependem de infraestrutura que não existe no POC:

| Dimensão PRD | Requer |
|---|---|
| Encontrabilidade | Audit de SEO, Google Business Profile |
| Entidade | Entity Builder completo (CRM, RQE, schema JSON-LD) |
| Conteúdo | Engine de conteúdo educativo + pipeline de compliance |
| Reputação | Google Reviews, Doctoralia, score médio |
| Conversão | Pixel de atribuição + funil booking→consulta confirmada |

**Pesos são assumidos, não calibrados.** O próprio PRD reconhece isso como open question: "Pesos iniciais das 6 dimensões — calibrar com julgamento dos 3 médicos consultores ou com correlação ex-post a pacientes atribuíveis?" Em produção, os pesos seriam calibrados com sample de 50 médicos beta (Epic 4, 8 dias estimados no roadmap).

## Limitações conhecidas

### Score
- **1 de 6 dimensões implementada**: o score deste POC mede exclusivamente citação em IA. O score de produção agregaria SEO, entidade, conteúdo, reputação e conversão.
- **Pesos arbitrários (40/30/20/10)**: sem dados reais para calibrar. Em produção seriam ajustados com correlação a pacientes atribuíveis.
- **Benchmarks por especialidade são estimativas**: hardcoded (Dermatologia=35, Cardiologia=28, etc.). Em produção seriam calculados a partir de dados reais agregados.
- **Variância entre runs ~±5 pontos**: o `web_search_preview` retorna resultados diferentes a cada chamada (a web é não-determinística). O scorer é determinístico (±0), mas o input dele varia. O PRD pede ±2 assumindo simulação estável — com busca web real, ±5 é mais realista.

### Judge
- **Accuracy ~80%**: audit manual identificou que o judge confunde conselho genérico ("vá ao dermatologista") com recomendação concreta de especialidade. Mitigado no prompt v2 com exemplos explícitos.
- **Confidence pouco granular**: varia entre 0.9-1.0. O ideal seria 0.3-1.0 com mais granularidade. Requer few-shot calibration com exemplos scored manualmente.

### Pipeline
- **Médico fictício pontua baixo**: esperado — LLMs não conhecem médicos inventados. É o ponto do produto.
- **10 prompts por diagnóstico**: em produção seriam 50+ (PRD P0.7).
- **1 fonte (OpenAI)**: em produção incluiria Perplexity e Google AI Overviews. Interface plugável (`BaseJudge`, `BaseSimulator`) preparada para isso.
- **Validação CFM é best-effort**: site do CFM pode bloquear scraping — fallback para validação de formato.

## What I'd do with more time

- **Implementar as 5 dimensões restantes** do score (Encontrabilidade, Entidade, Conteúdo, Reputação, Conversão) à medida que a infraestrutura correspondente for construída
- **Calibração de pesos** com sample de 50 médicos beta + correlação com pacientes atribuíveis
- Scraping real de Perplexity e Google AI Overviews (PRD P0.7 pede 3 fontes)
- Múltiplos providers de judge (Claude, Gemini) com majority voting para reduzir variância
- **Pipeline de avaliação humana** (Cohen's Kappa entre judges humanos vs LLM) para validar accuracy do judge
- Sample maior (50 prompts/médico) com custo otimizado via cache agressivo
- Dashboard web para rodar diagnósticos sem CLI
- Versionamento de prompts (prompt registry) para rastrear impacto de mudanças no judge/generator
