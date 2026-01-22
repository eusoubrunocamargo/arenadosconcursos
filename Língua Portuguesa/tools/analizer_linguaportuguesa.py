import json
import re
import os

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
ARQUIVO_ENTRADA = "dataset_portugues_final.json"
ARQUIVO_APROVADO = "dataset_portugues_aprovado.json"
ARQUIVO_REVISAO = "dataset_portugues_revisao.json"

# ==============================================================================
# REGRAS DE QUALIDADE
# ==============================================================================

def auditar_questao(q):
    flags = []
    status = "APROVADA"

    # 1. Verificação de ID e Link
    if not q.get('id_tec') or not q.get('link'):
        flags.append("ID_AUSENTE")

    # 2. Verificação de Gabarito
    gab = q.get('gabarito', '').strip()
    if not gab or gab not in ["Certo", "Errado", "A", "B", "C", "D", "E"]:
        flags.append("GABARITO_INVALIDO")

    # 3. Verificação de Texto (Português exige textos longos)
    comando = q.get('comando', '').strip()
    enunciado = q.get('enunciado', '').strip()

    if len(comando) < 20:
        flags.append("COMANDO_MUITO_CURTO")
    
    if len(enunciado) < 5:
        flags.append("ENUNCIADO_MUITO_CURTO")

    # 4. Verificação de Separação (O ponto crítico)
    # Se o enunciado contiver "Julgue o item", a separação falhou e pegou o gatilho
    if "Julgue o item" in enunciado or "Julgue os itens" in enunciado:
        # Não reprova automaticamente, mas marca warning, pois as vezes faz parte da frase
        flags.append("POSSIVEL_FALHA_SEPARACAO") 

    # 5. Verificação de Falha Explícita
    if "[Enunciado não separado]" in enunciado:
        flags.append("FALHA_SEPARACAO_TOTAL")

    # DECISÃO FINAL
    if flags:
        status = "REVISAR"
    
    q['qa_status'] = status
    q['qa_flags'] = flags
    return q

def main():
    print("--- ANALISADOR DE QUALIDADE (LÍNGUA PORTUGUESA) ---")
    
    if not os.path.exists(ARQUIVO_ENTRADA):
        print(f"Arquivo {ARQUIVO_ENTRADA} não encontrado.")
        return

    with open(ARQUIVO_ENTRADA, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    aprovadas = []
    revisar = []
    stats_erros = {}

    for item in dados:
        q_auditada = auditar_questao(item)
        
        if q_auditada['qa_status'] == "APROVADA":
            aprovadas.append(q_auditada)
        else:
            revisar.append(q_auditada)
            for f in q_auditada['qa_flags']:
                stats_erros[f] = stats_erros.get(f, 0) + 1

    # Cálculo da Precisão
    total = len(dados)
    taxa = (len(aprovadas) / total * 100) if total > 0 else 0

    print(f"\n📊 RELATÓRIO FINAL")
    print(f"   Total Processado: {total}")
    print(f"   ✅ Aprovadas: {len(aprovadas)}")
    print(f"   ⚠️  Revisar:  {len(revisar)}")
    print(f"   🎯 Taxa de Precisão: {taxa:.2f}%")
    
    if stats_erros:
        print("\n🔍 Principais Motivos de Reprovação:")
        for k, v in stats_erros.items():
            print(f"   - {k}: {v}")

    # Salva arquivos
    with open(ARQUIVO_APROVADO, 'w', encoding='utf-8') as f:
        json.dump(aprovadas, f, indent=4, ensure_ascii=False)
    
    with open(ARQUIVO_REVISAO, 'w', encoding='utf-8') as f:
        json.dump(revisar, f, indent=4, ensure_ascii=False)

    print(f"\nArquivos gerados:")
    print(f"   -> {ARQUIVO_APROVADO} (Pronto para DB)")
    print(f"   -> {ARQUIVO_REVISAO} (Para QA Humano)")

if __name__ == "__main__":
    main()