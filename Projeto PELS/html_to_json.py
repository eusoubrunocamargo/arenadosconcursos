import re
import json
import html
import argparse
import sys
import os

def limpar_html_para_texto(html_content):
    """Limpa tags HTML e prepara o texto para processamento."""
    print("Iniciando limpeza do HTML...")
    
    texto = html.unescape(html_content)
    
    # Substituições básicas de tags por quebras de linha
    texto = re.sub(r'<(p|br|div|h\d)[^>]*>', '\n', texto, flags=re.IGNORECASE)
    texto = re.sub(r'</(p|div|h\d)>', '\n', texto, flags=re.IGNORECASE)
    texto = re.sub(r'<[^>]+>', '', texto)
    texto = re.sub(r'\s+', ' ', texto).strip()
    
    # --- MARCADORES ESTRATÉGICOS ---
    # Inserimos \n antes destes termos para garantir que fiquem no início da linha.
    # A novidade: (?<!\() impede que quebremos linhas se o termo estiver dentro de parênteses.
    # Ex: "(Parágrafo único...)" não ganhará \n antes, logo não será tratado como novo item.
    
    marcadores = [
        r"(Art\.\s*[\d\wº°ª]+)", 
        r"(?<!\()(?<!\(\s)(Parágrafo\s*único)", # Protege contra "(Parágrafo único"
        r"(§\s*[\dº°ª]+)", 
        r"([IVXLCDM]+\s*-)", 
        r"([a-z]\))"
    ]
    for m in marcadores:
        texto = re.sub(m, r'\n\1', texto)
        
    return texto

def gerar_estrutura(texto, preview_mode=False):
    """Processa o texto limpo e gera a estrutura JSON corrigida."""
    print("Processando estrutura hierárquica...")
    
    linhas = texto.split('\n')
    estrutura = []
    
    # Variáveis de Estado
    artigo_atual = None      
    container_atual = None   # Artigo ou Parágrafo (quem recebe incisos)
    ultimo_inciso = None     # Quem recebe alíneas
    item_focado = None       # O último item criado (para concatenar texto solto)
    
    # Regex de identificação
    re_artigo = re.compile(r"^\s*Art\.\s*([\d\wº°ª]+)[\.\s\-]*(.*)", re.IGNORECASE)
    re_paragrafo = re.compile(r"^\s*(§\s*[\dº°ª]+|Parágrafo\s*único)[\.\s\-]*(.*)", re.IGNORECASE)
    re_inciso = re.compile(r"^\s*([IVXLCDM]+)\s*-\s*(.*)", re.IGNORECASE)
    re_alinea = re.compile(r"^\s*([a-z])\)\s*(.*)", re.IGNORECASE)

    count_artigos = 0

    for linha in linhas:
        linha = linha.strip()
        if not linha: continue

        # --- 1. É ARTIGO? ---
        match_art = re_artigo.match(linha)
        if match_art:
            if preview_mode and count_artigos >= 10: break
            
            if artigo_atual:
                estrutura.append(artigo_atual)
            
            count_artigos += 1
            
            artigo_atual = {
                "tipo": "artigo",
                "rotulo": match_art.group(1).replace('.', ''),
                "texto": match_art.group(2).strip(),
                "itens": []
            }
            
            container_atual = artigo_atual
            ultimo_inciso = None
            item_focado = artigo_atual # Foco para append de texto
            continue

        # --- 2. É PARÁGRAFO? ---
        match_par = re_paragrafo.match(linha)
        if match_par and artigo_atual:
            rotulo = match_par.group(1).strip()
            # Remove pontuação final do rótulo se houver (ex: "§ 1º.")
            if rotulo.endswith('.'): rotulo = rotulo[:-1]

            novo_par = {
                "tipo": "paragrafo",
                "rotulo": rotulo, 
                "texto": match_par.group(2).strip(),
                "itens": []
            }
            
            artigo_atual["itens"].append(novo_par)
            container_atual = novo_par 
            ultimo_inciso = None 
            item_focado = novo_par
            continue

        # --- 3. É INCISO? ---
        match_inc = re_inciso.match(linha)
        if match_inc and container_atual:
            novo_inciso = {
                "tipo": "inciso",
                "rotulo": match_inc.group(1),
                "texto": match_inc.group(2).strip(),
                "itens": []
            }
            
            container_atual["itens"].append(novo_inciso)
            ultimo_inciso = novo_inciso
            item_focado = novo_inciso
            continue

        # --- 4. É ALÍNEA? ---
        match_ali = re_alinea.match(linha)
        if match_ali and ultimo_inciso:
            nova_alinea = {
                "tipo": "alinea",
                "rotulo": match_ali.group(1),
                "texto": match_ali.group(2).strip()
            }
            ultimo_inciso["itens"].append(nova_alinea)
            item_focado = nova_alinea
            continue
            
        # --- 5. TEXTO SOLTO (CONTINUAÇÃO) ---
        # Se chegou aqui, a linha não é inicio de nada, mas contém texto.
        # Provavelmente é a continuação de uma frase quebrada.
        if item_focado:
            item_focado["texto"] += " " + linha

    # Adiciona o último artigo
    if artigo_atual and (not preview_mode or count_artigos <= 10):
        estrutura.append(artigo_atual)
        
    return estrutura

def main():
    parser = argparse.ArgumentParser(description="Conversor HTML -> JSON")
    parser.add_argument("arquivo_entrada", help="Caminho do arquivo HTML")
    parser.add_argument("--preview", action="store_true", help="Gera apenas os 10 primeiros artigos")
    
    args = parser.parse_args()

    if not os.path.exists(args.arquivo_entrada):
        print(f"Erro: Arquivo '{args.arquivo_entrada}' não encontrado.")
        return

    try:
        with open(args.arquivo_entrada, 'r', encoding='utf-8', errors='ignore') as f:
            conteudo = f.read()

        dados = gerar_estrutura(limpar_html_para_texto(conteudo), args.preview)

        nome_saida = "constituicao_preview.json" if args.preview else "constituicao_completa.json"
        
        with open(nome_saida, 'w', encoding='utf-8') as f_out:
            json.dump(dados, f_out, indent=2, ensure_ascii=False)
            
        print(f"Sucesso! Arquivo salvo em: {nome_saida}")

    except Exception as e:
        print(f"Erro: {e}")

if __name__ == "__main__":
    main()