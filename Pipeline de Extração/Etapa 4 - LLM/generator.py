#!/usr/bin/env python3
"""
Etapa 4 - Gerador de justificativas via LLM.

Para cada questao do dataset_enriquecido, chama uma LLM para gerar
uma justificativa pedagogica estruturada com quatro campos:
  - por_que_errado   (ou por_que_correto, dependendo do gabarito)
  - conceito_cobrado
  - armadilha
  - ponto_atencao
  + confianca_llm (metadado de autoavaliacao do modelo)

Suporta dois provedores:
  - Anthropic (claude-sonnet-4-6, claude-haiku-4-5)
  - OpenAI    (gpt-5.4, gpt-5.4-mini, gpt-5.4-nano)

Variaveis de ambiente:
  ANTHROPIC_API_KEY
  OPENAI_API_KEY

Uso:
    python llm_justificativa.py --entrada dataset_enriquecido_da.json \
        --saida dataset_com_justificativa_da.json --modelo claude-sonnet-4-6

    # Lote de teste A/B (N questoes, arquivo separado _lote_<modelo>.json)
    python llm_justificativa.py ... --modelo gpt-5.4-mini --lote-teste 50
"""

import json, time, random, argparse, os
from datetime import datetime, timezone
from pathlib import Path

# =============================================================================
# CONFIGURACAO
# =============================================================================

CHECKPOINT_A_CADA = 50

CAMPOS_OBRIGATORIOS = [
    "por_que_errado", "conceito_cobrado",
    "armadilha", "ponto_atencao", "confianca_llm"
]

MODELOS = {
    "claude-sonnet-4-6": "anthropic",
    "claude-haiku-4-5":  "anthropic",
    "gpt-5.4":           "openai",
    "gpt-5.4-mini":      "openai",
    "gpt-5.4-nano":      "openai",
}

CUSTOS_POR_M_TOKENS = {
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5":  (0.25,  1.25),
    "gpt-5.4":           (2.50, 15.00),
    "gpt-5.4-mini":      (0.75,  4.50),
    "gpt-5.4-nano":      (0.20,  1.25),
}


# =============================================================================
# PROMPTS
# =============================================================================

SISTEMA = """\
Voce e um professor especialista em preparacao para concursos publicos brasileiros,
com foco em questoes do estilo CEBRASPE/CESPE (Certo/Errado).

Sua tarefa e gerar uma justificativa pedagogica estruturada para uma questao de concurso.
Ajude o candidato a entender o erro ou acerto de forma clara e objetiva.

Regras:
- Seja direto e didatico. Evite jargoes desnecessarios.
- Se o gabarito for ERRADO, explique o erro com precisao.
- Se o gabarito for CERTO, use o campo por_que_errado para explicar por que esta correto
  (ex: "O item esta correto porque...").
- O campo armadilha identifica a tecnica da banca (inversao de conceitos, troca de termos,
  restricao indevida, etc.), ou "Sem armadilha identificada" se nao houver.
- confianca_llm: ALTA se havia comentario do professor, MEDIA se so alunos, BAIXA se so enunciado.
- Responda em portugues do Brasil.\
"""


def montar_prompt(q):
    gabarito = q.get("gabarito", "ERRADO").upper()
    linhas   = ["=== QUESTAO ==="]

    if q.get("texto_apoio_texto"):
        linhas.append(f"[Texto de apoio]\n{q['texto_apoio_texto']}\n")
    if q.get("comando_texto"):
        linhas.append(f"[Comando]\n{q['comando_texto']}\n")
    linhas.append(f"[Afirmacao]\n{q.get('enunciado_texto', '')}\n")
    linhas.append(f"[Gabarito] {gabarito}")
    if q.get("tipo_cobranca"):
        linhas.append(f"[Tipo] {q['tipo_cobranca']}")
    if q.get("referencia_legal"):
        linhas.append(f"[Referencia legal] {q['referencia_legal']}")

    fonte = q.get("fonte_contexto", "ENUNCIADO_APENAS")

    if fonte == "PROFESSOR":
        prof = q.get("comentario_professor") or {}
        linhas.append(f"\n=== COMENTARIO DO PROFESSOR ({prof.get('nome_professor','')}) ===")
        linhas.append(prof.get("texto_puro", ""))
        alunos = q.get("comentarios_alunos") or []
        if alunos:
            linhas.append("\n=== TOP COMENTARIOS DE ALUNOS ===")
            for a in alunos[:2]:
                linhas.append(f"[{a['apelido']} — {a['votos']} votos]\n{a['texto']}")

    elif fonte == "ALUNOS":
        alunos = q.get("comentarios_alunos") or []
        linhas.append("\n=== COMENTARIOS DE ALUNOS (sem professor) ===")
        for a in alunos:
            linhas.append(f"[{a['apelido']} — {a['votos']} votos]\n{a['texto']}")

    else:
        linhas.append("\n[Sem comentarios externos. Analise baseada no enunciado e gabarito.]")

    linhas.append("\n=== TAREFA ===")
    linhas.append("Gere a justificativa pedagogica estruturada.")
    return "\n".join(linhas)


