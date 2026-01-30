import json
import re
import os
import argparse
from bs4 import BeautifulSoup

# ==============================================================================
# CONFIGURAÇÃO PADRÃO
# ==============================================================================
ARQUIVO_PADRAO = "dataset_completo_linguainglesa.json"

def limpar_espacos(texto):
    """Remove excesso de quebras de linha e espaços."""
    if not texto: return ""
    texto = re.sub(r'\s+', ' ', texto) 
    return texto.strip()

def extrair_pergunta_ingles(html_comando):
    """
    Busca gatilhos de comando em inglês e retorna do gatilho até o fim.
    """
    if not html_comando: return ""

    soup = BeautifulSoup(html_comando, "html.parser")
    texto_completo = soup.get_text("\n")
    
    # LISTA DE GATILHOS ATUALIZADA
    gatilhos = [
        # Padrão Clássico CESPE/CEBRASPE
        r'(judge\s+the\s+(following\s+)?item.*)', 
        r'(judge\s+the\s+items.*)',
        r'(judge\s+the\s+follow\s+item.*)',
        r'(judge\s+the\s+follow\s+items.*)',
        r'(judge\s+whether\s+the*)',
        r'(decide\s+whether\s+the*)', 
        
        # Padrões de Interpretação
        r'(according\s+to\s+the\s+text.*)',
        r'(based\s+on\s+the\s+text.*)',
        r'(considering\s+the\s+text.*)',
        r'(regarding\s+the\s+text.*)',
        r'(in\s+relation\s+to\s+the\s+text.*)',
        
        # Padrões de Vocabulário/Gramática
        r'(in\s+the\s+fragment.*)',
        r'(in\s+line\s+\d+.*)',
        r'(the\s+word\s+.*)',
        r'(the\s+expression\s+.*)'

        # 1. VARIAÇÕES DE "JUDGE" (Com erros de OCR/Digitação comuns)
        # Cobre: "Judge the following item", "j udge the following", "Judge the followin item"
        r'(j\s*udge\s+the\s+follow(ing|in)?\s+item.*)', 
        
        # Cobre: "Judge the items", "Judge item", "Judge the item"
        r'(j\s*udge\s+(the\s+)?item.*)',
        
        # Cobre: "Judge if the item", "Judge if the translation", "Judge whether"
        r'(j\s*udge\s+(if|whether)\s+.*)',

        # 2. REFERÊNCIAS DIRETAS AO TEXTO (Sem o verbo Judge)
        # Cobre: "Based on text 1A1...", "Based on the cartoon..."
        r'(based\s+on\s+(the\s+)?(text|cartoon|image|figure).*?(\.|,)\s*judge.*)', 
        r'(based\s+on\s+(the\s+)?(text|cartoon|image|figure).*)', 

        # Cobre: "According to the text...", "According to text..."
        r'(according\s+to\s+(the\s+)?text.*)',
        
        # Cobre: "In the text 5A5AAA...", "In text V..."
        r'(in\s+(the\s+)?text\s+[A-Z0-9]+.*)',

        # Cobre: "Concerning the text...", "Regarding the text..."
        r'((concerning|regarding|considering)\s+(the\s+)?text.*)',

        # 3. COMANDOS DIRETOS DE VOCABULÁRIO
        # Cobre: "In line 10...", "The word X..."
        r'(in\s+line\s+\d+.*)',
        r'(the\s+word\s+.*)',
        r'(the\s+expression\s+.*)',
        r'(the\s+pronoun\s+.*)',
        
        # Cobre: "In the sentence..."
        r'(in\s+the\s+sentence.*)'
    ]

    enunciado_encontrado = ""
    match_pos = -1

    for p in gatilhos:
        iterator = re.finditer(p, texto_completo, re.IGNORECASE | re.DOTALL)
        for match in iterator:
            # Prioridade absoluta para "Judge"
            if "judge" in match.group(0).lower():
                return limpar_espacos(match.group(0))
            
            # Para outros, pega o último ou mais relevante
            if match.start() > match_pos:
                match_pos = match.start()
                enunciado_encontrado = match.group(0)

    if enunciado_encontrado:
        return limpar_espacos(enunciado_encontrado)
    
    return ""

def modo_analise(arquivo_entrada):
    """
    Percorre o JSON e separa apenas questões onde 'enunciado' está vazio.
    """
    print(f"🕵️  MODO ANÁLISE: Verificando vazios em '{arquivo_entrada}'...")
    
    with open(arquivo_entrada, 'r', encoding='utf-8') as f:
        dados = json.load(f)
    
    # Filtra: Capturado = True E Enunciado Vazio
    vazios = [q for q in dados if q.get('capturado') and not q.get('enunciado', '').strip()]
    
    qtd_total = len(dados)
    qtd_vazios = len(vazios)
    
    print(f"📊 Relatório:")
    print(f"   Total de Questões: {qtd_total}")
    print(f"   Questões com Enunciado VAZIO: {qtd_vazios}")
    
    if qtd_vazios > 0:
        nome_saida = arquivo_entrada.replace(".json", "_ANALISE_VAZIOS.json")
        with open(nome_saida, 'w', encoding='utf-8') as f:
            json.dump(vazios, f, indent=4, ensure_ascii=False)
        
        print(f"\n💾 Arquivo de diagnóstico salvo: {nome_saida}")
        print("   -> Abra este arquivo para identificar novos padrões de regex necessários.")
    else:
        print("\n✅ Sucesso Total! Nenhuma questão está com enunciado vazio.")

def modo_correcao(arquivo_entrada):
    """
    Percorre o JSON e aplica a extração de regex, salvando um novo arquivo FIXED.
    """
    print(f"🛠️  MODO CORREÇÃO: Aplicando regex em '{arquivo_entrada}'...")
    
    with open(arquivo_entrada, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    atualizados = 0
    
    for q in dados:
        if not q.get('capturado'): continue

        comando = q.get('comando', '')
        # Tenta extrair novamente
        novo_enunciado = extrair_pergunta_ingles(comando)

        if novo_enunciado:
            q['enunciado'] = novo_enunciado
            atualizados += 1

    nome_saida = arquivo_entrada.replace(".json", "_FIXED.json")
    
    with open(nome_saida, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)
        
    print(f"✅ Processamento concluído. {atualizados} enunciados processados.")
    print(f"💾 Arquivo salvo: {nome_saida}")

def main():
    parser = argparse.ArgumentParser(description="Ferramenta de Ajuste de Enunciados (Inglês)")
    
    parser.add_argument("arquivo", nargs='?', default=ARQUIVO_PADRAO, 
                        help="Caminho do arquivo JSON (Padrão: dataset_completo_linguainglesa.json)")
    
    parser.add_argument("--analyze", action="store_true", 
                        help="Apenas analisa e exporta questões com enunciado vazio.")
    
    args = parser.parse_args()

    if not os.path.exists(args.arquivo):
        print(f"❌ Erro: Arquivo '{args.arquivo}' não encontrado.")
        return

    if args.analyze:
        modo_analise(args.arquivo)
    else:
        modo_correcao(args.arquivo)

if __name__ == "__main__":
    main()