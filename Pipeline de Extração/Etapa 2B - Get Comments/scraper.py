#!/usr/bin/env python3
"""
Etapa 2b - Scraper de comentarios do TEC.

Para cada questao do dataset bruto, busca dois recursos distintos:
  1. Comentario do professor (/api/questoes/{id}/comentario)
  2. Comentarios dos alunos, ordenados por votos (/api/discussoes/{id}/comentarios-alunos)

O resultado e um JSON paralelo ao dataset bruto, indexado por id_tec,
com a estrutura:
  {
    "id_tec": "474260",
    "comentario_professor": {
      "nome_professor": "Cyonil Borges",
      "texto_html": "<p>O item está CERTO...</p>",
      "texto_puro": "O item está CERTO. Aplica-se aqui...",
      "data_publicacao": "18/06/2017"
    },
    "comentarios_alunos": [
      {
        "apelido": "RPHL",
        "votos": 67,
        "texto": "Teoria dos motivos determinantes...",
        "professor": false,
        "data": "14/06/2017"
      },
      ...  (top 3 por votos, apenas com votos > 0)
    ]
  }

Esse JSON e consumido pelo gerador de justificativas (Etapa 2c)
como contexto para a LLM, nunca diretamente como justificativa final.

Endpoints:
  Professor: GET /api/questoes/{id_questao}/comentario
  Alunos:    GET /api/discussoes/{id_questao}/comentarios-alunos
                 ?ordenarPor=pontos&pagina=1

Uso:
    python scraper_comentarios.py \\
        --entrada dataset_bruto_linguaportuguesa.json \\
        --cookies cookies.json \\
        --saida   comentarios_linguaportuguesa.json

    python scraper_comentarios.py ... --limite 20   # validacao
    python scraper_comentarios.py ... --apenas-prof # so comentario do professor

Dependencias: pip install requests
"""

import json
import time
import random
import argparse
import smtplib
from email.mime.text import MIMEText
from pathlib import Path
from bs4 import BeautifulSoup

try:
    import requests
    import urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    SSL_VERIFY = False
except ImportError:
    raise SystemExit("Instale: pip install requests")


# =============================================================================
# CONFIGURACAO
# =============================================================================

BASE = "https://www.tecconcursos.com.br"
URL_PROFESSOR = BASE + "/api/questoes/{id}/comentario"
URL_ALUNOS    = BASE + "/api/discussoes/{id}/comentarios-alunos"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
    "Accept":           "application/json, text/plain, */*",
    "Accept-Language":  "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin":           "https://www.tecconcursos.com.br",
    # Fetch Metadata — presentes em toda requisicao XHR/fetch de browser real.
    # O TEC provavelmente passou a exigir esses headers para distinguir
    # scraping de navegacao legítima (causa do HTTP 405).
    "X-Requested-With": "XMLHttpRequest",
    "Sec-Ch-Ua":        '"Chromium";v="146", "Not.A.Brand";v="24", "Google Chrome";v="146"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Site":   "same-origin",
    "Sec-Fetch-Mode":   "cors",
    "Sec-Fetch-Dest":   "empty",
}

# Intervalos separados por endpoint:
# - Endpoint de professor (/api/questoes/) tem rate limit agressivo (~17 req/sessao).
#   Sleep longo reduz a taxa de acesso e evita o throttle ao longo do run completo.
# - Endpoint de alunos (/api/discussoes/) nao tem rate limit observado.
#   Sleep curto para nao aumentar desnecessariamente o tempo total.
INTERVALO_PROF_MIN  = 4.5   # segundos apos GET de professor
INTERVALO_PROF_MAX  = 8.0
INTERVALO_ALUNO_MIN = 0.5   # segundos apos GET de alunos
INTERVALO_ALUNO_MAX = 1.2
CHECKPOINT_A_CADA = 100
TOP_ALUNOS = 3      # quantos comentarios de alunos preservar


