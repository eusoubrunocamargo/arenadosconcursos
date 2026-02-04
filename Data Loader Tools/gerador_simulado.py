import json
import psycopg
import sys
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

# Distribuição solicitada no Edital (Total: 180 questões)
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

# Mapeamento: "Nome no Edital" -> ["Nomes Exatos no Banco de Dados (arvore_final)"]
MAPA_DB = {
    "lingua_portuguesa": ["Língua Portuguesa (Português)"],
    "lingua_inglesa": ["Língua Inglesa (Inglês)"],
    "raciocinio_logico": ["Raciocínio Lógico", "Matemática", "Estatística"],
    "direito_administrativo": ["Direito Administrativo (Doutrina e Leis Federais)"],
    "administracao_publica": ["Administração Geral e Pública"],
    
    # Agrupando tudo que cheira a Regimento/Ética/Legislação do Senado/Câmara
    "regimentos_etica": [
        "Legislação das Casas Legislativas", 
        "Legislação Geral Federal",
        "Redação Oficial"
    ],
    
    "direito_constitucional": ["Direito Constitucional (CF/1988 e Doutrina)"],
    "ciencia_politica": ["Ciências Políticas"], # Estava no plural no DB
    
    # Agrupando Informática Básica + TI Avançada
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
    tipo_filtro: 'interpretacao' (apenas assuntos com essa palavra) ou 'gramatica' (exclui interpretação)
    """
    placeholders_materia = ', '.join(['%s'] * len(materias_db))
    parametros = list(materias_db)

    # Base da Query
    query = f"""
        SELECT q.id_tec, m.nome as materia, a.nome as assunto, q.comando, q.enunciado, q.gabarito, q.imagem_url
        FROM questao q
        JOIN materia m ON q.id_materia = m.id
        JOIN assunto a ON q.id_assunto = a.id
        WHERE q.ativo = true AND m.nome IN ({placeholders_materia})
    """

    # Filtros Especiais para Línguas (Interpretação vs Gramática)
    if tipo_filtro == 'interpretacao':
        query += " AND a.nome ILIKE %s "
        parametros.append('%Interpretação%') # O % fica no parâmetro, não na query
    elif tipo_filtro == 'gramatica':
        query += " AND a.nome NOT ILIKE %s "
        parametros.append('%Interpretação%')

    # Ordenação Aleatória e Limite
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
def gerar_simulado():
    print("🚀 Iniciando geração do Simulado (180 Questões)...")
    simulado = {
        "metadados": {"total_questoes": 0, "basicos": 0, "especificos": 0},
        "caderno_basico": [],
        "caderno_especifico": []
    }

    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:

                # --- PARTE 1: CONHECIMENTOS BÁSICOS ---
                print("📚 Buscando Conhecimentos Básicos (90 q)...")
                for disciplina, regras in DISTRIBUICAO["basicos"].items():
                    materias_alvo = MAPA_DB.get(disciplina, [])
                    questoes_temp = []

                    # Tratamento Especial para Línguas (Port/Inglês)
                    if "interpretacao" in regras:
                        # Pega a cota de Interpretação
                        q_int = buscar_questoes(cursor, materias_alvo, regras["interpretacao"], 'interpretacao')
                        # Pega a cota de Gramática (o resto)
                        q_gram = buscar_questoes(cursor, materias_alvo, regras["gramatica"], 'gramatica')
                        questoes_temp.extend(q_int + q_gram)
                    else:
                        # Demais matérias básicas
                        questoes_temp.extend(buscar_questoes(cursor, materias_alvo, regras["total"]))

                    print(f"   ✓ {disciplina}: {len(questoes_temp)}/{regras['total']} encontradas.")
                    simulado["caderno_basico"].extend(questoes_temp)

                # --- PARTE 2: CONHECIMENTOS ESPECÍFICOS ---
                print("🔬 Buscando Conhecimentos Específicos (90 q)...")
                for disciplina, regras in DISTRIBUICAO["especificos"].items():
                    materias_alvo = MAPA_DB.get(disciplina, [])
                    
                    questoes_temp = buscar_questoes(cursor, materias_alvo, regras["total"])
                    
                    print(f"   ✓ {disciplina}: {len(questoes_temp)}/{regras['total']} encontradas.")
                    simulado["caderno_especifico"].extend(questoes_temp)

        # --- FINALIZAÇÃO E METADADOS ---
        simulado["metadados"]["basicos"] = len(simulado["caderno_basico"])
        simulado["metadados"]["especificos"] = len(simulado["caderno_especifico"])
        simulado["metadados"]["total_questoes"] = simulado["metadados"]["basicos"] + simulado["metadados"]["especificos"]

        # Salva o arquivo JSON final
        nome_arquivo = "simulado_pronto_180q.json"
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            json.dump(simulado, f, indent=4, ensure_ascii=False)

        print("-" * 50)
        print(f"✅ SIMULADO GERADO COM SUCESSO!")
        print(f"   Total Real: {simulado['metadados']['total_questoes']} questões")
        print(f"   Arquivo: {nome_arquivo}")
        print("-" * 50)

    except psycopg.Error as e:
        print(f"❌ Erro no Banco de Dados: {e}")

if __name__ == "__main__":
    gerar_simulado()