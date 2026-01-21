import os
import time
import json
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ================= CONFIGURAÇÃO =================
# URL do Caderno (Comece na Questão 1)
URL_CADERNO = "https://www.tecconcursos.com.br/questoes/cadernos/86161349" 
ARQUIVO_SAIDA = "raciocinio_web_amostra_30.json"
LIMITE_TESTE = 30  # TRAVA DE SEGURANÇA PARA O TESTE

# Correção SSL
os.environ['WDM_SSL_VERIFY'] = '0'
# ================================================

def limpar_texto(texto):
    if not texto: return ""
    return re.sub(r'\n{3,}', '\n\n', texto).strip()

def extrair_id_tec_do_html(soup):
    """
    Busca o ID real da questão nos links internos do HTML (ex: href='/questoes/123456')
    Isso é vital para cruzar com o PDF depois.
    """
    # Tenta achar link de 'Estatísticas', 'Comentários' ou 'Resolver'
    links = soup.find_all("a", href=re.compile(r"/questoes/\d+"))
    for link in links:
        match = re.search(r"/questoes/(\d+)", link['href'])
        if match:
            return match.group(1)
    return None

def processar_conteudo_rico(html_content, seq_interna):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Localiza o Texto
    enunciado_div = soup.find("div", class_="questao-enunciado-texto")
    if not enunciado_div:
        enunciado_div = soup.find("div", class_="questao-conteudo")
    
    if not enunciado_div: return None

    # 2. Resgata o ID Real (Chave de Segurança)
    id_tec_real = extrair_id_tec_do_html(soup)

    # 3. LaTeX (MathJax) -> $$...$$
    tem_latex = False
    for script in enunciado_div.find_all("script", type="math/tex"):
        tem_latex = True
        script.replace_with(f" $${script.get_text()}$$ ")
    
    # Limpa lixo visual do MathJax
    for tag in enunciado_div.find_all(class_=["MathJax_Preview", "MathJax"]):
        tag.decompose()

    # 4. Imagens -> Markdown
    tem_imagem = False
    urls_imagens = []
    for img in enunciado_div.find_all("img"):
        src = img.get("src")
        if src and "icon" not in src and "spinner" not in src:
            tem_imagem = True
            urls_imagens.append(src)
            img.replace_with(f"\n![Imagem]({src})\n")

    # 5. Texto Limpo
    texto_rico = limpar_texto(enunciado_div.get_text(separator="\n"))

    return {
        "numero": seq_interna,       # 1 a 30
        "id_tec_html": id_tec_real,  # Ex: 219384 (Para JOIN com PDF)
        "comando_rico": texto_rico,  # Texto com LaTeX e Imagens
        "imagens_urls": urls_imagens,
        "tem_latex": tem_latex,
        "tem_imagem": tem_imagem
    }

def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    
    try:
        path = ChromeDriverManager().install()
    except:
        path = "chromedriver.exe"
    service = Service(path)
    driver = webdriver.Chrome(service=service, options=options)
    
    coletados = []
    
    try:
        print(f"--- PILOTO: EXTRAÇÃO DE {LIMITE_TESTE} QUESTÕES ---")
        driver.get("https://www.tecconcursos.com.br/entrar")
        print("1. Realize o Login e resolva o Captcha.")
        print("2. Aguarde carregar a Home.")
        input(">>> Pressione ENTER para iniciar...")
        
        print(f"Acedendo ao caderno: {URL_CADERNO}")
        driver.get(URL_CADERNO)
        time.sleep(5)
        
        contador = 1
        
        while contador <= LIMITE_TESTE:
            # Scroll e Wait (Fundamental para LaTeX)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2.5) 
            
            html = driver.page_source
            dados = processar_conteudo_rico(html, contador)
            
            if dados:
                coletados.append(dados)
                print(f"Q.{contador:02d} | ID TEC: {dados['id_tec_html']} | LaTeX: {dados['tem_latex']}")
            else:
                print(f"Q.{contador:02d} ❌ Erro ao ler HTML")
                coletados.append({"numero": contador, "erro": True})

            # Se chegamos ao limite, paramos antes de clicar no próximo
            if contador == LIMITE_TESTE:
                print("Limite de teste alcançado.")
                break

            # Próxima Página
            try:
                btn = driver.find_element(By.CSS_SELECTOR, "button.questao-navegacao-botao-proxima")
                if not btn.is_enabled(): break
                btn.click()
                contador += 1
            except Exception:
                print("Botão Próximo não encontrado.")
                break

        # Final
        with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
            json.dump(coletados, f, indent=4, ensure_ascii=False)
        print(f"\nSucesso! Amostra salva em: {ARQUIVO_SAIDA}")

    except Exception as e:
        print(f"Erro fatal: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()