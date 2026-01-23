import re
import json
import pdfplumber
import glob
import os

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
PADRAO_PDF = "../Raciocínio Lógico*.pdf"
ARQUIVO_SAIDA = "mapa_RL.json"

# ==============================================================================
# MOTOR DE EXTRAÇÃO (LEVE - APENAS IDs E METADADOS)
# ==============================================================================

def processar_pdf(caminho_pdf):
    nome_arquivo = os.path.basename(caminho_pdf)
    print(f"   📄 A mapear: {nome_arquivo}...")
    
    texto_bruto = ""
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: texto_bruto += t + "\n"
    except Exception as e:
        print(f"      ❌ Erro ao ler PDF: {e}")
        return []

    linhas = texto_bruto.split('\n')
    mapa_questoes = []
    
    regex_url = re.compile(r'tecconcursos\.com\.br/questoes/(\d+)')
    regex_inicio = re.compile(r'^(\d+)\)\s*')
    regex_gabarito = re.compile(r'^Gabarito:\s*(Certo|Errado)', re.IGNORECASE)

    i = 0
    total = len(linhas)
    q_atual = None

    while i < total:
        linha = linhas[i].strip()
        
        # 1. CAPTURA DO ID
        match_id = regex_url.search(linha)
        if match_id:
            # Salva a anterior se tiver gabarito válido
            if q_atual and q_atual.get('gabarito'):
                mapa_questoes.append(q_atual)
            
            novo_id = match_id.group(1)
            banca = ""
            materia = "Raciocínio Lógico"
            assunto = ""
            
            # Lookahead para Metadados (Banca e Assunto)
            offset = 1
            while offset <= 5 and (i + offset) < total:
                prox = linhas[i + offset].strip()
                if not prox: 
                    offset += 1
                    continue
                
                if not banca and ("CEBRASPE" in prox or "FGV" in prox or "FCC" in prox):
                    banca = prox
                elif not assunto and " - " in prox and prox != banca:
                    parts = prox.split(" - ", 1)
                    if len(parts) > 1:
                        assunto = parts[1].strip()
                        materia = parts[0].strip()
                    else:
                        assunto = prox

                if regex_inicio.match(prox):
                    if not banca: banca = "Questões Inéditas"
                    q_atual = {
                        "id_tec": novo_id,
                        "url_direta": f"https://www.tecconcursos.com.br/questoes/{novo_id}",
                        "banca_orgao": banca,
                        "materia": materia,
                        "assunto": assunto,
                        "gabarito": "" # Será preenchido quando achar a linha "Gabarito:"
                    }
                    i += offset
                    break
                offset += 1
            
            # Se não achou o "1)", cria um placeholder
            if q_atual is None or q_atual['id_tec'] != novo_id:
                if not banca: banca = "Questões Inéditas"
                q_atual = {
                    "id_tec": novo_id,
                    "url_direta": f"https://www.tecconcursos.com.br/questoes/{novo_id}",
                    "banca_orgao": banca, "materia": materia, "assunto": assunto, "gabarito": ""
                }
                i += offset
            i += 1
            continue

        # 2. CAPTURA DO GABARITO (Filtro rigoroso: Apenas Certo/Errado)
        match_gab = regex_gabarito.search(linha)
        if match_gab and q_atual:
            q_atual['gabarito'] = match_gab.group(1).capitalize()
        
        # Ignoramos todo o resto do texto!
        i += 1

    # Salva a última
    if q_atual and q_atual.get('gabarito'):
        mapa_questoes.append(q_atual)

    return mapa_questoes

def main():
    print("--- PASSO 1: MAPEAMENTO DE RACIOCÍNIO LÓGICO ---")
    arquivos = glob.glob(PADRAO_PDF)
    
    if not arquivos:
        print(f"Nenhum PDF encontrado em: {PADRAO_PDF}")
        return

    todos_ids = []
    for arq in arquivos:
        todos_ids.extend(processar_pdf(arq))
    
    # Deduplicação baseada no ID TEC
    unicas = {q['id_tec']: q for q in todos_ids if q.get('id_tec')}
    lista_final = sorted(list(unicas.values()), key=lambda x: int(x['id_tec']))

    print("-" * 50)
    print(f"📋 Total de IDs Válidos (Certo/Errado): {len(lista_final)}")
    print("-" * 50)

    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(lista_final, f, indent=4, ensure_ascii=False)
    print(f"✅ MAPA GERADO: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    main()