# =============================================================================
# COOKIES
# =============================================================================

def caminho_session_cookies(caminho_saida):
    """Arquivo de cookies de sessao ao lado do arquivo de saida principal."""
    p = Path(caminho_saida)
    return str(p.parent / (p.stem + "_session_cookies.json"))


def carregar_cookies(caminho_cookies, caminho_saida=None):
    """
    Carrega cookies na seguinte ordem de prioridade:
      1. Cookies de sessao persistidos pelo run anterior (session_cookies.json)
         → contém AWSALB/JSESSIONID atualizados pela ultima resposta do servidor
      2. Cookies exportados do Chrome (arquivo original)
         → usado apenas se nao houver sessao persistida

    Essa estrategia resolve o problema de AWSALB rotacionado:
    o servidor emite um novo AWSALB a cada resposta. O Session() o captura
    durante o run, mas um novo run sem esse arquivo recomeçaria com o AWSALB
    antigo, causando 405 apos N requisicoes.
    """
    # Tenta carregar cookies de sessao persistidos primeiro
    if caminho_saida:
        path_session = caminho_session_cookies(caminho_saida)
        if Path(path_session).exists():
            with open(path_session, encoding="utf-8") as f:
                cookies_session = json.load(f)
            print(f"   Cookies de sessao carregados: {path_session}")
            return cookies_session

    # Fallback: cookies originais exportados do Chrome
    with open(caminho_cookies, encoding="utf-8") as f:
        lista = json.load(f)
    return {c["name"]: c["value"] for c in lista}


def persistir_session_cookies(session, caminho_saida):
    """
    Grava os cookies atuais da sessao HTTP em disco.
    Chamado a cada checkpoint — garante que AWSALB e JSESSIONID
    atualizados pelo servidor sejam reutilizados no proximo run.

    Usa get_dict() em vez de dict() para evitar CookieConflictError:
    quando o servidor emite um novo AWSALB, o jar fica com dois valores
    para o mesmo nome. get_dict() resolve silenciosamente mantendo o
    mais recente (ultimo a ser inserido no jar).
    """
    cookies_atuais = session.cookies.get_dict()
    path_session = caminho_session_cookies(caminho_saida)
    with open(path_session, "w", encoding="utf-8") as f:
        json.dump(cookies_atuais, f, ensure_ascii=False, indent=2)


# =============================================================================
# CHECKPOINT
# =============================================================================

def carregar_checkpoint(caminho_saida):
    path = Path(caminho_saida)
    if not path.exists():
        return {}, set()
    with open(path, encoding="utf-8") as f:
        lista = json.load(f)
    mapa = {q["id_tec"]: q for q in lista}

    # Ids com erro de servidor NAO entram em ids_prontos:
    # serao reprocessados no proximo run automaticamente.
    ids_prontos    = {k for k, v in mapa.items() if not v.get("_erro_http")}
    ids_com_erro   = {k for k, v in mapa.items() if v.get("_erro_http")}

    print(f"   Checkpoint: {len(ids_prontos)} prontos | "
          f"{len(ids_com_erro)} com erro HTTP (serao reprocessados).")
    return mapa, ids_prontos


def salvar(mapa, caminho):
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(list(mapa.values()), f, ensure_ascii=False, indent=2)


# =============================================================================
# PARSE DE COMENTARIOS
# =============================================================================

