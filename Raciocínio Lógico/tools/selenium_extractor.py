import os
import time
import json
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================

# URL EXATA da Questão 1 (Modo Resolver)
# Exemplo: https://www.tecconcursos.com.br/questoes/123456
URL_INICIAL = "https://www.tecconcursos.com.br/questoes/cadernos/86161349" 

ARQUIVO_SAIDA = "teste_20_questoes_raciocinio.json"
LIMITE_TESTE = 20  # Trava para o teste piloto

# Correção SSL
os.environ['WDM_SSL_VERIFY'] = '0'

# ==============================================================================
# LÓGICA DE EXTRAÇÃO
# ==============================================================================

def limpar_texto(texto):
    if not texto: return ""
    # Remove quebras excessivas mas mantém parágrafos
    return re.sub(r'\n{3,}', '\n\n', texto).strip()

def processar_html_questao(html_content, numero_sequencial):
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # 1. Tenta encontrar o container do enunciado
    # Classes comuns no Tec: 'questao-enunciado-texto' ou dentro de 'q-questao'
    enunciado_div = soup.find("div", class_="questao-enunciado-texto")
    
    # Fallback se não achar a classe específica (pega o container maior e limpa)
    if not enunciado_div:
        enunciado_div = soup.find("div", class_="questao-conteudo")
        
    if not enunciado_div:
        return None

    # 2. Processa MathJax (LaTeX)
    # Procura scripts do tipo math/tex e converte para $$...$$
    math_scripts = enunciado_div.find_all("script", type="math/tex")
    for script in math_scripts:
        latex = script.get_text()
        script.replace_with(f" $${latex}$$ ")

    # Remove previews visuais do MathJax (para não duplicar texto)
    for tag in enunciado_div.find_all(class_=["MathJax_Preview", "MathJax"]):
        tag.decompose()

    # 3. Processa Imagens
    imgs = enunciado_div.find_all("img")
    for img in imgs:
        src = img.get("src")
        if src and "icon" not in src:
            img.replace_with(f"\n![Imagem]({src})\n")

    # 4. Extrai Texto Limpo
    texto_markdown = limpar_texto(enunciado_div.get_text(separator="\n"))
    
    # 5. Extrai Alternativas
    alternativas = []
    lista_alts = soup.find("div", class_="questao-alternativas") # Tenta container geral
    if not lista_alts:
        lista_alts = soup.find("ul", class_="questao-enunciado-alternativas")

    if lista_alts:
        # Tenta pegar itens de lista ou divs de opção
        itens = lista_alts.find_all(["li", "div"], class_=re.compile("alternativa-row|alternativa-opcao"))
        
        # Se não achou estrutura, tenta pegar texto bruto das classes de letra/texto
        if not itens:
             itens = lista_alts.find_all("div", class_="questao-enunciado-alternativa-texto")

        for item in itens:
            # Aplica mesma lógica de MathJax nas alternativas
            for script in item.find_all("script", type="math/tex"):
                script.replace_with(f" $${script.get_text()}$$ ")
            for tag in item.find_all(class_=["MathJax_Preview", "MathJax"]):
                tag.decompose()
            
            # Tenta achar a letra
            letra_tag = item.find_previous("span", class_="questao-enunciado-alternativa-opcao")
            letra = letra_tag.get_text().strip() if letra_tag else "*"
            
            texto_alt = limpar_texto(item.get_text(separator=" "))
            if texto_alt:
                alternativas.append(f"{letra}) {texto_alt}")

    return {
        "id_sequencia": numero_sequencial,
        "enunciado": texto_markdown,
        "alternativas": alternativas,
        "tem_latex": "$$" in texto_markdown,
        "tem_imagem": "![" in texto_markdown
    }

# ==============================================================================
# EXECUÇÃO
# ==============================================================================

def main():
    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    
    try:
        path = ChromeDriverManager().install()
    except:
        path = "chromedriver.exe"
    
    driver = webdriver.Chrome(service=Service(path), options=options)
    coletados = []

    try:
        print("--- INICIANDO TESTE PILOTO (20 QUESTÕES) ---")
        driver.get("https://www.tecconcursos.com.br/entrar")
        print("1. Faça LOGIN.")
        print("2. Navegue até a QUESTÃO 1.")
        input(">>> Pressione ENTER quando estiver vendo a Questão 1...")

        contador = 1
        while contador <= LIMITE_TESTE:
            print(f"Processando questão {contador}/{LIMITE_TESTE}...")
            
            # Pequena pausa para MathJax renderizar
            time.sleep(2)
            
            html = driver.page_source
            dados = processar_html_questao(html, contador)
            
            if dados:
                coletados.append(dados)
                print(f"  > Capturado (LaTeX: {dados['tem_latex']} | Img: {dados['tem_imagem']})")
            else:
                print("  > FALHA: Não foi possível identificar o conteúdo.")

            # Avançar
            if contador < LIMITE_TESTE:
                try:
                    btn = driver.find_element(By.CSS_SELECTOR, "button.questao-navegacao-botao-proxima")
                    if not btn.is_enabled():
                        print("Fim do caderno alcançado.")
                        break
                    btn.click()
                    contador += 1
                    time.sleep(2) # Pausa transição
                except:
                    print("Botão Próximo não encontrado.")
                    break
            else:
                break
        
        # Salva
        with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
            json.dump(coletados, f, indent=4, ensure_ascii=False)
        print(f"\nSucesso! {len(coletados)} questões salvas em '{ARQUIVO_SAIDA}'")

    except Exception as e:
        print(f"Erro: {e}")
        if coletados:
            with open(ARQUIVO_SAIDA, "w", encoding="utf-8") as f:
                json.dump(coletados, f, indent=4, ensure_ascii=False)
    finally:
        driver.quit()

if __name__ == "__main__":
    main()