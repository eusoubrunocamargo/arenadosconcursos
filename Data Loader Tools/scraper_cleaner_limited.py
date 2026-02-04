import json
import time
import random
import re
import os
import argparse
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
CSS_BOTAO_PROXIMA = "button.questao-navegacao-botao-proxima"
TAGS_PERMITIDAS = ['p', 'b', 'strong', 'i', 'em', 'u', 'ul', 'ol', 'li', 'br', 'img', 'table', 'tr', 'td', 'th', 'tbody', 'thead', 'span', 'div', 'article', 'h1', 'h2', 'h3', 'code', 'pre', 'blockquote']

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    # chrome_options.add_argument("--headless") 
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- FUNÇÕES DE LIMPEZA APRIMORADAS ---

def limpar_espacos_excessivos(texto):
    """
    Remove quebras de linha duplicadas e espaços em branco desnecessários.
    """
    if not texto: return ""
    texto_limpo = re.sub(r'\n\s*\n', '\n', texto)
    return texto_limpo.strip()

def sanitizar_html(html_source):
    soup = BeautifulSoup(html_source, 'html.parser')
    div_texto = soup.find('div', class_='questao-enunciado-texto')
    if not div_texto: return None

    # 1. Remove elementos de sistema/lixo
    for tag in div_texto(['script', 'style', 'button', 'input', 'form', 'noscript', 'iframe']): tag.decompose()
    for b in div_texto.find_all(class_='container-textoassociado'): b.decompose()

    # 2. LIMPEZA DE PARÁGRAFOS VAZIOS
    for p in div_texto.find_all('p'):
        conteudo = p.get_text(strip=True).replace('\xa0', '')
        if not conteudo and not p.find('img'):
            p.decompose()

    # 3. Limpeza de Atributos
    for tag in div_texto.find_all(True):
        if tag.name == 'article':
            tag.name = 'div'
            if 'collapse' in tag.get('class', []):
                tag['style'] = "display: block; border: 1px solid #ddd; padding: 10px; margin: 10px 0;"
        
        attrs_to_keep = []
        if tag.name == 'img':
            if tag.has_attr('src') and tag['src'].startswith('/'):
                tag['src'] = "https://www.tecconcursos.com.br" + tag['src']
            if tag.has_attr('ng-src'):
                tag['src'] = tag['ng-src']
                if tag['src'].startswith('/'): tag['src'] = "https://www.tecconcursos.com.br" + tag['src']
            attrs_to_keep = ['src', 'alt', 'width', 'height']
        elif tag.name == 'a': attrs_to_keep = ['href', 'target']
        elif tag.name in ['table', 'td', 'th', 'div', 'span', 'p']:
             if tag.has_attr('style'): attrs_to_keep = ['style']

        attrs = dict(tag.attrs)
        for attr in attrs:
            if attr not in attrs_to_keep: del tag[attr]

    # 4. Unwrap tags não permitidas
    for tag in div_texto.find_all(True):
        if tag.name not in TAGS_PERMITIDAS: tag.unwrap()

    html_final = div_texto.decode_contents().strip()
    html_final = re.sub(r'>\s+<', '><', html_final) 
    
    return html_final

def separar_comando_enunciado(html_completo):
    texto_puro = BeautifulSoup(html_completo, "html.parser").get_text("\n")
    gatilhos = [
        r'(julgue\s+o(s)?\s+.*?(item|itens)\s+(a\s+seguir|seguintes?|subsequentes?|próximos?|abaixo).*)',
        r'(julgue\s+o(s)?\s+(seguintes?|próximos?|subsequentes?)\s+(item|itens).*)',
        r'(julgue\s+o(s)?\s+.*?(item|itens).*)',
        r'(assinale\s+a\s+opção\s+correta.*)',
        r'(com\s+relação\s+a.*?julgue\s+o\s+item.*)'
    ]
    enunciado_extraido = ""
    match_pos = -1
    for g in gatilhos:
        iterator = re.finditer(g, texto_puro, re.IGNORECASE | re.DOTALL)
        for match in iterator:
            if match.start() > match_pos:
                match_pos = match.start()
                enunciado_extraido = match.group(0)
    
    if enunciado_extraido:
        enunciado_extraido = limpar_espacos_excessivos(enunciado_extraido)

    return html_completo, enunciado_extraido

