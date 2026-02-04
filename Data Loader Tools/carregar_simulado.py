#!/usr/bin/env python3
"""
Script para carregar simulados no banco de dados PostgreSQL.
Lê arquivos JSON de simulados e insere nas tabelas simulado e simulado_questao.

Uso:
    python carga_simulados.py simulado_01.json --numero 1 --data 2026-02-05
    python carga_simulados.py pasta_simulados/ --data-inicio 2026-02-05
    python carga_simulados.py simulado.json --dry-run --verbose

Autor: Bruno / Claude
Versão: 1.0
"""

import json
import sys
import argparse
import re
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

try:
    import psycopg
except ImportError:
    print("Erro: psycopg não instalado. Execute: pip install 'psycopg[binary]'")
    sys.exit(1)

# =============================================================================
# CONFIGURAÇÃO DO BANCO DE DADOS
# =============================================================================

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'rinhadeconcurseiro',
    'user': 'postgres',
    'password': 'root'
}

# =============================================================================
# FUNÇÕES AUXILIARES
# =============================================================================

def conectar_banco() -> psycopg.Connection:
    """Estabelece conexão com o banco de dados."""
    try:
        conn = psycopg.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"Erro ao conectar ao banco: {e}")
        sys.exit(1)


def carregar_json(caminho: Path) -> Optional[Dict[str, Any]]:
    """Carrega e valida arquivo JSON."""
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        print(f"Erro ao decodificar JSON {caminho}: {e}")
        return None
    except Exception as e:
        print(f"Erro ao ler arquivo {caminho}: {e}")
        return None


def extrair_numero_simulado(caminho: Path, dados: Dict) -> Optional[int]:
    """
    Extrai o número do simulado.
    Tenta primeiro dos metadados, depois do nome do arquivo.
    """
    # Tenta dos metadados
    if 'metadados' in dados and 'numero' in dados['metadados']:
        return int(dados['metadados']['numero'])
    
    # Tenta do nome do arquivo (ex: simulado_01.json, simulado_pronto_180q.json)
    nome = caminho.stem.lower()
    
    # Procura padrões como _01, _1, _02, etc.
    match = re.search(r'_(\d+)', nome)
    if match:
        return int(match.group(1))
    
    return None


def buscar_questao_por_id_tec(cursor, id_tec: str, cache: Dict[str, int]) -> Optional[int]:
    """Busca o ID interno da questão pelo id_tec."""
    if id_tec in cache:
        return cache[id_tec]
    
    cursor.execute("SELECT id FROM questao WHERE id_tec = %s", (id_tec,))
    resultado = cursor.fetchone()
    
    if resultado:
        cache[id_tec] = resultado[0]
        return resultado[0]
    
    return None


def simulado_existe(cursor, numero: int) -> bool:
    """Verifica se já existe um simulado com este número."""
    cursor.execute("SELECT 1 FROM simulado WHERE numero = %s", (numero,))
    return cursor.fetchone() is not None


def carregar_cache_questoes(cursor) -> Dict[str, int]:
    """Carrega cache de id_tec -> id para todas as questões."""
    print("Carregando cache de questões...")
    cursor.execute("SELECT id_tec, id FROM questao WHERE id_tec IS NOT NULL")
    cache = {row[0]: row[1] for row in cursor.fetchall()}
    print(f"  {len(cache)} questões em cache")
    return cache


# =============================================================================
# FUNÇÕES DE PROCESSAMENTO
# =============================================================================

