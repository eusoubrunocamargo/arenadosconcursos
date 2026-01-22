#!/usr/bin/env python3
"""
Extrator de Língua Portuguesa (Baseado na v2.1)
===============================================
Adaptação para processar TODOS os PDFs da pasta mantendo a lógica 
de extração que obteve o melhor resultado de separação.
"""

import re
import json
import glob
import os
import pdfplumber
from pathlib import Path

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================
# Busca todos os PDFs que começam com "Língua Portuguesa" na pasta pai
PADRAO_PDF = "../Língua Portuguesa - *.pdf"
ARQUIVO_SAIDA = "dataset_portugues_final.json"

# =============================================================================
# LÓGICA DO EXTRATOR V2.1 (Preservada)
# =============================================================================

def extrair_texto_pdf(caminho):
    """Lê o PDF e retorna texto bruto."""
    print(f"   📄 Lendo: {os.path.basename(caminho)}...")
    texto_completo = ""
    try:
        with pdfplumber.open(caminho) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: texto_completo += t + "\n"
    except Exception as e:
        print(f"      ❌ Erro ao ler PDF: {e}")
    return texto_completo

def filtrar_linhas(texto_bruto):
    """Limpa linhas inúteis (cabeçalhos repetitivos)."""
    linhas = texto_bruto.split('\n')
    linhas_uteis = []
    ignorar = [
        "https://www.tecconcursos.com.br",
        "Ordenação: Por Matéria",
        "Língua Portuguesa para Câmara"
    ]
    
    for linha in linhas:
        linha = linha.strip()
        if not linha: continue
        if any(x in linha for x in ignorar): continue
        linhas_uteis.append(linha)
    return linhas_uteis

def separar_comando_enunciado(texto_completo):
    """
    Lógica 'v2.1' de separação.
    Tenta identificar onde termina o texto de apoio e começa a ordem.
    """
    # Gatilhos comuns no final dos textos de Português do Cespe
    gatilhos = [
        r'(Julgue o item a seguir.*?(:|\.))',
        r'(Julgue os itens a seguir.*?(:|\.))',
        r'(Julgue o próximo item.*?(:|\.))',
        r'(Julgue os próximos itens.*?(:|\.))',
        r'(Julgue os itens.*?(:|\.))',
        r'(Com base no texto.*?julgue.*?)',
        r'(Acerca d.*?julgue.*?)',
        r'(A respeito d.*?julgue.*?)',
        r'(Considerando.*?julgue.*?)'
    ]
    
    divisor = None
    posicao_divisor = -1

    # Busca o gatilho que está mais próximo do fim do bloco, 
    # mas que ainda deixa espaço para o enunciado.
    for g in gatilhos:
        # Encontra todas as ocorrências
        iterator = re.finditer(g, texto_completo, re.IGNORECASE | re.DOTALL)
        for match in iterator:
            if match.start() > posicao_divisor:
                posicao_divisor = match.start()
                divisor = match

    if divisor:
        comando = texto_completo[:divisor.end()].strip()
        enunciado = texto_completo[divisor.end():].strip()
        
        # Limpeza fina
        enunciado = re.sub(r'^[\.\:\-\s]+', '', enunciado)
        # Remove vazamento de gabarito
        enunciado = re.sub(r'\s+(Certo|Errado)$', '', enunciado, flags=re.IGNORECASE)
        
        return comando, enunciado
    
    # Fallback da v2.1: Se não achar, tenta quebrar na última linha curta
    partes = texto_completo.split('\n')
    if len(partes) > 1:
        ultimo_paragrafo = partes[-1]
        # Se o último parágrafo for curto (< 300 chars) e o resto longo
        if len(ultimo_paragrafo) < 300 and len(texto_completo) > 500:
            enunciado = ultimo_paragrafo
            comando = "\n".join(partes[:-1])
            return comando, enunciado

    return texto_completo, "[Enunciado não separado]"

