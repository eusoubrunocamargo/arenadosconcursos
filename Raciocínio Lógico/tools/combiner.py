import json
import re
import os

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
ARQUIVO_MAPA = "mapa_RL.json"
ARQUIVO_RICO = "dataset_RL_rico.json"

ARQUIVO_FINAL_TEXTO = "dataset_RL_final.json" # Vai direto pro Banco de Dados
ARQUIVO_FINAL_IMAGEM = "dataset_RL_imagens.json" # Precisa da sua curadoria visual

# ==============================================================================
# INTELIGÊNCIA DE TEXTO (V5)
# ==============================================================================

def separar_comando_enunciado(texto_completo):
    if not texto_completo: return "", ""

    gatilhos = [
        r'(julgue\s+o(s)?\s+.*?(item|itens)\s+(a\s+seguir|seguintes?|subsequentes?|próximos?).*?(:|\.))',
        r'(julgue\s+o(s)?\s+(seguintes?|próximos?|subsequentes?)\s+(item|itens).*?(:|\.))',
        r'(julgue\s+o(s)?\s+(item|itens).*?de\s+acordo.*?(:|\.))',
        r'(julgue\s+o(s)?\s+.*?(item|itens).*?(:|\.))',
        r'(assinale\s+a\s+opção\s+correta.*?(:|\.))'
    ]
    
    divisor = None
    match_pos = -1

    for g in gatilhos:
        iterator = re.finditer(g, texto_completo, re.IGNORECASE | re.DOTALL)
        for match in iterator:
            if match.end() > match_pos and match.end() < len(texto_completo) - 2:
                match_pos = match.end()
                divisor = match

    if divisor:
        comando = texto_completo[:divisor.end()].strip()
        enunciado = texto_completo[divisor.end():].strip()
        enunciado = re.sub(r'^[\.\:\-\s]+', '', enunciado)
        enunciado = re.sub(r'\s+(Certo|Errado)$', '', enunciado, flags=re.IGNORECASE)
        return comando, enunciado

    partes = texto_completo.split('\n\n')
    if len(partes) >= 2:
        enunciado_cand = partes[-1].strip()
        # Enunciado de matemática pode ser curto, mas o comando também pode ser.
        if len(enunciado_cand) < 600: 
            comando = "\n\n".join(partes[:-1]).strip()
            return comando, enunciado_cand
        
    return texto_completo, "[Enunciado não separado automaticamente]"

# ==============================================================================
# FUSÃO DOS DADOS
# ==============================================================================

def main():
    print("--- PASSO 3: FUSÃO E TRIAGEM (RACIOCÍNIO LÓGICO) ---")

    if not os.path.exists(ARQUIVO_MAPA) or not os.path.exists(ARQUIVO_RICO):
        print("❌ Erro: Arquivos base (mapa_RL.json ou dataset_RL_rico.json) não encontrados.")
        return

    # 1. Carrega o Mapa num Dicionário para busca rápida (O(1))
    with open(ARQUIVO_MAPA, 'r', encoding='utf-8') as f:
        mapa_lista = json.load(f)
    map_dict = {q['id_tec']: q for q in mapa_lista}

    # 2. Carrega o texto Rico da Web
    with open(ARQUIVO_RICO, 'r', encoding='utf-8') as f:
        rico_lista = json.load(f)

    questoes_texto = []
    questoes_imagem = []
    orfãs = 0

    # 3. Processamento e Fusão
    for q_rico in rico_lista:
        id_tec = q_rico.get('id_tec')
        
        # Ignora se por algum motivo não capturou o ID
        if id_tec not in map_dict:
            orfãs += 1
            continue

        q_mapa = map_dict[id_tec]

        # Separa Comando e Enunciado
        cmd, enun = separar_comando_enunciado(q_rico.get('texto_completo', ''))

        # Monta o objeto final
        questao_final = {
            "numero": q_mapa.get('numero', 0), # Será 0, pois descartamos a numeração do PDF
            "id_tec": id_tec,
            "link": f"www.tecconcursos.com.br/questoes/{id_tec}",
            "banca_orgao": q_mapa.get('banca_orgao'),
            "materia": q_mapa.get('materia'),
            "assunto": q_mapa.get('assunto'),
            "gabarito": q_mapa.get('gabarito'),
            "comando": cmd,
            "enunciado": enun,
            "has_latex": q_rico.get('has_latex', False),
            "image_url": q_rico.get('image_url', '')
        }

        # 4. Triagem (Com Imagem vs Sem Imagem)
        if q_rico.get('has_image', False):
            # Essas têm figuras. O DB precisa aceitar o campo image_url
            questoes_imagem.append(questao_final)
        else:
            # Texto/Latex Puro. Prontas para o banco!
            questoes_texto.append(questao_final)

    # Ordenação por ID
    questoes_texto.sort(key=lambda x: int(x['id_tec']))
    questoes_imagem.sort(key=lambda x: int(x['id_tec']))

    print("-" * 50)
    print(f"📊 RESUMO DA FUSÃO:")
    print(f"   ✅ Texto Puro / LaTeX (Prontas pro DB): {len(questoes_texto)}")
    print(f"   🖼️ Com Imagem (Para Revisão Visual): {len(questoes_imagem)}")
    print(f"   🗑️ Órfãs (ID não achado no mapa): {orfãs}")
    print("-" * 50)

    # Salva as prontas
    with open(ARQUIVO_FINAL_TEXTO, 'w', encoding='utf-8') as f:
        json.dump(questoes_texto, f, indent=4, ensure_ascii=False)
    print(f"Salvo: {ARQUIVO_FINAL_TEXTO}")

    # Salva as que precisam de imagem
    if questoes_imagem:
        with open(ARQUIVO_FINAL_IMAGEM, 'w', encoding='utf-8') as f:
            json.dump(questoes_imagem, f, indent=4, ensure_ascii=False)
        print(f"Salvo: {ARQUIVO_FINAL_IMAGEM}")

if __name__ == "__main__":
    main()