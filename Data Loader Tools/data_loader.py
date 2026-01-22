#!/usr/bin/env python3
"""
Script de carga de questões para o banco PostgreSQL do Rinha de Concurseiro.

Uso:
    python carga_questoes.py arquivo.json [--dry-run] [--verbose]

Argumentos:
    arquivo.json    Arquivo JSON com as questões extraídas
    --dry-run       Executa sem persistir no banco (apenas validação)
    --verbose       Mostra detalhes de cada questão processada
"""

import json
import sys
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    print("Erro: psycopg não instalado. Execute: pip install psycopg[binary]")
    sys.exit(1)


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'rinhadeconcurseiro',
    'user': 'postgres',
    'password': 'root'
}

# Mapeamento de gabaritos aceitos
GABARITO_MAP = {
    # Certo
    'CERTO': 'CERTO',
    'C': 'CERTO',
    'V': 'CERTO',
    'VERDADEIRO': 'CERTO',
    'TRUE': 'CERTO',
    # Errado
    'ERRADO': 'ERRADO',
    'E': 'ERRADO',
    'F': 'ERRADO',
    'FALSO': 'ERRADO',
    'FALSE': 'ERRADO',
}


# =============================================================================
# FUNÇÕES DE BANCO DE DADOS
# =============================================================================

def conectar():
    """Estabelece conexão com o banco de dados."""
    try:
        conn = psycopg.connect(**DB_CONFIG, autocommit=False)
        return conn
    except psycopg.Error as e:
        print(f"Erro ao conectar ao banco: {e}")
        sys.exit(1)


def get_or_create_materia(cursor, nome, cache):
    """
    Busca ou cria matéria, retorna ID.
    Usa cache para evitar queries repetidas.
    """
    nome = nome.strip()
    
    if nome in cache['materias']:
        return cache['materias'][nome]
    
    cursor.execute("SELECT id FROM materia WHERE nome = %s", (nome,))
    result = cursor.fetchone()
    
    if result:
        cache['materias'][nome] = result[0]
        return result[0]
    
    cursor.execute(
        "INSERT INTO materia (nome, created_at) VALUES (%s, %s) RETURNING id",
        (nome, datetime.now())
    )
    materia_id = cursor.fetchone()[0]
    cache['materias'][nome] = materia_id
    cache['stats']['materias_criadas'] += 1
    
    return materia_id


def get_or_create_assunto(cursor, materia_id, nome, cache):
    """
    Busca ou cria assunto, retorna ID.
    Usa cache para evitar queries repetidas.
    """
    if not nome or not nome.strip():
        return None
    
    nome = nome.strip()
    cache_key = f"{materia_id}:{nome}"
    
    if cache_key in cache['assuntos']:
        return cache['assuntos'][cache_key]
    
    cursor.execute(
        "SELECT id FROM assunto WHERE id_materia = %s AND nome = %s",
        (materia_id, nome)
    )
    result = cursor.fetchone()
    
    if result:
        cache['assuntos'][cache_key] = result[0]
        return result[0]
    
    cursor.execute(
        "INSERT INTO assunto (id_materia, nome, created_at) VALUES (%s, %s, %s) RETURNING id",
        (materia_id, nome, datetime.now())
    )
    assunto_id = cursor.fetchone()[0]
    cache['assuntos'][cache_key] = assunto_id
    cache['stats']['assuntos_criados'] += 1
    
    return assunto_id


def questao_existe(cursor, id_tec, cache):
    """Verifica se questão já existe pelo id_tec."""
    if id_tec in cache['questoes_existentes']:
        return True
    
    cursor.execute("SELECT 1 FROM questao WHERE id_tec = %s", (id_tec,))
    existe = cursor.fetchone() is not None
    
    if existe:
        cache['questoes_existentes'].add(id_tec)
    
    return existe