# =============================================================================
# SCHEMAS PARA STRUCTURED OUTPUT
# =============================================================================

# OpenAI — json_schema strict=True
OPENAI_SCHEMA = {
    "name": "justificativa_questao",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["por_que_errado", "conceito_cobrado",
                     "armadilha", "ponto_atencao", "confianca_llm"],
        "properties": {
            "por_que_errado": {
                "type": "string",
                "description": "Explicacao do erro ou acerto. 2-4 frases."
            },
            "conceito_cobrado": {
                "type": "string",
                "description": "Conceito juridico ou dispositivo legal avaliado. 1-2 frases."
            },
            "armadilha": {
                "type": "string",
                "description": "Tecnica da banca ou 'Sem armadilha identificada'."
            },
            "ponto_atencao": {
                "type": "string",
                "description": "Frase de fixacao para o candidato nao errar."
            },
            "confianca_llm": {
                "type": "string",
                "enum": ["ALTA", "MEDIA", "BAIXA"],
                "description": "ALTA=com professor, MEDIA=so alunos, BAIXA=so enunciado."
            }
        }
    }
}

# Anthropic — tool use (equivalente funcional)
ANTHROPIC_TOOL = {
    "name": "registrar_justificativa",
    "description": "Registra a justificativa pedagogica estruturada da questao.",
    "input_schema": {
        "type": "object",
        "required": ["por_que_errado", "conceito_cobrado",
                     "armadilha", "ponto_atencao", "confianca_llm"],
        "properties": {
            "por_que_errado":   {"type": "string"},
            "conceito_cobrado": {"type": "string"},
            "armadilha":        {"type": "string"},
            "ponto_atencao":    {"type": "string"},
            "confianca_llm":    {"type": "string", "enum": ["ALTA", "MEDIA", "BAIXA"]}
        }
    }
}


# =============================================================================
# CHAMADAS DE API
# =============================================================================

def chamar_anthropic(client, modelo, prompt):
    import anthropic
    resp = client.messages.create(
        model=modelo,
        max_tokens=1024,
        system=SISTEMA,
        tools=[ANTHROPIC_TOOL],
        tool_choice={"type": "tool", "name": "registrar_justificativa"},
        messages=[{"role": "user", "content": prompt}]
    )
    bloco = next((b for b in resp.content if b.type == "tool_use"), None)
    if not bloco:
        raise ValueError("Anthropic nao retornou tool_use block")
    return bloco.input, resp.usage.input_tokens, resp.usage.output_tokens


def chamar_openai(client, modelo, prompt):
    resp = client.chat.completions.create(
        model=modelo,
        max_tokens=1024,
        messages=[
            {"role": "system", "content": SISTEMA},
            {"role": "user",   "content": prompt},
        ],
        response_format={"type": "json_schema", "json_schema": OPENAI_SCHEMA}
    )
    choice = resp.choices[0]
    if getattr(choice.message, "refusal", None):
        raise ValueError(f"OpenAI recusou: {choice.message.refusal}")
    return (json.loads(choice.message.content),
            resp.usage.prompt_tokens,
            resp.usage.completion_tokens)


# =============================================================================
# VALIDACAO E DERIVACAO
# =============================================================================

def validar(j):
    for campo in CAMPOS_OBRIGATORIOS:
        if not str(j.get(campo, "")).strip():
            raise ValueError(f"Campo vazio: {campo}")
    if j.get("confianca_llm") not in ("ALTA", "MEDIA", "BAIXA"):
        raise ValueError(f"confianca_llm invalido: {j.get('confianca_llm')}")


def derivar_texto(j, gabarito):
    label = "Por que esta correto" if gabarito == "CERTO" else "Por que esta errado"
    return (
        f"{label}: {j['por_que_errado']}\n\n"
        f"Conceito cobrado: {j['conceito_cobrado']}\n\n"
        f"Armadilha: {j['armadilha']}\n\n"
        f"Ponto de atencao: {j['ponto_atencao']}"
    )


# =============================================================================
# CHECKPOINT
# =============================================================================

def carregar_checkpoint(caminho):
    path = Path(caminho)
    if not path.exists():
        return {}, set()
    with open(path, encoding="utf-8") as f:
        lista = json.load(f)
    mapa = {q["id_tec"]: q for q in lista}
    ids_prontos = {k for k, v in mapa.items() if v.get("justificativa_json")}
    ids_erro    = {k for k, v in mapa.items() if v.get("_erro_llm")}
    print(f"   Checkpoint: {len(ids_prontos)} prontos | "
          f"{len(ids_erro)} com erro (serao reprocessados).")
    return mapa, ids_prontos


