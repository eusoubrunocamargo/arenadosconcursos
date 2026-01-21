import json
import sys
from pathlib import Path

# Configurações de Arquivo
ARQUIVO_ENTRADA = "questoes_extraidas.json"
ARQUIVO_SAIDA = "dataset_portugues_llm.md"

def limpar_texto(texto):
    """Remove espaços extras e quebras de linha excessivas."""
    if not texto:
        return ""
    # Substitui múltiplos espaços/quebras por um único espaço
    return " ".join(texto.split())

def converter_para_markdown(questoes):
    """Converte a lista de questões para formato Markdown KV."""
    md_output = []
    
    # Cabeçalho do Documento
    md_output.append("# Dataset de Questões: Língua Portuguesa")
    md_output.append(f"> Total de Questões: {len(questoes)}")
    md_output.append("")
    
    for q in questoes:
      
        # Extração e Limpeza
        id_questao = q.get('numero', 'N/A')
        id_tec = q.get('id_tec', 'N/A')
        banca_orgao = q.get('banca_orgao', 'N/A')
        materia = q.get('materia', 'N/A')
        assunto = q.get('assunto', 'N/A')
        
        # O comando aqui é o Contexto (Texto de apoio)
        contexto = limpar_texto(q.get('comando', ''))
        
        # O enunciado é a assertiva a ser julgada
        enunciado = limpar_texto(q.get('enunciado', ''))
        
        gabarito = q.get('gabarito', 'N/A')
        
        # --- Construção do Bloco Markdown ---
        
        # Identificador único como cabeçalho nível 2
        md_output.append(f"## Questão {id_questao}")
        md_output.append(f"## ID Tec: {id_tec}")
        md_output.append(f"## Banca/Órgão: {banca_orgao}") 
        md_output.append(f"## Matéria:{materia}")
        
        # Metadados em itálico (opcional, ajuda o modelo a se situar mas não interfere)
        md_output.append(f"*Assunto: {assunto}*")
        md_output.append("")
        
        # Contexto: Se houver texto de apoio, colocamos em destaque
        if contexto:
            md_output.append("**Contexto / Texto de Apoio:**")
            md_output.append(f"> {contexto}")
            md_output.append("")
        
        # A pergunta em si
        md_output.append("**Enunciado:**")
        md_output.append(enunciado)
        md_output.append("")
        
        # O Output esperado (Gabarito)
        md_output.append("**Gabarito:**")
        md_output.append(gabarito)
        
        # Separador horizontal para clareza
        md_output.append("\n---\n")

    return "\n".join(md_output)

def main():
    path_entrada = Path(ARQUIVO_ENTRADA)
    
    if not path_entrada.exists():
        print(f"Erro: Arquivo {ARQUIVO_ENTRADA} não encontrado.")
        return

    print(f"Lendo {ARQUIVO_ENTRADA}...")
    with open(path_entrada, 'r', encoding='utf-8') as f:
        dados = json.load(f)

    print(f"Convertendo {len(dados)} questões...")
    conteudo_md = converter_para_markdown(dados)

    print(f"Salvando em {ARQUIVO_SAIDA}...")
    with open(ARQUIVO_SAIDA, 'w', encoding='utf-8') as f:
        f.write(conteudo_md)

    print("Concluído com sucesso!")

if __name__ == "__main__":
    main()