def processar_simulado(
    cursor,
    dados: Dict,
    numero: int,
    data_disponivel: date,
    titulo: Optional[str],
    cache_questoes: Dict[str, int],
    verbose: bool = False
) -> Tuple[bool, Dict[str, Any]]:
    """
    Processa um simulado e insere no banco.
    Retorna (sucesso, estatisticas).
    """
    estatisticas = {
        'questoes_basicas': 0,
        'questoes_especificas': 0,
        'questoes_nao_encontradas': [],
        'erros': []
    }
    
    # Extrair metadados
    metadados = dados.get('metadados', {})
    total_questoes = metadados.get('total_questoes', 180)
    qtd_basicas = metadados.get('basicos', 90)
    qtd_especificas = metadados.get('especificos', 90)
    
    # Gerar título se não fornecido
    if not titulo:
        titulo = f"Simulado {numero:02d}"
    
    # Inserir simulado
    cursor.execute("""
        INSERT INTO simulado (numero, titulo, data_disponivel, total_questoes, 
                              questoes_basicas, questoes_especificas)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id
    """, (numero, titulo, data_disponivel, total_questoes, qtd_basicas, qtd_especificas))
    
    id_simulado = cursor.fetchone()[0]
    
    if verbose:
        print(f"  Simulado #{numero} criado (id={id_simulado})")
    
    # Processar caderno básico
    caderno_basico = dados.get('caderno_basico', [])
    ordem = 1
    
    for questao in caderno_basico:
        id_tec = questao.get('id_tec')
        if not id_tec:
            estatisticas['erros'].append(f"Questão sem id_tec na ordem {ordem}")
            continue
        
        id_questao = buscar_questao_por_id_tec(cursor, id_tec, cache_questoes)
        
        if not id_questao:
            estatisticas['questoes_nao_encontradas'].append(id_tec)
            if verbose:
                print(f"    ⚠ Questão id_tec={id_tec} não encontrada no banco")
            continue
        
        cursor.execute("""
            INSERT INTO simulado_questao (id_simulado, id_questao, ordem, caderno)
            VALUES (%s, %s, %s, 'BASICO')
        """, (id_simulado, id_questao, ordem))
        
        estatisticas['questoes_basicas'] += 1
        ordem += 1
    
    # Processar caderno específico
    caderno_especifico = dados.get('caderno_especifico', [])
    
    for questao in caderno_especifico:
        id_tec = questao.get('id_tec')
        if not id_tec:
            estatisticas['erros'].append(f"Questão sem id_tec na ordem {ordem}")
            continue
        
        id_questao = buscar_questao_por_id_tec(cursor, id_tec, cache_questoes)
        
        if not id_questao:
            estatisticas['questoes_nao_encontradas'].append(id_tec)
            if verbose:
                print(f"    ⚠ Questão id_tec={id_tec} não encontrada no banco")
            continue
        
        cursor.execute("""
            INSERT INTO simulado_questao (id_simulado, id_questao, ordem, caderno)
            VALUES (%s, %s, %s, 'ESPECIFICO')
        """, (id_simulado, id_questao, ordem))
        
        estatisticas['questoes_especificas'] += 1
        ordem += 1
    
    return True, estatisticas


