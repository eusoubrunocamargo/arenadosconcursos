#!/usr/bin/env python3
"""
Etapa 3 - Sanitizador do pipeline rinhadeconcurseiro.

Transforma o JSON bruto da Etapa 2 (dataset_bruto_[materia].json)
no JSON sanitizado (dataset_sanitizado_[materia].json), com estrutura
exata do schema do banco.

Responsabilidades:
  1. parse_banca()              - 'CEBRASPE (CESPE)' -> banca + variante
  2. separar_componentes()      - decompoe enunciado_tec_html em tres partes
  3. html_para_texto()          - texto puro para LLM e busca textual
  4. avaliar_qualidade()        - PERFEITA / PARCIAL / REQUER_REVISAO_MANUAL
  5. inferir_tipo_cobranca()    - heuristica de classificacao
  6. extrair_referencia_legal() - regex sobre enunciado_texto

Campos preenchidos aqui:
  Todos do schema EXCETO conceito_principal, armadilha, subconceitos,
  nivel_dificuldade, justificativa e tags (responsabilidade da Etapa 4).

NOMENCLATURA CRITICA:
  'enunciado' do TEC  = todo o corpo da questao (entrada deste script).
  'enunciado' do banco = so a afirmacao especifica (saida deste script).

Uso:
    python sanitizer.py --entrada dataset_bruto_lp.json --saida out.json
    python sanitizer.py --entrada dataset_bruto_da.json --saida out.json --limite 20

Dependencias: pip install beautifulsoup4
"""

import json
import re
import argparse
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:
    raise SystemExit("Instale: pip install beautifulsoup4")


# =============================================================================
# PADROES DE REGEX
# =============================================================================

# --- Gatilho primario ---
# Cobre todas as variacoes canonicas de "julgue o item" do CEBRASPE.
# Alternativas ordenadas do mais especifico para o mais generico.
_RE_GATILHO_PRIMARIO = re.compile(
    r'('
    r'(?:(?:acerca\s+d\w*|com\s+base\s+n\w*|com\s+rela[cç][aã]o\s+a\w*|'
    r'no\s+que\s+(?:se\s+)?refer\w*|a\s+respeito\s+d\w*|'
    r'considerando\w*\s+o\s+(?:texto|fragmento|trecho)|'
    r'em\s+rela[cç][aã]o\s+a\w*|quanto\s+a\w*)'
    r'\s*[,.]?\s*)?'
    r'julgue\s+(?:o|os|cada)\s+'
    r'(?:'
    r'(?:pr[oó]xim\w+\s+(?:item|itens))'
    r'|(?:item\s+a\s+seguir)'
    r'|(?:itens?\s+a\s+seguir)'
    r'|(?:item\s+que\s+se\s+segue)'
    r'|(?:itens?\s+(?:abaixo|subsequentes?))'
    r'|(?:seguintes?\s+itens?)'
    r'|(?:seguinte\s+item)'
    r'|(?:item)'
    r'|(?:itens?)'
    r')'
    r'\s*[.:]?)',
    re.IGNORECASE
)

# --- Gatilho typo: "julgue o seguintes item" (erro gramatical do TEC) ---
_RE_GATILHO_TYPO = re.compile(
    r'((?:acerca\s+d\w*|com\s+rela[cç][aã]o\s+a\w*|a\s+respeito\s+d\w*|'
    r'no\s+que\s+(?:se\s+)?refer\w*)?'
    r'\s*[,.]?\s*'
    r'julgue\s+o\s+seguintes?\s+item\b[^.,:]*[.,:]?)',
    re.IGNORECASE
)

# --- Gatilho de intro explicita de situacao hipotetica ---
# Cobre: "O item a seguir é/apresenta uma situação hipotética..."
#        "Em cada um do item que se seguem, é apresentada..."
_RE_INTRO_HIPOTETICA = re.compile(
    r'((?:em\s+cada\s+um\s+d\w+\s+item\w*\s+que\s+se\s+seguem|'
    r'o\s+(?:item|pr[oó]xim\w+)\s+(?:a\s+seguir|que\s+se\s+segue))\s*[,é]?\s*'
    r'(?:[eé]\s+)?apresent\w+'
    r'[^.]*?'
    r'(?:assertiva\s+a\s+ser\s+julgad\w+)?[^.]*?\.)',
    re.IGNORECASE | re.DOTALL
)

