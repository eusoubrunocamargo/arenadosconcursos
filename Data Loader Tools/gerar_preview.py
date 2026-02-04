import json
import os
import argparse
import webbrowser

# ==============================================================================
# CONFIGURAÇÃO VISUAL (CSS)
# ==============================================================================
HTML_TEMPLATE_START = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Preview de Qualidade - {nome_arquivo}</title>
    <style>
        body {{ font-family: 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f0f2f5; margin: 0; padding: 20px; color: #333; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        
        .header {{ text-align: center; margin-bottom: 30px; }}
        .header h1 {{ margin: 0; color: #2c3e50; }}
        .badge-info {{ background: #e9ecef; padding: 5px 15px; border-radius: 20px; font-size: 0.9em; color: #495057; font-weight: bold; margin-top: 10px; display: inline-block; }}
        
        /* CARD PRINCIPAL */
        .card {{ 
            background: #fff; 
            border-radius: 16px; 
            box-shadow: 0 4px 12px rgba(0,0,0,0.08); 
            margin-bottom: 40px; 
            overflow: hidden; 
            border: 1px solid #dfe1e5;
        }}
        
        .card-header {{ 
            background: linear-gradient(135deg, #0061f2 0%, #00ba94 100%); 
            color: white; 
            padding: 12px 25px; 
            display: flex; 
            justify-content: space-between; 
            align-items: center;
        }}
        .card-header .id-badge {{ font-size: 1.1em; font-weight: bold; }}

        .card-body {{ padding: 25px; }}

        /* CAIXAS DE CAMPOS (ROUNDED BOXES) */
        .field-box {{ 
            border: 1px solid #e0e0e0; 
            border-radius: 12px; 
            padding: 20px; 
            margin-bottom: 20px; 
            background-color: #f8f9fa;
            position: relative;
        }}
        
        .field-label {{ 
            position: absolute; 
            top: -10px; 
            left: 15px; 
            background: #f8f9fa; 
            padding: 0 8px; 
            font-size: 0.75rem; 
            font-weight: 800; 
            color: #6c757d; 
            text-transform: uppercase; 
            letter-spacing: 0.5px;
            border: 1px solid #e0e0e0;
            border-radius: 6px;
        }}

        /* TIPOGRAFIA DOS CAMPOS */
        .texto-materia {{ color: #2c3e50; font-weight: 500; font-size: 0.95rem; }}
        
        .texto-comando {{ 
            font-family: 'Georgia', serif; 
            line-height: 1.6; 
            color: #000; 
            background: #fff; 
            padding: 15px; 
            border-radius: 8px; 
            border: 1px dashed #ccc;
        }}
        .texto-comando img {{ max-width: 100%; border: 3px solid #ffc107; border-radius: 4px; display: block; margin: 10px auto; }}

        .texto-enunciado {{ 
            font-family: 'Consolas', 'Courier New', monospace; 
            color: #d63384; 
            font-size: 0.9rem; 
            background: #fff0f6; 
            padding: 10px; 
            border-radius: 8px; 
            border: 1px solid #f8d7da;
        }}

        /* GABARITO E IMAGEM */
        .tag-gabarito {{ padding: 6px 14px; border-radius: 20px; font-weight: bold; color: white; font-size: 0.9em; }}
        .bg-certo {{ background-color: #28a745; }}
        .bg-errado {{ background-color: #dc3545; }}
        .bg-anulada {{ background-color: #6c757d; }}

        .box-imagem {{ border-color: #ffeeba; background-color: #fff3cd; }}
        .label-imagem {{ color: #856404; border-color: #ffeeba; background-color: #fff3cd; }}

    </style>
</head>
<body>
    <div class="container">
"""

def main():
    parser = argparse.ArgumentParser(description="Gera HTML de preview para dataset de questões.")
    
    # Argumento Posicional: O arquivo JSON
    parser.add_argument("arquivo_json", help="Caminho do arquivo JSON (ex: ./dataset.json)")
    
    # Argumento Opcional: Flag de Debug/Limite
    parser.add_argument("--debug", action="store_true", help="Ativa modo debug (limita a 10 questões)")
    parser.add_argument("--limit", type=int, default=0, help="Define um limite personalizado (ex: 50)")

    args = parser.parse_args()

    # Validação
    if not os.path.exists(args.arquivo_json):
        print(f"❌ Erro: O arquivo '{args.arquivo_json}' não foi encontrado.")
        return

    print(f"📂 Lendo: {args.arquivo_json}")
    
    try:
        with open(args.arquivo_json, 'r', encoding='utf-8') as f:
            dados = json.load(f)
    except Exception as e:
        print(f"❌ Erro ao ler JSON: {e}")
        return

    # Filtra apenas questões capturadas (HTML Rico)
    questoes_ricas = [q for q in dados if q.get('capturado')]
    total_ricas = len(questoes_ricas)

    # Aplica Limites
    limite = 0
    modo_texto = "Completo"

    if args.debug:
        limite = 10
        modo_texto = "Debug (10 itens)"
    elif args.limit > 0:
        limite = args.limit
        modo_texto = f"Limitado ({limite} itens)"

    if limite > 0:
        questoes_exibicao = questoes_ricas[:limite]
    else:
        questoes_exibicao = questoes_ricas

    print(f"📊 Questões com HTML: {total_ricas}")
    print(f"🚀 Gerando preview: {len(questoes_exibicao)} questões ({modo_texto})")

    # Gera Nome de Saída
    nome_base = os.path.basename(args.arquivo_json).replace(".json", "")
    arquivo_saida = f"preview_{nome_base}.html"

    # MONTAGEM DO HTML
    html = HTML_TEMPLATE_START.format(nome_arquivo=os.path.basename(args.arquivo_json))
    
    html += f"""
        <div class="header">
            <h1>Relatório de Qualidade</h1>
            <div class="badge-info">{modo_texto} • {len(questoes_exibicao)} Questões Exibidas</div>
        </div>
    """

    for i, q in enumerate(questoes_exibicao):
        # Dados com fallback
        id_tec = q.get('id_tec', '???')
        gabarito = q.get('gabarito', 'N/A')
        materia = q.get('materia', 'Não Identificada')
        assunto = q.get('assunto', 'Não Identificado')
        comando = q.get('comando', '')
        enunciado = q.get('enunciado', '')
        img_url = q.get('imagem_url', '')

        # Estilo Gabarito
        classe_gab = "bg-anulada"
        if gabarito == 'Certo': classe_gab = "bg-certo"
        elif gabarito == 'Errado': classe_gab = "bg-errado"

        # HTML da Imagem (Condicional)
        bloco_imagem = ""
        if img_url:
            bloco_imagem = f"""
            <div class="field-box box-imagem">
                <span class="field-label label-imagem">📸 Imagem Detectada</span>
                <div>
                    <strong>URL:</strong> <a href="{img_url}" target="_blank">{img_url}</a><br>
                    <img src="{img_url}" title="Imagem da questão {id_tec}">
                </div>
            </div>
            """

        # Bloco da Questão
        html += f"""
        <div class="card">
            <div class="card-header">
                <span class="id-badge">#{i+1} | ID {id_tec}</span>
                <span class="tag-gabarito {classe_gab}">{gabarito.upper()}</span>
            </div>
            <div class="card-body">
                
                <div class="field-box">
                    <span class="field-label">Classificação</span>
                    <div class="texto-materia">
                        <strong>Matéria:</strong> {materia} <br>
                        <strong>Assunto:</strong> {assunto}
                    </div>
                </div>

                <div class="field-box">
                    <span class="field-label">Comando (HTML Rico)</span>
                    <div class="texto-comando">
                        {comando if comando else "<em>[HTML Vazio ou não capturado]</em>"}
                    </div>
                </div>

                {bloco_imagem}

                <div class="field-box" style="background: #fff0f6; border-color: #f8d7da;">
                    <span class="field-label" style="color: #a71d2a; background: #fff0f6; border-color: #f8d7da;">Enunciado (IA)</span>
                    <div class="texto-enunciado">
                        {enunciado if enunciado else "<em>[Não detectado]</em>"}
                    </div>
                </div>

            </div>
        </div>
        """

    html += """
    </div>
    </body>
    </html>
    """

    with open(arquivo_saida, 'w', encoding='utf-8') as f:
        f.write(html)

    print("-" * 50)
    print(f"✅ Preview gerado: {arquivo_saida}")
    print("-" * 50)
    
    try:
        webbrowser.open(arquivo_saida)
    except:
        pass

if __name__ == "__main__":
    main()