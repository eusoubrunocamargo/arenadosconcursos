import json
import os

# ==============================================================================
# CONFIGURAÇÃO DOS ARQUIVOS
# ==============================================================================
ARQUIVO_TEXTO = "dataset_RL_final.json"               # Feito no Passo 3
ARQUIVO_IMAGENS = "dataset_RL_imagens_APROVADAS.json" # Baixado do Dashboard
ARQUIVO_DEFINITIVO = "dataset_RL_DEFINITIVO.json"     # O Banco Final

def main():
    print("--- UNIFICADOR FINAL: RACIOCÍNIO LÓGICO ---")

    if not os.path.exists(ARQUIVO_TEXTO):
        print(f"❌ Erro: Arquivo base {ARQUIVO_TEXTO} não encontrado.")
        return

    # 1. Carrega as questões de Texto/Latex
    with open(ARQUIVO_TEXTO, 'r', encoding='utf-8') as f:
        questoes_texto = json.load(f)
    print(f"📄 Carregadas {len(questoes_texto)} questões de Texto Puro/LaTeX.")

    # 2. Carrega as questões com Imagem Aprovadas (se o arquivo existir)
    questoes_imagem = []
    if os.path.exists(ARQUIVO_IMAGENS):
        with open(ARQUIVO_IMAGENS, 'r', encoding='utf-8') as f:
            questoes_imagem = json.load(f)
        print(f"🖼️ Carregadas {len(questoes_imagem)} questões com Imagem (Aprovadas).")
    else:
        print(f"⚠️ Aviso: Arquivo {ARQUIVO_IMAGENS} não encontrado. Nenhuma imagem adicionada.")

    # 3. Junta as duas listas
    questoes_totais = questoes_texto + questoes_imagem

    # 4. Ordena pelo ID para ficar organizado
    questoes_totais.sort(key=lambda x: int(x['id_tec']))

    # 5. Salva o Arquivo Definitivo
    with open(ARQUIVO_DEFINITIVO, 'w', encoding='utf-8') as f:
        json.dump(questoes_totais, f, indent=4, ensure_ascii=False)

    print("-" * 50)
    print(f"✅ SUCESSO! Banco de Raciocínio Lógico CONCLUÍDO.")
    print(f"📊 Total de Questões Válidas: {len(questoes_totais)}")
    print(f"💾 Arquivo final: {ARQUIVO_DEFINITIVO}")
    print("-" * 50)

if __name__ == "__main__":
    main()