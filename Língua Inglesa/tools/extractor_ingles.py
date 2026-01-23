import re
import json
import pdfplumber
import glob
import os

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
PADRAO_PDF = "../ING*.pdf"
ARQUIVO_SAIDA_TEXTO = "dataset_ingles_final.json"
ARQUIVO_SAIDA_IMAGEM = "dataset_ingles_imagens.json"
ARQUIVO_ANULADAS = "dataset_ingles_anuladas.json"

# Palavras que indicam que a questão depende de um elemento visual
KEYWORDS_IMAGEM = [
    "infographic", "figure", "image", "picture", 
    "cartoon", "comic strip", "chart", "graph"
]

# ==============================================================================
# INTELIGÊNCIA DE TEXTO (Adaptada para INGLÊS)
# ==============================================================================

def limpar_texto(texto):
    if not texto: return ""
    return re.sub(r'\n{3,}', '\n\n', texto).strip()

def detectar_imagem(texto_completo):
    """Verifica se há menção a imagens no texto."""
    texto_lower = texto_completo.lower()
    for kw in KEYWORDS_IMAGEM:
        # Busca a palavra como termo isolado usando word boundary (\b)
        if re.search(r'\b' + kw + r's?\b', texto_lower):
            return True
    return False

def separar_comando_enunciado(texto_completo):
    if not texto_completo: return "", ""

    # Gatilhos de Separação em INGLÊS
    gatilhos = [
        # Ex: "Judge the following item concerning the ideas..."
        r'(Judge\s+the\s+(following|next|subsequent)?\s*items?.*?(:|\.))',
        r'(Judge\s+the\s+.*?items?.*?(:|\.))',
        # Ex: "Based on the infographic presented, judge the following item."
        r'(Based\s+on\s+the\s+.*?judge.*?(:|\.))',
        r'(Considering\s+the\s+.*?judge.*?(:|\.))',
        r'(Choose\s+the\s+correct\s+option.*?(:|\.))'
    ]
    
    divisor = None
    match_pos = -1

    # Busca o ÚLTIMO gatilho válido no texto
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
        # Limpa o gabarito que vaza no final em Português (O TEC mantém o gabarito em PT)
        enunciado = re.sub(r'\s+(Certo|Errado)$', '', enunciado, flags=re.IGNORECASE)
        return comando, enunciado

    # Fallback estrutural para Inglês
    partes = texto_completo.split('\n\n')
    if len(partes) >= 2:
        enunciado_cand = partes[-1].strip()
        if len(enunciado_cand) < 800: 
            comando = "\n\n".join(partes[:-1]).strip()
            return comando, enunciado_cand
        
    return texto_completo, "[Enunciado não separado automaticamente]"

# ==============================================================================
# MOTOR DE EXTRAÇÃO (V5)
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
        return [], [], []

    linhas = texto_bruto.split('\n')
    questoes = []
    
    regex_url = re.compile(r'tecconcursos\.com\.br/questoes/(\d+)')
    regex_inicio = re.compile(r'^(\d+)\)\s*(.*)')
    # Gabarito da plataforma continua em português
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
                # Flag de Imagem
                q_atual['maybe_image'] = detectar_imagem(full)
                questoes.append(q_atual)
                q_atual = None
                buffer_texto = []
            
            novo_id = match_id.group(1)
            banca = ""
            materia = "Língua Inglesa"
            assunto = ""
            
            offset = 1
            found_start = False
            
            while offset <= 5 and (i + offset) < total:
                prox = linhas[i + offset].strip()
                if not prox: 
                    offset += 1
                    continue
                
                # Metadados continuam em português
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
                    if not banca: banca = "Questões Inéditas"

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
        q_atual['maybe_image'] = detectar_imagem(full)
        questoes.append(q_atual)

    # --- TRIPLA SEGREGAÇÃO ---
    lista_validas_texto = []
    lista_validas_imagem = []
    lista_anuladas = []
    
    for q in questoes:
        gab = q.get('gabarito', '').capitalize()
        # Filtro de Gabarito
        if gab in ["Certo", "Errado"]:
            # Filtro de Imagem
            if q.get('maybe_image'):
                lista_validas_imagem.append(q)
            else:
                lista_validas_texto.append(q)
        else:
            lista_anuladas.append(q)
            
    print(f"      ✅ Texto: {len(lista_validas_texto)} | 🖼️  Imagens: {len(lista_validas_imagem)} | 🗑️  Anuladas: {len(lista_anuladas)}")
    return lista_validas_texto, lista_validas_imagem, lista_anuladas

def main():
    print("--- EXTRATOR INGLÊS (V5 + Detecção de Imagem) ---")
    arquivos = glob.glob(PADRAO_PDF)
    
    if not arquivos:
        print(f"Nenhum PDF encontrado em {PADRAO_PDF}")
        return

    todas_texto = []
    todas_imagem = []
    todas_anuladas = []
    
    for arq in arquivos:
        t, im, a = processar_pdf(arq)
        todas_texto.extend(t)
        todas_imagem.extend(im)
        todas_anuladas.extend(a)
    
    # Deduplicação
    def deduplicar(lista):
        unicas = {q['id_tec']: q for q in lista if q.get('id_tec')}
        return sorted(list(unicas.values()), key=lambda x: int(x['id_tec']) if x['id_tec'].isdigit() else 0)

    final_texto = deduplicar(todas_texto)
    final_imagem = deduplicar(todas_imagem)
    final_anuladas = deduplicar(todas_anuladas)

    print("-" * 50)
    print(f"✅ TEXTO PURO (P/ DB): {len(final_texto)}")
    print(f"🖼️  COM IMAGEM (Revisão): {len(final_imagem)}")
    print(f"🗑️  ANULADAS: {len(final_anuladas)}")
    print("-" * 50)

    # Salva os arquivos
    with open(ARQUIVO_SAIDA_TEXTO, 'w', encoding='utf-8') as f:
        json.dump(final_texto, f, indent=4, ensure_ascii=False)
    
    if final_imagem:
        with open(ARQUIVO_SAIDA_IMAGEM, 'w', encoding='utf-8') as f:
            json.dump(final_imagem, f, indent=4, ensure_ascii=False)
            
    if final_anuladas:
        with open(ARQUIVO_ANULADAS, 'w', encoding='utf-8') as f:
            json.dump(final_anuladas, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    main()