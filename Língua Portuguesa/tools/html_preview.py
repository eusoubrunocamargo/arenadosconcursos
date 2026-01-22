import json
import os

# ==============================================================================
# CONFIGURAÇÃO
# ==============================================================================
ARQUIVO_JSON = "../../questoes_extraidas.json"
ARQUIVO_HTML = "preview_qualidade_portugues.html"

def gerar_html():
    # 1. Carregar os dados
    if not os.path.exists(ARQUIVO_JSON):
        print(f"Erro: O arquivo {ARQUIVO_JSON} não foi encontrado.")
        return

    with open(ARQUIVO_JSON, 'r', encoding='utf-8') as f:
        questoes = json.load(f)

    print(f"Gerando preview para {len(questoes)} questões...")

    # 2. Construir o HTML
    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Controle de Qualidade - Língua Portuguesa</title>
        <style>
            body {{
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background-color: #f0f2f5;
                color: #333;
                margin: 0;
                padding: 20px;
            }}
            .container {{
                max-width: 900px;
                margin: 0 auto;
            }}
            h1 {{
                text-align: center;
                color: #2c3e50;
            }}
            .card {{
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 5px rgba(0,0,0,0.1);
                margin-bottom: 30px;
                overflow: hidden;
                border: 1px solid #ddd;
            }}
            .card-header {{
                background-color: #ecf0f1;
                padding: 10px 20px;
                border-bottom: 1px solid #ddd;
                font-size: 0.85em;
                color: #555;
                display: flex;
                justify-content: space-between;
            }}
            .card-body {{
                padding: 20px;
            }}
            /* Estilo para o Texto de Apoio (Comando) */
            .comando {{
                font-family: 'Georgia', serif; /* Fonte de leitura de texto */
                font-size: 1.05em;
                line-height: 1.6;
                color: #2c3e50;
                background-color: #fafafa;
                padding: 15px;
                border-left: 5px solid #3498db; /* Azul para indicar texto base */
                white-space: pre-wrap; /* Mantém as quebras de linha originais do PDF */
                margin-bottom: 20px;
            }}
            /* Estilo para a Pergunta (Enunciado) */
            .enunciado {{
                font-weight: 600;
                font-size: 1.1em;
                color: #e74c3c; /* Vermelho escuro para destacar a ordem */
                padding: 15px;
                border: 1px dashed #e74c3c;
                background-color: #fff5f5;
                border-radius: 5px;
            }}
            .gabarito {{
                margin-top: 15px;
                font-weight: bold;
                color: #27ae60;
                text-align: right;
            }}
            .badge {{
                background: #34495e;
                color: white;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 0.8em;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Preview de Qualidade ({len(questoes)} Questões)</h1>
            <p style="text-align: center;">Verifique se o texto azul (Comando) está bem separado do texto vermelho (Pergunta).</p>
    """

    for q in questoes:
        # Tratamento de segurança para campos vazios
        numero = q.get('numero', '?')
        id_tec = q.get('id_tec', '?')
        banca = q.get('banca_orgao', 'Desconhecida')
        assunto = q.get('assunto', 'Geral')
        
        # Importante: replace para escapar HTML básico se necessário, 
        # mas aqui focamos em exibir o texto cru
        comando = q.get('comando', '').replace("<", "&lt;")
        enunciado = q.get('enunciado', '').replace("<", "&lt;")
        gabarito = q.get('gabarito', 'N/A')

        html += f"""
            <div class="card">
                <div class="card-header">
                    <span><span class="badge">Q.{numero}</span> ID: {id_tec}</span>
                    <span>{banca} | {assunto}</span>
                </div>
                <div class="card-body">
                    <div class="comando">{comando}</div>
                    
                    <div class="enunciado">{enunciado}</div>
                    
                    <div class="gabarito">Gabarito: {gabarito}</div>
                </div>
            </div>
        """

    html += """
        </div>
    </body>
    </html>
    """

    # 3. Salvar o arquivo
    with open(ARQUIVO_HTML, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"Sucesso! Abra o arquivo '{ARQUIVO_HTML}' no seu navegador.")

if __name__ == "__main__":
    gerar_html()