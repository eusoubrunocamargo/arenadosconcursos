#!/usr/bin/env python3
"""
Etapa NLM — Gerador de cadernos para o NotebookLM.

Lê o dataset_enriquecido e gera um arquivo Markdown por assunto.
Cada arquivo é uma fonte para o NotebookLM, estruturada para
maximizar a qualidade das respostas do modelo.

Uso:
    python gerar_notebooklm.py \
        --entrada dataset_enriquecido_linguaportuguesa.json \
        --saida   notebooklm/

    # Apenas assuntos com pelo menos N questões
    python gerar_notebooklm.py --entrada ... --saida ... --min-questoes 5

    # Gera também um índice geral do caderno
    python gerar_notebooklm.py --entrada ... --saida ... --indice

Estrutura de cada arquivo:
    # <Assunto>
    ## Visão Geral
    ## Padrões da Banca
    ## Questões
    ### Q001 · <Órgão> · <Ano> · <Gabarito>
    ...
"""

import json
import re
import argparse
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime


# =============================================================================
# SLUGIFY
# =============================================================================

def slugify(texto):
    """Converte nome de assunto em nome de arquivo seguro."""
    texto = texto.lower()
    texto = re.sub(r'[àáâãä]', 'a', texto)
    texto = re.sub(r'[èéêë]', 'e', texto)
    texto = re.sub(r'[ìíîï]', 'i', texto)
    texto = re.sub(r'[òóôõö]', 'o', texto)
    texto = re.sub(r'[ùúûü]', 'u', texto)
    texto = re.sub(r'[ç]', 'c', texto)
    texto = re.sub(r'[^a-z0-9]+', '_', texto)
    return texto.strip('_')


# =============================================================================
# ANÁLISE DO ASSUNTO
# =============================================================================

def analisar_assunto(questoes):
    """
    Calcula estatísticas e padrões do assunto a partir das questões.
    Retorna dict com métricas para o cabeçalho do arquivo.
    """
    total     = len(questoes)
    certos    = sum(1 for q in questoes if (q.get('gabarito') or '').upper() == 'CERTO')
    errados   = total - certos
    pct_certo = certos / total * 100 if total else 0

    anos     = sorted({q.get('ano') for q in questoes if q.get('ano')})
    orgaos   = Counter(q.get('orgao_sigla', '') for q in questoes if q.get('orgao_sigla'))
    bancas   = Counter(q.get('banca', '') or q.get('banca_sigla', '') for q in questoes)
    tipos    = Counter(q.get('tipo_cobranca', '') for q in questoes)
    com_prof = sum(1 for q in questoes if q.get('tem_comentario_prof') or q.get('comentario_professor'))
    com_just = sum(1 for q in questoes if q.get('justificativa_json') or q.get('justificativa_texto'))

    return {
        'total':     total,
        'certos':    certos,
        'errados':   errados,
        'pct_certo': pct_certo,
        'anos':      anos,
        'orgaos':    orgaos,
        'bancas':    bancas,
        'tipos':     tipos,
        'com_prof':  com_prof,
        'com_just':  com_just,
    }


# =============================================================================
# GERAÇÃO DO MARKDOWN
# =============================================================================

