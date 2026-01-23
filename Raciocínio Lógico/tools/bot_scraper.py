import json
import time
import os
import re
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
ARQUIVO_MAPA = "mapa_RL.json"
ARQUIVO_SAIDA = "dataset_RL_rico.json"

# Seletor exato do botão "Próxima"
CSS_BOTAO_PROXIMA = "button.questao-navegacao-botao-proxima" 
DOMINIO_BASE = "https://www.tecconcursos.com.br"

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# ==============================================================================
# PARSER DE HTML (CORREÇÃO DO ID + IMAGENS)
# ==============================================================================

def extrair_conteudo_html(html_source):
    soup = BeautifulSoup(html_source, 'html.parser')
    
    # 1. Extração do ID (NOVA LÓGICA)
    # Busca a tag <a> com a classe exata que você nos forneceu
    id_questao = "Desconhecido"
    tag_id = soup.find('a', class_='id-questao')
    if tag_id:
        # Pega o texto (ex: "#3303579") e remove a hashtag
        id_questao = tag_id.get_text(strip=True).replace('#', '')

    # 2. Localiza o Enunciado
    div_questao = soup.find('div', class_=re.compile(r'question-statement|enunciado|texto|question-body'))
    if not div_questao:
        return id_questao, "ERRO: Div do enunciado não encontrado", False, "", False

    has_image = False
    img_url = ""
    has_latex = False

    # 3. Imagens (Com correção de URL relativa)
    imagens = div_questao.find_all('img')
    if imagens:
        has_image = True
        src = imagens[0].get('src', '')
        # Se a imagem começar com "/", adiciona o domínio do TEC
        if src.startswith('/'):
            img_url = DOMINIO_BASE + src
        else:
            img_url = src

    # 4. Latex / MathJax
    latex_tags = div_questao.find_all('script', {'type': re.compile(r'math/tex')})
    if latex_tags:
        has_latex = True
        for tag in latex_tags:
            new_tag = soup.new_string(f" ${tag.string}$ ")
            tag.replace_with(new_tag)
    elif "$$" in div_questao.text or "\\[" in div_questao.text:
        has_latex = True

    # 5. Texto Limpo
    texto_limpo = div_questao.get_text(separator='\n', strip=True)

    return id_questao, texto_limpo, has_image, img_url, has_latex

# ==============================================================================
# EXECUÇÃO DO ROBÔ
# ==============================================================================

def main():
    print("--- PASSO 2: BOT DE ENRIQUECIMENTO (V4 - CORREÇÃO DE ID) ---")
    
    global driver 
    driver = init_driver()
    
    driver.get("https://www.tecconcursos.com.br/login")
    
    print("\n" + "="*70)
    print("🛑 PAUSA HUMANA: O navegador foi aberto.")
    print("1. Faça o seu login.")
    print("2. Abra o caderno de Raciocínio Lógico.")
    print("3. Vá para a PRIMEIRA QUESTÃO e aguarde ela carregar na tela.")
    print("="*70)
    
    input("\n✅ Pressione [ENTER] quando a 1ª questão estiver visível na tela...")

    print("\n🚀 Robô assumindo o controle! Raspando dados...")

    questoes_enriquecidas = []
    LIMITE = 20 # Ajuste se quiser testar apenas 10 primeiro
    
    try:
        for i in range(LIMITE):
            time.sleep(1.2) # Pausa estratégica para o Angular carregar os dados novos

            html = driver.page_source
            id_q, texto, tem_img, url_img, tem_latex = extrair_conteudo_html(html)

            print(f"   [{i+1}] ID {id_q} capturado. (Img: {tem_img}, Latex: {tem_latex})")

            questao_dado = {
                "id_tec": id_q,
                "texto_completo": texto,
                "has_image": tem_img,
                "image_url": url_img,
                "has_latex": tem_latex
            }
            questoes_enriquecidas.append(questao_dado)

            # Clique via JavaScript
            try:
                btn_proxima = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, CSS_BOTAO_PROXIMA))
                )
                driver.execute_script("arguments[0].click();", btn_proxima)
            except Exception:
                print("   ⚠️ Botão 'Próxima' não encontrado. Fim do caderno alcançado!")
                break

    except KeyboardInterrupt:
        print("\n⚠️ Interrompido pelo usuário. Salvando...")
    except Exception as e:
        print(f"\n❌ Erro crítico: {e}")
    finally:
        driver.quit()

    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(questoes_enriquecidas, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ Concluído! {len(questoes_enriquecidas)} questões salvas em {ARQUIVO_SAIDA}.")

if __name__ == "__main__":
    main()