def processar_linhas(linhas):
    questoes = []
    
    # Regex fundamentais
    regex_url = re.compile(r'tecconcursos\.com\.br/questoes/(\d+)')
    regex_inicio = re.compile(r'^(\d+)\)\s*(.*)') # "1) Texto..."
    regex_gabarito = re.compile(r'^Gabarito:\s*(Certo|Errado|[A-E])', re.IGNORECASE)
    
    i = 0
    total = len(linhas)
    q_atual = None
    buffer_texto = []

    while i < total:
        linha = linhas[i]

        # 1. Identificou LINK (Início de bloco)
        match_url = regex_url.search(linha)
        if match_url:
            # Salva anterior
            if q_atual:
                full = "\n".join(buffer_texto)
                cmd, enun = separar_comando_enunciado(full)
                q_atual['comando'] = cmd
                q_atual['enunciado'] = enun
                questoes.append(q_atual)
                q_atual = None
                buffer_texto = []
            
            # Prepara nova
            id_tec = match_url.group(1)
            banca = ""
            materia = "Língua Portuguesa (Português)"
            assunto = ""
            
            # Tenta pegar metadados nas próximas linhas (Lookahead simples)
            offset = 1
            found_start = False
            
            while offset <= 6 and (i + offset) < total:
                prox = linhas[i + offset]
                
                # Pega Banca
                if not banca and ("CEBRASPE" in prox or "FGV" in prox):
                    banca = prox
                # Pega Assunto
                elif " - " in prox and not assunto and ("Português" in prox):
                    parts = prox.split(" - ", 1)
                    if len(parts) > 1: assunto = parts[1]

                # Pega Início do Texto "1) ..."
                match_num = regex_inicio.match(prox)
                if match_num:
                    numero = int(match_num.group(1))
                    resto = match_num.group(2)
                    
                    q_atual = {
                        "numero": numero,
                        "id_tec": id_tec,
                        "link": f"www.tecconcursos.com.br/questoes/{id_tec}",
                        "banca_orgao": banca,
                        "materia": materia,
                        "assunto": assunto,
                        "gabarito": ""
                    }
                    if resto: buffer_texto.append(resto)
                    i += offset # Pula para cá
                    found_start = True
                    break
                
                offset += 1
            
            # Se não achou o "1)", avança só a linha do link
            if not found_start:
                 # Cria um placeholder para não perder o ID
                 q_atual = {
                        "numero": 0, "id_tec": id_tec,
                        "link": f"www.tecconcursos.com.br/questoes/{id_tec}",
                        "banca_orgao": banca, "materia": materia, "assunto": assunto,
                        "gabarito": ""
                    }
            
            i += 1
            continue

        # 2. Identificou Gabarito
        match_gab = regex_gabarito.search(linha)
        if match_gab and q_atual:
            q_atual['gabarito'] = match_gab.group(1)
        
        # 3. Corpo do texto
        elif q_atual and "www.tecconcursos" not in linha:
            buffer_texto.append(linha)
        
        i += 1

    # Salva a última
    if q_atual:
        full = "\n".join(buffer_texto)
        cmd, enun = separar_comando_enunciado(full)
        q_atual['comando'] = cmd
        q_atual['enunciado'] = enun
        questoes.append(q_atual)

    return questoes

# =============================================================================
# MAIN
# =============================================================================

def main():
    print("--- EXTRATOR PORTUGUÊS (LÓGICA V2.1 EM LOTE) ---")
    arquivos = glob.glob(PADRAO_PDF)
    
    if not arquivos:
        print(f"Nenhum arquivo encontrado em: {PADRAO_PDF}")
        return

    todas_questoes = []
    
    for arq in arquivos:
        texto = extrair_texto_pdf(arq)
        linhas = filtrar_linhas(texto)
        questoes = processar_linhas(linhas)
        todas_questoes.extend(questoes)
        print(f"      > Extraídas: {len(questoes)}")

    # Remove duplicatas (caso haja sobreposição de PDFs)
    # Usa id_tec como chave única
    unicas = {}
    for q in todas_questoes:
        if q.get('id_tec'):
            unicas[q['id_tec']] = q
    
    lista_final = list(unicas.values())
    
    # Ordena por número (se disponível) ou ID
    lista_final.sort(key=lambda x: int(x['id_tec']) if x['id_tec'].isdigit() else 0)

    print("-" * 50)
    print(f"TOTAL BRUTO: {len(todas_questoes)}")
    print(f"TOTAL ÚNICO: {len(lista_final)}")
    print("-" * 50)

    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(lista_final, f, indent=4, ensure_ascii=False)
    
    print(f"Salvo em: {ARQUIVO_SAIDA}")

if __name__ == "__main__":
    main()