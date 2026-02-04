import json
import sys
import os
import argparse
import psycopg
from collections import defaultdict

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

def get_or_create_materia(cursor, nome):
    if not nome: return None
    nome = nome[:255]
    cursor.execute("SELECT id FROM materia WHERE nome = %s", (nome,))
    res = cursor.fetchone()
    if res: return res[0]
    # print(f"   ✨ [Nova Matéria] {nome}")
    cursor.execute("INSERT INTO materia (nome) VALUES (%s) RETURNING id", (nome,))
    return cursor.fetchone()[0]

def get_or_create_assunto(cursor, nome, id_materia):
    if not nome or not id_materia: return None
    nome = nome[:255]
    cursor.execute("SELECT id FROM assunto WHERE nome = %s AND id_materia = %s", (nome, id_materia))
    res = cursor.fetchone()
    if res: return res[0]
    # print(f"   ✨ [Novo Assunto] {nome}")
    cursor.execute("INSERT INTO assunto (nome, id_materia) VALUES (%s, %s) RETURNING id", (nome, id_materia))
    return cursor.fetchone()[0]

def gerar_relatorio_arvore(stats, nome_arquivo="arvore_assuntos.json"):
    """
    Converte o dicionário de estatísticas para o formato de lista JSON solicitado.
    """
    relatorio = []
    
    # Ordena por matéria com mais questões
    for materia, dados in sorted(stats.items(), key=lambda x: x[1]['total'], reverse=True):
        obj_materia = {
            "materia": materia,
            "totalQuestoes": dados['total'],
            # Ordena assuntos alfabeticamente
            "assuntos": dict(sorted(dados['assuntos'].items()))
        }
        relatorio.append(obj_materia)

    with open(nome_arquivo, 'w', encoding='utf-8') as f:
        json.dump(relatorio, f, indent=4, ensure_ascii=False)
    
    return nome_arquivo

def main():
    parser = argparse.ArgumentParser(description="Loader V5 - Estatísticas e Hierarquia")
    parser.add_argument("arquivo_json", help="Arquivo JSON gerado pelo scraper")
    parser.add_argument("--dry-run", action="store_true", help="Simulação sem persistência + Geração de Árvore JSON")
    
    args = parser.parse_args()

    if not os.path.exists(args.arquivo_json):
        print(f"❌ Arquivo {args.arquivo_json} não encontrado.")
        return

    print(f"📂 Lendo: {args.arquivo_json}")
    with open(args.arquivo_json, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    questoes_validas = [q for q in dados if q.get('capturado')]
    print(f"🚀 Iniciando processamento de {len(questoes_validas)} questões...")

    if args.dry_run:
        print("\n⚠️  MODO DRY-RUN: As alterações no banco serão revertidas ao final.")
        print("ℹ️  Um JSON com a árvore de assuntos será gerado.\n")

    # Estrutura para estatísticas: stats['Direito X'] = {'total': 0, 'assuntos': {'Assunto Y': 0}}
    stats = defaultdict(lambda: {'total': 0, 'assuntos': defaultdict(int)})

    try:
        with psycopg.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                
                sucessos = 0
                erros = 0

                for i, q in enumerate(questoes_validas):
                    try:
                        # --- 1. COLETA DE ESTATÍSTICAS (Memória) ---
                        materia_txt = q.get('materia', 'Geral')
                        assunto_txt = q.get('assunto', 'Geral')
                        
                        stats[materia_txt]['total'] += 1
                        stats[materia_txt]['assuntos'][assunto_txt] += 1

                        # --- 2. LÓGICA DE BANCO (SQL) ---
                        # Resolve IDs (cria se necessário dentro da transação)
                        id_materia = get_or_create_materia(cursor, materia_txt)
                        id_assunto = get_or_create_assunto(cursor, assunto_txt, id_materia)
                        
                        # Prepara dados
                        id_tec = q.get('id_tec')
                        comando = q.get('comando')
                        enunciado = q.get('enunciado')
                        imagem_url = q.get('imagem_url', '')
                        
                        gabarito_raw = q.get('gabarito', '').lower()
                        if 'certo' in gabarito_raw or 'c' == gabarito_raw: gabarito = 'Certo'
                        elif 'errado' in gabarito_raw or 'e' == gabarito_raw: gabarito = 'Errado'
                        elif 'anula' in gabarito_raw: gabarito = 'Anulada'
                        else: gabarito = q.get('gabarito')

                        sql = """
                            INSERT INTO questao 
                            (id_tec, id_materia, id_assunto, banca_orgao, comando, enunciado, gabarito, imagem_url, ativo, created_at, updated_at)
                            VALUES 
                            (%s, %s, %s, 'CEBRASPE', %s, %s, %s, %s, true, NOW(), NOW())
                            ON CONFLICT (id_tec) DO UPDATE SET
                                comando = EXCLUDED.comando,
                                enunciado = EXCLUDED.enunciado,
                                gabarito = EXCLUDED.gabarito,
                                imagem_url = EXCLUDED.imagem_url,
                                id_materia = EXCLUDED.id_materia,
                                id_assunto = EXCLUDED.id_assunto,
                                updated_at = NOW();
                        """
                        cursor.execute(sql, (id_tec, id_materia, id_assunto, comando, enunciado, gabarito, imagem_url))
                        
                        sucessos += 1
                        if (i+1) % 100 == 0:
                            print(f"   ⏳ Processados: {i+1}...")

                    except Exception as e:
                        print(f"   ❌ Erro ID {q.get('id_tec')}: {e}")
                        erros += 1

                # Finalização
                print("-" * 50)
                
                # Gera o relatório JSON independentemente de ser dry-run ou não
                arquivo_stats = gerar_relatorio_arvore(stats)
                print(f"📊 Árvore de Assuntos gerada: {arquivo_stats}")

                if args.dry_run:
                    conn.rollback()
                    print(f"✅ DRY-RUN FINALIZADO! (Rollback executado)")
                    print(f"   Simulação de Sucessos: {sucessos}")
                    print(f"   Simulação de Erros: {erros}")
                else:
                    conn.commit()
                    print(f"✅ CARGA REALIZADA COM SUCESSO!")
                    print(f"   Registros Salvos: {sucessos}")
                    print(f"   Erros: {erros}")
                print("-" * 50)

    except psycopg.Error as e:
        print(f"❌ Erro Crítico de Conexão: {e}")

if __name__ == "__main__":
    main()