import json
import sys
from pathlib import Path

# ==============================================================================
# CONFIGURAÇÃO DOS ARQUIVOS
# ==============================================================================
ARQUIVO_PDF = "metadados_rl_v3.json"           # Dados estruturados (Gabarito, Ano)
ARQUIVO_WEB = "raciocinio_web_data.json"       # Conteúdo Rico (LaTeX, Imagens)
ARQUIVO_FINAL = "../dataset_final_rl.json"     # Resultado final (na pasta raiz da matéria)

def carregar_json(caminho):
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERRO: Arquivo não encontrado: {caminho}")
        return []

def merge_datasets(dados_pdf, dados_web):
    """
    Une os dados do PDF e da Web usando 'id_tec' como chave primária.
    """
    # Cria um dicionário indexado pelo ID do Tec para busca rápida
    # Nota: O extrator Web salva como 'id_tec_html' ou 'id_tec'
    mapa_web = {}
    for item in dados_web:
        # Tenta pegar ID, tratando possíveis variações de nome de chave
        chave_id = item.get('id_tec_html') or item.get('id_tec')
        if chave_id:
            mapa_web[str(chave_id)] = item
    
    dataset_final = []
    questoes_sem_match = []

    print(f"Indexadas {len(mapa_web)} questões da Web para cruzamento.")

    for q_pdf in dados_pdf:
        id_tec = str(q_pdf.get('id_tec'))
        
        # Tenta encontrar o conteúdo rico correspondente
        q_web = mapa_web.get(id_tec)
        
        item_final = {
            "numero": q_pdf['numero'],
            "id_tec": id_tec,
            "link": f"https://www.tecconcursos.com.br/questoes/{id_tec}",
            
            # --- DADOS DO PDF ---
            "banca": q_pdf.get('banca', ''),
            "orgao": q_pdf.get('orgao', ''),
            "ano": q_pdf.get('ano', ''),
            "materia": "Raciocínio Lógico",
            "gabarito": q_pdf.get('gabarito', ''),
            
            # --- DADOS DA WEB (ou Fallback) ---
            "comando": "",
            "imagens": [],
            "tem_latex": False,
            "tem_imagem": False
        }

        if q_web:
            # Enriquecimento com dados do Selenium
            # O campo 'comando_rico' vem do script web v4/final
            item_final["comando"] = q_web.get('comando_rico') or q_web.get('comando') or ""
            item_final["imagens"] = q_web.get('imagens_urls') or q_web.get('imagens') or []
            item_final["tem_latex"] = q_web.get('tem_latex', False)
            item_final["tem_imagem"] = q_web.get('tem_imagem', False)
            item_final["status_merge"] = "SUCESSO"
        else:
            # Caso não tenha baixado ainda via Selenium (ou falha de ID)
            item_final["status_merge"] = "PENDENTE_WEB"
            questoes_sem_match.append(id_tec)
            # Mantém vazio ou coloca aviso
            item_final["comando"] = "[AGUARDANDO EXTRAÇÃO WEB]"

        dataset_final.append(item_final)

    return dataset_final, questoes_sem_match

def main():
    print("--- MERGER RACIOCÍNIO LÓGICO ---")
    
    # 1. Carrega dados
    print(f"Lendo PDF: {ARQUIVO_PDF}")
    dados_pdf = carregar_json(ARQUIVO_PDF)
    
    print(f"Lendo Web: {ARQUIVO_WEB}")
    dados_web = carregar_json(ARQUIVO_WEB)

    if not dados_pdf:
        print("Abortando: Sem dados do PDF.")
        return

    # 2. Processa
    print("Cruzando informações...")
    final, erros = merge_datasets(dados_pdf, dados_web)

    # 3. Relatório
    total = len(final)
    sucessos = total - len(erros)
    
    print("-" * 40)
    print(f"Total Processado: {total}")
    print(f"Merge Completo (PDF+Web): {sucessos}")
    print(f"Pendentes de Web: {len(erros)}")
    print("-" * 40)
    
    if erros:
        print(f"IDs sem correspondência Web (Amostra): {erros[:5]}...")

    # 4. Salva
    with open(ARQUIVO_FINAL, 'w', encoding='utf-8') as f:
        json.dump(final, f, indent=4, ensure_ascii=False)
    
    print(f"\nArquivo Final gerado: {Path(ARQUIVO_FINAL).resolve()}")

if __name__ == "__main__":
    main()