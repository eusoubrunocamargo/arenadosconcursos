import json
import os
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)

DATASET_FILE = 'dataset_completo_raciociniologico.json'
AUDIT_FILE = 'audit_dataset_completo_raciociniologico.json'

# Carrega o Dataset Original
def load_dataset():
    with open(DATASET_FILE, 'r', encoding='utf-8') as f:
        # Filtra apenas os capturados para não perder tempo com os quebrados
        return [q for q in json.load(f) if q.get('capturado')]

# Carrega ou Cria o Arquivo de Auditoria
def load_audit():
    if os.path.exists(AUDIT_FILE):
        with open(AUDIT_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_audit(audit_data):
    with open(AUDIT_FILE, 'w', encoding='utf-8') as f:
        json.dump(audit_data, f, indent=4, ensure_ascii=False)

DATASET = load_dataset()
AUDIT_STATE = load_audit()

# ==============================================================================
# TEMPLATE HTML (FRONT-END)
# ==============================================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <title>Auditoria de Questões</title>
    <script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></script>
    <script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></script>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: #f4f6f9; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100vh; }
        header { background: #2c3e50; color: white; padding: 15px; display: flex; justify-content: space-between; align-items: center; }
        .progress { font-size: 1.2rem; font-weight: bold; }
        
        main { flex: 1; padding: 20px; max-width: 900px; margin: 0 auto; width: 100%; overflow-y: auto; }
        
        .card { background: white; padding: 25px; border-radius: 12px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
        .meta { display: flex; justify-content: space-between; color: #7f8c8d; font-size: 0.9rem; border-bottom: 1px solid #eee; padding-bottom: 10px; margin-bottom: 15px; }
        
        .box-html { background: #fff; padding: 15px; border: 1px dashed #bdc3c7; border-radius: 8px; margin-bottom: 15px; }
        .box-html img { max-width: 100%; }
        
        .box-enunciado { background: #e8f4fd; padding: 15px; border-left: 4px solid #3498db; font-family: monospace; font-size: 1.1em; color: #2980b9;}
        
        footer { background: #ecf0f1; padding: 15px; text-align: center; border-top: 2px solid #bdc3c7; position: sticky; bottom: 0; }
        .controls { display: flex; justify-content: center; gap: 20px; align-items: center; }
        
        .btn { padding: 10px 30px; border-radius: 30px; font-size: 1.2rem; font-weight: bold; border: 2px solid #bdc3c7; color: #7f8c8d; background: white; transition: 0.2s; }
        .btn.active-yes { background: #27ae60; color: white; border-color: #27ae60; box-shadow: 0 0 10px #27ae60; }
        .btn.active-no { background: #e74c3c; color: white; border-color: #e74c3c; box-shadow: 0 0 10px #e74c3c; }
        
        .status-badge { padding: 5px 10px; border-radius: 10px; font-weight: bold; }
        .status-true { background: #d5f5e3; color: #27ae60; }
        .status-false { background: #fadbd8; color: #e74c3c; }
        .status-null { background: #ebedef; color: #7f8c8d; }

        .helper { font-size: 0.8rem; color: #95a5a6; margin-top: 10px; }
    </style>
</head>
<body>

    <header>
        <div>🔍 Auditoria: <span id="materia-nome">...</span></div>
        <div class="progress">Questão <span id="idx-display">1</span> / <span id="total-display">...</span></div>
        <div>Status: <span id="status-display" class="status-badge status-null">Pendente</span></div>
    </header>

    <main>
        <div class="card">
            <div class="meta">
                <span><strong>ID TEC:</strong> <span id="q-id">...</span></span>
                <span><strong>Gabarito:</strong> <span id="q-gabarito">...</span></span>
            </div>
            
            <div style="margin-bottom: 10px; font-weight: bold; color: #34495e;">Comando (HTML Renderizado):</div>
            <div class="box-html" id="q-comando"></div>
            
            <div id="q-img-container" style="display:none; text-align: center; margin-bottom: 15px;">
                <img id="q-img" src="" style="max-height: 250px; border: 1px solid #ccc;">
            </div>

            <div style="margin-bottom: 10px; font-weight: bold; color: #34495e;">Enunciado (Extraído):</div>
            <div class="box-enunciado" id="q-enunciado"></div>
        </div>
    </main>

    <footer>
        <div class="controls">
            <span style="font-size: 1.5rem; color: #7f8c8d;">Aprovar?</span>
            <div id="btn-yes" class="btn">Sim [S]</div>
            <div id="btn-no" class="btn">Não [N]</div>
        </div>
        <div class="helper">Use <strong>← / →</strong> para navegar | <strong>S / N</strong> para selecionar | <strong>ENTER</strong> para confirmar voto</div>
    </footer>

    <script>
        let currentIndex = 0;
        let totalQuestions = 0;
        let currentChoice = null; // 'true' ou 'false'

        // Busca a questão via API
        async function fetchQuestion(index) {
            const res = await fetch(`/api/question/${index}`);
            const data = await res.json();
            
            totalQuestions = data.total;
            currentIndex = data.index;

            // Atualiza UI
            document.getElementById('idx-display').innerText = currentIndex + 1;
            document.getElementById('total-display').innerText = totalQuestions;
            document.getElementById('materia-nome').innerText = data.question.assunto;
            document.getElementById('q-id').innerText = data.question.id_tec;
            document.getElementById('q-gabarito').innerText = data.question.gabarito;
            document.getElementById('q-comando').innerHTML = data.question.comando;
            document.getElementById('q-enunciado').innerText = data.question.enunciado;
            
            if(data.question.imagem_url) {
                document.getElementById('q-img').src = data.question.imagem_url;
                document.getElementById('q-img-container').style.display = 'block';
            } else {
                document.getElementById('q-img-container').style.display = 'none';
            }

            // Status atual da auditoria
            const statusEl = document.getElementById('status-display');
            if (data.auditado === true) {
                statusEl.innerText = "Aprovada"; statusEl.className = "status-badge status-true";
            } else if (data.auditado === false) {
                statusEl.innerText = "Reprovada"; statusEl.className = "status-badge status-false";
            } else {
                statusEl.innerText = "Pendente"; statusEl.className = "status-badge status-null";
            }

            // Reset Escolha
            currentChoice = null;
            updateButtons();
            
            // Força o MathJax a re-renderizar caso haja fórmulas
            if (window.MathJax) { MathJax.typesetPromise(); }
        }

        // Salva o voto via API
        async function submitVote() {
            if (currentChoice === null) return;
            
            const id_tec = document.getElementById('q-id').innerText;
            await fetch('/api/vote', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id_tec: id_tec, auditado: currentChoice })
            });

            // Avança para a próxima questão automaticamente
            if (currentIndex < totalQuestions - 1) {
                fetchQuestion(currentIndex + 1);
            }
        }

        function updateButtons() {
            document.getElementById('btn-yes').classList.toggle('active-yes', currentChoice === true);
            document.getElementById('btn-no').classList.toggle('active-no', currentChoice === false);
        }

        // Controle de Teclado
        document.addEventListener('keydown', (e) => {
            if (e.key === "ArrowRight") { if(currentIndex < totalQuestions - 1) fetchQuestion(currentIndex + 1); }
            if (e.key === "ArrowLeft") { if(currentIndex > 0) fetchQuestion(currentIndex - 1); }
            
            if (e.key.toLowerCase() === "s") { currentChoice = true; updateButtons(); }
            if (e.key.toLowerCase() === "n") { currentChoice = false; updateButtons(); }
            
            if (e.key === "Enter") { submitVote(); }
        });

        // Inicia na última questão pendente ou na 0
        window.onload = () => fetchQuestion(0);
    </script>
</body>
</html>
"""

# ==============================================================================
# ROTAS FLASK
# ==============================================================================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/question/<int:idx>')
def get_question(idx):
    if idx < 0 or idx >= len(DATASET):
        return jsonify({"error": "Index out of bounds"}), 404
        
    question = DATASET[idx]
    id_tec = question['id_tec']
    audit_status = AUDIT_STATE.get(id_tec, None)

    return jsonify({
        "index": idx,
        "total": len(DATASET),
        "question": question,
        "auditado": audit_status
    })

@app.route('/api/vote', methods=['POST'])
def vote():
    data = request.json
    id_tec = data['id_tec']
    auditado = data['auditado']
    
    # Atualiza o estado na memória e salva no disco
    AUDIT_STATE[id_tec] = auditado
    save_audit(AUDIT_STATE)
    
    return jsonify({"success": True})

if __name__ == '__main__':
    # Cria arquivo audit vazio se não existir
    if not os.path.exists(AUDIT_FILE): save_audit({})
    print("🚀 Iniciando Dashboard de Auditoria...")
    print("👉 Acesse no navegador: http://127.0.0.1:5000")
    app.run(debug=True, port=5000)