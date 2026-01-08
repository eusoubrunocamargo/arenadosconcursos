#!/usr/bin/env python3
"""
Extrator de Questões do TEC Concursos
=====================================
Processa PDFs exportados do TEC Concursos e gera CSV/JSON estruturados.

Requisitos:
    pip install pdfplumber

Uso:
    python extrair_questoes_tec.py

Configuração:
    Altere a variável CAMINHO_PDF para o arquivo desejado.

Autor: Bruno
Versão: 2.0 - Correção de encoding + padrões de comando melhorados
"""

import re
import csv
import json
import sys
from pathlib import Path

# =============================================================================
# CONFIGURAÇÃO - Altere aqui conforme necessário
# =============================================================================

CAMINHO_PDF = "Direito Constitucional - 1 a 200 - Certo ou Errado.pdf"
NOME_SAIDA = "questoes_extraidas"  # Gera .csv e .json

# =============================================================================
# FUNÇÕES DE NORMALIZAÇÃO E LIMPEZA
# =============================================================================

def normalizar_encoding(texto: str) -> str:
    """
    Corrige problemas de encoding (double-encoding Latin-1/UTF-8).
    
    Problema comum: texto em Latin-1 é lido como UTF-8, gerando:
    - "Ã§" em vez de "ç"
    - "Ã£" em vez de "ã"
    - "Ã©" em vez de "é"
    
    Solução: re-codifica para Latin-1 e decodifica como UTF-8.
    """
    try:
        # Tenta corrigir double-encoding
        return texto.encode('latin-1').decode('utf-8')
    except (UnicodeDecodeError, UnicodeEncodeError):
        # Se falhar, retorna o texto original
        return texto


def limpar_texto(texto: str) -> str:
    """
    Remove espaços extras e normaliza o texto.
    """
    # Remove espaços múltiplos
    texto = re.sub(r'\s+', ' ', texto)
    return texto.strip()


# =============================================================================
# FUNÇÕES DE EXTRAÇÃO DO PDF
# =============================================================================

def extrair_texto_pdf(caminho_pdf: str) -> str:
    """
    Extrai todo o texto do PDF usando pdfplumber.
    
    Args:
        caminho_pdf: Caminho para o arquivo PDF
        
    Returns:
        String com todo o texto extraído, páginas separadas por quebra de linha
    """
    try:
        import pdfplumber
    except ImportError:
        print("=" * 60)
        print("ERRO: Biblioteca 'pdfplumber' não instalada.")
        print("Execute: pip install pdfplumber")
        print("=" * 60)
        sys.exit(1)
    
    # Verifica se o arquivo existe
    if not Path(caminho_pdf).exists():
        print(f"ERRO: Arquivo não encontrado: {caminho_pdf}")
        sys.exit(1)
    
    texto_completo = []
    
    print(f"Abrindo PDF: {caminho_pdf}")
    
    with pdfplumber.open(caminho_pdf) as pdf:
        total_paginas = len(pdf.pages)
        print(f"Total de páginas: {total_paginas}")
        
        for i, pagina in enumerate(pdf.pages, 1):
            texto = pagina.extract_text()
            if texto:
                # Aplica normalização de encoding em cada página
                texto = normalizar_encoding(texto)
                texto_completo.append(texto)
            
            # Progresso a cada 10 páginas
            if i % 10 == 0 or i == total_paginas:
                print(f"  Lendo página {i}/{total_paginas}...")
    
    return '\n'.join(texto_completo)


# =============================================================================
# FUNÇÕES AUXILIARES DE PARSING
# =============================================================================

def extrair_id_do_link(link: str) -> str:
    """
    Extrai o ID numérico do link da questão.
    
    Exemplo:
        Input:  "www.tecconcursos.com.br/questoes/3440688"
        Output: "3440688"
    """
    match = re.search(r'/questoes/(\d+)', link)
    return match.group(1) if match else ""


def separar_materia_assunto(texto: str) -> tuple:
    """
    Separa a string "Matéria (detalhes) - Assunto" em duas partes.
    
    Exemplo:
        Input:  "Direito Constitucional (CF/1988) - Eficácia das Normas"
        Output: ("Direito Constitucional (CF/1988)", "Eficácia das Normas")
    """
    if ' - ' in texto:
        partes = texto.split(' - ', 1)  # Divide apenas no primeiro " - "
        materia = partes[0].strip()
        assunto = partes[1].strip() if len(partes) > 1 else ""
        return materia, assunto
    return texto.strip(), ""


