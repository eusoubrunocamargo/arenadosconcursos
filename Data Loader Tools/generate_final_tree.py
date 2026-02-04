import json
import psycopg
import sys
from collections import defaultdict

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

def extrair_arvore():
    print("🔍 Conectando ao banco de dados...")
    
    # Dicionário padrão para agrupar: {'Nome da Matéria': ['Assunto 1', 'Assunto 2']}
    arvore = defaultdict(list)

    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                # Busca as matérias e seus respectivos assuntos, ordenados alfabeticamente.
                # O INNER JOIN garante que só virão matérias que tenham pelo menos 1 assunto.
                query = """
                    SELECT m.nome as materia, a.nome as assunto
                    FROM materia m
                    INNER JOIN assunto a ON m.id = a.id_materia
                    ORDER BY m.nome ASC, a.nome ASC;
                """
                
                cursor.execute(query)
                resultados = cursor.fetchall()

                for linha in resultados:
                    materia = linha[0]
                    assunto = linha[1]
                    arvore[materia].append(assunto)

        print(f"✅ Sucesso! {len(arvore)} matérias processadas.")

        # Converte o dicionário em uma lista estruturada de objetos (melhor para APIs e Front-end)
        arvore_final = []
        for materia, assuntos in arvore.items():
            arvore_final.append({
                "materia": materia,
                "assuntos": assuntos
            })

        # Salva o resultado em JSON
        nome_arquivo = "arvore_final_simulados.json"
        with open(nome_arquivo, 'w', encoding='utf-8') as f:
            json.dump(arvore_final, f, indent=4, ensure_ascii=False)

        print(f"💾 Árvore salva no arquivo: {nome_arquivo}")

    except psycopg.Error as e:
        print(f"❌ Erro de Banco de Dados: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Erro Inesperado: {e}")

if __name__ == "__main__":
    print("-" * 50)
    print("🌳 GERADOR DE ÁRVORE DE MATÉRIAS/ASSUNTOS")
    print("-" * 50)
    extrair_arvore()