def extrair_metadados_pagina(html_pagina):
    soup = BeautifulSoup(html_pagina, 'html.parser')
    
    # 1. ID
    id_tec = "N/A"
    tag_id = soup.find(class_='id-questao')
    if tag_id: id_tec = tag_id.get_text(strip=True).replace('#', '')
    
    # 2. MATÉRIA
    materia = "Geral"
    div_materia = soup.find('div', class_='questao-cabecalho-informacoes-materia')
    if div_materia:
        link_materia = div_materia.find('a')
        if link_materia:
            materia = link_materia.get_text(strip=True)

    # 3. ASSUNTO
    assunto = "Geral"
    div_assunto = soup.find('div', class_='questao-cabecalho-informacoes-assunto')
    if div_assunto:
        span_link = div_assunto.find('span', class_='questao-cabecalho-informacoes-assunto-link')
        if span_link:
            assunto = span_link.get_text(strip=True)

    return id_tec, materia, assunto

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("arquivo_json", help="Arquivo JSON gerado na Fase 1 (ex: gabaritos_constitucional.json)")
    parser.add_argument("--preview", action="store_true", help="Processa apenas as 10 primeiras questões para teste.")
    
    args = parser.parse_args()

    if not os.path.exists(args.arquivo_json):
        print(f"❌ Arquivo {args.arquivo_json} não encontrado.")
        return

    # 1. Carrega Mapa
    with open(args.arquivo_json, 'r', encoding='utf-8') as f:
        questoes_map = json.load(f)
    
    db_questoes = {q['id_tec']: q for q in questoes_map}
    total_questoes = len(questoes_map)
    
    # --- CONTROLE DE QUANTIDADE ---
    # Conta quantas já estão marcadas como capturadas (para o caso de retomar scraping)
    questoes_ja_capturadas = sum(1 for q in questoes_map if q.get('capturado'))
    
    print(f"--- FASE 2: ENRIQUECIMENTO (SCRAPER HÍBRIDO V3 - FINAL) ---")
    print(f"🎯 Alvo Total: {total_questoes} questões.")
    print(f"📦 Já capturadas anteriormente: {questoes_ja_capturadas}")
    
    if questoes_ja_capturadas >= total_questoes:
        print("\n✅ Todas as questões do arquivo já foram capturadas! Nada a fazer.")
        return

    if args.preview:
        print(f"🚀 MODO PREVIEW ATIVADO: Limite de 10 questões.")

    driver = init_driver()
    driver.get("https://www.tecconcursos.com.br/login")
    
    print("\n" + "="*70)
    print("🛑 INSTRUÇÕES:")
    print("1. Faça login.")
    print("2. Abra o caderno/filtro correspondente ao PDF.")
    print("3. Vá para a QUESTÃO 1 (ou a primeira que quiser capturar).")
    print("="*70)
    input("\n✅ Pressione [ENTER] quando estiver na tela da questão para iniciar...")

    capturadas_sessao = 0
    ultimo_id = None
    
    nome_saida = args.arquivo_json.replace("gabaritos_", "dataset_completo_")
    if args.preview:
        nome_saida = nome_saida.replace(".json", "_PREVIEW.json")

    try:
        while True:
            # --- CHECAGEM DE TÉRMINO ---
            # Se já pegamos todas as questões do JSON, paramos para evitar o loop do site
            if questoes_ja_capturadas >= total_questoes:
                print(f"\n🎉 Meta atingida: {questoes_ja_capturadas}/{total_questoes} questões capturadas.")
                break

            if args.preview and capturadas_sessao >= 10:
                print("\n🛑 MODO PREVIEW: Limite de 10 questões atingido.")
                break

            # 1. Identifica ID na tela
            tentativas = 0
            id_atual = "N/A"
            while tentativas < 5:
                html_pagina = driver.page_source
                id_atual, materia_atual, assunto_atual = extrair_metadados_pagina(html_pagina)
                
                if id_atual != "N/A" and id_atual != ultimo_id and materia_atual != "Geral":
                    break
                time.sleep(1)
                tentativas += 1
            
            if id_atual == "N/A":
                print("⚠️ ID não identificado. Tentando próxima...")
            
            # 2. Verifica se o ID está no nosso Mapa
            if id_atual in db_questoes:
                # Verifica se já capturamos esta específica
                foi_capturado_antes = db_questoes[id_atual].get('capturado', False)

                html_rico = sanitizar_html(driver.page_source)
                
                if html_rico:
                    cmd, enun = separar_comando_enunciado(html_rico)
                    
                    soup_img = BeautifulSoup(cmd, 'html.parser')
                    img_tag = soup_img.find('img')
                    url_img = img_tag['src'] if img_tag else ""
                    
                    db_questoes[id_atual].update({
                        "materia": materia_atual,
                        "assunto": assunto_atual,
                        "comando": cmd,
                        "enunciado": enun,
                        "imagem_url": url_img,
                        "capturado": True 
                    })
                    
                    # Se não tinha sido capturado ainda, incrementa o contador global
                    if not foi_capturado_antes:
                        questoes_ja_capturadas += 1
                    
                    capturadas_sessao += 1
                    status_img = "[IMG]" if url_img else ""
                    print(f"✅ [{capturadas_sessao}] ID {id_atual} | Progresso: {questoes_ja_capturadas}/{total_questoes} {status_img}")
                else:
                    print(f"❌ ID {id_atual}: Falha ao sanitizar HTML.")
            else:
                print(f"⏩ ID {id_atual} ignorado (não consta no PDF).")

            ultimo_id = id_atual

            # 3. Salva Parcialmente
            if capturadas_sessao % 20 == 0 and capturadas_sessao > 0:
                print(f"💾 Salvando progresso...")
                lista_final = list(db_questoes.values())
                with open(nome_saida, 'w', encoding='utf-8') as f:
                    json.dump(lista_final, f, indent=4, ensure_ascii=False)

            # 4. Navega para Próxima
            # Verifica novamente antes de clicar em proxima se já acabou
            if questoes_ja_capturadas >= total_questoes:
                print(f"\n🎉 Todas as questões capturadas! Finalizando antes de navegar.")
                break

            tempo_espera = random.uniform(1.0, 1.5)
            time.sleep(tempo_espera)

            try:
                btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, CSS_BOTAO_PROXIMA))
                )
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(1.0) 
            except:
                print("\n🏁 Fim do caderno ou botão 'Próxima' não encontrado.")
                break

    except KeyboardInterrupt:
        print("\n⚠️ Interrompido pelo usuário.")

    # Salvamento Final
    print("-" * 50)
    print("💾 Salvando arquivo final...")
    lista_final = list(db_questoes.values())
    
    total_ricos = sum(1 for q in lista_final if q.get('capturado'))
    
    with open(nome_saida, 'w', encoding='utf-8') as f:
        json.dump(lista_final, f, indent=4, ensure_ascii=False)
        
    print(f"📊 Relatório Final:")
    print(f"   Total no Arquivo: {total_questoes}")
    print(f"   Total Capturados: {total_ricos}")
    print(f"   Arquivo: {nome_saida}")
    print("-" * 50)

if __name__ == "__main__":
    main()