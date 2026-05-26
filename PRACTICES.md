# LLM Development Practices — Referência Curada para o POC

> Doc para alimentar o Claude Code junto com o `SPEC.md`. Cada seção tem: (a) o problema que resolve no seu POC, (b) o pattern recomendado, (c) o link autoritativo, (d) anti-pattern a evitar.

---

## TL;DR aplicado ao seu POC

| Onde no POC | Prática crítica |
|---|---|
| `models.py` | Pydantic v2 com `Literal`, `Field(ge=, le=)`, sem `Optional` sem default |
| `stages/prompts.py`, `stages/simulator.py`, `stages/judge.py` | `client.responses.parse(response_format=PydanticModel)` em vez de pedir JSON em texto |
| `stages/judge.py` | `temperature=0`, `seed=42`, exigir `evidence_quote` no schema, definir rubric com exemplos negativos |
| `stages/simulator.py` | `AsyncOpenAI` + `asyncio.Semaphore(5)` + SDK retries |
| `llm.py` | `OpenAI(max_retries=5)` — SDK já faz exponential backoff em 429 desde v1.0 |
| `pipeline.py` | `trace.jsonl` com `{stage, model, tokens_in, tokens_out, latency_ms, cost_usd}` por chamada |
| `tests/test_scorer.py` | Fixtures determinísticas, asserts numéricos, sem LLM no test |
| `tests/test_judge.py` (se houver tempo) | N=3 runs do mesmo input, threshold em vez de equality, agregação de scores |

---

## 1. Structured Outputs com Pydantic

**Problema no seu POC**: cada estágio (gerar prompts, simular resposta, judgar citação) precisa devolver dados tipados. Parsear JSON livre com regex é frágil — quebra na 1ª resposta com aspas mal-fechadas.

**Pattern (OpenAI structured outputs com Pydantic)**:

```python
from pydantic import BaseModel, Field
from typing import Literal
from openai import OpenAI

class Verdict(BaseModel):
    citation_type: Literal[
        "mentioned_by_name",
        "mentioned_as_specialty",
        "competitor_in_place",
        "not_mentioned",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_quote: str
    position: int | None = None
    competitors_named: list[str] = []

client = OpenAI()

response = client.responses.parse(
    model="gpt-4o-mini",
    input=[
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": user_input},
    ],
    response_format=Verdict,
    temperature=0,
    seed=42,
)

verdict: Verdict = response.output_parsed  # já validado pelo Pydantic
```

**Por que isso funciona**: a OpenAI usa decoding com constrained sampling pra forçar o output a seguir o JSON Schema gerado a partir do modelo Pydantic. Não é "pede e reza" — é garantido a nível de geração de token.

**Limitações conhecidas**: Structured Outputs ainda pode conter erros. Se ver erros, tente ajustar as instruções, fornecer exemplos nas instruções do sistema, ou quebrar tarefas em sub-tarefas mais simples.

**Anti-patterns a evitar**:
- ❌ `json.loads(response.choices[0].message.content)` sem schema
- ❌ Regex pra extrair campos de texto livre
- ❌ `Optional[X]` sem default (vira `X | None = None` no Pydantic v2)
- ❌ Usar `instructor` ou `outlines` — overkill pro POC, adiciona dependência

**Referência canônica**: 
- OpenAI Structured Outputs: https://developers.openai.com/api/docs/guides/structured-outputs
- Walkthrough prático: https://dida.do/blog/structured-outputs-with-openai-and-pydantic

---

## 2. LLM-as-Judge — o coração do POC

**Problema no seu POC**: o estágio 3 (Judge) classifica como o médico aparece na resposta. É um LLM julgando outro LLM. Se for mal feito, o score inteiro é lixo.

**Pesquisa atual**: Pesquisa mostra que modelos juízes sofisticados podem se alinhar com julgamento humano em até 85%, que é na verdade maior do que a concordância humano-humano (81%).

### Os 4 elementos não-negociáveis de um prompt de Judge

O prompt de um Judge deve: definir critérios de avaliação explicitamente (ex: "verifique se a resposta inclui todos os pontos-chave"). Especificar formato de saída (ex: "Retorne 'Pass' ou 'Fail' seguido de uma justificativa de uma frase").

Para o seu Judge, aplique os 4:

