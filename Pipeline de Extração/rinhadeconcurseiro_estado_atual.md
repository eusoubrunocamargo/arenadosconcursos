# rinhadeconcurseiro — Estado Atual do Pipeline

> **Documento de continuidade.** Cole este arquivo no início de uma nova conversa para retomar o projeto sem perda de contexto.

---

## 1. Contexto do Projeto

App de curadoria de questões de concurso (CEBRASPE/CESPE), focado em múltiplas fontes com garantia de qualidade por curadoria humana. Nome: **rinhadeconcurseiro**.

- **Foco inicial:** Língua Portuguesa, Direito Administrativo, Direito Constitucional
- **Stack:** Python (pipeline), PostgreSQL (banco final), frontend separado (desktop/mobile)
- **Fonte de dados:** plataforma TEC (tecconcursos.com.br) via API REST autenticada por cookies

---

## 2. Schema SQL — tabela `questao`

```sql
CREATE TABLE questao (
    id                  BIGSERIAL PRIMARY KEY,
    id_tec              VARCHAR(20) UNIQUE,
    link_tec            VARCHAR(255),
    banca               VARCHAR(50) NOT NULL,
    variante_banca      VARCHAR(20),
    ano                 SMALLINT NOT NULL,
    orgao_sigla         VARCHAR(30),
    orgao_nome          VARCHAR(150),
    cargo               VARCHAR(200),
    concurso_area       VARCHAR(100),
    id_materia          INTEGER NOT NULL REFERENCES materia(id),
    id_assunto          INTEGER REFERENCES assunto(id),
    tags                TEXT[],
    nivel_dificuldade   VARCHAR(15) CHECK (nivel_dificuldade IN ('INICIANTE','INTERMEDIARIO','AVANCADO')),
    texto_apoio_html    TEXT,
    texto_apoio_texto   TEXT,
    comando_html        TEXT NOT NULL,
    comando_texto       TEXT NOT NULL,
    enunciado_html      TEXT NOT NULL,
    enunciado_texto     TEXT NOT NULL,
    gabarito            VARCHAR(6) NOT NULL CHECK (gabarito IN ('CERTO','ERRADO')),
    justificativa       TEXT,
    tem_imagem          BOOLEAN NOT NULL DEFAULT FALSE,
    imagem_url_tec      VARCHAR(500),
    imagem_url_propria  VARCHAR(500),
    tipo_cobranca       VARCHAR(25),
    referencia_legal    TEXT,
    conceito_principal  TEXT,
    armadilha           TEXT,
    subconceitos        TEXT[],
    qualidade_extracao  VARCHAR(22) NOT NULL DEFAULT 'REQUER_REVISAO_MANUAL'
                        CHECK (qualidade_extracao IN ('PERFEITA','PARCIAL','REQUER_REVISAO_MANUAL')),
    ativo               BOOLEAN NOT NULL DEFAULT FALSE,
    data_publicacao     TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW()
);
```

**Decisões arquiteturais fixadas:**

- `id_tec` é rastreabilidade temporária, **nunca** chave primária
- `ativo = false` por padrão — nada vai ao ar sem curadoria humana
- Texto de apoio desnormalizado (sem tabela 1:N separada)
- Representação dual: `_html` (frontend) + `_texto` (LLM)
- `conceito_principal`, `armadilha`, `subconceitos` → preenchidos na curadoria (E6)
- `tipo_cobranca` e `referencia_legal` → inferidos automaticamente pelo sanitizador (E3)

**Conflito crítico de nomenclatura:**

| Contexto | `enunciado` significa |
|---|---|
| API do TEC | Corpo completo da questão (texto_apoio + comando + afirmação) |
| Schema interno | Apenas a afirmação a ser julgada (após o "julgue o item") |

O sanitizador (`separar_componentes()`) faz essa separação. Nunca confundir.

---

## 3. Pipeline — 8 Etapas