# --- Divisor de situacao hipotetica sem intro explicita ---
# "Nessa situacao [hipotetica]" inicia o enunciado; tudo antes = texto_apoio
_RE_NESSA_SITUACAO = re.compile(
    r'(nessa\s+situa[cç][aã]o\s*(?:hipot[eé]tica)?\s*[,:]?)',
    re.IGNORECASE
)

# --- Referencia legal ---
_RE_REF_LEGAL = re.compile(
    r'(art\.?\s*\d+[\w°º]*'
    r'(?:[,\s]+(?:§\s*\d+[\w°º]*|inciso\s+[IVXLC]+|par[aá]grafo\s+\w+))*'
    r'(?:\s+d[ao]?\s*'
    r'(?:Lei\s+(?:n[oº°]?\s*)?\d[\d./]*|CF(?:/\d+)?|'
    r'Constitui[cç][aã]o[^,;.]{0,40}|Decreto[^,;.]{0,40}|'
    r'C[oó]digo\s+\w+[^,;.]{0,30}))?)',
    re.IGNORECASE
)

# --- Heuristicas tipo_cobranca ---
_RE_JURISPRUDENCIA = re.compile(
    r'\bjurisprud[eê]ncia\b|stf\b|stj\b|tse\b|tcu\b|'
    r's[uú]mula\s*(?:vinculante\s*)?\d+|\bprecedente\b|\bac[oó]rd[aã]o\b',
    re.IGNORECASE
)
_RE_REF_LEI_HEUR = re.compile(
    r'\bart\.?\s*\d+|\blei\s+(?:n[oº°]?\s*)?\d+|\bdecreto\b|'
    r'\bcf/\d{2}\b|\bconstitui[cç][aã]o\b',
    re.IGNORECASE
)
_RE_DOUTRINA = re.compile(
    r'\bdoutrina\b|segundo\s+\w+|\bprofessor\b|majorit[aá]ri\w+|'
    r'minorit[aá]ri\w+|\bdoutrinador\b',
    re.IGNORECASE
)
_RE_CASO_CONCRETO = re.compile(
    r'\bsitua[cç][aã]o\s+hipot[eé]tica\b|nessa\s+situa[cç][aã]o\b|'
    r'nesse\s+caso\b|nessa\s+hip[oó]tese\b',
    re.IGNORECASE
)


# =============================================================================
# 1. PARSE DE BANCA
# =============================================================================

def parse_banca(banca_sigla):
    """'CEBRASPE (CESPE)' -> {banca: 'CEBRASPE', variante_banca: 'CESPE'}"""
    if not banca_sigla or not banca_sigla.strip():
        return {"banca": None, "variante_banca": None}
    m = re.match(r'^([^(]+?)\s*\(([^)]+)\)\s*$', banca_sigla.strip())
    if m:
        return {"banca": m.group(1).strip(), "variante_banca": m.group(2).strip()}
    return {"banca": banca_sigla.strip(), "variante_banca": None}


# =============================================================================
# 2. HTML -> TEXTO PURO
# =============================================================================

def html_para_texto(html):
    """Converte HTML rico para texto puro normalizado (para LLM e busca)."""
    if not html:
        return None
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["p", "br", "li", "article", "div", "h1", "h2", "h3"]):
        tag.insert_before("\n")
    texto = soup.get_text(" ")
    texto = re.sub(r'[ \t]+', ' ', texto)
    texto = re.sub(r'\n[ \t]+', '\n', texto)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    texto = texto.replace('\xa0', ' ').strip()
    return texto if texto else None


# =============================================================================
# 3. SEPARACAO TERNARIA
# =============================================================================