# =============================================================================
# FUNÇÃO PRINCIPAL
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Carrega simulados no banco de dados',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemplos:
  python carga_simulados.py simulado_01.json --numero 1 --data 2026-02-05
  python carga_simulados.py pasta_simulados/ --data-inicio 2026-02-05
  python carga_simulados.py simulado.json --dry-run --verbose
        """
    )
    parser.add_argument('entrada', nargs='+', help='Arquivo(s) JSON ou pasta com simulados')
    parser.add_argument('--numero', '-n', type=int, help='Número do simulado (para arquivo único)')
    parser.add_argument('--data', '-d', help='Data de disponibilização (YYYY-MM-DD)')
    parser.add_argument('--data-inicio', help='Data inicial para múltiplos simulados (YYYY-MM-DD)')
    parser.add_argument('--titulo', '-t', help='Título do simulado')
    parser.add_argument('--dry-run', action='store_true', help='Não persiste no banco')
    parser.add_argument('--verbose', '-v', action='store_true', help='Mostra detalhes')
    
    args = parser.parse_args()
    
    # Coletar arquivos JSON
    arquivos: List[Path] = []
    for entrada in args.entrada:
        path = Path(entrada)
        if path.is_dir():
            arquivos.extend(sorted(path.glob('*.json')))
        elif path.is_file() and path.suffix == '.json':
            arquivos.append(path)
        else:
            print(f"Aviso: {entrada} não é um arquivo JSON válido ou diretório")
    
    if not arquivos:
        print("Erro: Nenhum arquivo JSON encontrado")
        sys.exit(1)
    
    print(f"Encontrados {len(arquivos)} arquivo(s) para processar")
    
    # Conectar ao banco
    conn = conectar_banco()
    cursor = conn.cursor()
    
    # Carregar cache de questões
    cache_questoes = carregar_cache_questoes(cursor)
    
    # Processar cada arquivo
    total_processados = 0
    total_erros = 0
    total_questoes_inseridas = 0
    questoes_nao_encontradas_global: set = set()
    
    # Determinar data inicial
    data_atual: Optional[date] = None
    if args.data:
        data_atual = datetime.strptime(args.data, '%Y-%m-%d').date()
    elif args.data_inicio:
        data_atual = datetime.strptime(args.data_inicio, '%Y-%m-%d').date()
    
    for i, arquivo in enumerate(arquivos):
        print(f"\n[{i+1}/{len(arquivos)}] Processando: {arquivo.name}")
        
        # Carregar JSON
        dados = carregar_json(arquivo)
        if not dados:
            total_erros += 1
            continue
        
        # Determinar número do simulado
        if args.numero and len(arquivos) == 1:
            numero = args.numero
        else:
            numero = extrair_numero_simulado(arquivo, dados)
            if numero is None:
                numero = i + 1
                print(f"  Usando número sequencial: {numero}")
        
        # Verificar se simulado já existe
        if simulado_existe(cursor, numero):
            print(f"  ⚠ Simulado #{numero} já existe. Pulando...")
            continue
        
        # Determinar data
        if data_atual is None:
            print(f"  Erro: Data não especificada. Use --data ou --data-inicio")
            total_erros += 1
            continue
        
        data_simulado = data_atual
        
        # Incrementar data para próximo simulado (se múltiplos arquivos)
        if len(arquivos) > 1:
            data_atual = data_atual + timedelta(days=1)
        
        # Processar simulado
        try:
            sucesso, estatisticas = processar_simulado(
                cursor,
                dados,
                numero,
                data_simulado,
                args.titulo,
                cache_questoes,
                args.verbose
            )
            
            if sucesso:
                total_processados += 1
                total_questoes_inseridas += estatisticas['questoes_basicas'] + estatisticas['questoes_especificas']
                questoes_nao_encontradas_global.update(estatisticas['questoes_nao_encontradas'])
                
                print(f"  ✓ Básicas: {estatisticas['questoes_basicas']}, "
                      f"Específicas: {estatisticas['questoes_especificas']}, "
                      f"Data: {data_simulado}")
                
                if estatisticas['questoes_nao_encontradas']:
                    print(f"  ⚠ {len(estatisticas['questoes_nao_encontradas'])} questão(ões) não encontrada(s)")
            else:
                total_erros += 1
                
        except Exception as e:
            print(f"  ✗ Erro ao processar: {e}")
            total_erros += 1
            conn.rollback()
            continue
    
    # Commit ou rollback
    if args.dry_run:
        print("\n[DRY-RUN] Nenhuma alteração foi persistida")
        conn.rollback()
    else:
        conn.commit()
        print("\n✓ Alterações persistidas no banco")
    
    # Fechar conexão
    cursor.close()
    conn.close()
    
    # Relatório final
    print("\n" + "=" * 60)
    print("RELATÓRIO FINAL")
    print("=" * 60)
    print(f"Simulados processados:       {total_processados}")
    print(f"Simulados com erro:          {total_erros}")
    print(f"Total questões inseridas:    {total_questoes_inseridas}")
    
    if questoes_nao_encontradas_global:
        print(f"\nQuestões não encontradas ({len(questoes_nao_encontradas_global)}):")
        for id_tec in sorted(questoes_nao_encontradas_global)[:20]:
            print(f"  - {id_tec}")
        if len(questoes_nao_encontradas_global) > 20:
            print(f"  ... e mais {len(questoes_nao_encontradas_global) - 20}")
    
    print("=" * 60)


if __name__ == '__main__':
    main()