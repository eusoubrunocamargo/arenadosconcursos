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
URL_CADERNO = "https://www.tecconcursos.com.br/questoes/cadernos/86161349" 
ARQUIVO_WEB = "raciocinio_web_data.json"
BACKUP_INTERVALO = 50

# Correção SSL
os.environ['WDM_SSL_VERIFY'] = '0'
# ================================================

def limpar_texto(texto):
    if not texto: return ""
    return re.sub(r'\n{3,}', '\n\n', texto).strip()

def extrair_id_tec_do_html(soup):
    links = soup.find_all("a", href=re.compile(r"/questoes/\d+"))
    for link in links:
        match = re.search(r"/questoes/(\d+)", link['href'])
        if match:
            return match.group(1)
    return None

def converter_tabelas_html(soup_element):
    """
    Localiza tabelas HTML e as transforma em tabelas Markdown estruturadas
    antes da extração de texto plano.
    """
    tables = soup_element.find_all("table")
    
    for table in tables:
        try:
            trs = table.find_all("tr")
            if not trs: continue

            markdown_lines = []
            num_cols = 0

            # Processa linha a linha
            for i, tr in enumerate(trs):
                cells = tr.find_all(["th", "td"])
                if not cells: continue

                # Pega o texto limpo de cada célula
                row_cells = [cell.get_text(" ", strip=True) for cell in cells]
                
                # Atualiza número de colunas baseado na primeira linha válida
                if num_cols == 0:
                    num_cols = len(row_cells)

                # Monta a linha Markdown: | Célula | Célula |
                markdown_lines.append("| " + " | ".join(row_cells) + " |")

                # Se for a primeira linha, adiciona o separador de cabeçalho
                if i == 0:
                    # Cria: | --- | --- | --- |
                    separator = "| " + " | ".join(["---"] * num_cols) + " |"
                    markdown_lines.append(separator)

            # Substitui a tag <table> original pelo bloco Markdown gerado
            tabela_md = "\n\n" + "\n".join(markdown_lines) + "\n\n"
            table.replace_with(tabela_md)
            
        except Exception as e:
            print(f"Aviso: Erro ao converter tabela HTML: {e}")
            # Se falhar, deixa como está para o get_text padrão pegar

def processar_conteudo_rico(html_content, seq_interna):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Localiza o Texto
    enunciado_div = soup.find("div", class_="questao-enunciado-texto")
    if not enunciado_div:
        enunciado_div = soup.find("div", class_="questao-conteudo")
    
    if not enunciado_div: return None

    # 2. Resgata ID
    id_tec_real = extrair_id_tec_do_html(soup)

    # 3. Tratamento de Tabelas (A NOVIDADE AQUI) 🔥
    # Executamos isso ANTES de extrair o texto final
    converter_tabelas_html(enunciado_div)

    # 4. LaTeX (MathJax) -> $$...$$
    tem_latex = False
    for script in enunciado_div.find_all("script", type="math/tex"):
        tem_latex = True
        script.replace_with(f" $${script.get_text()}$$ ")
    
    for tag in enunciado_div.find_all(class_=["MathJax_Preview", "MathJax"]):
        tag.decompose()

    # 5. Imagens
    tem_imagem = False
    urls_imagens = []
    for img in enunciado_div.find_all("img"):
        src = img.get("src")
        if src and "icon" not in src and "spinner" not in src:
            tem_imagem = True
            urls_imagens.append(src)
            img.replace_with(f"\n![Imagem]({src})\n")

    # 6. Texto Limpo (Agora já contendo as tabelas em Markdown)
    texto_rico = limpar_texto(enunciado_div.get_text(separator="\n"))

    return {
        "numero": seq_interna,
        "id_tec_html": id_tec_real,
        "comando_rico": texto_rico,
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
        print("--- EXTRATOR WEB ROBUSTO (Com Tabelas) ---")
        driver.get("https://www.tecconcursos.com.br/entrar")
        print("1. Login + Captcha.")
        input(">>> Pressione ENTER para iniciar...")
        
        driver.get(URL_CADERNO)
        time.sleep(5)
        
        contador = 1
        
        while True:
            # Scroll e Wait
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2.5) 
            
            html = driver.page_source
            dados = processar_conteudo_rico(html, contador)
            
            if dados:
                coletados.append(dados)
                # Log visual para debug
                status = "Tabela Detectada" if "| --- |" in dados['comando_rico'] else "OK"
                print(f"Q.{contador} | ID: {dados['id_tec_html']} | {status}")
            else:
                coletados.append({"numero": contador, "erro": True})

            # Backup
            if contador % BACKUP_INTERVALO == 0:
                with open(ARQUIVO_WEB, "w", encoding="utf-8") as f:
                    json.dump(coletados, f, indent=4, ensure_ascii=False)
            
            # Próxima
            try:
                btn = driver.find_element(By.CSS_SELECTOR, "button.questao-navegacao-botao-proxima")
                if not btn.is_enabled(): break
                btn.click()
                contador += 1
            except:
                break

        with open(ARQUIVO_WEB, "w", encoding="utf-8") as f:
            json.dump(coletados, f, indent=4, ensure_ascii=False)
            
    except Exception as e:
        print(f"Erro: {e}")
        if coletados:
            with open(f"backup_{ARQUIVO_WEB}", "w", encoding="utf-8") as f:
                json.dump(coletados, f, indent=4, ensure_ascii=False)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()