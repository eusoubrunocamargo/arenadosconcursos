#!/usr/bin/env python3
"""
Etapa 2 - Enriquecimento via API REST do TEC.

Consome a API do caderno sequencialmente (posicao 1 ate N),
cruza cada questao com o mapa de gabaritos da Etapa 1,
e produz o dataset bruto enriquecido para a Etapa 3 (sanitizador).

Uso basico:
    python scraper_api.py \
        --gabaritos gabaritos_linguaportuguesa.json \
        --caderno   90331308 \
        --total     5411 \
        --cookies   cookies.json \
        --saida     dataset_bruto_linguaportuguesa.json

Modo de validacao (primeiras 20 questoes):
    python scraper_api.py ... --limite 20

Modo de diagnostico (inspeciona estrutura da resposta da API):
    python scraper_api.py ... --debug

Retomada automatica:
    Se o arquivo de saida ja existe, o script detecta o progresso
    anterior e retoma da posicao seguinte a ultima salva.

Dependencias:
    pip install requests
"""

import json
import time
import random
import argparse
from pathlib import Path

try:
    import requests
    import urllib3
    # verify=False e necessario em ambientes Windows com antivirus ou proxy
    # que fazem inspecao SSL (MITM). Para scraping local isso e aceitavel.
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    SSL_VERIFY = False
except ImportError:
    raise SystemExit("Instale o requests: pip install requests")


# =============================================================================
# CONFIGURACAO
# =============================================================================

API_URL = "https://www.tecconcursos.com.br/api/cadernos/{caderno}/questoes/{posicao}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept":  "application/json, text/plain, */*",
    "Referer": "https://www.tecconcursos.com.br/",
}

INTERVALO_MIN = 0.8
INTERVALO_MAX = 1.3
CHECKPOINT_A_CADA = 50


# =============================================================================
# COOKIES
# =============================================================================

def carregar_cookies(caminho):
    """
    Le o arquivo JSON exportado pela extensao 'Cookie-Editor' do Chrome.
    Converte lista de objetos para dicionario simples {name: value}.
    """
    with open(caminho, encoding="utf-8") as f:
        lista = json.load(f)
    return {c["name"]: c["value"] for c in lista}


# =============================================================================
# CHECKPOINT
# =============================================================================

def carregar_checkpoint(caminho_saida):
    """
    Se o arquivo de saida ja existe, recarrega progresso anterior.
    Retorna (mapa_resultados, ultima_posicao_salva).
    """
    path = Path(caminho_saida)
    if not path.exists():
        return {}, 0

    with open(path, encoding="utf-8") as f:
        lista = json.load(f)

    if not lista:
        return {}, 0

    mapa = {str(q["id_tec"]): q for q in lista}
    ultima_pos = max(q.get("_posicao_caderno", 0) for q in lista)
    print(f"   Checkpoint encontrado: {len(mapa)} questoes salvas.")
    print(f"   Retomando a partir da posicao {ultima_pos + 1}.\n")
    return mapa, ultima_pos


def salvar(mapa, caminho):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(list(mapa.values()), f, ensure_ascii=False, indent=2)


# =============================================================================
# BUSCA E NORMALIZACAO
# =============================================================================

def fazer_request(session, caderno, posicao):
    """Faz GET para uma posicao do caderno. Retorna JSON bruto ou None."""
    url = API_URL.format(caderno=caderno, posicao=posicao)
    try:
        resp = session.get(
            url,
            params={"atualizarCronometro": "false"},
            timeout=20,
            verify=SSL_VERIFY,
        )
    except requests.RequestException as e:
        print(f"   [pos {posicao}] Erro de rede: {e}")
        return None

    if resp.status_code == 401:
        raise SystemExit(
            "\n Sessao expirada (HTTP 401). "
            "Faca login no TEC, exporte os cookies novamente e reexecute."
        )
    if resp.status_code == 404:
        print(f"   [pos {posicao}] HTTP 404 - fim do caderno.")
        return None
    if resp.status_code != 200:
        print(f"   [pos {posicao}] HTTP {resp.status_code} inesperado. Pulando.")
        return None

    return resp.json()