def separar_comando_enunciado(texto: str) -> tuple:
    """
    Separa o comando (instrução) do enunciado (assertiva).
    
    Comando: Instrução da banca (ex: "Julgue o item a seguir, acerca de X.")
    Enunciado: A assertiva a ser julgada (ex: "A CF é a lei suprema.")
    
    Versão 2.0: Padrões expandidos para cobrir mais variações CEBRASPE.
    """
    # Remove número inicial se houver (ex: "1) ")
    texto = re.sub(r'^\d+\)\s*', '', texto).strip()
    
    # Lista de padrões para detectar fim do comando
    # ORDEM IMPORTA: padrões mais específicos primeiro
    padroes_fim_comando = [
        # =================================================================
        # PADRÕES ESPECÍFICOS (mais restritivos)
        # =================================================================
        
        # Padrão com "(C ou E)" - formato alternativo do CEBRASPE
        r'(.+?julgue\s*\(C\s+ou\s+E\)\s+o\s+item\s+a\s+seguir\.)\s+',
        
        # "A respeito de X, julgue o item a seguir." (introdução + julgue)
        r'(.+?[Aa]\s+respeito\s+.+?julgue\s+o\s+item\s+(?:a\s+seguir|seguinte|subsequente)[^.]*\.)\s+(?=[A-Z])',
        
        # "Em relação a X, julgue o item a seguir."
        r'(.+?[Ee]m\s+rela[çc][ãa]o\s+.+?julgue\s+o\s+item\s+(?:a\s+seguir|seguinte|subsequente)[^.]*\.)\s+(?=[A-Z])',
        
        # "No que se refere a X, julgue o item a seguir."
        r'(.+?[Nn]o\s+que\s+se\s+refere\s+.+?julgue\s+o\s+item\s+(?:a\s+seguir|seguinte|subsequente)[^.]*\.)\s+(?=[A-Z])',
        
        # "Considerando X, julgue o item a seguir."
        r'(.+?[Cc]onsiderando\s+.+?julgue\s+o\s+item\s+(?:a\s+seguir|seguinte|subsequente)[^.]*\.)\s+(?=[A-Z])',
        
        # "Acerca de X, julgue o item a seguir."
        r'(.+?[Aa]cerca\s+d[eoa]\s+.+?julgue\s+o\s+item\s+(?:a\s+seguir|seguinte|subsequente)[^.]*\.)\s+(?=[A-Z])',
        
        # "Com base em X, julgue o item a seguir."
        r'(.+?[Cc]om\s+base\s+.+?julgue\s+o\s+item\s+(?:a\s+seguir|seguinte|subsequente)[^.]*\.)\s+(?=[A-Z])',
        
        # =================================================================
        # PADRÕES DE JULGAMENTO (variações de "julgue o item")
        # =================================================================
        
        # "Julgue o item a seguir." / "Julgue o próximo item." / "Julgue o item seguinte."
        r'([^.]*[Jj]ulgue\s+o\s+(?:próximo\s+)?item\s+(?:a\s+seguir|seguinte|subsequente|que\s+se\s+segue)[^.]*\.)\s+(?=[A-Z])',
        
        # "Julgue os itens a seguir." (plural)
        r'([^.]*[Jj]ulgue\s+os\s+itens?\s+(?:a\s+seguir|seguintes?|que\s+se\s+seguem?)[^.]*\.)\s+(?=[A-Z])',
        
        # "Julgue o item a seguir, com base em X." (vírgula após "seguir")
        r'([^.]*[Jj]ulgue\s+o\s+item\s+(?:a\s+seguir|seguinte),\s+[^.]+\.)\s+(?=[A-Z])',
        
        # =================================================================
        # PADRÕES GENÉRICOS (fallback)
        # =================================================================
        
        # Qualquer frase com "julgue" terminando em ponto, seguida de maiúscula
        r'([^.]*[Jj]ulgue[^.]+\.)\s+(?=[A-Z])',
        
        # Frase terminando em ponto seguida de maiúscula (último recurso)
        # Só usa se tiver palavras-chave de comando
        r'([^.]+(?:julgue|avalie|analise|verifique)[^.]*\.)\s+(?=[A-Z])',
    ]
    
    for padrao in padroes_fim_comando:
        match = re.search(padrao, texto, re.IGNORECASE)
        if match:
            comando = match.group(1).strip()
            inicio_enunciado = match.end()
            enunciado = texto[inicio_enunciado:].strip()
            
            # Remove "Certo Errado" do final do enunciado
            enunciado = re.sub(r'\s*(Certo\s+Errado|Certo|Errado)\s*$', '', enunciado).strip()
            
            if enunciado:  # Só retorna se tiver enunciado válido
                return comando, enunciado
    
    # =================================================================
    # FALLBACK FINAL: Tenta separar pelo primeiro ponto + maiúscula
    # =================================================================
    match_ponto = re.search(r'^([^.]+\.)\s+([A-Z].*)', texto)
    if match_ponto:
        possivel_comando = match_ponto.group(1).strip()
        possivel_enunciado = match_ponto.group(2).strip()
        
        # Verifica se o possível comando contém palavras-chave típicas
        palavras_comando = [
            'julgue', 'acerca', 'respeito', 'relação', 'base', 
            'considerando', 'refere', 'seguinte', 'item', 'quanto'
        ]
        
        if any(palavra in possivel_comando.lower() for palavra in palavras_comando):
            # Remove "Certo Errado" do final
            possivel_enunciado = re.sub(r'\s*(Certo\s+Errado|Certo|Errado)\s*$', '', possivel_enunciado).strip()
            return possivel_comando, possivel_enunciado
    
    # Se nada funcionou, retorna tudo como enunciado (comando vazio)
    texto_limpo = re.sub(r'\s*(Certo\s+Errado|Certo|Errado)\s*$', '', texto).strip()
    return "", texto_limpo