1. **Critérios explícitos com exemplos negativos** — pra cada categoria de `CitationType`, dê 1-2 exemplos de "isto é, isto não é".
2. **Formato de saída via Pydantic** (não em texto livre).
3. **Exigir evidência** — `evidence_quote: str` força fundamentação literal. Reduz alucinação dramaticamente.
4. **Calibração de confiança** — explicite no prompt: `1.0 = inequívoco`, `0.5 = ambíguo`, `<0.3 = palpite`.

### Vieses conhecidos do Judge (e como mitigar)

- **Position bias** (ordem afeta julgamento) — não relevante no seu caso porque você só julga 1 resposta por vez, não pares.
- **Verbosity bias** (respostas longas são vistas como melhores) — mitiga pedindo o judge classificar *type* e *confidence*, não *quality*.
- **Self-preference bias** (judge do mesmo modelo da resposta favorece) — mitiga usando modelos diferentes pra simulator e judge se possível. No seu caso, mesmo modelo (gpt-4o-mini) pros dois é aceitável pra POC, mas mencione em "limitações".
- **Stylistic bias** — formate o input pro judge com **XML tags** separando médico-alvo, prompt do paciente, e resposta simulada. Anthropic recomenda isso: Para obter saída estável de LLMs, é necessário distinguir claramente "o que é instrução, o que é dado, e o que é regra" dentro do prompt. Estruturar com tags XML é o método mais eficaz para definir esses limites explicitamente.

### Reprodutibilidade

- `temperature=0` no judge (não no generator — lá você quer diversidade).
- `seed=42` (passa pra API; não garante 100% mas reduz variância significativamente).
- Se variar muito mesmo assim, **rode N=3 vezes e use majority vote**: Em muitos deployments, mesmo com prompts idênticos e temperature zero, LLMs podem produzir saídas diferentes entre chamadas devido a numéricos de hardware, implementações de decoding, concorrência, ou mudanças upstream no modelo. Essa variabilidade significa que testes de exact-match podem ser pouco confiáveis a menos que a stack de inferência seja totalmente controlada.

### Exemplo de template Judge (ajuste pro seu domínio)

```
SYSTEM:
Você é um avaliador de citações de médicos em respostas de assistentes de IA.

Sua tarefa: dado um médico-alvo, um prompt de paciente, e a resposta de uma IA, 
classificar como o médico-alvo aparece (ou não) na resposta.

<categorias>
- mentioned_by_name: nome próprio do médico-alvo citado literalmente
- mentioned_as_specialty: a especialidade dele é citada mas o nome não  
  (ex: "consulte um dermatologista" sem citar Dra. Mariana)
- competitor_in_place: outro médico (não o alvo) é citado pelo nome
- not_mentioned: nenhuma das anteriores
</categorias>

<exemplos_negativos>
- "consulte um dermatologista em São Paulo" → NÃO é mentioned_by_name (não tem nome)
- "Dra. Carla Mendes é referência" (alvo era Dra. Mariana) → competitor_in_place
- "..." (resposta vazia ou sobre outra coisa) → not_mentioned
</exemplos_negativos>

<regras>
- evidence_quote DEVE ser um trecho LITERAL da resposta, não paráfrase
- position só preenche quando citation_type == "mentioned_by_name"  
  (posição de aparição na resposta, 1 = primeiro)
- confidence: 1.0 inequívoco, 0.5 ambíguo, <0.3 palpite
- Se ambíguo (ex: "Dra. M. Costa" pode ou não ser a alvo), confidence < 0.7
</regras>

USER:
<medico_alvo>
{doctor_input.model_dump_json()}
</medico_alvo>

<prompt_paciente>
{generated_prompt.text}
</prompt_paciente>

<resposta_simulada>
{simulated_response.raw_text}
</resposta_simulada>

Classifique segundo o schema.
```

**Referências canônicas**:
- Evidently AI guide: https://www.evidentlyai.com/llm-guide/llm-as-a-judge
- Patronus tutorial: https://www.patronus.ai/llm-testing/llm-as-a-judge
- Hamel Husain on evals: https://hamel.dev/blog/posts/evals-faq/ (leia este se puder, é o gold standard)

---

## 3. Async + Rate Limit Handling

**Problema no seu POC**: você roda 10 prompts no estágio 2 (simulator) e 10 no estágio 3 (judge). Sequencial seria ~30s a 1min por execução. Paralelizado, ~3s.

### Pattern: AsyncOpenAI + Semaphore

