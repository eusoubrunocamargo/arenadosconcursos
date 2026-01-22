import re
import json
import pdfplumber
import glob
import os

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
# Ajuste do padrão para encontrar os PDFs de Administração Pública
PADRAO_PDF = "../AP*.pdf"
ARQUIVO_SAIDA = "dataset_administracao_publica_final.json"

# ==============================================================================
# INTELIGÊNCIA DE TEXTO (Lógica V4 - Blindada)
# ==============================================================================

def limpar_texto(texto):
    if not texto: return ""
    return re.sub(r'\n{3,}', '\n\n', texto).strip()

def separar_comando_enunciado(texto_completo):
    """
    Separa o Comando do Enunciado usando gatilhos hierárquicos.
    """
    if not texto_completo: return "", ""

    gatilhos = [
        # Gatilhos de alta especificidade (V4)
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
            # Garante que o gatilho está no final do texto de apoio
            if match.end() > match_pos and match.end() < len(texto_completo) - 2:
                match_pos = match.end()
                divisor = match

    if divisor:
        comando = texto_completo[:divisor.end()].strip()
        enunciado = texto_completo[divisor.end():].strip()
        
        # Limpezas pós-separação
        enunciado = re.sub(r'^[\.\:\-\s]+', '', enunciado)
        enunciado = re.sub(r'\s+(Certo|Errado)$', '', enunciado, flags=re.IGNORECASE)
        
        return comando, enunciado

    # Fallback estrutural
    partes = texto_completo.split('\n\n')
    if len(partes) >= 2:
        enunciado_cand = partes[-1].strip()
        if len(enunciado_cand) < 800: # Tolerância levemente maior para textos desta matéria
            comando = "\n\n".join(partes[:-1]).strip()
            return comando, enunciado_cand
        
    return texto_completo, "[Enunciado não separado automaticamente]"

# ==============================================================================
# MOTOR DE EXTRAÇÃO
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
        return []

    linhas = texto_bruto.split('\n')
    questoes = []
    
    regex_url = re.compile(r'tecconcursos\.com\.br/questoes/(\d+)')
    regex_inicio = re.compile(r'^(\d+)\)\s*(.*)')
    # Filtro Rígido de Gabarito
    regex_gabarito = re.compile(r'^Gabarito:\s*(Certo|Errado)', re.IGNORECASE)

    i = 0
    total = len(linhas)
    q_atual = None
    buffer_texto = []

    while i < total:
        linha = linhas[i].strip()
        
        # 1. LINK ID (Início de nova questão)
        match_id = regex_url.search(linha)
        if match_id:
            # Salva a anterior
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
            materia = "Administração Pública"
            assunto = ""
            
            # Lookahead para metadados (até 5 linhas)
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
                        materia = parts[0].strip() # Pega o nome da matéria do PDF se disponível
                    else:
                        assunto = prox

                match_num = regex_inicio.match(prox)
                if match_num:
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
                q_atual = {
                    "numero": 0, "id_tec": novo_id,
                    "link": f"www.tecconcursos.com.br/questoes/{novo_id}",
                    "banca_orgao": banca, "materia": materia, "assunto": assunto, "gabarito": ""
                }
                i += offset
            i += 1
            continue

        # 2. GABARITO
        match_gab = regex_gabarito.search(linha)
        if match_gab and q_atual:
            q_atual['gabarito'] = match_gab.group(1)
        
        # 3. TEXTO
        elif q_atual and "www.tecconcursos" not in linha:
            buffer_texto.append(linha)
        
        i += 1

    # Salva a última
    if q_atual:
        full = "\n".join(buffer_texto)
        cmd, enun = separar_comando_enunciado(full)
        q_atual['comando'] = limpar_texto(cmd)
        q_atual['enunciado'] = limpar_texto(enun)
        questoes.append(q_atual)

    # Filtro final (Exclui anuladas/múltipla escolha)
    questoes_validas = []
    excluidas = 0
    for q in questoes:
        if q.get('gabarito', '').capitalize() in ["Certo", "Errado"]:
            questoes_validas.append(q)
        else:
            excluidas += 1
            
    print(f"      🗑️ Excluídas (Gabarito inválido/anulada): {excluidas}")
    return questoes_validas

def main():
    print("--- EXTRATOR ADMINISTRAÇÃO PÚBLICA (V4) ---")
    arquivos = glob.glob(PADRAO_PDF)
    
    if not arquivos:
        print(f"Nenhum PDF encontrado com padrão: {PADRAO_PDF}")
        return

    todas = []
    for arq in arquivos:
        todas.extend(processar_pdf(arq))
    
    # Deduplicação
    unicas = {q['id_tec']: q for q in todas if q.get('id_tec')}
    lista_final = list(unicas.values())
    lista_final.sort(key=lambda x: int(x['id_tec']) if x['id_tec'].isdigit() else 0)

    print("-" * 50)
    print(f"Total Válido: {len(lista_final)}")
    print("-" * 50)

    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(lista_final, f, indent=4, ensure_ascii=False)
    print(f"Salvo em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    main()