```
E1  → Extração PDF              → gabaritos.json
E2A → Scraper API (enrichment)  → dataset_bruto.json
E2B → Scraper comentários       → comentarios.json
E3  → Sanitizador               → dataset_sanitizado.json
E3B → Merger (E3 + E2B)         → dataset_enriquecido.json   ← a construir
E4  → LLM: justificativa        → dataset_com_justificativa.json
E5  → Dashboard auditoria       → patches aprovação/rejeição
E6  → Dashboard curadoria       → patches + ativo=true
E7  → verify_json               → validação pré-carga
E8  → data_loader               → PostgreSQL
```

### Status por etapa

| Etapa | Nome | Status |
|---|---|---|
| E1 | Extração PDF → gabaritos | ✅ Concluído |
| E2A | Scraper API enrichment | ✅ DA concluído / ⏳ LP em andamento |
| E2B | Scraper comentários | ⚠️ Re-run necessário (ver bug abaixo) |
| E3 | Sanitizador | ✅ DA concluído (99,97% PERFEITA) |
| E3B | Merger | 🔲 A construir |
| E4 | LLM justificativa | 🔲 Planejamento em aberto |
| E5 | Dashboard auditoria | 🔲 A construir |
| E6 | Dashboard curadoria | 🔲 A construir |
| E7 | verify_json | 🔲 Atualizar para novo schema |
| E8 | data_loader | 🔲 Atualizar para novo schema |

---

## 4. Estado dos Datasets

| Arquivo | Questões | Status | Observações |
|---|---|---|---|
| `gabaritos_linguaportuguesa.json` | 5.411 | ✅ | 0 duplicatas |
| `dataset_bruto_linguaportuguesa.json` | ~5.411 | ⏳ | Captura em andamento |
| `dataset_bruto_direitoadministrativo.json` | 3.847 | ✅ | 100% CEBRASPE/CESPE |
| `dataset_sanitizado_da_v2.json` | 3.847 | ✅ | 99,97% PERFEITA, 1 REQUER_REVISAO |
| `comentarios_da.json` | 3.847 | ⚠️ | Apenas 24 com prof — bug diagnosticado |

**Cadernos TEC mapeados:**

- Língua Portuguesa: caderno `90331308`, total `5411`
- Direito Administrativo: capturado completo (3.847 questões, 100% CEBRASPE)

---

## 5. Scripts do Pipeline

### 5.1 `scraper_api.py` — Etapa 2A (estável)

Endpoint: `GET /api/cadernos/{caderno_id}/questoes/{posicao}?atualizarCronometro=false`

Resposta encapsulada em chave `"questao"`. Campo `enunciado` do TEC = corpo completo da questão.

```bash
python scraper_api.py \
    --gabaritos gabaritos_X.json \
    --caderno 90331308 \
    --total 5411 \
    --cookies www_tecconcursos_com_br_cookies.json \
    --saida dataset_bruto_X.json \
    [--limite 20]   # para validação
    [--debug]
```

Configurações: `verify=False` (proxy Windows), rate limit 0.8–1.3s, checkpoint a cada 50 questões.

### 5.2 `scraper_comentarios.py` — Etapa 2B (v3 — versão atual)

Dois endpoints independentes por questão:

- **Professor:** `GET /api/questoes/{id}/comentario`
- **Alunos:** `GET /api/discussoes/{id}/comentarios-alunos?ordenarPor=pontos&pagina=1`

```bash
python scraper_comentarios.py \
    --entrada dataset_bruto_X.json \
    --cookies www_tecconcursos_com_br_cookies.json \
    --saida comentarios_X.json \
    [--limite 10]        # para validação
    [--apenas-prof]      # só comentário do professor
```

**Histórico de fixes aplicados:**

**Fix 1 — `html_para_texto_robusto` (comentários de alunos):**
A API retorna três formatos distintos que precisam de tratamento diferente:
- HTML completo `<html><head></head><body>…</body></html>` (questões recentes)
- HTML fragmento `<p>texto</p>` (formato antigo)
- Texto puro (passado diretamente)

