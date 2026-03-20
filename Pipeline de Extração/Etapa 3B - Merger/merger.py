#!/usr/bin/env python3
"""
Etapa 3B - Merger: une dataset_sanitizado + comentarios em dataset_enriquecido.

O enriquecido e o artefato de entrada exclusivo da Etapa 4 (LLM).
Pode ser re-executado a qualquer momento: sempre reflete o estado mais
atual do arquivo de comentarios (que pode ser parcial durante o scraping).

Decisoes de design:
  - Descarta texto_html do professor: irrelevante para a LLM.
  - Questoes sem comentarios no arquivo de entrada recebem campos nulos,
    e serao processadas pelo template "sem professor" na Etapa 4.
  - _erro_http: questoes com erro HTTP no scraper sao tratadas como
    "sem comentario" para a LLM — o erro e interno ao pipeline.
  - Questoes presentes no sanitizado mas ausentes no arquivo de comentarios
    (scraping ainda nao chegou la) tambem recebem campos nulos.

Uso:
    python merger.py \\
        --sanitizado dataset_sanitizado_da_v2.json \\
        --comentarios comentarios_direitoadministrativo.json \\
        --saida dataset_enriquecido_da.json

Dependencias: nenhuma alem da stdlib.
"""

import json
import sys
import argparse
from pathlib import Path


# =============================================================================
# MERGER
# =============================================================================

def extrair_comentarios(obj_comentario):
    """
    A partir de um objeto do arquivo de comentarios, extrai apenas
    o que a LLM vai consumir — descartando texto_html do professor
    e o campo _erro_http (artefato interno do scraper).

    Retorna uma tupla (comentario_prof, comentarios_alunos, fonte_contexto):
      - comentario_prof: dict com nome_professor, texto_puro, data_publicacao
                         ou None se nao houver
      - comentarios_alunos: lista de dicts com apelido, votos, texto
                            (vazia se nao houver)
      - fonte_contexto: "PROFESSOR" | "ALUNOS" | "ENUNCIADO_APENAS"
    """
    if not obj_comentario or obj_comentario.get("_erro_http"):
        return None, [], "ENUNCIADO_APENAS"

    # Extrai comentario do professor (sem o HTML — irrelevante para LLM)
    prof_raw = obj_comentario.get("comentario_professor")
    comentario_prof = None
    if prof_raw and isinstance(prof_raw, dict):
        texto_puro = (prof_raw.get("texto_puro") or "").strip()
        if texto_puro:
            comentario_prof = {
                "nome_professor":  prof_raw.get("nome_professor", ""),
                "texto_puro":      texto_puro,
                "data_publicacao": prof_raw.get("data_publicacao", ""),
            }

    # Extrai comentarios de alunos (ja em texto limpo, vindo do scraper)
    alunos_raw = obj_comentario.get("comentarios_alunos") or []
    comentarios_alunos = [
        {
            "apelido": c.get("apelido", ""),
            "votos":   c.get("votos", 0),
            "texto":   (c.get("texto") or "").strip(),
        }
        for c in alunos_raw
        if (c.get("texto") or "").strip()  # descarta alunos sem texto util
    ]

    # Determina a fonte de contexto disponivel para a LLM
    if comentario_prof:
        fonte_contexto = "PROFESSOR"
    elif comentarios_alunos:
        fonte_contexto = "ALUNOS"
    else:
        fonte_contexto = "ENUNCIADO_APENAS"

    return comentario_prof, comentarios_alunos, fonte_contexto


