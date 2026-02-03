import json
import os
import argparse

def main():
    parser = argparse.ArgumentParser(description="Mescla a Auditoria com o Dataset Original")
    parser.add_argument("dataset_original", help="Ex: dataset_completo_raciociniologico.json")
    parser.add_argument("dataset_audit", help="Ex: audit_dataset_completo_raciociniologico.json")
    args = parser.parse_args()

    # 1. Carrega os dados
    with open(args.dataset_original, 'r', encoding='utf-8') as f:
        questoes = json.load(f)
        
    with open(args.dataset_audit, 'r', encoding='utf-8') as f:
        auditoria_map = json.load(f)

    print(f"📦 Total de questões originais: {len(questoes)}")
    print(f"✅ Votos computados na auditoria: {len(auditoria_map)}")

    # 2. Processa o Filtro
    dataset_final = []
    aprovadas = 0
    reprovadas = 0
    pendentes = 0

    for q in questoes:
        id_tec = q.get('id_tec')
        status = auditoria_map.get(id_tec) # True, False ou None

        if status is True:
            # Adiciona a flag de auditado = true
            q['auditado'] = True
            dataset_final.append(q)
            aprovadas += 1
        elif status is False:
            reprovadas += 1
        else:
            pendentes += 1

    # 3. Salva o resultado
    nome_saida = args.dataset_original.replace(".json", "_AUDITADO_FINAL.json")
    with open(nome_saida, 'w', encoding='utf-8') as f:
        json.dump(dataset_final, f, indent=4, ensure_ascii=False)

    print("-" * 50)
    print(f"📊 RELATÓRIO FINAL DE AUDITORIA")
    print("-" * 50)
    print(f"👍 Aprovadas (Prontas pro BD): {aprovadas}")
    print(f"👎 Reprovadas (Descartadas):   {reprovadas}")
    print(f"⏳ Ignoradas/Pendentes:        {pendentes}")
    print(f"💾 Arquivo final gerado: {nome_saida}")

if __name__ == "__main__":
    main()