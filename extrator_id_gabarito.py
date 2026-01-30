import pdfplumber
import re
import json
import os
import glob
import argparse

# ==============================================================================
# LÓGICA DE EXTRAÇÃO (Robustez Aumentada)
# ==============================================================================
def processar_texto_bruto(texto_completo):
    questoes_extraidas = []
    ids_vistos = set()
    
    # Divide nos links das questões
    blocos = re.split(r'www\.tecconcursos\.com\.br/questoes/', texto_completo)
    
    for i, bloco in enumerate(blocos[1:]):
        try:
            # 1. PEGAR O ID
            match_id = re.match(r'^(\d+)', bloco)
            if not match_id: continue
            
            id_tec = match_id.group(1)
            
            if id_tec in ids_vistos: continue

            # 2. PEGAR O GABARITO (Mais flexível)
            # Procura a palavra Gabarito seguida de qualquer palavra (Certo, Errado, Anulada, X...)
            match_gab = re.search(r'Gabarito:\s*([a-zA-Zçã]+)', bloco, re.IGNORECASE)
            
            gabarito_final = "N/A" # Valor padrão se não encontrar

            if match_gab:
                texto_capturado = match_gab.group(1).title() # Ex: Certo, Errado, Anulada
                
                if texto_capturado in ['Certo', 'Errado']:
                    gabarito_final = texto_capturado
                elif 'Anula' in texto_capturado or 'Nula' in texto_capturado:
                    gabarito_final = "Anulada"
                else:
                    gabarito_final = texto_capturado # Salva o que achou (ex: "X")
            
            # 3. SALVAR (Mesmo se for N/A ou Anulada, salvamos o ID)
            questoes_extraidas.append({
                "id_tec": id_tec,
                "gabarito": gabarito_final
            })
            ids_vistos.add(id_tec)

        except Exception:
            pass

    return questoes_extraidas

# ==============================================================================
# LÓGICA DE DEBUG DETALHADA
# ==============================================================================
def diagnosticar_detalhado(texto_completo):
    print("\n🕵️  DIAGNÓSTICO DETALHADO...")
    
    ids_encontrados = set()
    qtd_padrao = 0        # Certo ou Errado
    qtd_fora_padrao = 0   # Anulada, N/A, X, etc
    
    # Usa a mesma lógica de blocos para garantir consistência
    blocos = re.split(r'www\.tecconcursos\.com\.br/questoes/', texto_completo)
    
    for bloco in blocos[1:]:
        match_id = re.match(r'^(\d+)', bloco)
        if not match_id: continue
        
        id_tec = match_id.group(1)
        if id_tec in ids_encontrados: continue
        ids_encontrados.add(id_tec)
        
        # Análise do Gabarito
        match_gab = re.search(r'Gabarito:\s*([a-zA-Zçã]+)', bloco, re.IGNORECASE)
        
        eh_padrao = False
        if match_gab:
            resp = match_gab.group(1).title()
            if resp in ['Certo', 'Errado']:
                eh_padrao = True
        
        if eh_padrao:
            qtd_padrao += 1
        else:
            qtd_fora_padrao += 1

    print(f"   ------------------------------------------------")
    print(f"   Total de IDs únicos encontrados:      {len(ids_encontrados)}")
    print(f"   Total de gabaritos 'Certo ou Errado': {qtd_padrao}")
    print(f"   Total de gabaritos fora do padrão:    {qtd_fora_padrao}")
    print(f"   ------------------------------------------------")
    
    return len(ids_encontrados)

# ==============================================================================
# MAIN
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="Extrai IDs e Gabaritos de PDFs.")
    parser.add_argument("pasta_alvo", help="Caminho da pasta com PDFs")
    parser.add_argument("-n", "--nome", help="Nome do arquivo de saída", default=None)
    parser.add_argument("-d", "--debug", help="Apenas exibe contagem estatística", action="store_true")
    
    args = parser.parse_args()
    pasta_pdfs = args.pasta_alvo

    if not os.path.exists(pasta_pdfs):
        print(f"❌ Erro: Caminho '{pasta_pdfs}' não encontrado.")
        return

    print(f"📂 Lendo pasta: {pasta_pdfs}")
    arquivos_pdf = glob.glob(os.path.join(pasta_pdfs, "*.pdf"))
    
    if not arquivos_pdf:
        print("❌ Nenhum PDF encontrado.")
        return

    texto_total_acumulado = ""

    # 1. Leitura de Todos os PDFs
    for caminho_pdf in arquivos_pdf:
        print(f"📖 Lendo {os.path.basename(caminho_pdf)}...", end="", flush=True)
        try:
            with pdfplumber.open(caminho_pdf) as pdf:
                for pagina in pdf.pages:
                    texto_total_acumulado += "\n" + (pagina.extract_text() or "")
            print(" OK")
        except Exception as e:
            print(f" ❌ Erro: {e}")

    # 2. Decisão: Debug ou Extração Real
    if args.debug:
        diagnosticar_detalhado(texto_total_acumulado)
    else:
        # Extração Real (Agora salvando tudo)
        dados = processar_texto_bruto(texto_total_acumulado)
        
        # Definição do nome do arquivo
        if args.nome:
            arquivo_saida = f"gabaritos_{args.nome}.json"
        else:
            try:
                caminho_abs = os.path.abspath(pasta_pdfs)
                if os.path.basename(caminho_abs).lower() == 'fonts':
                    nome_base = os.path.basename(os.path.dirname(caminho_abs))
                else:
                    nome_base = os.path.basename(caminho_abs)
                nome_limpo = nome_base.replace(" ", "").lower()
                arquivo_saida = f"gabaritos_{nome_limpo}.json"
            except:
                arquivo_saida = "gabaritos_extraidos.json"

        print("-" * 50)
        print(f"📊 RELATÓRIO FINAL:")
        print(f"   Total de Questões Salvas: {len(dados)}")
        
        # Pequena verificação interna
        anuladas = sum(1 for q in dados if q['gabarito'] not in ['Certo', 'Errado'])
        print(f"   (Incluindo {anuladas} questões anuladas ou sem gabarito)")
        
        with open(arquivo_saida, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=4)
        print(f"💾 Salvo em: {arquivo_saida}")

if __name__ == "__main__":
    main()