def inserir_questao(cursor, questao_data):
    """Insere uma questão no banco."""
    cursor.execute("""
        INSERT INTO questao 
        (id_materia, id_assunto, id_tec, link, banca_orgao, comando, enunciado, gabarito, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        questao_data['materia_id'],
        questao_data['assunto_id'],
        questao_data['id_tec'],
        questao_data['link'],
        questao_data['banca_orgao'],
        questao_data['comando'],
        questao_data['enunciado'],
        questao_data['gabarito'],
        datetime.now()
    ))


# =============================================================================
# FUNÇÕES DE PROCESSAMENTO
# =============================================================================

def salvar_duplicadas(duplicadas: List[Dict[str, Any]], arquivo_origem: Path) -> Path:
    """
    Salva as questões duplicadas em um arquivo JSON.
    Retorna o caminho do arquivo gerado.
    """
    if not duplicadas:
        return None
    
    # Gerar nome do arquivo: duplicadas_<arquivo_original>_<timestamp>.json
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nome_base = arquivo_origem.stem  # Nome sem extensão
    nome_saida = f"duplicadas_{nome_base}_{timestamp}.json"
    arquivo_saida = arquivo_origem.parent / nome_saida
    
    # Estrutura do JSON de saída
    saida = {
        "metadata": {
            "arquivo_origem": str(arquivo_origem),
            "data_geracao": datetime.now().isoformat(),
            "total_duplicadas": len(duplicadas)
        },
        "questoes": duplicadas
    }
    
    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        json.dump(saida, f, ensure_ascii=False, indent=2)
    
    return arquivo_saida

def normalizar_gabarito(gabarito_raw):
    """
    Converte gabarito do JSON para o formato do banco.
    Retorna None se não for um gabarito válido de Certo/Errado.
    """
    if not gabarito_raw:
        return None
    
    valor = gabarito_raw.strip().upper()
    return GABARITO_MAP.get(valor)


def normalizar_link(link):
    """Adiciona protocolo https:// se necessário."""
    if not link:
        return None
    
    link = link.strip()
    if not link.startswith('http'):
        link = f"https://{link}"
    
    return link


def limpar_enunciado(enunciado, gabarito_raw):
    """
    Remove gabarito duplicado do final do enunciado.
    Alguns enunciados terminam com "Certo" ou "Errado" repetido.
    """
    if not enunciado:
        return enunciado
    
    # Remove trailing whitespace
    enunciado = enunciado.strip()
    
    # Padrões comuns de gabarito no final
    padroes = [
        r'\n?Certo\s*$',
        r'\n?Errado\s*$',
        r'\n?CERTO\s*$',
        r'\n?ERRADO\s*$',
    ]
    
    for padrao in padroes:
        enunciado = re.sub(padrao, '', enunciado, flags=re.IGNORECASE)
    
    return enunciado.strip()


def processar_questao(questao_json, cursor, cache, verbose=False):
    """
    Processa uma questão do JSON e prepara para inserção.
    Retorna dict com dados ou None se inválida.
    """
    id_tec = questao_json.get('id_tec')
    
    if not id_tec:
        return None, "id_tec ausente"
    
    # Verificar se já existe
    if questao_existe(cursor, id_tec, cache):
        return None, "duplicada"
    
    # Validar e normalizar gabarito
    gabarito_raw = questao_json.get('gabarito', '')
    gabarito = normalizar_gabarito(gabarito_raw)
    
    if not gabarito:
        return None, f"gabarito inválido: {gabarito_raw}"
    
    # Validar campos obrigatórios
    materia = questao_json.get('materia', '').strip()
    enunciado = questao_json.get('enunciado', '').strip()
    
    if not materia:
        return None, "matéria ausente"
    
    if not enunciado:
        return None, "enunciado ausente"
    
    # Buscar/criar matéria
    materia_id = get_or_create_materia(cursor, materia, cache)
    
    # Buscar/criar assunto
    assunto = questao_json.get('assunto', '')
    assunto_id = get_or_create_assunto(cursor, materia_id, assunto, cache) if assunto else None
    
    # Preparar dados
    return {
        'id_tec': id_tec,
        'materia_id': materia_id,
        'assunto_id': assunto_id,
        'link': normalizar_link(questao_json.get('link')),
        'banca_orgao': questao_json.get('banca_orgao', '').strip() or None,
        'comando': questao_json.get('comando', '').strip() or None,
        'enunciado': limpar_enunciado(enunciado, gabarito_raw),
        'gabarito': gabarito
    }, None


def carregar_questoes_existentes(cursor, cache):
    """Carrega IDs de questões existentes para o cache."""
    cursor.execute("SELECT id_tec FROM questao WHERE id_tec IS NOT NULL")
    for row in cursor.fetchall():
        cache['questoes_existentes'].add(row[0])
    
    print(f"  Cache: {len(cache['questoes_existentes'])} questões existentes carregadas")


def carregar_materias_existentes(cursor, cache):
    """Carrega matérias existentes para o cache."""
    cursor.execute("SELECT id, nome FROM materia")
    for row in cursor.fetchall():
        cache['materias'][row[1]] = row[0]
    
    print(f"  Cache: {len(cache['materias'])} matérias carregadas")


def carregar_assuntos_existentes(cursor, cache):
    """Carrega assuntos existentes para o cache."""
    cursor.execute("SELECT id, id_materia, nome FROM assunto")
    for row in cursor.fetchall():
        cache_key = f"{row[1]}:{row[2]}"
        cache['assuntos'][cache_key] = row[0]
    
    print(f"  Cache: {len(cache['assuntos'])} assuntos carregados")


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Carrega questões no banco de dados')
    parser.add_argument('arquivo', help='Arquivo JSON com as questões')
    parser.add_argument('--dry-run', action='store_true', help='Não persiste no banco')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mostra detalhes')
    parser.add_argument('--no-duplicadas', action='store_true', 
                        help='Não gera arquivo JSON com duplicadas')
    args = parser.parse_args()
    
    # Verificar arquivo
    arquivo = Path(args.arquivo)
    if not arquivo.exists():
        print(f"Erro: Arquivo não encontrado: {arquivo}")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"CARGA DE QUESTÕES - Rinha de Concurseiro")
    print(f"{'='*60}")
    print(f"Arquivo: {arquivo.name}")
    print(f"Dry-run: {'Sim' if args.dry_run else 'Não'}")
    print(f"{'='*60}\n")
    
    # Carregar JSON
    print("Carregando arquivo JSON...")
    try:
        with open(arquivo, 'r', encoding='utf-8') as f:
            questoes_json = json.load(f)
    except json.JSONDecodeError as e:
        print(f"Erro ao ler JSON: {e}")
        sys.exit(1)
    
    total_arquivo = len(questoes_json)
    print(f"  Total de questões no arquivo: {total_arquivo}\n")
    
    # Conectar ao banco
    print("Conectando ao banco de dados...")
    conn = conectar()
    cursor = conn.cursor()
    print("  Conexão estabelecida\n")
    
    # Inicializar cache e estatísticas
    cache = {
        'materias': {},
        'assuntos': {},
        'questoes_existentes': set(),
        'stats': {
            'materias_criadas': 0,
            'assuntos_criados': 0
        }
    }
    
    # Carregar dados existentes no cache
    print("Carregando cache...")
    carregar_questoes_existentes(cursor, cache)
    carregar_materias_existentes(cursor, cache)
    carregar_assuntos_existentes(cursor, cache)
    print()
    
    # Processar questões
    print("Processando questões...")
    
    importadas = 0
    ignoradas_duplicadas = 0
    erros = []
    duplicadas = []  # Lista para armazenar questões duplicadas
    
    for i, questao_json in enumerate(questoes_json, 1):
        id_tec = questao_json.get('id_tec', 'N/A')
        
        questao_data, erro = processar_questao(questao_json, cursor, cache, args.verbose)
        
        if erro == "duplicada":
            ignoradas_duplicadas += 1
            duplicadas.append(questao_json)  # Armazena a questão original
            if args.verbose:
                print(f"  [{i}/{total_arquivo}] {id_tec}: IGNORADA (duplicada)")
            continue
        
        if erro:
            erros.append(f"Questão {id_tec}: {erro}")
            if args.verbose:
                print(f"  [{i}/{total_arquivo}] {id_tec}: ERRO - {erro}")
            continue
        
        # Inserir questão
        if not args.dry_run:
            try:
                inserir_questao(cursor, questao_data)
                cache['questoes_existentes'].add(id_tec)
            except psycopg.Error as e:
                erros.append(f"Questão {id_tec}: Erro de banco - {e}")
                if args.verbose:
                    print(f"  [{i}/{total_arquivo}] {id_tec}: ERRO BD - {e}")
                continue
        
        importadas += 1
        
        if args.verbose:
            print(f"  [{i}/{total_arquivo}] {id_tec}: OK")
        elif i % 500 == 0:
            print(f"  Processadas: {i}/{total_arquivo}")
    
    # Commit ou rollback
    if args.dry_run:
        print("\n[DRY-RUN] Rollback - nenhuma alteração persistida")
        conn.rollback()
    else:
        print("\nCommit das alterações...")
        conn.commit()
    
    # Fechar conexão
    cursor.close()
    conn.close()
    
    # Salvar duplicadas em JSON
    arquivo_duplicadas = None
    if duplicadas and not args.no_duplicadas:
        arquivo_duplicadas = salvar_duplicadas(duplicadas, arquivo)
        print(f"\nDuplicadas exportadas para: {arquivo_duplicadas.name}")
    
    # Relatório final
    print(f"\n{'='*60}")
    print("RELATÓRIO DE IMPORTAÇÃO")
    print(f"{'='*60}")
    print(f"Total no arquivo:      {total_arquivo:>6}")
    print(f"Importadas:            {importadas:>6}")
    print(f"Ignoradas (duplicadas):{ignoradas_duplicadas:>6}")
    print(f"Erros:                 {len(erros):>6}")
    print(f"{'='*60}")
    print(f"Matérias criadas:      {cache['stats']['materias_criadas']:>6}")
    print(f"Assuntos criados:      {cache['stats']['assuntos_criados']:>6}")
    print(f"{'='*60}")
    
    if erros:
        print("\nERROS ENCONTRADOS:")
        for erro in erros[:20]:  # Mostra até 20 erros
            print(f"  - {erro}")
        if len(erros) > 20:
            print(f"  ... e mais {len(erros) - 20} erros")
    
    print()
    
    # Código de saída
    if erros:
        sys.exit(1)
    sys.exit(0)


if __name__ == '__main__':
    main()