Antes do fix, o HTML completo gerava tags residuais no output. A lógica antiga usava o campo `formato` da API (não confiável) para decidir o tratamento.

**Fix 2 — `get_json()` com sentinel `ERRO_HTTP` e backoff:**
O `get_json()` original tratava todos os status não-200/401/404 como `None` — indistinguível de "sem comentário" (404 legítimo). Isso causou o bug de 3.823 questões com `comentario_professor: null`.

O `get_json()` atual:
- Retorna `None` apenas para 404 (sem comentário — normal)
- Retorna sentinel `ERRO_HTTP` para 403/429/5xx (erros de servidor)
- Backoff exponencial: 429 → respeita `Retry-After`; 503 → 30s + jitter, até 3 tentativas
- 403 → aviso imediato, não retenta (sessão inválida)
- Checkpoint exclui `_erro_http: true` de `ids_prontos` → re-run automático

**Fix 3 — Headers de browser (versão atual — fix do HTTP 405):**
Após re-exportação de cookies, o servidor passou a retornar 405 em todas as requisições. Causa: o TEC adicionou validação de "Fetch Metadata" para distinguir requisições AJAX legítimas de scraping. O scraper v2 não enviava os headers que um browser real envia.

Headers adicionados:
```python
"Accept-Language":  "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
"Origin":           "https://www.tecconcursos.com.br",
"X-Requested-With": "XMLHttpRequest",
"Sec-Fetch-Site":   "same-origin",
"Sec-Fetch-Mode":   "cors",
"Sec-Fetch-Dest":   "empty",
```
O `Referer` também foi atualizado para `https://www.tecconcursos.com.br/questoes/lista` (mais específico que a raiz).

**Se o 405 persistir após esse fix**, a próxima hipótese é que o endpoint mudou de GET para POST. Nesse caso: usar o DevTools do Chrome (Network → XHR/Fetch) para inspecionar a requisição real ao abrir os comentários de uma questão e comparar com o que o scraper envia.

### 5.3 `sanitizer.py` — Etapa 3 (estável)

**Padrões tratados por `separar_componentes()`:**

| Padrão | Descrição |
|---|---|
| `article` | Texto de apoio em `<article class="textoassociado">` |
| `primario` | Sem texto de apoio, "julgue o item" direto |
| `primario+apoio` | "julgue o item" no meio do HTML |
| `typo` | Variante "julgue o **seguintes** item" |
| `intro_hipotetica` | "O item a seguir é/apresenta..." |
| `nessa_situacao` | "Nessa situação..." como enunciado |
| `fallback` | Qualquer outro padrão |

**Funções principais:**

- `parse_banca()` — normaliza `banca_sigla` → `CEBRASPE` + `variante_banca: CESPE`
- `html_para_texto()` — converte HTML para texto puro (representação dual)
- `separar_componentes()` — divide `texto_apoio` / `comando` / `enunciado`
- `avaliar_qualidade()` — classifica `PERFEITA | PARCIAL | REQUER_REVISAO_MANUAL`
- `inferir_tipo_cobranca()` — `DOUTRINA | LITERALIDADE_LEI | JURISPRUDENCIA` etc.
- `extrair_referencia_legal()` — captura dispositivos legais do enunciado

**Resultados DA:** 3.847 questões, 99,97% PERFEITA, 1 REQUER_REVISAO_MANUAL.

---

## 6. Formatos JSON dos Artefatos

### Dataset sanitizado (saída E3)