def extrair_questao(resposta_bruta):
    """
    A API pode retornar o objeto da questao de duas formas:
      - Diretamente: {"idQuestao": 123, ...}
      - Encapsulado: {"questao": {"idQuestao": 123, ...}, ...}

    Esta funcao normaliza os dois casos, retornando sempre o objeto
    que contem 'idQuestao'. Retorna None se nao encontrar.
    """
    if not isinstance(resposta_bruta, dict):
        return None

    # Caso direto
    if "idQuestao" in resposta_bruta:
        return resposta_bruta

    # Caso encapsulado: procura 'idQuestao' um nivel abaixo
    for chave, valor in resposta_bruta.items():
        if isinstance(valor, dict) and "idQuestao" in valor:
            return valor

    return None


def montar_objeto(tec, gabarito, posicao):
    """
    Combina dados da API com o gabarito do PDF.

    ATENCAO - 'enunciado_tec_html':
        O campo 'enunciado' do TEC contem TODO o corpo da questao
        (texto de apoio + comando + afirmacao misturados).
        Renomeamos para deixar explicito que e a ENTRADA do sanitizador.
        A Etapa 3 vai decompor em:
          texto_apoio_html/texto | comando_html/texto | enunciado_html/texto
    """
    return {
        "id_tec":             str(tec["idQuestao"]),
        "link_tec":           f"https://www.tecconcursos.com.br/questoes/{tec['idQuestao']}",
        "_posicao_caderno":   posicao,      # campo interno; removido pelo sanitizador
        "gabarito":           gabarito,     # vem do PDF (Etapa 1)
        "enunciado_tec_html": tec.get("enunciado", ""),
        "nome_materia":       tec.get("nomeMateria",          ""),
        "nome_assunto":       tec.get("nomeAssunto",          ""),
        "banca_sigla":        tec.get("bancaSigla",           ""),
        "orgao_sigla":        tec.get("orgaoSigla",           ""),
        "orgao_nome":         tec.get("orgaoNome",            ""),
        "cargo_sigla":        tec.get("cargoSigla",           ""),
        "concurso_area":      tec.get("concursoArea",         ""),
        "concurso_ano":       tec.get("concursoAno"),
        "logotipo_orgao":     tec.get("caminhoLogotipoOrgao", ""),
        "data_publicacao":    tec.get("dataPublicacao", {}).get("$", ""),
    }


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Etapa 2 - Scraper via API REST do TEC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--gabaritos", required=True)
    parser.add_argument("--caderno",   required=True)
    parser.add_argument("--total",     required=True, type=int)
    parser.add_argument("--cookies",   required=True)
    parser.add_argument("--saida",     required=True)
    parser.add_argument("--limite",    type=int, default=0,
                        help="Limita as primeiras N questoes (0 = sem limite)")
    parser.add_argument("--debug",     action="store_true",
                        help="Inspeciona estrutura da API na posicao 1 e encerra")
    args = parser.parse_args()

    # Sessao autenticada (usada em todos os modos)
    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(carregar_cookies(args.cookies))

    # ------------------------------------------------------------------
    # MODO DEBUG - fundamental para diagnosticar estrutura da resposta
    # ------------------------------------------------------------------
    if args.debug:
        print("=== MODO DEBUG: estrutura da resposta da API ===\n")
        bruto = fazer_request(session, args.caderno, 1)

        if bruto is None:
            print("Nenhuma resposta. Verifique cookies e ID do caderno.")
            return

        print(f"Tipo da resposta: {type(bruto).__name__}")
        print(f"\nChaves de nivel raiz:")
        if isinstance(bruto, dict):
            for k, v in bruto.items():
                preview = str(v)[:100].replace("\n", " ")
                print(f"  '{k}' ({type(v).__name__}): {preview}")
        else:
            print(f"  Nao e um dict: {str(bruto)[:300]}")

        print(f"\n--- Tentando extrair idQuestao ---")
        questao = extrair_questao(bruto)
        if questao:
            print(f"  idQuestao:   {questao.get('idQuestao')}")
            print(f"  nomeMateria: {questao.get('nomeMateria')}")
            print(f"  bancaSigla:  {questao.get('bancaSigla')}")
            print(f"  concursoAno: {questao.get('concursoAno')}")
            preview = str(questao.get('enunciado', ''))[:120].replace("\n", " ")
            print(f"  enunciado:   {preview}")
        else:
            print("  FALHA: 'idQuestao' nao encontrado.")
            print(f"  Resposta completa:\n{str(bruto)[:1000]}")
        return

    # ------------------------------------------------------------------
    # MODO NORMAL - carrega gabaritos e executa o loop de captura
    # ------------------------------------------------------------------
    with open(args.gabaritos, encoding="utf-8") as f:
        gabaritos_lista = json.load(f)
    mapa_gabaritos = {str(q["id_tec"]): q["gabarito"] for q in gabaritos_lista}
    print(f"Gabaritos carregados:  {len(mapa_gabaritos)} questoes")

    resultados, ultima_pos = carregar_checkpoint(args.saida)

    pos_inicio = ultima_pos + 1
    pos_fim    = min(pos_inicio + args.limite - 1, args.total) if args.limite > 0 else args.total

    if args.limite > 0:
        print(f"Modo --limite ativo:   posicoes {pos_inicio} a {pos_fim} ({pos_fim - pos_inicio + 1} questoes)\n")
    else:
        print(f"Captura completa:      posicoes {pos_inicio} a {pos_fim}\n")

    capturadas = ignoradas = erros = 0

    for posicao in range(pos_inicio, pos_fim + 1):

        bruto = fazer_request(session, args.caderno, posicao)
        if bruto is None:
            erros += 1
            time.sleep(random.uniform(INTERVALO_MIN, INTERVALO_MAX))
            continue

        objeto_tec = extrair_questao(bruto)
        if objeto_tec is None:
            print(f"   [pos {posicao}] Estrutura inesperada. Use --debug para investigar.")
            erros += 1
            time.sleep(random.uniform(INTERVALO_MIN, INTERVALO_MAX))
            continue

        id_tec = str(objeto_tec.get("idQuestao", ""))
        if not id_tec:
            print(f"   [pos {posicao}] idQuestao ausente. Pulando.")
            erros += 1
            time.sleep(random.uniform(INTERVALO_MIN, INTERVALO_MAX))
            continue

        if id_tec not in mapa_gabaritos:
            ignoradas += 1
            print(f"   [pos {posicao}] ID {id_tec} sem gabarito no mapa. Ignorando.")
            time.sleep(random.uniform(INTERVALO_MIN, INTERVALO_MAX))
            continue

        resultados[id_tec] = montar_objeto(objeto_tec, mapa_gabaritos[id_tec], posicao)
        capturadas += 1

        if capturadas % 10 == 0 or posicao == pos_fim:
            print(f"   [pos {posicao}/{pos_fim}] {capturadas} capturadas | "
                  f"{ignoradas} ignoradas | {erros} erros")

        if capturadas % CHECKPOINT_A_CADA == 0:
            salvar(resultados, args.saida)
            print(f"   Checkpoint salvo ({len(resultados)} questoes)")

        time.sleep(random.uniform(INTERVALO_MIN, INTERVALO_MAX))

    salvar(resultados, args.saida)

    print(f"\n{'='*60}")
    print(f"RELATORIO DA ETAPA 2")
    print(f"{'='*60}")
    print(f"Posicoes processadas:  {pos_fim - pos_inicio + 1}")
    print(f"Questoes capturadas:   {capturadas}")
    print(f"Ignoradas (sem gab.):  {ignoradas}")
    print(f"Erros de rede/HTTP:    {erros}")
    print(f"Total no arquivo:      {len(resultados)}")
    print(f"Arquivo de saida:      {args.saida}")
    if args.limite > 0 and capturadas > 0:
        print(f"\nValidacao com --limite {args.limite} concluida.")
        print(f"Verifique '{args.saida}' antes de rodar sem --limite.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()