def salvar(mapa, caminho):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(list(mapa.values()), f, ensure_ascii=False, indent=2)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Etapa 4 - Gerador de justificativas via LLM"
    )
    parser.add_argument("--entrada", required=True)
    parser.add_argument("--saida",   required=True)
    parser.add_argument("--modelo",  default="claude-sonnet-4-6",
                        choices=list(MODELOS))
    parser.add_argument("--lote-teste", type=int, default=0,
                        help="Modo A/B: N questoes, arquivo _lote_<modelo>.json")
    parser.add_argument("--limite",  type=int, default=0,
                        help="Limita N questoes (0 = todas)")
    args = parser.parse_args()

    # Inicializa cliente
    provedor = MODELOS[args.modelo]
    if provedor == "anthropic":
        key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise SystemExit("Defina ANTHROPIC_API_KEY.")
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=key)
            chamar = lambda p: chamar_anthropic(client, args.modelo, p)
        except ImportError:
            raise SystemExit("pip install anthropic")
    else:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise SystemExit("Defina OPENAI_API_KEY.")
        try:
            from openai import OpenAI
            client = OpenAI(api_key=key)
            chamar = lambda p: chamar_openai(client, args.modelo, p)
        except ImportError:
            raise SystemExit("pip install openai")

    # Arquivo de saida
    modelo_slug = args.modelo.replace(".", "-")
    if args.lote_teste > 0:
        p = Path(args.saida)
        caminho_saida = str(p.parent / f"{p.stem}_lote_{modelo_slug}{p.suffix}")
        print(f"Modo lote-teste ({args.lote_teste} questoes) → {caminho_saida}")
    else:
        caminho_saida = args.saida

    # Carrega dataset
    with open(args.entrada, encoding="utf-8") as f:
        questoes = json.load(f)
    n_orig = len(questoes)

    if args.lote_teste > 0:
        questoes = questoes[:args.lote_teste]
    elif args.limite > 0:
        questoes = questoes[:args.limite]

    mapa, ids_prontos = carregar_checkpoint(caminho_saida)
    for q in questoes:
        if q["id_tec"] not in mapa:
            mapa[q["id_tec"]] = q

    total       = len(questoes)
    processadas = sucessos = erros = 0
    tokens_in_total = tokens_out_total = 0

    print(f"\nModelo:  {args.modelo}  ({provedor})")
    print(f"Total:   {total} | Ja prontas: {len(ids_prontos)}")
    print("=" * 60)

    for q in questoes:
        id_tec = q["id_tec"]
        if id_tec in ids_prontos:
            continue

        prompt       = montar_prompt(q)
        justificativa = None
        tokens_in = tokens_out = 0

        for tentativa in range(1, 4):
            try:
                justificativa, tokens_in, tokens_out = chamar(prompt)
                validar(justificativa)
                break
            except Exception as e:
                espera = 2 ** tentativa + random.uniform(0, 1)
                print(f"   ⚠ [{id_tec}] tentativa {tentativa}/3: {e} "
                      f"(aguardando {espera:.0f}s)")
                time.sleep(espera)
                justificativa = None

        obj = mapa[id_tec].copy()
        if justificativa:
            obj.update({
                "justificativa_json":  justificativa,
                "justificativa_texto": derivar_texto(
                    justificativa, q.get("gabarito", "ERRADO").upper()
                ),
                "modelo_usado":   args.modelo,
                "confianca_llm":  justificativa.get("confianca_llm"),
                "tokens_input":   tokens_in,
                "tokens_output":  tokens_out,
                "data_geracao":   datetime.now(timezone.utc).isoformat(),
            })
            obj.pop("_erro_llm", None)
            tokens_in_total  += tokens_in
            tokens_out_total += tokens_out
            sucessos += 1
        else:
            obj["_erro_llm"] = True
            erros += 1

        mapa[id_tec] = obj
        processadas += 1

        prontas_total = processadas + len(ids_prontos)
        if processadas % 10 == 0 or prontas_total == total:
            pct = prontas_total / total * 100
            print(f"   [{prontas_total}/{total}] ({pct:.0f}%) "
                  f"ok={sucessos} erros={erros}")

        if processadas % CHECKPOINT_A_CADA == 0:
            salvar(mapa, caminho_saida)

    salvar(mapa, caminho_saida)

    # Relatorio final
    total_com = sum(1 for v in mapa.values() if v.get("justificativa_json"))
    total_err = sum(1 for v in mapa.values() if v.get("_erro_llm"))
    pi, po    = CUSTOS_POR_M_TOKENS.get(args.modelo, (0, 0))
    custo     = (tokens_in_total / 1e6 * pi) + (tokens_out_total / 1e6 * po)

    print(f"\n{'='*60}")
    print(f"RELATORIO E4 - JUSTIFICATIVAS")
    print(f"{'='*60}")
    print(f"Modelo:              {args.modelo}")
    print(f"Processadas:         {processadas}")
    print(f"Com justificativa:   {total_com}/{n_orig} ({total_com/n_orig*100:.1f}%)")
    print(f"Erros LLM:           {total_err}")
    print(f"Tokens input:        {tokens_in_total:,}")
    print(f"Tokens output:       {tokens_out_total:,}")
    print(f"Custo estimado:      US$ {custo:.2f}")
    print(f"Arquivo de saida:    {caminho_saida}")
    print(f"{'='*60}\n")

    if args.lote_teste > 0:
        print("Lote de teste concluido. Compare os arquivos _lote_*.json")
        print("antes de rodar o dataset completo.")


if __name__ == "__main__":
    main()