def separar_componentes(html):
    """
    Decompoe enunciado_tec_html em:
      texto_apoio_html/texto | comando_html/texto | enunciado_html/texto

    Cinco padroes tratados, em ordem de prioridade:
      A. <article class='textoassociado'>  — marcador explicito do TEC
      B. Gatilho primario canonico         — 'julgue o item a seguir'
      C. Gatilho com typo                  — 'julgue o seguintes item'
      D. Intro explicita de hipotetica     — 'O item a seguir é apresentada...'
      E. Divisor 'Nessa situacao'          — caso hipotetico sem intro
      F. Fallback                          — REQUER_REVISAO_MANUAL
    """
    if not html or not html.strip():
        return _fallback(html, "html_vazio")

    soup = BeautifulSoup(html, "html.parser")

    # Deteccao de imagem
    img     = soup.find("img")
    tem_img = img is not None
    img_url = img.get("src") if img else None

    # =========================================================
    # A. <article class="textoassociado">
    # =========================================================
    article = soup.find("article", class_=re.compile(r"textoassociado", re.I))
    if article:
        apoio_html = _limpar(str(article))
        article.decompose()
        for p in soup.find_all("p", class_="container-textoassociado"):
            p.decompose()
        cmd_html, enum_html = _dividir_pelo_gatilho(soup.decode_contents())
        if not enum_html:
            return _fallback(html, "article_sem_enum")
        return _resultado(apoio_html, cmd_html, enum_html, tem_img, img_url, "article")

    texto = html_para_texto(html) or ""

    # =========================================================
    # B. Gatilho primario canonico
    # =========================================================
    m = _RE_GATILHO_PRIMARIO.search(texto)
    if m:
        return _construir_a_partir_do_gatilho(html, texto, m, tem_img, img_url, "primario")

    # =========================================================
    # C. Gatilho com typo ("julgue o seguintes item")
    # =========================================================
    m = _RE_GATILHO_TYPO.search(texto)
    if m:
        return _construir_a_partir_do_gatilho(html, texto, m, tem_img, img_url, "typo")

    # =========================================================
    # D. Intro explicita de situacao hipotetica
    #    "O item a seguir é/apresenta uma situação hipotética..."
    #    "Em cada um do item que se seguem, é apresentada..."
    # =========================================================
    m = _RE_INTRO_HIPOTETICA.search(texto)
    if m:
        cmd_txt   = m.group(0).strip()
        enum_txt  = texto[m.end():].strip()
        enum_txt  = re.sub(r'^[\s.,;:]+', '', enum_txt).strip()
        return _resultado(
            None,
            f"<p>{cmd_txt}</p>",
            f"<p>{enum_txt}</p>",
            tem_img, img_url, "intro_hipotetica"
        )

    # =========================================================
    # E. Divisor "Nessa situacao [hipotetica]" — sem intro
    # =========================================================
    m = _RE_NESSA_SITUACAO.search(texto)
    if m:
        apoio_txt = texto[:m.start()].strip()
        enum_txt  = texto[m.start():].strip()
        apoio_html = _reconstruir_apoio(html, apoio_txt) if len(apoio_txt) > 40 else None
        return _resultado(
            apoio_html,
            None,
            f"<p>{enum_txt}</p>",
            tem_img, img_url, "nessa_situacao"
        )

    # =========================================================
    # F. Fallback
    # =========================================================
    return _fallback(html, "sem_gatilho")


# --- Auxiliares internos ---

def _construir_a_partir_do_gatilho(html, texto, m, tem_img, img_url, padrao):
    antes    = texto[:m.start()].strip()
    cmd_txt  = m.group(0).strip()
    enum_txt = re.sub(r'^[\s.,;:]+', '', texto[m.end():]).strip()
    tem_apoio  = len(antes) > 80
    apoio_html = _reconstruir_apoio(html, antes) if tem_apoio else None
    return _resultado(
        apoio_html,
        f"<p>{cmd_txt}</p>",
        f"<p>{enum_txt}</p>",
        tem_img, img_url,
        padrao + ("+apoio" if tem_apoio else "")
    )


def _dividir_pelo_gatilho(html):
    texto = html_para_texto(html) or ""
    for regex in (_RE_GATILHO_PRIMARIO, _RE_GATILHO_TYPO):
        m = regex.search(texto)
        if m:
            cmd_txt  = m.group(0).strip()
            enum_txt = re.sub(r'^[\s.,;:]+', '', texto[m.end():]).strip()
            return f"<p>{cmd_txt}</p>", f"<p>{enum_txt}</p>"
    return html, ""