```python
import asyncio
from openai import AsyncOpenAI

client = AsyncOpenAI(max_retries=5)  # SDK já faz exponential backoff em 429
semaphore = asyncio.Semaphore(5)     # 5 calls concorrentes

async def call_one(prompt: str) -> SimulatedResponse:
    async with semaphore:
        response = await client.responses.parse(
            model="gpt-4o-mini",
            input=[...],
            response_format=SimulatedResponseSchema,
            temperature=0.3,
        )
        return response.output_parsed

async def run_stage_2(prompts: list[GeneratedPrompt]) -> list[SimulatedResponse]:
    tasks = [call_one(p.text) for p in prompts]
    return await asyncio.gather(*tasks, return_exceptions=True)
```

### Por que `Semaphore(5)` e não `gather` solto

Usar asyncio.gather() ou Promise.all() para disparar centenas de chamadas de API de uma vez vai bater nos limites RPM e TPM instantaneamente. Sem um semáforo ou rate limiter no seu código, qualquer batch job que escale além de algumas dezenas de itens vai gerar erros 429 independente do seu tier de uso.

Pro seu caso (10 chamadas por estágio), semáforo de 5 é seguro em qualquer tier. Pra produção (50 prompts × 3 fontes × N médicos) você ajustaria.

### Retries são automáticos no SDK

Adicione lógica de retry com exponential backoff às suas chamadas de API. Exemplo Python usando SDK oficial: 'from openai import OpenAI; client = OpenAI(max_retries=5)' — o retry built-in do SDK lida com 429s automaticamente em openai>=1.0.0.

Você **não precisa** escrever lógica de retry manualmente. Use `max_retries=5` no constructor e pronto.

**Anti-patterns**:
- ❌ Loop síncrono `for prompt in prompts: result = client.responses.parse(...)` — 10x mais lento sem motivo.
- ❌ Implementar backoff manualmente — SDK já faz.
- ❌ `gather` sem semáforo — você vai bater rate limit no primeiro stress test.
- ❌ `asyncio.run(asyncio.gather(...))` dentro de função async — vira `RuntimeError`.

**Referência canônica**:
- asyncio.Semaphore guide: https://www.soumendrak.com/blog/semaphores-python-async-programming/
- 2026 rate limit guide: https://gptprompts.ai/ai-errors-and-fixes/openai-api-rate-limit

---

## 4. Prompt Engineering para os 3 prompts críticos

Você tem **3 prompts que importam** no POC:

1. **Generator** (gera 10 prompts diversos de paciente)
2. **Simulator** (simula resposta de IA)
3. **Judge** (classifica citação)

Princípios que se aplicam aos 3:

### a) XML tags pra separar instrução/dado/regra

Estruturar com tags XML é o método mais eficaz para definir explicitamente esses limites.

Use `<medico_alvo>`, `<prompt_paciente>`, `<resposta_simulada>`, `<regras>`, `<exemplos>`. Não confie em separação por quebra de linha.

### b) Few-shot com exemplos negativos

Mais importante que mostrar o caso bom é mostrar **o caso ruim e por que é ruim**. Pro generator: "evite prompts genéricos tipo 'preciso de médico' — eles não capturam variação real de paciente". Pro judge: dê 2-3 exemplos de classificação errada e explique o que estava errado.

### c) Pin de modelo (reprodutibilidade)

Vinculando suas aplicações de produção a snapshots específicos de modelo (como gpt-4.1-2025-04-14 por exemplo) para garantir comportamento consistente.

No `config.py`, use `gpt-4o-mini-2024-07-18` (ou snapshot atual), não `gpt-4o-mini` solto. Isso evita que sua POC quebre quando a OpenAI atualizar o alias.

### d) Context engineering > prompt engineering

Comecei a pensar nisso menos como "prompt engineering" e mais como o que a Anthropic começou a chamar de context engineering — projetar a janela de contexto inteira (instruções do sistema, schemas de ferramentas, documentos injetados, exemplos, a própria query) como um contrato de interface entre um gerador probabilístico e seu sistema de software determinístico. Os prompts mais confiáveis não são espertos.

Tradução pro seu POC: o prompt do generator não é só "gere 10 prompts". É (system role) + (regras de diversidade) + (exemplos few-shot) + (schema Pydantic forçado) + (instrução final). Cada peça é parte do contrato.