```json
{
  "id_tec": "3339247",
  "link_tec": "https://www.tecconcursos.com.br/questoes/3339247",
  "banca": "CEBRASPE",
  "variante_banca": "CESPE",
  "ano": 2024,
  "orgao_sigla": "BDMG",
  "orgao_nome": "...",
  "cargo": "...",
  "concurso_area": "...",
  "id_materia_nome": "Direito Administrativo (Doutrina e Leis Federais)",
  "id_assunto_nome": "Poder Regulamentar",
  "texto_apoio_html": null,
  "texto_apoio_texto": null,
  "comando_html": "<p>julgue o item a seguir.</p>",
  "comando_texto": "julgue o item a seguir.",
  "enunciado_html": "<p>Afirmação...</p>",
  "enunciado_texto": "Afirmação...",
  "gabarito": "ERRADO",
  "tipo_cobranca": "DOUTRINA",
  "referencia_legal": null,
  "conceito_principal": null,
  "armadilha": null,
  "subconceitos": [],
  "tags": [],
  "nivel_dificuldade": null,
  "justificativa": null,
  "qualidade_extracao": "PERFEITA",
  "ativo": false,
  "data_publicacao": "..."
}
```

### Comentários (saída E2B)

```json
{
  "id_tec": "474260",
  "comentario_professor": {
    "nome_professor": "Cyonil Borges",
    "url_professor": "cyonil-borges",
    "texto_html": "<p>...</p>",
    "texto_puro": "O item está CERTO...",
    "data_publicacao": "18/06/2017"
  },
  "comentarios_alunos": [
    {
      "apelido": "RPHL",
      "votos": 67,
      "professor": false,
      "texto": "Teoria dos motivos...",
      "data": "14/06/2017 10:30:00"
    }
  ]
}
```

Entradas com erro HTTP têm `"_erro_http": true` — reprocessadas automaticamente no próximo run.

---

## 7. Bugs Diagnosticados e Corrigidos

### Bug 1 — HTML completo em comentários de alunos (E2B)

**Sintoma:** Tags HTML residuais no campo `texto` dos comentários de alunos.

**Causa:** A API do TEC retorna HTML completo com wrapper `<html>` para questões recentes, mas o código usava o campo `formato` (não confiável) para decidir o tratamento.

**Fix:** `html_para_texto_robusto()` — detecta o formato pelo conteúdo, não pelo metadado.

### Bug 2 — 403 silencioso como "sem comentário" (E2B)

**Sintoma:** Run completo resultou em apenas 24 questões com comentário de professor (esperado: ~3.600).

**Causa:** `get_json()` tratava todos os status != 200/401/404 como `None`. O TEC rotacionou o JSESSIONID após ~24 requisições, retornando 403. O scraper interpretou como "sem comentário" e seguiu em frente silenciosamente.

**Evidência:** Questões 3339247 e 3339250 (BDMG, mesmo concurso) têm comentário; 3339251, 3339254, 3339259 (mesmo concurso) não têm — incoerente com cobertura parcial.

**Fix:** Sentinel `ERRO_HTTP`, tratamento diferenciado por status, backoff, re-run automático via checkpoint.

### Bug 3 — HTTP 405 após re-exportação de cookies (E2B)

**Sintoma:** 405 Method Not Allowed em todas as requisições após atualizar os cookies.

**Causa:** O TEC adicionou validação de Fetch Metadata. O scraper não enviava `X-Requested-With: XMLHttpRequest` nem os headers `Sec-Fetch-*` que um browser real envia em toda requisição AJAX/fetch. O servidor passou a rejeitar requisições sem esses headers.

**Fix:** Adição de `X-Requested-With`, `Sec-Fetch-Site/Mode/Dest`, `Origin`, `Accept-Language` ao dicionário `HEADERS`.

**Se persistir:** Inspecionar no DevTools (Network → XHR/Fetch) a requisição real ao abrir comentários de uma questão e comparar headers por headers com o que o scraper envia.

---

## 8. Ambiente e Cookies

**Configurações de ambiente:**

- Windows com proxy/antivirus com inspeção SSL → `verify=False` em todas as requisições HTTPS
- Autenticação: Cookie-Editor (extensão Chrome) exporta cookies em JSON

**Estado dos cookies (referência de 18/03/2026):**

| Cookie | Expira | Status |
|---|---|---|
| AWSALB | 23/03/2026 | ⚠️ Expira em breve |
| AWSALBCORS | 23/03/2026 | ⚠️ Expira em breve |
| TecPermanecerLogado | 30/03/2026 | OK |
| JSESSIONID | sem expiração registrada | Re-exportar sempre |
| _clsk | expirado | Só analytics, não afeta auth |

