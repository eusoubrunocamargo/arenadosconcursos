#!/usr/bin/env python3
"""
Extrator Raciocínio Lógico V3 (Baseado no Debug)
================================================
Adaptado para o padrão onde:
1. O ID é um link URL antes da questão.
2. A questão começa com "1) " (número e parêntese).
3. O Gabarito fecha o bloco.
"""

import re
import json
import csv
import pdfplumber
from pathlib import Path

# Caminho relativo assumindo execução dentro de /tools
CAMINHO_PDF = "../Raciocínio Lógico - 1.pdf"
NOME_SAIDA = "metadados_rl_v3"

def extrair_texto_pdf(caminho):
    print(f"Lendo: {caminho}")
    texto_completo = ""
    try:
        with pdfplumber.open(caminho) as pdf:
            for pagina in pdf.pages:
                t = pagina.extract_text()
                if t: texto_completo += t + "\n"
        return texto_completo
    except Exception as e:
        print(f"Erro ao abrir PDF: {e}")
        return ""

def extrair_questoes_v3(texto):
    linhas = texto.split('\n')
    questoes = []
    
    # --- PADRÕES IDENTIFICADOS NO DEBUG ---
    
    # Pega o ID da URL: www.tecconcursos.com.br/questoes/3303579
    regex_id_url = re.compile(r'tecconcursos\.com\.br/questoes/(\d+)')
    
    # Pega Metadados: CEBRASPE (CESPE) - Órgão/Cargo/Ano
    # Ex: CEBRASPE (CESPE) - Prof (InoversaSul)/InoversaSul/Matemática/Anos Finais/2025
    regex_meta = re.compile(r'^(.+?)\s+-\s+(.+?)/(\d{4})')
    
    # Pega o Início da Questão: "1) " ou "2) "
    regex_inicio = re.compile(r'^(\d+)\)\s*(.*)')
    
    # Pega Gabarito
    regex_gabarito = re.compile(r'^Gabarito:\s*(.+)', re.IGNORECASE)

    # Variáveis de Estado
    temp_id = None
    temp_banca_linha = None
    
    questao_atual = {}
    
    for linha in linhas:
        linha = linha.strip()
        if not linha: continue
        
        # 1. CAPTURA DE ID (Aparece antes da questão)
        match_id = regex_id_url.search(linha)
        if match_id:
            temp_id = match_id.group(1)
            continue # Vai para próxima linha buscar metadados

        # 2. CAPTURA DE METADADOS (Aparece antes da questão)
        # Só tentamos pegar metadados se já temos um ID engatilhado ou se parece muito com header
        if "CEBRASPE" in linha or "FGV" in linha or "FCC" in linha: # Heurística simples
            match_meta = regex_meta.search(linha)
            if match_meta:
                temp_banca_linha = linha # Guardamos a linha toda para processar depois se precisar
            continue

        # 3. INÍCIO DA QUESTÃO (O Gatilho Principal) -> "1) ..."
        match_inicio = regex_inicio.match(linha)
        if match_inicio:
            # Se havia uma questão aberta sem gabarito, salvamos ela agora (segurança)
            if questao_atual:
                questoes.append(questao_atual)
            
            numero = int(match_inicio.group(1))
            resto_texto = match_inicio.group(2)
            
            # Processa metadados guardados
            banca = ""
            ano = ""
            orgao = ""
            if temp_banca_linha:
                m = regex_meta.search(temp_banca_linha)
                if m:
                    banca = m.group(1).strip()
                    # O regex pega o meio como orgao, pode precisar ajuste fino depois
                    orgao = m.group(2).strip() 
                    ano = m.group(3).strip()

            questao_atual = {
                "numero": numero,
                "id_tec": temp_id, # O ID que capturamos linhas atrás
                "banca": banca,
                "orgao": orgao,
                "ano": ano,
                "gabarito": None, # Será preenchido no fechamento
                # "texto_inicio": resto_texto # Opcional, o Selenium vai pegar o texto rico
            }
            
            # Limpa temporários
            temp_id = None
            temp_banca_linha = None
            continue

        # 4. GABARITO (Fechamento da Questão)
        match_gab = regex_gabarito.search(linha)
        if match_gab and questao_atual:
            questao_atual['gabarito'] = match_gab.group(1).strip()
            
            # Salva e reseta
            questoes.append(questao_atual)
            questao_atual = {}
            continue

    # Salva a última se sobrou
    if questao_atual:
        questoes.append(questao_atual)

    return questoes

if __name__ == "__main__":
    if not Path(CAMINHO_PDF).exists():
        print(f"ERRO: PDF não encontrado em {CAMINHO_PDF}")
        exit()

    print("Extraindo texto...")
    texto = extrair_texto_pdf(CAMINHO_PDF)
    
    print("Processando padrões...")
    dados = extrair_questoes_v3(texto)
    
    print(f"Total extraído: {len(dados)}")
    
    if dados:
        print(f"Exemplo Q1: {dados[0]}")
        # Salva JSON
        with open(f"{NOME_SAIDA}.json", 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        print(f"Salvo em {NOME_SAIDA}.json")
        
        # Validação Rápida
        sem_id = [q['numero'] for q in dados if not q['id_tec']]
        if sem_id:
            print(f"ATENÇÃO: Questões sem ID TEC: {sem_id}")
        else:
            print("Sucesso: Todas as questões possuem ID TEC vinculado.")
    else:
        print("Ainda retornou 0. Verifique se o padrão '1) ' ocorre em todo o arquivo.")