import json
import os

ARQUIVO_ENTRADA = "dataset_constitucional_final.json"
ARQUIVO_APROVADO = "dataset_constitucional_aprovado.json"
ARQUIVO_REVISAO = "dataset_constitucional_revisao.json"

def auditar_questao(q):
    flags = []
    status = "APROVADA"

    # ID e Link
    if not q.get('id_tec'): flags.append("ID_AUSENTE")

    # Gabarito
    gab = q.get('gabarito', '').strip()
    if not gab or gab not in ["Certo", "Errado", "A", "B", "C", "D", "E"]:
        flags.append("GABARITO_INVALIDO")

    # Textos
    cmd = q.get('comando', '').strip()
    enun = q.get('enunciado', '').strip()
    
    # Regra relaxada para DC: Comando pode ser curto
    if len(cmd) < 5: flags.append("COMANDO_MUITO_CURTO")
    if len(enun) < 10: flags.append("ENUNCIADO_MUITO_CURTO")
    
    if "[Enunciado não separado" in enun:
        flags.append("FALHA_SEPARACAO")

    # Metadados
    if not q.get('banca_orgao'): flags.append("BANCA_AUSENTE")
    if not q.get('assunto'): flags.append("ASSUNTO_AUSENTE")

    if flags: status = "REVISAR"
    
    q['qa_status'] = status
    q['qa_flags'] = flags
    return q

def main():
    print("--- ANALISADOR DIREITO CONSTITUCIONAL ---")
    if not os.path.exists(ARQUIVO_ENTRADA):
        print("Arquivo de entrada não encontrado.")
        return

    with open(ARQUIVO_ENTRADA, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    aprovadas = []
    revisar = []

    for item in dados:
        q = auditar_questao(item)
        if q['qa_status'] == "APROVADA":
            aprovadas.append(q)
        else:
            revisar.append(q)

    total = len(dados)
    precisao = (len(aprovadas) / total * 100) if total > 0 else 0

    print(f"Total: {total}")
    print(f"Aprovadas: {len(aprovadas)}")
    print(f"Revisar: {len(revisar)}")
    print(f"Precisão: {precisao:.2f}%")

    with open(ARQUIVO_APROVADO, 'w', encoding='utf-8') as f:
        json.dump(aprovadas, f, indent=4, ensure_ascii=False)
    
    if revisar:
        with open(ARQUIVO_REVISAO, 'w', encoding='utf-8') as f:
            json.dump(revisar, f, indent=4, ensure_ascii=False)

if __name__ == "__main__":
    main()