def merge(sanitizado, comentarios_map):
    """
    Une cada questao do dataset sanitizado com seus comentarios.
    Retorna (enriquecido, contadores) onde contadores e um dict com
    as metricas de cobertura — acumuladas durante o loop para evitar
    uma segunda varredura sobre a lista e para garantir que os valores
    estejam sempre disponiveis mesmo que o caller falhe depois.
    """
    enriquecido = []
    contadores = {
        "com_prof":   0,
        "com_alunos": 0,
        "so_enunc":   0,
        "sem_coment": 0,
    }

    for q in sanitizado:
        id_tec = q["id_tec"]
        obj_comentario = comentarios_map.get(id_tec)  # None se ainda nao scraped

        comentario_prof, comentarios_alunos, fonte_contexto = extrair_comentarios(
            obj_comentario
        )

        # Monta o objeto enriquecido: todos os campos do sanitizado
        # mais os campos de contexto para a LLM
        enriquecido_q = {
            **q,  # todos os campos do sanitizado (id_tec, enunciado, gabarito, etc.)

            # --- Campos adicionados pelo merger ---
            "comentario_professor":  comentario_prof,
            "comentarios_alunos":    comentarios_alunos,

            # Metadados de contexto (uteis para o E4 selecionar o template
            # e para o E5 priorizar revisao de questoes sem professor)
            "tem_comentario_prof":   comentario_prof is not None,
            "n_comentarios_alunos":  len(comentarios_alunos),
            "fonte_contexto":        fonte_contexto,

            # --- Campos que serao preenchidos pela LLM na Etapa 4 ---
            "justificativa_json":    None,  # {"por_que_errado", "conceito_cobrado",
                                            #  "armadilha", "ponto_atencao"}
            "justificativa_texto":   None,  # derivado do json, para o banco
            "modelo_usado":          None,
            "confianca_llm":         None,  # "ALTA" | "MEDIA" | "BAIXA"
            "tokens_input":          None,
            "tokens_output":         None,
            "data_geracao":          None,
        }
        # Acumula contadores durante o loop — evita segunda varredura
        if enriquecido_q["tem_comentario_prof"]:
            contadores["com_prof"] += 1
        if enriquecido_q["n_comentarios_alunos"] > 0:
            contadores["com_alunos"] += 1
        if enriquecido_q["fonte_contexto"] == "ENUNCIADO_APENAS":
            contadores["so_enunc"] += 1
        if comentarios_map.get(id_tec) is None:
            contadores["sem_coment"] += 1

        enriquecido.append(enriquecido_q)

    return enriquecido, contadores


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Etapa 3B - Merger: sanitizado + comentarios → enriquecido",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--sanitizado",  required=True,
                        help="dataset_sanitizado_X.json (saida da Etapa 3)")
    parser.add_argument("--comentarios", required=True,
                        help="comentarios_X.json (saida da Etapa 2B, pode ser parcial)")
    parser.add_argument("--saida",       required=True,
                        help="dataset_enriquecido_X.json (entrada da Etapa 4)")
    args = parser.parse_args()

    # Carrega o dataset sanitizado
    print(f"Carregando sanitizado:  {args.sanitizado}")
    with open(args.sanitizado, encoding="utf-8") as f:
        sanitizado = json.load(f)
    print(f"  {len(sanitizado)} questoes carregadas.")

    # Carrega o arquivo de comentarios e indexa por id_tec
    print(f"\nCarregando comentarios: {args.comentarios}")
    with open(args.comentarios, encoding="utf-8") as f:
        comentarios_lista = json.load(f)
    comentarios_map = {c["id_tec"]: c for c in comentarios_lista}
    print(f"  {len(comentarios_map)} entradas de comentario carregadas.")

    # Executa o merge
    print("\nMerging...")
    enriquecido, cnt = merge(sanitizado, comentarios_map)
    total = len(enriquecido)

    # Relatorio impresso e flushed ANTES de salvar — garante visibilidade
    # mesmo em terminais Windows que bufferizam stdout
    print(f"\n{'='*60}")
    print(f"RELATORIO E3B - MERGER")
    print(f"{'='*60}")
    print(f"Total de questoes:            {total}")
    print(f"Com comentario de professor:  {cnt['com_prof']:5d}  ({cnt['com_prof']/max(total,1)*100:.1f}%)")
    print(f"Com comentarios de alunos:    {cnt['com_alunos']:5d}  ({cnt['com_alunos']/max(total,1)*100:.1f}%)")
    print(f"Somente enunciado (sem ctx):  {cnt['so_enunc']:5d}  ({cnt['so_enunc']/max(total,1)*100:.1f}%)")
    print(f"Ainda nao scraped:            {cnt['sem_coment']:5d}  (scraping em andamento)")
    print(f"{'='*60}")
    sys.stdout.flush()  # garante flush antes de iniciar o write em disco

    # Salva o dataset enriquecido
    print(f"\nSalvando: {args.saida}")
    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(enriquecido, f, ensure_ascii=False, indent=2)

    tamanho_mb = Path(args.saida).stat().st_size / 1024 / 1024
    print(f"  {len(enriquecido)} questoes salvas ({tamanho_mb:.1f} MB).")
    print("\nConcluido. Para re-executar quando o scraping terminar:")
    print(f"  python merger.py --sanitizado {args.sanitizado} "
          f"--comentarios {args.comentarios} --saida {args.saida}")


if __name__ == "__main__":
    main()