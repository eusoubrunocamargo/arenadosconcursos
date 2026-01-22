import re
import json
import pdfplumber
import glob
import os

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
PADRAO_PDF = "../Regimentos*.pdf"
PADRAO_EXTRA = "../REG*.pdf" 

ARQUIVO_SAIDA = "dataset_regimentos_final.json"
ARQUIVO_ANULADAS = "dataset_regimentos_anuladas.json"

# ==============================================================================
# INTELIGÊNCIA DE TEXTO
# ==============================================================================

def limpar_texto(texto):
    if not texto: return ""
    return re.sub(r'\n{3,}', '\n\n', texto).strip()

def separar_comando_enunciado(texto_completo):
    if not texto_completo: return "", ""

    gatilhos = [
        r'(julgue\s+o(s)?\s+.*?(item|itens)\s+(a\s+seguir|seguintes?|subsequentes?|próximos?).*?(:|\.))',
        r'(julgue\s+o(s)?\s+(seguintes?|próximos?|subsequentes?)\s+(item|itens).*?(:|\.))',
        r'(julgue\s+o(s)?\s+(item|itens).*?de\s+acordo.*?(:|\.))',
        r'(julgue\s+o(s)?\s+.*?(item|itens).*?(:|\.))',
        r'(assinale\s+a\s+opção\s+correta.*?(:|\.))'
    ]
    
    divisor = None
    match_pos = -1

    for g in gatilhos:
        iterator = re.finditer(g, texto_completo, re.IGNORECASE | re.DOTALL)
        for match in iterator:
            if match.end() > match_pos and match.end() < len(texto_completo) - 2:
                match_pos = match.end()
                divisor = match

    if divisor:
        comando = texto_completo[:divisor.end()].strip()
        enunciado = texto_completo[divisor.end():].strip()
        enunciado = re.sub(r'^[\.\:\-\s]+', '', enunciado)
        enunciado = re.sub(r'\s+(Certo|Errado)$', '', enunciado, flags=re.IGNORECASE)
        return comando, enunciado

    partes = texto_completo.split('\n\n')
    if len(partes) >= 2:
        enunciado_cand = partes[-1].strip()
        if len(enunciado_cand) < 800: 
            comando = "\n\n".join(partes[:-1]).strip()
            return comando, enunciado_cand
        
    return texto_completo, "[Enunciado não separado automaticamente]"

# ==============================================================================
# MOTOR DE EXTRAÇÃO (COM FALLBACK DE BANCA)
# ==============================================================================

def processar_pdf(caminho_pdf):
    nome_arquivo = os.path.basename(caminho_pdf)
    print(f"   📄 Processando: {nome_arquivo}...")
    
    texto_bruto = ""
    try:
        with pdfplumber.open(caminho_pdf) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: texto_bruto += t + "\n"
    except Exception as e:
        print(f"      ❌ Erro ao ler PDF: {e}")
        return [], []

    linhas = texto_bruto.split('\n')
    questoes = []
    
    regex_url = re.compile(r'tecconcursos\.com\.br/questoes/(\d+)')
    regex_inicio = re.compile(r'^(\d+)\)\s*(.*)')
    regex_gabarito = re.compile(r'^Gabarito:\s*(.*)', re.IGNORECASE)

    i = 0
    total = len(linhas)
    q_atual = None
    buffer_texto = []

    while i < total:
        linha = linhas[i].strip()
        
        match_id = regex_url.search(linha)
        if match_id:
            if q_atual:
                full = "\n".join(buffer_texto)
                cmd, enun = separar_comando_enunciado(full)
                q_atual['comando'] = limpar_texto(cmd)
                q_atual['enunciado'] = limpar_texto(enun)
                questoes.append(q_atual)
                q_atual = None
                buffer_texto = []
            
            novo_id = match_id.group(1)
            banca = ""
            materia = "Regimentos e Código de Ética"
            assunto = ""
            
            offset = 1
            found_start = False
            
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

                match_num = regex_inicio.match(prox)
                if match_num:
                    # --- NOVIDADE V3: FALLBACK DE BANCA ---
                    if not banca:
                        banca = "Questões Inéditas"
                    # --------------------------------------

                    q_atual = {
                        "numero": int(match_num.group(1)),
                        "id_tec": novo_id,
                        "link": f"www.tecconcursos.com.br/questoes/{novo_id}",
                        "banca_orgao": banca,
                        "materia": materia,
                        "assunto": assunto,
                        "gabarito": ""
                    }
                    if match_num.group(2): buffer_texto.append(match_num.group(2))
                    i += offset
                    found_start = True
                    break
                offset += 1
            
            if not found_start:
                # Fallback aqui também
                if not banca: banca = "Questões Inéditas"
                
                q_atual = {
                    "numero": 0, "id_tec": novo_id,
                    "link": f"www.tecconcursos.com.br/questoes/{novo_id}",
                    "banca_orgao": banca, "materia": materia, "assunto": assunto, "gabarito": ""
                }
                i += offset
            i += 1
            continue

        match_gab = regex_gabarito.search(linha)
        if match_gab and q_atual:
            q_atual['gabarito'] = match_gab.group(1).strip()
        
        elif q_atual and "www.tecconcursos" not in linha:
            buffer_texto.append(linha)
        
        i += 1

    if q_atual:
        full = "\n".join(buffer_texto)
        cmd, enun = separar_comando_enunciado(full)
        q_atual['comando'] = limpar_texto(cmd)
        q_atual['enunciado'] = limpar_texto(enun)
        questoes.append(q_atual)

    # Segregação
    lista_validas = []
    lista_anuladas = []
    
    for q in questoes:
        gab = q.get('gabarito', '').capitalize()
        if gab in ["Certo", "Errado"]:
            lista_validas.append(q)
        else:
            lista_anuladas.append(q)
            
    print(f"      ✅ Válidas: {len(lista_validas)} | 🗑️  Anuladas: {len(lista_anuladas)}")
    return lista_validas, lista_anuladas

def main():
    print("--- EXTRATOR REGIMENTOS V3 (Banca Inédita) ---")
    arquivos = glob.glob(PADRAO_PDF)
    arquivos += glob.glob(PADRAO_EXTRA)
    
    if not arquivos:
        print(f"Nenhum PDF encontrado.")
        return

    todas_validas = []
    todas_anuladas = []
    
    for arq in arquivos:
        v, a = processar_pdf(arq)
        todas_validas.extend(v)
        todas_anuladas.extend(a)
    
    # Deduplicação
    unicas_v = {q['id_tec']: q for q in todas_validas if q.get('id_tec')}
    final_v = list(unicas_v.values())
    final_v.sort(key=lambda x: int(x['id_tec']) if x['id_tec'].isdigit() else 0)

    unicas_a = {q['id_tec']: q for q in todas_anuladas if q.get('id_tec')}
    final_a = list(unicas_a.values())

    print("-" * 50)
    print(f"TOTAL VÁLIDO: {len(final_v)}")
    print(f"TOTAL ANULADO: {len(final_a)}")
    print("-" * 50)

    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(final_v, f, indent=4, ensure_ascii=False)
    print(f"Salvo: {ARQUIVO_SAIDA}")

    if final_a:
        with open(ARQUIVO_ANULADAS, 'w', encoding='utf-8') as f:
            json.dump(final_a, f, indent=4, ensure_ascii=False)
        print(f"Salvo (Anuladas): {ARQUIVO_ANULADAS}")

if __name__ == "__main__":
    main()