**Referências canônicas**:
- OpenAI: https://developers.openai.com/api/docs/guides/prompt-engineering
- Anthropic: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/overview
- Steve Kinney (cross-provider): https://stevekinney.com/writing/prompt-engineering-frontier-llms

---

## 5. Observabilidade — o `trace.jsonl`

**Problema no seu POC**: o entregável pede um arquivo de trace. Bem feito, sinaliza maturidade.

### O que logar por chamada LLM

Cada linha do `trace.jsonl` deve ter no mínimo:

```json
{
  "timestamp": "2026-05-27T10:42:01.123Z",
  "stage": "judge",
  "prompt_id": "p3",
  "model": "gpt-4o-mini-2024-07-18",
  "temperature": 0.0,
  "seed": 42,
  "tokens_in": 612,
  "tokens_out": 187,
  "latency_ms": 1340,
  "cost_usd": 0.000212,
  "request_id": "req_abc123",
  "status": "success"
}
```

### Como pegar tokens e custo

A resposta da OpenAI vem com `response.usage`:

```python
usage = response.usage  # PromptUsage com input_tokens, output_tokens
cost = (
    usage.input_tokens * MODEL_COST[model]["input"] +
    usage.output_tokens * MODEL_COST[model]["output"]
)
```

Tabela `MODEL_COST` no `config.py`, hardcoded com os preços atuais (gpt-4o-mini em maio/2026 é ~$0.15/1M input, $0.60/1M output).

### Por que JSONL e não JSON

JSON = arquivo único, parsing all-or-nothing. JSONL = uma linha por evento, streaming-friendly, dá pra `jq`/grep direto:

```bash
jq 'select(.stage == "judge")' trace.jsonl
jq '.cost_usd' trace.jsonl | awk '{sum+=$1} END {print sum}'
```

Mostra que você pensa em ops, não só em código.

### Pra POC não precisa de Langfuse/Phoenix/LangSmith

Esses são produtos de observabilidade (Langfuse, Phoenix, LangSmith, Datadog LLM). Pra POC, JSONL em disco basta. Mencionar no README "em produção isso iria pra Langfuse ou similar" mostra awareness sem inflar a entrega.

**Referência canônica**:
- Langfuse tracing overview: https://langfuse.com/docs/observability/overview
- Hamel on what to log: https://hamel.dev/blog/posts/evals-faq/

---

## 6. Testes para LLM apps

**Problema no seu POC**: testar código que chama LLM é não-trivial. Mas testar o **scorer** (puro Python) é obrigatório.

### Framework Hamel Husain: 3 níveis

O custo de Level 3 > Level 2 > Level 1. Isso dita a cadência e maneira que você executa. Por exemplo, frequentemente rodo evals Level 1 em cada mudança de código, Level 2 em uma cadência fixa e Level 3 só após mudanças significativas no produto. Testes unitários para LLMs são assertions (como você escreveria no pytest).

- **Level 1 — Assertions determinísticas** (rápido, todo commit): `test_scorer.py` aqui. Fixtures de Verdict → ScoreBreakdown esperado, calculado à mão.
- **Level 2 — LLM-as-judge tests** (cadência fixa): roda o pipeline contra inputs conhecidos, judge avalia, threshold em vez de equality.
- **Level 3 — End-to-end com curadoria humana** (mudanças grandes): pra POC, fora de escopo.

### Para o scorer: Level 1 não-negociável

```python
# tests/test_scorer.py
import pytest
from ai_visibility.models import Verdict
from ai_visibility.stages.scorer import score

@pytest.fixture
def all_mentioned_by_name():
    return [
        Verdict(prompt_id=f"p{i}", citation_type="mentioned_by_name",
                confidence=1.0, position=1, evidence_quote="...")
        for i in range(1, 11)
    ]

def test_perfect_score(all_mentioned_by_name):
    result = score(all_mentioned_by_name)
    assert result.presence == 100.0
    assert result.quality == 100.0
    assert result.competitive == 100.0
    # position bonus = (11-1)*10 = 100 → max
    assert result.position == 100.0
    assert result.overall == 100.0

def test_all_not_mentioned():
    verdicts = [
        Verdict(prompt_id=f"p{i}", citation_type="not_mentioned",
                confidence=1.0, evidence_quote="...")
        for i in range(1, 11)
    ]
    result = score(verdicts)
    assert result.presence == 0.0
    assert result.quality == 0.0
    assert result.overall < 15.0  # só competitive contribui

def test_all_competitors():
    verdicts = [
        Verdict(prompt_id=f"p{i}", citation_type="competitor_in_place",
                confidence=1.0, evidence_quote="...",
                competitors_named=["Outro Médico"])
        for i in range(1, 11)
    ]
    result = score(verdicts)
    assert result.competitive == 0.0  # 100% de competidor no lugar
```