def _reconstruir_apoio(html_orig, texto_apoio):
    soup   = BeautifulSoup(html_orig, "html.parser")
    blocos = [
        _limpar(str(tag)) for tag in soup.find_all("p")
        if (txt := tag.get_text(" ", strip=True).replace('\xa0', ' ')) and txt in texto_apoio
    ]
    if blocos:
        return "".join(blocos)
    return "<p>" + "</p><p>".join(
        p.strip() for p in texto_apoio.split("\n") if p.strip()
    ) + "</p>"


def _limpar(html):
    """Remove atributos internos do TEC sem valor semantico."""
    html = re.sub(r'\s+hash="[^"]*"', '', html)
    html = re.sub(r'\s+id="0\d+Q-[^"]*"', '', html)
    return html.strip()


def _resultado(apoio_html, cmd_html, enum_html, tem_img, img_url, padrao):
    return {
        "texto_apoio_html":  apoio_html,
        "texto_apoio_texto": html_para_texto(apoio_html),
        "comando_html":      cmd_html,
        "comando_texto":     html_para_texto(cmd_html),
        "enunciado_html":    enum_html,
        "enunciado_texto":   html_para_texto(enum_html),
        "tem_imagem":        tem_img,
        "imagem_url_tec":    img_url,
        "_padrao":           padrao,
    }


def _fallback(html, motivo):
    return {
        "texto_apoio_html":  None,
        "texto_apoio_texto": None,
        "comando_html":      None,
        "comando_texto":     None,
        "enunciado_html":    html or None,
        "enunciado_texto":   html_para_texto(html),
        "tem_imagem":        False,
        "imagem_url_tec":    None,
        "_padrao":           f"fallback:{motivo}",
    }


# =============================================================================
# 4. AVALIACAO DE QUALIDADE
# =============================================================================

def avaliar_qualidade(comp):
    if comp["_padrao"].startswith("fallback"):
        return "REQUER_REVISAO_MANUAL"
    enum_txt = (comp.get("enunciado_texto") or "").strip()
    cmd_txt  = (comp.get("comando_texto")   or "").strip()
    if not enum_txt or len(enum_txt.split()) < 5:
        return "REQUER_REVISAO_MANUAL"
    if len(enum_txt) < 20:
        return "PARCIAL"
    if cmd_txt and len(cmd_txt) > 400:
        return "PARCIAL"
    return "PERFEITA"


# =============================================================================
# 5. TIPO DE COBRANCA
# =============================================================================

def inferir_tipo_cobranca(comp):
    if comp.get("texto_apoio_html"):
        return "INTERPRETACAO_TEXTUAL"
    ref = " ".join(filter(None, [comp.get("comando_texto"), comp.get("enunciado_texto")]))
    if _RE_CASO_CONCRETO.search(ref):  return "CASO_CONCRETO"
    if _RE_JURISPRUDENCIA.search(ref): return "JURISPRUDENCIA"
    if _RE_REF_LEI_HEUR.search(ref):  return "LITERALIDADE_LEI"
    if _RE_DOUTRINA.search(ref):       return "DOUTRINA"
    return "DOUTRINA"


# =============================================================================
# 6. REFERENCIA LEGAL
# =============================================================================

def extrair_referencia_legal(texto):
    if not texto:
        return None
    m = _RE_REF_LEGAL.search(texto)
    return m.group(0).strip() if m else None


# =============================================================================
# MONTAGEM DO OBJETO FINAL
# =============================================================================

