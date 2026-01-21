import re
import json
import pdfplumber
import glob
import os
from pathlib import Path

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
# Procura todos os PDFs na pasta pai (nível da matéria)
PADRAO_PDF = "../Língua Portuguesa - *.pdf"
ARQUIVO_SAIDA = "dataset_portugues_v1.json"

# ==============================================================================
# LÓGICA DE EXTRAÇÃO
# ==============================================================================

def limpar_texto(texto):
    """Remove quebras de linha excessivas e espaços duplos."""
    if not texto: return ""
    # Substitui quebras múltiplas por uma quebra dupla (parágrafo)
    texto = re.sub(r'\n{3,}', '\n\n', texto)
    return texto.strip()

def separar_comando_enunciado(texto_completo):
    """
    Separa o Texto de Apoio (Comando) da Pergunta Específica (Enunciado).
    Estratégia: Procura a frase imperativa 'Julgue o item' como divisor.
    """
    # Lista de gatilhos comuns do CESPE/Cebraspe
    gatilhos = [
        r'(Com base no texto.*?julgue os? itens?)',
        r'(Julgue os? (próximos? )?itens?)', 
        r'(Acerca d.*?julgue os? itens?)',
        r'(Com relação a.*?julgue os? itens?)',
        r'(No que se refere a.*?julgue os? itens?)',
        r'(A respeito d.*?julgue os? itens?)'
    ]
    
    divisor = None
    match_pos = -1
    tamanho_gatilho = 0

    # Tenta encontrar o primeiro gatilho que aparece no texto
    for g in gatilhos:
        match = re.search(g, texto_completo, re.IGNORECASE | re.DOTALL)
        if match:
            if match_pos == -1 or match.start() < match_pos:
                match_pos = match.start()
                divisor = match
                tamanho_gatilho = match.end() - match.start()

    if divisor:
        # Tudo antes do gatilho + o gatilho = COMANDO (Inclui o Texto de Apoio)
        comando = texto_completo[:divisor.end()].strip()
        
        # Tudo depois = ENUNCIADO (A pergunta específica)
        enunciado = texto_completo[divisor.end():].strip()
        
        # Limpeza fina
        enunciado = re.sub(r'^[\.\s]+', '', enunciado) # Remove ponto inicial
        
        return comando, enunciado
    
    # Fallback: Se não achar "Julgue", retorna tudo como comando para não perder dados
    return texto_completo, "[Enunciado não separado automaticamente]"

def processar_pdf(caminho_pdf):
    print(f"   📄 A processar: {os.path.basename(caminho_pdf)}...")
    questoes = []
    
    try:
        texto_bruto = ""
        with pdfplumber.open(caminho_pdf) as pdf:
            for page in pdf.pages:
                t = page.extract_text()
                if t: texto_bruto += t + "\n"
    except Exception as e:
        print(f"      ❌ Erro ao ler PDF: {e}")
        return []

    linhas = texto_bruto.split('\n')
    
    q_atual = {}
    buffer_texto = []
    
    # Regex para identificar início de questão (ex: "1 Questão 123456")
    regex_inicio = re.compile(r'^(\d+)\s+Questão\s+(\d+)', re.IGNORECASE)
    
    # Regex para Metadados (Banca - Órgão/Ano)
    regex_meta = re.compile(r'([A-Z\s\(\)]+)\s+-\s+(.+?)/(\d{4})')
    
    # Regex para Gabarito
    regex_gab = re.compile(r'^Gabarito:\s*(Certo|Errado|[A-E])', re.IGNORECASE)

    for linha in linhas:
        linha = linha.strip()
        if not linha: continue

        # 1. Início de Nova Questão
        match_inicio = regex_inicio.match(linha)
        if match_inicio:
            # Salva a anterior
            if q_atual:
                full_text = "\n".join(buffer_texto)
                
                # Tenta extrair metadados do topo do texto se estiverem misturados
                if not q_atual.get('banca_orgao'):
                    match_meta = regex_meta.search(full_text)
                    if match_meta:
                        q_atual['banca_orgao'] = match_meta.group(0)
                        # Removemos a linha de metadados do texto para não sujar o comando
                        full_text = full_text.replace(match_meta.group(0), "")

                comando, enunciado = separar_comando_enunciado(full_text)
                q_atual['comando'] = limpar_texto(comando)
                q_atual['enunciado'] = limpar_texto(enunciado)
                questoes.append(q_atual)

            # Inicia nova estrutura
            q_atual = {
                "numero": int(match_inicio.group(1)),
                "id_tec": match_inicio.group(2),
                "link": f"https://www.tecconcursos.com.br/questoes/{match_inicio.group(2)}",
                "materia": "Língua Portuguesa",
                "banca_orgao": "",
                "gabarito": ""
            }
            buffer_texto = []
            continue

        # 2. Captura de Gabarito
        match_gab = regex_gab.search(linha)
        if match_gab and q_atual:
            q_atual['gabarito'] = match_gab.group(1)
            continue 

        # 3. Acumula texto do corpo
        if q_atual:
            buffer_texto.append(linha)

    # Salva a última do arquivo
    if q_atual:
        full_text = "\n".join(buffer_texto)
        if not q_atual.get('banca_orgao'):
            match_meta = regex_meta.search(full_text)
            if match_meta:
                q_atual['banca_orgao'] = match_meta.group(0)
                full_text = full_text.replace(match_meta.group(0), "")
        
        comando, enunciado = separar_comando_enunciado(full_text)
        q_atual['comando'] = limpar_texto(comando)
        q_atual['enunciado'] = limpar_texto(enunciado)
        questoes.append(q_atual)

    return questoes

def main():
    print("--- EXTRATOR DE LÍNGUA PORTUGUESA ---")
    lista_pdfs = glob.glob(PADRAO_PDF)
    
    if not lista_pdfs:
        print(f"Nenhum PDF encontrado com o padrão: {PADRAO_PDF}")
        return

    todas_questoes = []
    
    for arquivo in lista_pdfs:
        questoes = processar_pdf(arquivo)
        todas_questoes.extend(questoes)

    # Reordena por ID do Tec (opcional, para organização)
    todas_questoes.sort(key=lambda x: int(x['id_tec']) if x['id_tec'].isdigit() else 0)

    print(f"\n💾 Salvando {len(todas_questoes)} questões em {ARQUIVO_SAIDA}...")
    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        json.dump(todas_questoes, f, indent=4, ensure_ascii=False)
    
    print("Concluído.")

if __name__ == "__main__":
    main()