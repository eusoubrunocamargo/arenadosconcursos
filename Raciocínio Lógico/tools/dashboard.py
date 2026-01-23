import json
import os

ARQUIVO_JSON = "dataset_RL_imagens.json"
ARQUIVO_HTML = "dashboard_RL.html"

def main():
    print("--- GERADOR DE DASHBOARD VISUAL (RACIOCÍNIO LÓGICO) ---")

    if not os.path.exists(ARQUIVO_JSON):
        print(f"❌ Erro: {ARQUIVO_JSON} não encontrado.")
        return

    with open(ARQUIVO_JSON, 'r', encoding='utf-8') as f:
        questoes = json.load(f)

    # Injeta os dados JSON diretamente no JavaScript do HTML para evitar bloqueios de CORS do navegador
    json_dados = json.dumps(questoes, ensure_ascii=False)

    html_template = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Dashboard de Revisão - Raciocínio Lógico</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        
        <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
        <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
        <script>
            window.MathJax = {{
                tex: {{ inlineMath: [['$', '$'], ['\\\\(', '\\\\)']] }}
            }};
        </script>

        <style>
            body {{ background-color: #f8f9fa; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }}
            .card-questao {{ border-radius: 10px; border: 1px solid #dee2e6; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 30px; background: #fff; }}
            .header-questao {{ background-color: #343a40; color: #fff; padding: 10px 20px; border-top-left-radius: 10px; border-top-right-radius: 10px; font-weight: bold; display: flex; justify-content: space-between; }}
            .badge-banca {{ background-color: #007bff; font-size: 0.8rem; }}
            .badge-gab {{ background-color: #28a745; font-size: 0.8rem; }}
            .badge-id {{ background-color: #6c757d; font-size: 0.8rem; }}
            .img-container {{ text-align: center; background-color: #e9ecef; padding: 15px; border-radius: 8px; margin: 15px 0; }}
            .img-questao {{ max-width: 100%; max-height: 400px; border: 1px solid #ccc; }}
            .comando {{ font-size: 1.1rem; color: #333; margin-bottom: 15px; }}
            .enunciado {{ font-size: 1.2rem; font-weight: bold; color: #000; padding: 15px; background-color: #f1f8ff; border-left: 5px solid #007bff; margin-bottom: 15px; }}
            .btn-action {{ width: 100%; font-weight: bold; }}
            #sticky-footer {{ position: fixed; bottom: 0; width: 100%; background: #343a40; color: white; padding: 10px; text-align: center; box-shadow: 0 -2px 10px rgba(0,0,0,0.2); z-index: 1000; }}
        </style>
    </head>
    <body>

        <div class="container py-4">
            <h1 class="text-center mb-4">🔬 Revisão Visual: Raciocínio Lógico ({len(questoes)} Questões)</h1>
            <p class="text-center text-muted">Abaixo estão as questões que possuem imagens e fórmulas. Verifique se o texto e a imagem estão compreensíveis.</p>
            
            <div id="questoes-container"></div>
        </div>

        <div id="sticky-footer">
            <span id="counter">Aprovadas: 0 | Reprovadas: 0 | Restantes: {len(questoes)}</span>
            <button class="btn btn-success ms-4" onclick="exportarDados()">💾 Exportar Aprovadas (JSON)</button>
        </div>

        <script>
            const questoes = {json_dados};
            let revisadas = {{ aprovadas: [], reprovadas: [] }};

            function renderizar() {{
                const container = document.getElementById('questoes-container');
                container.innerHTML = "";

                questoes.forEach((q, index) => {{
                    // Prepara a imagem se existir
                    const imgHtml = q.image_url 
                        ? `<div class="img-container"><img src="${{q.image_url}}" class="img-questao" alt="Imagem da Questão"></div>` 
                        : `<span class="text-muted">(Sem imagem identificada)</span>`;

                    const html = `
                        <div class="card-questao" id="card-${{q.id_tec}}">
                            <div class="header-questao">
                                <span>Questão ${{index + 1}}</span>
                                <div>
                                    <span class="badge badge-id me-1">ID: ${{q.id_tec}}</span>
                                    <span class="badge badge-banca me-1">${{q.banca_orgao}}</span>
                                    <span class="badge badge-gab">Gabarito: ${{q.gabarito}}</span>
                                </div>
                            </div>
                            <div class="p-4">
                                <h6 class="text-muted">${{q.assunto}}</h6>
                                <hr>
                                ${{imgHtml}}
                                <div class="comando">${{q.comando.replace(/\\n/g, '<br>')}}</div>
                                <div class="enunciado">${{q.enunciado.replace(/\\n/g, '<br>')}}</div>
                                
                                <div class="row mt-4">
                                    <div class="col-6">
                                        <button class="btn btn-outline-success btn-action" onclick="aprovar('${{q.id_tec}}', this)">✅ Aprovar (Imagem e Texto OK)</button>
                                    </div>
                                    <div class="col-6">
                                        <button class="btn btn-outline-danger btn-action" onclick="reprovar('${{q.id_tec}}', this)">❌ Reprovar / Precisa de Ajuste</button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `;
                    container.innerHTML += html;
                }});

                // Força o MathJax a renderizar as fórmulas recém inseridas
                MathJax.typesetPromise();
            }}

            function atualizarContador() {{
                const total = questoes.length;
                const feitas = revisadas.aprovadas.length + revisadas.reprovadas.length;
                document.getElementById('counter').innerText = 
                    `Aprovadas: ${{revisadas.aprovadas.length}} | Reprovadas: ${{revisadas.reprovadas.length}} | Restantes: ${{total - feitas}}`;
            }}

            function aprovar(id, btnElement) {{
                const q = questoes.find(x => x.id_tec === id);
                revisadas.aprovadas.push(q);
                
                const card = document.getElementById(`card-${{id}}`);
                card.style.opacity = "0.4";
                card.style.pointerEvents = "none";
                atualizarContador();
            }}

            function reprovar(id, btnElement) {{
                const q = questoes.find(x => x.id_tec === id);
                revisadas.reprovadas.push(q);

                const card = document.getElementById(`card-${{id}}`);
                card.style.opacity = "0.4";
                card.style.pointerEvents = "none";
                atualizarContador();
            }}

            function exportarDados() {{
                if (revisadas.aprovadas.length === 0) {{
                    alert("Você ainda não aprovou nenhuma questão!");
                    return;
                }}
                
                const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(revisadas.aprovadas, null, 4));
                const downloadAnchorNode = document.createElement('a');
                downloadAnchorNode.setAttribute("href",     dataStr);
                downloadAnchorNode.setAttribute("download", "dataset_RL_imagens_APROVADAS.json");
                document.body.appendChild(downloadAnchorNode);
                downloadAnchorNode.click();
                downloadAnchorNode.remove();
            }}

            // Inicia
            window.onload = renderizar;
        </script>
    </body>
    </html>
    """

    with open(ARQUIVO_HTML, 'w', encoding='utf-8') as f:
        f.write(html_template)

    print(f"✅ Dashboard gerado com sucesso! Dê um duplo-clique no arquivo '{ARQUIVO_HTML}' para iniciar a revisão.")

if __name__ == "__main__":
    main()