### Para o pipeline (opcional, Level 2)

Se sobrar tempo, mock o `AsyncOpenAI` com `respx` ou use uma fixture de respostas pré-gravadas. Não chame OpenAI de verdade em CI — vai dar flake e gastar tokens. Calcule médias dos scores de avaliação em 3+ runs para absorver variância não-determinística. Integre quality gates baseados em threshold no CI/CD para bloquear deployment quando scores caem.

**Referências canônicas**:
- Hamel Husain — Your AI Product Needs Evals: https://hamel.dev/blog/posts/evals/
- Hamel — Evals FAQ: https://hamel.dev/blog/posts/evals-faq/
- Langfuse practical guide: https://langfuse.com/blog/2025-10-21-testing-llm-applications

---

## 7. Configuração e segredos

**Pattern**: `pydantic-settings` com `.env`

```python
# config.py
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
    
    openai_api_key: str
    model_generator: str = "gpt-4o-mini-2024-07-18"
    model_simulator: str = "gpt-4o-mini-2024-07-18"
    model_judge: str = "gpt-4o-mini-2024-07-18"
    temperature_generator: float = 0.7
    temperature_simulator: float = 0.3
    temperature_judge: float = 0.0
    seed: int = 42
    semaphore_limit: int = 5
    max_retries: int = 5
    cache_dir: str = "./.cache"

settings = Settings()
```

`.env.example`:
```
OPENAI_API_KEY=sk-...
```

`.gitignore` precisa ter `.env`, `.cache/`, `__pycache__/`, `*.egg-info`, `.pytest_cache/`.

---

## 8. Top 5 links pra você abrir e ler antes de codar

Em ordem de retorno-sobre-tempo-de-leitura:

1. **Hamel Husain — Evals FAQ** (https://hamel.dev/blog/posts/evals-faq/) — 15 min, vai te dar vocabulário e framing. Mais citado da área.
2. **OpenAI Structured Outputs** (https://developers.openai.com/api/docs/guides/structured-outputs) — 10 min, é o que você vai usar nos 3 estágios.
3. **Steve Kinney — Prompt Engineering Frontier LLMs** (https://stevekinney.com/writing/prompt-engineering-frontier-llms) — 20 min, melhor síntese cross-provider que vi.
4. **dida.do — Structured Outputs walkthrough** (https://dida.do/blog/structured-outputs-with-openai-and-pydantic) — 10 min, exemplos limpos.
5. **Langfuse — Testing LLM Applications** (https://langfuse.com/blog/2025-10-21-testing-llm-applications) — 15 min, ground-up sobre testes não-determinísticos.

Total: ~70 minutos. Vale fazer antes de abrir o Claude Code.

---

## 9. Como usar este doc com Claude Code

1. **Como primeira mensagem**, cole `SPEC.md` + este arquivo.
2. **Não peça pro Claude Code "implementar o POC"**. Peça módulo por módulo, na ordem do `SPEC.md` §12, citando as seções deste doc.
3. **Exemplos de prompts pro Claude Code**:
   - "Implemente `models.py` seguindo §6 do SPEC e §1 do PRACTICES. Use Pydantic v2 com `Literal` e `Field(ge=, le=)`. Use `X | None = None` em vez de `Optional[X]`."
   - "Implemente `stages/judge.py` seguindo §7.3 do SPEC e §2 do PRACTICES. Use o template de prompt da §2.5 como base, mas adapte pro nosso domínio médico brasileiro."
   - "Escreva `tests/test_scorer.py` seguindo §6 do PRACTICES. Calcule os valores esperados à mão, não os deixe ser inferidos pela implementação."
4. **Revise manualmente** os 3 prompts críticos (generator, simulator, judge). Claude Code pode propor algo razoável mas é onde a qualidade do POC vai aparecer.
5. **Quando bater rate limit ou erro** durante teste local, **NÃO peça pro Claude Code consertar com retry manual**. Diga: "o SDK já faz retry, ajuste o `max_retries` no constructor".

---

**Fim do doc.** Use em conjunto com `SPEC.md`. Boa execução.