def html_para_texto(html):
    """
    Converte HTML do comentario do PROFESSOR para texto puro.
    O comentario do professor usa sempre HTML fragmento (<p>, <blockquote>).
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["p", "br", "li", "blockquote", "h1", "h2", "h3"]):
        tag.insert_before("\n")
    texto = soup.get_text(" ")
    texto = " ".join(texto.split())
    return texto.replace('\xa0', ' ').strip()


def html_para_texto_robusto(texto_raw):
    """
    Converte comentario de ALUNO para texto puro.
    Trata tres formatos distintos encontrados na API do TEC:

      1. HTML completo: <html><head></head><body>...</body></html>
         Formato novo, usado em questoes recentes. O BeautifulSoup
         extrai o conteudo do <body> descartando o wrapper.

      2. HTML fragmento: <p>texto</p> ou <strong>texto</strong>
         Formato antigo, sem wrapper <html>.

      3. Texto puro: ja limpo, sem nenhuma tag.
         Passado diretamente sem processamento.

    Todos os tres casos resultam em texto limpo, sem tags residuais.
    """
    if not texto_raw or not texto_raw.strip():
        return ""
    txt = texto_raw.strip()
    # Detecta qualquer forma de HTML (completo ou fragmento)
    if txt.startswith('<') or '<html' in txt.lower() or '<p' in txt.lower():
        soup = BeautifulSoup(txt, "html.parser")
        for tag in soup.find_all(["p", "br", "li", "h1", "h2", "h3", "div", "blockquote"]):
            tag.insert_before("\n")
        texto = soup.get_text(" ")
        texto = " ".join(texto.split())
        return texto.replace('\xa0', ' ').strip()
    return txt


def parse_comentario_professor(resp_json):
    """
    Extrai o comentario do professor da resposta da API.
    Retorna None se a questao nao tiver comentario de professor.
    """
    if not resp_json or not isinstance(resp_json, dict):
        return None

    # A API retorna diretamente o objeto ou encapsulado em 'comentario'
    obj = resp_json
    if "comentario" in resp_json and isinstance(resp_json["comentario"], dict):
        obj = resp_json["comentario"]

    texto_html = obj.get("textoComentario", "")
    if not texto_html or not texto_html.strip():
        return None

    return {
        "nome_professor":  obj.get("nomeProfessor", ""),
        "url_professor":   obj.get("urlProfessor", ""),
        "texto_html":      texto_html,
        "texto_puro":      html_para_texto(texto_html),
        "data_publicacao": obj.get("dataPublicacaoComentario", ""),
    }


def parse_comentarios_alunos(resp_json):
    """
    Extrai os top comentarios de alunos (por votos, excluindo negativos).
    Descarta comentarios que sao apenas imagens, muito curtos ou irrelevantes.
    """
    if not resp_json:
        return []

    # Navega ate a lista de comentarios (estrutura aninhada da API)
    lista = []
    try:
        page = resp_json.get("comentarios", {}).get("pageComentarios", {})
        lista = page.get("list", [])
    except (AttributeError, TypeError):
        pass

    if not lista:
        return []

    resultados = []
    for c in lista:
        votos = c.get("quantidadeVoto", 0)
        if votos <= 0:
            continue

        texto_raw = c.get("comentario", "")

        # Usa html_para_texto_robusto independente do campo 'formato':
        # a API retorna HTML completo (<html>...</html>) em questoes recentes
        # mesmo quando formato == "TEXTO", tornando o campo nao confiavel.
        texto = html_para_texto_robusto(texto_raw)

        # Descarta comentarios sem texto util (so imagens, espacos, etc.)
        if not texto or len(texto) < 15:
            continue

        # Descarta comentarios que sao claramente off-topic ou reclamacoes
        # (heuristica: menos de 3 palavras apos remover pontuacao)
        palavras = [w for w in texto.split() if w.isalpha()]
        if len(palavras) < 4:
            continue

        resultados.append({
            "apelido":   c.get("apelidoUsuario", ""),
            "votos":     votos,
            "professor": c.get("professor", False),
            "texto":     texto,
            "data":      c.get("dataPublicacao", {}).get("$", ""),
        })

        if len(resultados) >= TOP_ALUNOS:
            break

    return resultados


# =============================================================================
# REQUESTS
# =============================================================================

# Sentinel: distingue "questao sem comentario" (404 legitimo) de erro de servidor.
# Armazenado no checkpoint para que o re-run reprocesse questoes com falha.
ERRO_HTTP = "__ERRO_HTTP__"

def get_json(session, url, params=None, referer=None, _tentativa=1):
    """
    GET com tratamento de erros diferenciado.

    Retorna:
      dict/list : resposta JSON valida (HTTP 200)
      None      : questao sem conteudo (HTTP 404) — situacao normal
      ERRO_HTTP : erro de servidor (HTTP 403/429/5xx) — deve ser reprocessado

    Backoff automatico:
      429 Too Many Requests : espera Retry-After (ou 60s) + jitter
      503 Service Unavailable: espera 30s + jitter, ate 3 tentativas
      403 Forbidden         : aborta imediatamente (sessao invalida)
    """
    MAX_TENTATIVAS = 3
    try:
        headers_req = {}
        if referer:
            headers_req["Referer"] = referer
        resp = session.get(url, params=params, headers=headers_req, timeout=20, verify=SSL_VERIFY)
        status = resp.status_code

        if status == 200:
            return resp.json()

        if status == 401:
            raise SystemExit("\nSessao expirada (HTTP 401). Reexporte os cookies.")

        if status == 404:
            return None  # sem comentario — comportamento normal da API

        if status == 403:
            # Sessao provavelmente invalida — nao adianta tentar de novo
            print(f"\n   ⚠ HTTP 403 em {url.split('/')[-2:]}"
                  f" — sessao pode estar expirada. Reexporte os cookies.")
            return ERRO_HTTP

        if status == 429:
            retry_after = int(resp.headers.get("Retry-After", 60))
            espera = retry_after + random.uniform(2, 8)
            print(f"\n   ⚠ HTTP 429 (rate limit). Aguardando {espera:.0f}s...")
            time.sleep(espera)
            if _tentativa < MAX_TENTATIVAS:
                return get_json(session, url, params, referer, _tentativa + 1)
            return ERRO_HTTP

        if status in (500, 502, 503, 504):
            espera = 30 + random.uniform(2, 10)
            print(f"\n   ⚠ HTTP {status}. Aguardando {espera:.0f}s (tentativa {_tentativa}/{MAX_TENTATIVAS})...")
            time.sleep(espera)
            if _tentativa < MAX_TENTATIVAS:
                return get_json(session, url, params, referer, _tentativa + 1)
            return ERRO_HTTP

        # Qualquer outro status inesperado — registra e marca para reprocessamento
        print(f"\n   ⚠ HTTP {status} inesperado em {url[-60:]}")
        return ERRO_HTTP

    except requests.RequestException as e:
        print(f"\n   ⚠ Erro de rede: {e}")
        return ERRO_HTTP


# =============================================================================
# NOTIFICACOES POR EMAIL
# =============================================================================

def enviar_email(remetente, app_password, destinatario,
                 processadas, total, com_prof, com_alunos,
                 sem_nenhum, erros_http, dataset_nome):
    """
    Envia email de progresso via Gmail SMTP com TLS.
    Requer uma App Password do Google (nao a senha da conta):
      myaccount.google.com > Seguranca > Senhas de app

    Falhas de envio sao silenciosas — nunca interrompem o processamento.
    """
    pct = processadas / max(total, 1) * 100
    assunto = (
        f"[scraper] {dataset_nome}: "
        f"{processadas}/{total} ({pct:.0f}%) — "
        f"prof={com_prof} alunos={com_alunos}"
    )
    corpo = (
        f"Progresso do scraper de comentários\n"
        f"{'='*40}\n\n"
        f"Dataset:              {dataset_nome}\n"
        f"Processadas:          {processadas} / {total} ({pct:.1f}%)\n"
        f"Com comentário prof:  {com_prof} ({com_prof/max(processadas,1)*100:.1f}%)\n"
        f"Com comentário aluno: {com_alunos} ({com_alunos/max(processadas,1)*100:.1f}%)\n"
        f"Sem nenhum:           {sem_nenhum}\n"
        f"Erros HTTP:           {erros_http}\n"
    )
    msg = MIMEText(corpo, "plain", "utf-8")
    msg["Subject"] = assunto
    msg["From"]    = remetente
    msg["To"]      = destinatario
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=15) as smtp:
            smtp.starttls()
            smtp.login(remetente, app_password)
            smtp.sendmail(remetente, [destinatario], msg.as_string())
    except Exception as e:
        print(f"   ⚠ Email nao enviado: {e}")


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Etapa 2b - Scraper de comentarios do TEC",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--entrada",     required=True,
                        help="JSON bruto da Etapa 2")
    parser.add_argument("--cookies",     required=True,
                        help="Cookies exportados do Chrome")
    parser.add_argument("--saida",       required=True,
                        help="JSON de saida com comentarios")
    parser.add_argument("--limite",      type=int, default=0,
                        help="Limita a N questoes (0 = todas)")
    parser.add_argument("--apenas-prof", action="store_true",
                        help="Busca apenas o comentario do professor (mais rapido)")
    parser.add_argument("--email-remetente", default="",
                        help="Conta Gmail remetente (ex: seuemail@gmail.com)")
    parser.add_argument("--email-app-password", default="",
                        help="App Password do Gmail (16 caracteres, sem espacos)")
    parser.add_argument("--email-dest", default="eusoubrunocamargo@gmail.com",
                        help="Destinatario dos emails de progresso")
    args = parser.parse_args()

    with open(args.entrada, encoding="utf-8") as f:
        brutos = json.load(f)

    # Nome curto do dataset para os emails (ex: "dataset_bruto_direitoadministrativo")
    dataset_nome = Path(args.entrada).stem
    notificar = bool(args.email_remetente and args.email_app_password)
    if notificar:
        print(f"   Email de progresso ativado → {args.email_dest}")
    else:
        print("   Email desativado (use --email-remetente e --email-app-password para ativar).")

    if args.limite > 0:
        brutos = brutos[:args.limite]
        print(f"Modo --limite: {len(brutos)} questoes.\n")

    mapa, ids_prontos = carregar_checkpoint(args.saida)

    session = requests.Session()
    session.headers.update(HEADERS)
    session.cookies.update(carregar_cookies(args.cookies, args.saida))

    total         = len(brutos)
    processadas   = 0
    com_prof      = 0
    com_alunos    = 0
    sem_nenhum    = 0
    erros_http    = 0

    for i, bruto in enumerate(brutos):
        id_tec = bruto.get("id_tec", "")

        if id_tec in ids_prontos:
            continue

        obj = {"id_tec": id_tec}

        # Referer dinamico: aponta para a pagina da questao atual,
        # exatamente como um browser faria ao abrir a questao e depois
        # carregar os comentarios via XHR.
        referer_questao = f"https://www.tecconcursos.com.br/questoes/{id_tec}"

        # Aquecimento: GET na pagina da questao antes dos endpoints de comentario.
        # Simula a navegacao real do usuario (abre a questao, depois ve comentarios).
        # Nao processa a resposta — serve apenas para atualizar cookies de sessao
        # e estabelecer o historico de navegacao esperado pelo servidor.
        try:
            session.get(
                referer_questao,
                headers={"Referer": "https://www.tecconcursos.com.br/questoes/lista"},
                timeout=15,
                verify=SSL_VERIFY
            )
        except Exception:
            pass  # aquecimento e best-effort, nunca bloqueia o processamento
        time.sleep(random.uniform(0.3, 0.7))

        # --- Comentario do professor ---
        resp = get_json(session, URL_PROFESSOR.format(id=id_tec),
                        referer=referer_questao)
        if resp is ERRO_HTTP:
            # Marca para reprocessamento automatico no proximo run.
            # O carregar_checkpoint() exclui entradas com _erro_http=True
            # de ids_prontos, garantindo que sejam retentadas.
            obj["comentario_professor"] = None
            obj["_erro_http"] = True
            erros_http += 1
        else:
            prof = parse_comentario_professor(resp)
            obj["comentario_professor"] = prof
            if prof:
                com_prof += 1
        # Sleep longo apos o endpoint de professor — endpoint restritivo.
        # ~6s medio reduz a taxa efetiva para ~10 req/min, abaixo do threshold.
        time.sleep(random.uniform(INTERVALO_PROF_MIN, INTERVALO_PROF_MAX))

        # --- Comentarios dos alunos (opcional) ---
        if not args.apenas_prof:
            resp_alunos = get_json(
                session,
                URL_ALUNOS.format(id=id_tec),
                params={"ordenarPor": "pontos", "pagina": 1},
                referer=referer_questao
            )
            if resp_alunos is ERRO_HTTP:
                obj["comentarios_alunos"] = []
                obj["_erro_http"] = True
                erros_http += 1
            else:
                alunos = parse_comentarios_alunos(resp_alunos)
                obj["comentarios_alunos"] = alunos
                if alunos:
                    com_alunos += 1
            # Sleep curto apos endpoint de alunos — sem rate limit observado.
            time.sleep(random.uniform(INTERVALO_ALUNO_MIN, INTERVALO_ALUNO_MAX))
        else:
            obj["comentarios_alunos"] = []

        tem_erro = obj.get("_erro_http", False)
        if not tem_erro and not obj["comentario_professor"] and not obj["comentarios_alunos"]:
            sem_nenhum += 1

        mapa[id_tec] = obj
        processadas += 1

        # Progresso
        if processadas % 50 == 0 or processadas == total:
            print(f"   [{processadas}/{total}] prof={com_prof} | "
                  f"alunos={com_alunos} | sem_nenhum={sem_nenhum} | "
                  f"erros_http={erros_http}")

        # Checkpoint: salva dados e persiste cookies de sessao atuais.
        # A persistencia do AWSALB/JSESSIONID e critica para evitar
        # que o proximo run comece com cookies desatualizados (causa do 405).
        if processadas % CHECKPOINT_A_CADA == 0:
            salvar(mapa, args.saida)
            persistir_session_cookies(session, args.saida)
            if notificar:
                enviar_email(
                    args.email_remetente, args.email_app_password,
                    args.email_dest,
                    processadas, total, com_prof, com_alunos,
                    sem_nenhum, erros_http, dataset_nome
                )

        # Nao ha sleep global aqui — os sleeps assimetricos ja foram aplicados
        # individualmente apos cada chamada de endpoint no loop acima.

    salvar(mapa, args.saida)
    persistir_session_cookies(session, args.saida)
    if notificar:
        enviar_email(
            args.email_remetente, args.email_app_password,
            args.email_dest,
            processadas, total, com_prof, com_alunos,
            sem_nenhum, erros_http, dataset_nome
        )

    # Conta erros no mapa final (inclui runs anteriores)
    total_erros_no_arquivo = sum(1 for v in mapa.values() if v.get("_erro_http"))

    print(f"\n{'='*60}")
    print(f"RELATORIO DA ETAPA 2b - COMENTARIOS")
    print(f"{'='*60}")
    print(f"Questoes processadas:    {processadas}")
    print(f"Com comentario prof:     {com_prof} ({com_prof/max(processadas,1)*100:.1f}%)")
    print(f"Com comentarios alunos:  {com_alunos} ({com_alunos/max(processadas,1)*100:.1f}%)")
    print(f"Sem nenhum comentario:   {sem_nenhum}")
    print(f"Erros HTTP (este run):   {erros_http}")
    print(f"Erros HTTP (acumulado):  {total_erros_no_arquivo}"
          f"{'  <- reprocessar na proxima execucao' if total_erros_no_arquivo else ''}")
    print(f"Arquivo de saida:        {args.saida}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()