**Ponto crítico:** O JSESSIONID não tem expiração registrada no Cookie-Editor, mas o servidor o invalida após N requisições (causa do Bug 2). Sempre re-exportar cookies antes de um run completo.

---

## 9. Planejamento E4 — LLM

### Input disponível por questão (via dataset_enriquecido, saída E3B)

```
enunciado_texto       → afirmação a ser julgada
comando_texto         → "Julgue o item..."
texto_apoio_texto     → texto de lei/doutrina (quando houver)
gabarito              → CERTO | ERRADO
tipo_cobranca         → DOUTRINA | LITERALIDADE_LEI | etc.
referencia_legal      → dispositivo legal (quando inferido)
comentario_professor  → texto_puro (quando houver)
comentarios_alunos[]  → top 3 por votos, texto limpo
```

### Decisões acordadas

- **Dois templates de prompt:** com comentário de professor vs sem (risco de alucinação maior no segundo caso)
- **Checkpoint a cada 50 questões** — mesma lógica de E2A/E2B
- **Campos gerados:** `justificativa`, `modelo_usado`, `data_geracao`
- **`qualidade_justificativa: null`** → preenchido pelo E5 (dashboard de auditoria)
- **Testes A/B com usuários** para ranquear modelos — parte do roadmap
- **Modelos candidatos:** Haiku 4.5 (volume/custo) vs Sonnet 4.6 (qualidade)

### Decisões ainda em aberto

- Estrutura da justificativa: texto corrido com marcadores vs JSON interno estruturado
- Qual o schema do banco para campos gerados por LLM (só `justificativa` por enquanto; flashcards são etapa futura)

### E3B — Merger (prerequisito da E4)

`merger.py` faz join por `id_tec` entre sanitizado e comentários. Descarta `texto_html` do professor (mantém só `texto_puro`). Adiciona metadados: `tem_comentario_prof: bool`, `n_comentarios_alunos: int`.

---

## 10. Próximas Ações Imediatas

### 10.1 Resolver HTTP 405 no E2B (BLOQUEADOR)

```bash
# 1. Validar com --limite 10 em questão conhecida
python scraper_comentarios.py \
    --entrada dataset_bruto_direitoadministrativo.json \
    --cookies www_tecconcursos_com_br_cookies.json \
    --saida comentarios_da.json \
    --limite 10

# 2. Verificar se retorna comentário do Marcelo Sales para 3339251
# 3. Se OK: rodar sem --limite (~65 min, checkpoint processa só as 3.823 pendentes)
```

Se o 405 persistir: usar DevTools para capturar os headers exatos da requisição real.

### 10.2 E3B — Merger (quando E2B estiver OK)

Construir `merger.py`.

### 10.3 E4 — LLM

Definir estrutura da justificativa e rodar primeiro lote de 20 questões comparando Haiku 4.5 vs Sonnet 4.6.

---

## 11. Decisões Arquiteturais Completas

- Scraper API e scraper de comentários **separados** (ciclos de vida e checkpoints independentes)
- Texto de apoio desnormalizado — sem tabela separada no banco
- `id_tec` = rastreabilidade temporária, nunca chave primária
- `ativo = false` por padrão — nada vai ao ar sem curadoria humana
- JSON como artefato auditável entre etapas — banco é destino final, nunca rascunho
- Comentários **não** vão direto ao banco — são contexto para a LLM (E4)
- O seal do E6 (curadoria pedagógica) é o que muda `ativo` de `false` para `true`
- E4 produz apenas `justificativa`; novos produtos (flashcards etc.) são etapas futuras
- Feedback loop E5 → E4 (rejeições da auditoria) será modelado após primeiro ciclo de qualidade
- Dashboard (E5/E6): HTML estático gerado por Python, abre no Chrome localmente
