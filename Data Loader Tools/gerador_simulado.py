import json
import psycopg
import sys
import os
import random
from collections import defaultdict

# =============================================================================
# 1. CONFIGURAÇÕES E MAPEAMENTO (O "DE-PARA")
# =============================================================================
DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'dbname': 'rinhadeconcurseiro',
    'user': 'postgres',
    'password': 'root'
}

DISTRIBUICAO = {
    "basicos": {
        "lingua_portuguesa": {"total": 25, "interpretacao": 15, "gramatica": 10},
        "lingua_inglesa": {"total": 10, "interpretacao": 5, "gramatica": 5},
        "raciocinio_logico": {"total": 10},
        "direito_administrativo": {"total": 25},
        "administracao_publica": {"total": 20}
    },
    "especificos": {
        "regimentos_etica": {"total": 40},
        "direito_constitucional": {"total": 30},
        "ciencia_politica": {"total": 10},
        "informatica": {"total": 10}
    }
}

MAPA_DB = {
    "lingua_portuguesa": ["Língua Portuguesa (Português)"],
    "lingua_inglesa": ["Língua Inglesa (Inglês)"],
    "raciocinio_logico": ["Raciocínio Lógico", "Matemática", "Estatística"],
    "direito_administrativo": ["Direito Administrativo (Doutrina e Leis Federais)"],
    "administracao_publica": ["Administração Geral e Pública"],
    "regimentos_etica": [
        "Legislação das Casas Legislativas", 
        "Legislação Geral Federal",
        "Redação Oficial"
    ],
    "direito_constitucional": ["Direito Constitucional (CF/1988 e Doutrina)"],
    "ciencia_politica": ["Ciências Políticas"],
    "informatica": [
        "Informática",
        "TI - Ciência de Dados e Inteligência Artificial", 
        "TI - Segurança da Informação",
        "TI - Redes de Computadores",
        "TI - Engenharia de Software"
    ]
}

# =============================================================================
# 2. MOTOR DE BUSCA NO BANCO (ALEATÓRIO)
# =============================================================================
def buscar_questoes(cursor, materias_db, limite, tipo_filtro=None):
    """
    Busca questões aleatórias no banco baseadas na matéria e num filtro de assunto.
    """
    if not materias_db or limite == 0:
        return []

    placeholders_materia = ', '.join(['%s'] * len(materias_db))
    parametros = list(materias_db)

    query = f"""
        SELECT q.id_tec, m.nome as materia, a.nome as assunto, q.comando, q.enunciado, q.gabarito, q.imagem_url
        FROM questao q
        JOIN materia m ON q.id_materia = m.id
        JOIN assunto a ON q.id_assunto = a.id
        WHERE q.ativo = true AND m.nome IN ({placeholders_materia})
    """

    if tipo_filtro == 'interpretacao':
        query += " AND a.nome ILIKE %s "
        parametros.append('%Interpretação%')
    elif tipo_filtro == 'gramatica':
        query += " AND a.nome NOT ILIKE %s "
        parametros.append('%Interpretação%')

    query += " ORDER BY RANDOM() LIMIT %s;"
    parametros.append(limite)

    cursor.execute(query, parametros)
    
    colunas = [desc[0] for desc in cursor.description]
    resultados = []
    for row in cursor.fetchall():
        resultados.append(dict(zip(colunas, row)))
        
    return resultados

# =============================================================================
# 3. ALGORITMO GERADOR DO SIMULADO
# =============================================================================
def gerar_simulado(numero_simulado, pasta_saida):
    """
    Gera um único simulado e salva na pasta de saída com o número indicado.
    """
    print(f"🔄 Gerando Simulado #{numero_simulado}...")
    simulado = {
        "metadados": {
            "numero_simulado": numero_simulado,
            "total_questoes": 0, 
            "basicos": 0, 
            "especificos": 0
        },
        "caderno_basico": [],
        "caderno_especifico": []
    }

    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:

                # --- PARTE 1: CONHECIMENTOS BÁSICOS ---
                for disciplina, regras in DISTRIBUICAO["basicos"].items():
                    materias_alvo = MAPA_DB.get(disciplina, [])
                    questoes_temp = []

                    if "interpretacao" in regras:
                        q_int = buscar_questoes(cursor, materias_alvo, regras["interpretacao"], 'interpretacao')
                        q_gram = buscar_questoes(cursor, materias_alvo, regras["gramatica"], 'gramatica')
                        questoes_temp.extend(q_int + q_gram)
                    else:
                        questoes_temp.extend(buscar_questoes(cursor, materias_alvo, regras["total"]))

                    simulado["caderno_basico"].extend(questoes_temp)

                # --- PARTE 2: CONHECIMENTOS ESPECÍFICOS ---
                for disciplina, regras in DISTRIBUICAO["especificos"].items():
                    materias_alvo = MAPA_DB.get(disciplina, [])
                    questoes_temp = buscar_questoes(cursor, materias_alvo, regras["total"])
                    simulado["caderno_especifico"].extend(questoes_temp)

        # --- FINALIZAÇÃO ---
        simulado["metadados"]["basicos"] = len(simulado["caderno_basico"])
        simulado["metadados"]["especificos"] = len(simulado["caderno_especifico"])
        simulado["metadados"]["total_questoes"] = simulado["metadados"]["basicos"] + simulado["metadados"]["especificos"]

        # Caminho e nome do arquivo
        nome_arquivo = f"simulado_pronto_numero_{numero_simulado}.json"
        caminho_completo = os.path.join(pasta_saida, nome_arquivo)

        with open(caminho_completo, 'w', encoding='utf-8') as f:
            json.dump(simulado, f, indent=4, ensure_ascii=False)

        print(f"   ✅ Salvo: {nome_arquivo} ({simulado['metadados']['total_questoes']} questões)")

    except psycopg.Error as e:
        print(f"   ❌ Erro no Banco de Dados ao gerar simulado #{numero_simulado}: {e}")
    except Exception as e:
        print(f"   ❌ Erro inesperado: {e}")

# =============================================================================
# 4. EXECUÇÃO PRINCIPAL
# =============================================================================
if __name__ == "__main__":
    # 1. Identificar quantidade de simulados via argumento (ex: --30)
    qtd_simulados = 1 # Valor padrão
    
    for arg in sys.argv:
        if arg.startswith("--") and arg[2:].isdigit():
            qtd_simulados = int(arg[2:])
            break
            
    print("=" * 60)
    print(f"🚀 INICIANDO GERAÇÃO EM LOTE")
    print(f"   Quantidade solicitada: {qtd_simulados}")
    print("=" * 60)

    # 2. Criar pasta de saída se não existir
    PASTA_SAIDA = "generated_simulados"
    if not os.path.exists(PASTA_SAIDA):
        os.makedirs(PASTA_SAIDA)
        print(f"📂 Pasta criada: {PASTA_SAIDA}")
    else:
        print(f"📂 Pasta selecionada: {PASTA_SAIDA}")

    # 3. Loop de geração
    for i in range(1, qtd_simulados + 1):
        gerar_simulado(i, PASTA_SAIDA)

    print("=" * 60)
    print("🏁 PROCESSO CONCLUÍDO.")