def gerar_md_assunto(assunto, questoes, materia):
    """
    Gera o conteúdo Markdown completo para um assunto.
    """
    stats = analisar_assunto(questoes)
    linhas = []

    # ── Cabeçalho ────────────────────────────────────────────────────────────
    linhas.append(f"# {assunto}")
    linhas.append(f"\n**Matéria:** {materia}")
    linhas.append(f"**Total de questões:** {stats['total']}")
    linhas.append(
        f"**Gabarito:** {stats['certos']} CERTO ({stats['pct_certo']:.0f}%) · "
        f"{stats['errados']} ERRADO ({100 - stats['pct_certo']:.0f}%)"
    )
    if stats['anos']:
        anos_str = f"{stats['anos'][0]}–{stats['anos'][-1]}" if len(stats['anos']) > 1 else str(stats['anos'][0])
        linhas.append(f"**Período:** {anos_str}")

    top_bancas = ', '.join(f"{b} ({n})" for b, n in stats['bancas'].most_common(3) if b)
    if top_bancas:
        linhas.append(f"**Bancas:** {top_bancas}")

    top_orgaos = ', '.join(o for o, _ in stats['orgaos'].most_common(5) if o)
    if top_orgaos:
        linhas.append(f"**Órgãos frequentes:** {top_orgaos}")

    linhas.append(f"**Com comentário de professor:** {stats['com_prof']}/{stats['total']}")
    if stats['com_just'] > 0:
        linhas.append(f"**Com justificativa LLM:** {stats['com_just']}/{stats['total']}")

    # ── Padrões detectados ────────────────────────────────────────────────────
    linhas.append("\n---\n")
    linhas.append("## Padrões da Banca\n")

    # Tipo de cobrança dominante
    tipo_dom = stats['tipos'].most_common(1)
    if tipo_dom:
        tipo, n = tipo_dom[0]
        linhas.append(
            f"- **Tipo predominante:** {tipo} "
            f"({n}/{stats['total']} questões, {n/stats['total']*100:.0f}%)"
        )

    # Padrão de gabarito
    if stats['pct_certo'] >= 70:
        linhas.append(
            f"- **Tendência:** maioria CERTO ({stats['pct_certo']:.0f}%) — "
            "a banca tende a apresentar afirmações corretas neste assunto."
        )
    elif stats['pct_certo'] <= 30:
        linhas.append(
            f"- **Tendência:** maioria ERRADO ({100-stats['pct_certo']:.0f}%) — "
            "a banca tende a apresentar afirmações incorretas neste assunto."
        )
    else:
        linhas.append(
            f"- **Distribuição equilibrada:** {stats['pct_certo']:.0f}% CERTO / "
            f"{100-stats['pct_certo']:.0f}% ERRADO."
        )

    # Armadilhas recorrentes (das justificativas LLM, se disponíveis)
    armadilhas = []
    for q in questoes:
        j = q.get('justificativa_json') or {}
        arm = j.get('armadilha') or q.get('armadilha') or ''
        if arm and arm.lower() not in ('sem armadilha identificada', 'n/a', ''):
            armadilhas.append(arm)

    if armadilhas:
        linhas.append(f"\n### Armadilhas recorrentes\n")
        # Deduplica mantendo ordem de frequência
        seen = set()
        for arm in armadilhas:
            arm_norm = arm.strip().rstrip('.')
            if arm_norm not in seen:
                seen.add(arm_norm)
                linhas.append(f"- {arm_norm}")

    # ── Questões ─────────────────────────────────────────────────────────────
    linhas.append("\n---\n")
    linhas.append("## Questões\n")

    # Ordena: com justificativa primeiro, depois por ano desc
    questoes_ord = sorted(
        questoes,
        key=lambda q: (
            0 if (q.get('justificativa_json') or q.get('justificativa_texto')) else 1,
            -(q.get('ano') or 0)
        )
    )

    for i, q in enumerate(questoes_ord, 1):
        gab      = (q.get('gabarito') or '').upper()
        orgao    = q.get('orgao_sigla', '')
        ano      = q.get('ano', '')
        cargo    = q.get('cargo', '')
        area     = q.get('concurso_area', '')
        id_tec   = q.get('id_tec', '')
        link     = q.get('link_tec', f"https://www.tecconcursos.com.br/questoes/{id_tec}")

        gab_emoji = '✅' if gab == 'CERTO' else '❌'

        # Header da questão
        header_parts = [f"Q{i:03d}"]
        if orgao: header_parts.append(orgao)
        if ano:   header_parts.append(str(ano))
        if area:  header_parts.append(area)
        header_parts.append(f"{gab_emoji} {gab}")
        linhas.append(f"### {' · '.join(header_parts)}\n")

        if cargo:
            linhas.append(f"*{cargo}*\n")

        # Texto de apoio (resumido se muito longo)
        apoio = (q.get('texto_apoio_texto') or '').strip()
        if apoio:
            if len(apoio) > 800:
                linhas.append(f"> **Texto de apoio** (trecho):\n> {apoio[:800]}…\n")
            else:
                linhas.append(f"> **Texto de apoio:**\n> {apoio.replace(chr(10), chr(10) + '> ')}\n")

        # Comando + Enunciado
        cmd   = (q.get('comando_texto') or '').strip()
        enunc = (q.get('enunciado_texto') or '').strip()

        if cmd and enunc:
            linhas.append(f"**Comando:** {cmd}")
            linhas.append(f"\n**Afirmação:** {enunc}\n")
        elif enunc:
            linhas.append(f"**Afirmação:** {enunc}\n")

        linhas.append(f"**Gabarito:** {gab_emoji} **{gab}**\n")

        # Justificativa LLM (se disponível)
        just_json = q.get('justificativa_json')
        just_txt  = q.get('justificativa_texto')
        if just_json and isinstance(just_json, dict):
            linhas.append("**Análise:**")
            if just_json.get('por_que_errado'):
                label = 'Por que está correto' if gab == 'CERTO' else 'Por que está errado'
                linhas.append(f"- *{label}:* {just_json['por_que_errado']}")
            if just_json.get('conceito_cobrado'):
                linhas.append(f"- *Conceito cobrado:* {just_json['conceito_cobrado']}")
            if just_json.get('armadilha') and just_json['armadilha'].lower() not in ('sem armadilha identificada',):
                linhas.append(f"- *Armadilha:* {just_json['armadilha']}")
            if just_json.get('ponto_atencao'):
                linhas.append(f"- *Ponto de atenção:* {just_json['ponto_atencao']}")
            linhas.append("")
        elif just_txt:
            linhas.append(f"**Análise:** {just_txt}\n")

        # Comentário do professor (resumido)
        prof = q.get('comentario_professor')
        if prof and isinstance(prof, dict):
            texto_prof = (prof.get('texto_puro') or '').strip()
            nome_prof  = prof.get('nome_professor', 'Professor')
            if texto_prof:
                resumo = texto_prof[:600] + ('…' if len(texto_prof) > 600 else '')
                linhas.append(f"**Comentário ({nome_prof}):** {resumo}\n")

        # Top comentário de aluno (o mais votado)
        alunos = q.get('comentarios_alunos') or []
        if alunos:
            top = alunos[0]
            texto_aluno = (top.get('texto') or '').strip()
            if texto_aluno and len(texto_aluno) >= 20:
                resumo_aluno = texto_aluno[:400] + ('…' if len(texto_aluno) > 400 else '')
                linhas.append(
                    f"**Top comentário** ({top.get('apelido', '')}, "
                    f"{top.get('votos', 0)} votos):** {resumo_aluno}\n"
                )

        linhas.append(f"[Ver no TEC]({link})\n")
        linhas.append("---\n")

    # Rodapé
    linhas.append(
        f"\n*Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} "
        f"a partir do dataset rinhadeconcurseiro.*"
    )

    return "\n".join(linhas)