def sanitizar(bruto):
    banca_info = parse_banca(bruto.get("banca_sigla", ""))
    comp       = separar_componentes(bruto.get("enunciado_tec_html", ""))
    qualidade  = avaliar_qualidade(comp)
    tipo       = inferir_tipo_cobranca(comp)
    ref_legal  = extrair_referencia_legal(comp.get("enunciado_texto"))
    gabarito   = (bruto.get("gabarito") or "").upper() or None

    return {
        # Identidade
        "id_tec":            bruto.get("id_tec"),
        "link_tec":          bruto.get("link_tec"),
        # Cabecalho
        "banca":             banca_info["banca"],
        "variante_banca":    banca_info["variante_banca"],
        "ano":               bruto.get("concurso_ano"),
        "orgao_sigla":       bruto.get("orgao_sigla")   or None,
        "orgao_nome":        bruto.get("orgao_nome")    or None,
        "cargo":             bruto.get("cargo_sigla")   or None,
        "concurso_area":     bruto.get("concurso_area") or None,
        # Classificacao
        "id_materia_nome":   bruto.get("nome_materia")  or None,
        "id_assunto_nome":   bruto.get("nome_assunto")  or None,
        # Conteudo
        "texto_apoio_html":  comp["texto_apoio_html"],
        "texto_apoio_texto": comp["texto_apoio_texto"],
        "comando_html":      comp["comando_html"],
        "comando_texto":     comp["comando_texto"],
        "enunciado_html":    comp["enunciado_html"],
        "enunciado_texto":   comp["enunciado_texto"],
        # Resposta
        "gabarito":          gabarito,
        # Midia
        "tem_imagem":        comp["tem_imagem"],
        "imagem_url_tec":    comp["imagem_url_tec"],
        # Semantica automatica
        "tipo_cobranca":     tipo,
        "referencia_legal":  ref_legal,
        # Curadoria humana (Etapa 4)
        "conceito_principal": None,
        "armadilha":          None,
        "subconceitos":       [],
        "tags":               [],
        "nivel_dificuldade":  None,
        "justificativa":      None,
        # Controle
        "qualidade_extracao": qualidade,
        "ativo":              False,
        "data_publicacao":    bruto.get("data_publicacao") or None,
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Etapa 3 - Sanitizador rinhadeconcurseiro",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--entrada", required=True)
    parser.add_argument("--saida",   required=True)
    parser.add_argument("--limite",  type=int, default=0,
                        help="Processa apenas os primeiros N registros (0 = todos)")
    args = parser.parse_args()

    if not Path(args.entrada).exists():
        raise SystemExit(f"Arquivo nao encontrado: {args.entrada}")

    with open(args.entrada, encoding="utf-8") as f:
        brutos = json.load(f)

    if args.limite > 0:
        brutos = brutos[:args.limite]
        print(f"Modo --limite: {len(brutos)} registros.\n")

    resultados = []
    contadores = {}
    padroes    = {}
    tipos      = {}

    for bruto in brutos:
        obj  = sanitizar(bruto)
        comp = separar_componentes(bruto.get("enunciado_tec_html", ""))
        resultados.append(obj)
        q = obj["qualidade_extracao"]
        contadores[q] = contadores.get(q, 0) + 1
        p = comp["_padrao"]
        padroes[p] = padroes.get(p, 0) + 1
        t = obj["tipo_cobranca"]
        tipos[t] = tipos.get(t, 0) + 1

    with open(args.saida, "w", encoding="utf-8") as f:
        json.dump(resultados, f, ensure_ascii=False, indent=2)

    total = len(resultados)
    print(f"{'='*60}")
    print(f"RELATORIO DA ETAPA 3 - SANITIZACAO")
    print(f"{'='*60}")
    print(f"Registros:               {total}")
    print()
    print("QUALIDADE:")
    for k, v in sorted(contadores.items()):
        print(f"  {k:25s} {v:5d}  ({v/total*100:.1f}%)")
    print()
    print("PADROES ESTRUTURAIS:")
    for k, v in sorted(padroes.items(), key=lambda x: -x[1]):
        print(f"  {k:35s} {v:5d}  ({v/total*100:.1f}%)")
    print()
    print("TIPOS DE COBRANCA:")
    for k, v in sorted(tipos.items(), key=lambda x: -x[1]):
        print(f"  {k:25s} {v:5d}  ({v/total*100:.1f}%)")
    print()
    print(f"Saida: {args.saida}")
    print(f"{'='*60}\n")
    requer = contadores.get("REQUER_REVISAO_MANUAL", 0)
    if requer:
        print(f"  {requer} questao(oes) REQUER_REVISAO_MANUAL -> dashboard Etapa 4.\n")


if __name__ == "__main__":
    main()