def filtrar_linhas(texto: str) -> list:
    """
    Remove linhas inúteis do texto extraído.
    
    Filtra:
    - Linhas vazias
    - Linhas com apenas números de questão (ex: "1) 2) 3)")
    - Cabeçalhos do caderno
    - Links do caderno (não das questões)
    """
    linhas = texto.splitlines()
    linhas_filtradas = []
    
    for linha in linhas:
        linha_limpa = linha.strip()
        
        # Pula linhas vazias
        if not linha_limpa:
            continue
        
        # Pula linhas com apenas números de questão (ex: "1) 2) 3) 4)")
        if re.match(r'^(?:\d+\)\s*)+$', linha_limpa):
            continue
        
        # Pula cabeçalhos do caderno
        if linha_limpa.startswith("Caderno de Questões"):
            continue
        if linha_limpa.startswith("Ordenação:"):
            continue
        if linha_limpa.startswith("https://www.tecconcursos.com.br/s/"):
            continue
        
        linhas_filtradas.append(linha_limpa)
    
    return linhas_filtradas


def eh_inicio_comando(linha: str) -> bool:
    """
    Verifica se a linha é o início do comando/enunciado da questão.
    
    Padrões detectados:
    - Começa com número: "1) Julgue o item..."
    - Começa com verbos típicos de comando CEBRASPE
    """
    # Começa com número de questão
    if re.match(r'^\d+\)', linha):
        return True
    
    # Verbos/frases típicas de início de comando
    comandos_tipicos = [
        'julgue', 'acerca de', 'com base', 'no que se refere',
        'a respeito', 'considerando', 'em relação', 'com relação',
        'sobre o', 'quanto a', 'à luz', 'de acordo', 'conforme',
        'segundo', 'tendo em vista', 'relativamente', 'no tocante'
    ]
    
    linha_lower = linha.lower()
    return any(linha_lower.startswith(cmd) for cmd in comandos_tipicos)


# =============================================================================
# FUNÇÃO PRINCIPAL DE EXTRAÇÃO
# =============================================================================

