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

## Limitações

- **Médico fictício pontua baixo**: esperado — LLMs não conhecem médicos inventados. Esse é o ponto do produto.
- **10 prompts por diagnóstico**: em produção seriam 50+ (PRD P0.7).
- **1 fonte (OpenAI)**: em produção incluiria Perplexity e Google AI Overviews. Interface plugável (`BaseJudge`, `BaseSimulator`) preparada para isso.
- **Benchmarks por especialidade são estimativas**: em produção seriam calculados a partir de dados reais agregados.
- **Validação CFM é best-effort**: site do CFM pode bloquear scraping — fallback para validação de formato.

## What I'd do with more time

- Scraping real de Perplexity e Google AI Overviews (PRD P0.7 pede 3 fontes)
- Múltiplos providers de judge (Claude, Gemini) com voting
- Calibração dos benchmarks com dados reais de centenas de médicos
- Sample maior (50 prompts/médico) com custo otimizado via cache agressivo
- Pipeline de avaliação humana (Cohen's Kappa entre judges humanos vs LLM)
- Dashboard web (Streamlit) para rodar diagnósticos sem CLI
- Validação CFM via API oficial (se disponível) em vez de scraping