# =============================================================================
# ÍNDICE GERAL
# =============================================================================

def gerar_indice(assuntos_stats, materia, pasta_saida):
    """Gera um arquivo de índice listando todos os assuntos e suas métricas."""
    linhas = [
        f"# Índice — {materia}",
        f"\n**Total de assuntos:** {len(assuntos_stats)}",
        f"**Gerado em:** {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        "\n---\n",
        "| Assunto | Questões | % CERTO | Arquivo |",
        "|---------|----------|---------|---------|",
    ]
    for assunto, stats in sorted(assuntos_stats.items()):
        slug = slugify(assunto)
        linhas.append(
            f"| {assunto} | {stats['total']} | {stats['pct_certo']:.0f}% "
            f"| [{slug}.md]({slug}.md) |"
        )
    return "\n".join(linhas)


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Etapa NLM — Gera arquivos Markdown por assunto para o NotebookLM"
    )
    parser.add_argument("--entrada",      required=True,
                        help="dataset_enriquecido_X.json")
    parser.add_argument("--saida",        default="notebooklm",
                        help="Pasta de saída (criada se não existir)")
    parser.add_argument("--min-questoes", type=int, default=1,
                        help="Ignora assuntos com menos de N questões")
    parser.add_argument("--indice",       action="store_true",
                        help="Gera também um arquivo indice.md")
    args = parser.parse_args()

    print(f"Carregando: {args.entrada}")
    with open(args.entrada, encoding="utf-8") as f:
        questoes = json.load(f)
    print(f"  {len(questoes)} questões carregadas.")

    # Determina matéria
    materia = next(
        (q.get('id_materia_nome') or q.get('nome_materia') for q in questoes
         if q.get('id_materia_nome') or q.get('nome_materia')),
        "Matéria"
    )

    # Agrupa por assunto
    por_assunto = defaultdict(list)
    for q in questoes:
        assunto = q.get('id_assunto_nome') or q.get('nome_assunto') or 'Sem assunto'
        por_assunto[assunto].append(q)

    # Cria pasta de saída
    pasta = Path(args.saida)
    pasta.mkdir(parents=True, exist_ok=True)

    # Gera arquivos
    assuntos_stats = {}
    gerados = 0
    ignorados = 0

    print(f"\nGerando arquivos em {pasta}/")
    print(f"{'Assunto':<60} {'Qtd':>5}  {'Arquivo'}")
    print("-" * 85)

    for assunto, qs in sorted(por_assunto.items()):
        if len(qs) < args.min_questoes:
            ignorados += 1
            continue

        stats = analisar_assunto(qs)
        assuntos_stats[assunto] = stats

        slug     = slugify(assunto)
        caminho  = pasta / f"{slug}.md"
        conteudo = gerar_md_assunto(assunto, qs, materia)

        with open(caminho, "w", encoding="utf-8") as f:
            f.write(conteudo)

        tamanho_kb = caminho.stat().st_size / 1024
        print(f"  {assunto:<58} {len(qs):>5}  {slug}.md ({tamanho_kb:.0f} KB)")
        gerados += 1

    # Índice
    if args.indice:
        idx_path = pasta / "indice.md"
        with open(idx_path, "w", encoding="utf-8") as f:
            f.write(gerar_indice(assuntos_stats, materia, pasta))
        print(f"\n  Índice: {idx_path}")

    # Relatório
    total_q = sum(s['total'] for s in assuntos_stats.values())
    tamanho_total = sum(f.stat().st_size for f in pasta.glob("*.md")) / 1024

    print(f"\n{'='*60}")
    print(f"RELATÓRIO — ETAPA NLM")
    print(f"{'='*60}")
    print(f"Arquivos gerados:   {gerados}")
    print(f"Assuntos ignorados: {ignorados} (< {args.min_questoes} questão)")
    print(f"Questões cobertas:  {total_q}/{len(questoes)}")
    print(f"Tamanho total:      {tamanho_total:.0f} KB")
    print(f"Pasta:              {pasta.resolve()}")
    print(f"{'='*60}")
    print()
    if gerados <= 50:
        print(f"✅ {gerados} arquivos — dentro do limite do NotebookLM (50 fontes/caderno).")
    else:
        print(f"⚠️  {gerados} arquivos — acima do limite do NotebookLM (50 fontes/caderno).")
        print("   Considere usar --min-questoes para reduzir o número de arquivos.")


if __name__ == "__main__":
    main()