def extrair_questoes(linhas: list) -> list:
    """
    Processa as linhas filtradas e extrai as questões estruturadas.
    
    Args:
        linhas: Lista de linhas já filtradas do PDF
        
    Returns:
        Lista de dicionários, cada um representando uma questão
    """
    questoes = []
    indice = 0
    total_linhas = len(linhas)
    
    while indice < total_linhas:
        linha = linhas[indice]
        
        # Procura início de questão (link do TEC)
        if "tecconcursos.com.br/questoes/" not in linha:
            indice += 1
            continue
        
        # =====================================================================
        # INÍCIO DE UMA NOVA QUESTÃO
        # =====================================================================
        
        numero_questao = len(questoes) + 1
        link_questao = linha.strip()
        id_tec = extrair_id_do_link(link_questao)
        
        # Próxima linha: Banca/Órgão
        indice += 1
        if indice >= total_linhas:
            break
        banca_orgao = linhas[indice].strip()
        
        # ---------------------------------------------------------------------
        # Coletar MATÉRIA e ASSUNTO (pode ocupar múltiplas linhas)
        # ---------------------------------------------------------------------
        indice += 1
        materia_assunto_linhas = []
        
        while indice < total_linhas:
            linha_atual = linhas[indice]
            
            # Para quando encontrar o início do comando/enunciado
            if eh_inicio_comando(linha_atual):
                break
            
            # Para se encontrar outro link (próxima questão sem enunciado)
            if "tecconcursos.com.br/questoes/" in linha_atual:
                break
            
            # Para se encontrar gabarito (questão mal formatada)
            if linha_atual.startswith("Gabarito:"):
                break
            
            materia_assunto_linhas.append(linha_atual)
            indice += 1
        
        # Junta as linhas e separa matéria de assunto
        materia_assunto_texto = ' '.join(materia_assunto_linhas)
        materia, assunto = separar_materia_assunto(materia_assunto_texto)
        
        # ---------------------------------------------------------------------
        # Coletar COMANDO + ENUNCIADO (até encontrar "Gabarito:")
        # ---------------------------------------------------------------------
        texto_questao_linhas = []
        
        while indice < total_linhas:
            linha_atual = linhas[indice]
            
            # Para quando encontrar o gabarito
            if linha_atual.startswith("Gabarito:"):
                break
            
            # Para se encontrar outro link (questão sem gabarito)
            if "tecconcursos.com.br/questoes/" in linha_atual:
                break
            
            texto_questao_linhas.append(linha_atual)
            indice += 1
        
        # Monta o texto completo e separa comando do enunciado
        texto_questao = limpar_texto(' '.join(texto_questao_linhas))
        comando, enunciado = separar_comando_enunciado(texto_questao)
        
        # ---------------------------------------------------------------------
        # Extrair GABARITO
        # ---------------------------------------------------------------------
        gabarito = ""
        
        if indice < total_linhas and linhas[indice].startswith("Gabarito:"):
            # Extrai "Certo" ou "Errado" após "Gabarito:"
            match_gabarito = re.search(r'Gabarito:\s*(Certo|Errado)', linhas[indice])
            if match_gabarito:
                gabarito = match_gabarito.group(1)
            indice += 1
        
        # ---------------------------------------------------------------------
        # Validação e armazenamento
        # ---------------------------------------------------------------------
        
        # Só adiciona se tiver os campos mínimos
        if id_tec and enunciado and gabarito:
            questoes.append({
                "numero": numero_questao,
                "id_tec": id_tec,
                "link": link_questao,
                "banca_orgao": banca_orgao,
                "materia": materia,
                "assunto": assunto,
                "comando": comando,
                "enunciado": enunciado,
                "gabarito": gabarito
            })
        else:
            # Log de questão ignorada (útil para debug)
            print(f"  [AVISO] Questão ignorada (dados incompletos): ID={id_tec}")
    
    return questoes


# =============================================================================
# FUNÇÕES DE EXPORTAÇÃO
# =============================================================================

def salvar_csv(questoes: list, caminho: str):
    """Salva as questões em formato CSV."""
    if not questoes:
        print("Nenhuma questão para salvar.")
        return
    
    with open(caminho, 'w', newline='', encoding='utf-8') as f:
        # Usa as chaves do primeiro item como cabeçalho
        writer = csv.DictWriter(f, fieldnames=questoes[0].keys())
        writer.writeheader()
        writer.writerows(questoes)
    
    print(f"CSV salvo: {caminho}")


def salvar_json(questoes: list, caminho: str):
    """Salva as questões em formato JSON."""
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(questoes, f, ensure_ascii=False, indent=2)
    
    print(f"JSON salvo: {caminho}")


# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

def main():
    """Função principal do script."""
    print("=" * 60)
    print("EXTRATOR DE QUESTÕES - TEC CONCURSOS v2.0")
    print("=" * 60)
    
    # Etapa 1: Extrair texto do PDF
    print("\n[1/4] Extraindo texto do PDF...")
    texto = extrair_texto_pdf(CAMINHO_PDF)
    
    # Etapa 2: Filtrar linhas
    print("\n[2/4] Filtrando linhas...")
    linhas = filtrar_linhas(texto)
    print(f"  Linhas após filtro: {len(linhas)}")
    
    # Etapa 3: Extrair questões
    print("\n[3/4] Extraindo questões...")
    questoes = extrair_questoes(linhas)
    print(f"  Total de questões extraídas: {len(questoes)}")
    
    # Etapa 4: Salvar arquivos
    print("\n[4/4] Salvando arquivos...")
    salvar_csv(questoes, f"{NOME_SAIDA}.csv")
    salvar_json(questoes, f"{NOME_SAIDA}.json")
    
    # Resumo final
    print("\n" + "=" * 60)
    print("EXTRAÇÃO CONCLUÍDA!")
    print("=" * 60)
    print(f"  Questões extraídas: {len(questoes)}")
    print(f"  Arquivos gerados:")
    print(f"    - {NOME_SAIDA}.csv")
    print(f"    - {NOME_SAIDA}.json")
    print("=" * 60)


# Executa apenas se chamado diretamente (não quando importado)
if __name__ == "__main__":
    main()