import pdfplumber
import re
import csv

# Caminho do PDF
caminho_pdf = "Direito Constitucional - 1 a 200 - Certo ou Errado.pdf"

# Etapa 1: Leitura e extração de texto
texto_pdf = ""
with pdfplumber.open(caminho_pdf) as pdf:
    for pagina in pdf.pages:
        texto_pdf += pagina.extract_text() + "\n"

# Etapa 2: Filtrar linhas úteis
linhas = texto_pdf.splitlines()
linhas_filtradas = []
for linha in linhas:
    linha_str = linha.strip()
    if re.match(r'^(?:\d+\)\s*)+$', linha_str):
        continue
    if linha_str.startswith("Caderno de Questões") or linha_str.startswith("Ordenação:"):
        continue
    linhas_filtradas.append(linha_str)

# Etapa 3: Extração das questões
questoes = []
indice = 0

while indice < len(linhas_filtradas):
    linha = linhas_filtradas[indice]
    if "tecconcursos.com.br/questoes/" in linha:
        numero_questao = len(questoes) + 1
        link_questao = linha.strip()
        banca_orgao = linhas_filtradas[indice + 1] if indice + 1 < len(linhas_filtradas) else ""
        assunto = linhas_filtradas[indice + 2] if indice + 2 < len(linhas_filtradas) else ""
        indice += 3

        # Captura enunciado até gabarito
        enunciado_linhas = []
        while indice < len(linhas_filtradas) and not linhas_filtradas[indice].startswith("Gabarito:"):
            enunciado_linhas.append(linhas_filtradas[indice])
            indice += 1

        # Gabarito
        gabarito = None
        if indice < len(linhas_filtradas) and linhas_filtradas[indice].startswith("Gabarito:"):
            gabarito = linhas_filtradas[indice].split("Gabarito:")[1].strip()
            indice += 1

        questoes.append({
            "numero_questao": numero_questao,
            "link": link_questao,
            "banca_orgao": banca_orgao,
            "assunto": assunto,
            "enunciado": " ".join(enunciado_linhas).strip(),
            "alternativas": "Certo;Errado",
            "gabarito": gabarito
        })
    else:
        indice += 1

# Etapa 4: Exportação para CSV
nome_csv = "questoes_direito_constitucional_completo.csv"
with open(nome_csv, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=questoes[0].keys())
    writer.writeheader()
    writer.writerows(questoes)

print(f"Arquivo CSV gerado com sucesso: {nome_csv}")
