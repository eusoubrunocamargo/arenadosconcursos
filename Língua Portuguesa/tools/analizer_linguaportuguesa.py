#!/usr/bin/env python3
"""
Revisor de Questões de Língua Portuguesa
========================================
Analisa o JSON gerado pelo extrator especificamente para questões de Português.

Diferenças principais da versão original:
- Aceita comandos muito longos (devido aos textos de apoio).
- Alerta sobre comandos muito curtos (indício de perda do texto).
- Verifica padrões específicos de citação (linhas, parágrafos).

Uso:
    python analizer_portugues.py [arquivo.json opcional]
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

# Arquivos padrão (podem ser sobrescritos via argumento)
CAMINHO_JSON_PADRAO = "questoes_extraidas.json"
RELATORIO_SAIDA = "relatorio_portugues.txt"
JSON_PROBLEMATICAS = "revisar_portugues.json"

# --- Limites Ajustados para Português ---

# Textos de apoio podem ser grandes. 4000 caracteres cobre cerca de 1.5 páginas.
COMANDO_MAX_CHARS = 4000  

# Se o comando for muito curto (ex: só "Julgue o item."), perdemos o texto de apoio.
COMANDO_MIN_CHARS = 60    

# Enunciados (a assertiva em si) costumam ser diretos.
ENUNCIADO_MIN_CHARS = 10  
ENUNCIADO_MAX_CHARS = 1000 

# =============================================================================
# FUNÇÕES DE VERIFICAÇÃO
# =============================================================================

def verificar_comando_portugues(comando, id_questao):
    """Verifica problemas específicos no comando (Texto + Instrução)."""
    problemas = []
    
    # 1. Verificação de Tamanho (Lógica Invertida em relação ao Direito)
    tamanho = len(comando)
    
    # Em Português, comando curto é PERIGOSO (sinal de falta de texto)
    if tamanho < COMANDO_MIN_CHARS:
        problemas.append({
            "tipo": "ALERTA_TEXTO_AUSENTE",
            "msg": f"Comando muito curto ({tamanho} chars). Provável perda do texto de apoio.",
            "severidade": "ALTA"
        })
    
    # Se for absurdamente grande, pode ser erro de concatenação de duas questões
    if tamanho > COMANDO_MAX_CHARS:
        problemas.append({
            "tipo": "COMANDO_GIGANTE",
            "msg": f"Comando excede {COMANDO_MAX_CHARS} caracteres. Verificar concatenação.",
            "severidade": "MEDIA"
        })

    # 2. Verificação de Padrões de Sujeira
    if re.search(r'^\d+\s*[\).]', comando):
        problemas.append({
            "tipo": "NUMERO_INICIO",
            "msg": "Começa com número (falha na limpeza do ID).",
            "severidade": "BAIXA"
        })
        
    # 3. Verifica se tem a instrução de julgamento misturada no meio do texto
    # (Isso indicaria que o regex pegou pouco texto)
    if "Julgue o item" not in comando and "Julgue os itens" not in comando:
        # Às vezes o comando é diferente, mas é bom avisar
        problemas.append({
            "tipo": "INSTRUCAO_AUSENTE",
            "msg": "Não encontrou a frase padrão 'Julgue o item'.",
            "severidade": "MEDIA"
        })

    return problemas

def verificar_enunciado_portugues(enunciado, id_questao):
    """Verifica problemas na assertiva."""
    problemas = []
    tamanho = len(enunciado)

    # 1. Tamanho
    if tamanho < ENUNCIADO_MIN_CHARS:
        problemas.append({
            "tipo": "ENUNCIADO_CURTO",
            "msg": f"Enunciado muito curto ({tamanho} chars).",
            "severidade": "ALTA"
        })
    
    if tamanho > ENUNCIADO_MAX_CHARS:
        problemas.append({
            "tipo": "ENUNCIADO_LONGO",
            "msg": f"Enunciado muito longo ({tamanho} chars).",
            "severidade": "MEDIA"
        })

    # 2. Vazamentos de Gabarito (Certo/Errado no final)
    # Procura por "Certo" ou "Errado" isolados no final da string
    if re.search(r'\b(Certo|Errado)\.?\s*$', enunciado, re.IGNORECASE):
        problemas.append({
            "tipo": "GABARITO_VAZADO",
            "msg": "Possível gabarito (Certo/Errado) no final do enunciado.",
            "severidade": "ALTA"
        })

    return problemas

def revisar_questoes(questoes):
    """Itera sobre as questões e aplica as regras."""
    relatorio = {
        "total": len(questoes),
        "problematicas": [],
        "estatisticas": Counter()
    }
    
    for i, q in enumerate(questoes):
        # Garante ID
        q_id = q.get('id', f"IDX_{i+1}")
        comando = q.get('comando', '')
        enunciado = q.get('enunciado', '')
        
        probs_comando = verificar_comando_portugues(comando, q_id)
        probs_enunciado = verificar_enunciado_portugues(enunciado, q_id)
        
        todos_problemas = probs_comando + probs_enunciado
        
        if todos_problemas:
            # Classifica a severidade máxima desta questão
            severidades = [p['severidade'] for p in todos_problemas]
            if "ALTA" in severidades:
                nivel = "CRITICO"
            elif "MEDIA" in severidades:
                nivel = "ATENCAO"
            else:
                nivel = "INFO"

            relatorio["problematicas"].append({
                "id": q_id,
                "nivel": nivel,
                "problemas": todos_problemas,
                "preview_comando": comando[:100] + "...",
                "preview_enunciado": enunciado[:100] + "..."
            })
            
            # Contabiliza tipos de erro
            for p in todos_problemas:
                relatorio["estatisticas"][p['tipo']] += 1

    return relatorio

def gerar_relatorio_texto(resultado):
    """Formata o resultado em texto legível."""
    lines = []
    lines.append("RELATÓRIO DE QUALIDADE - LÍNGUA PORTUGUESA")
    lines.append("=" * 60)
    lines.append(f"Total Analisado: {resultado['total']}")
    lines.append(f"Questões com Alertas: {len(resultado['problematicas'])}")
    lines.append("-" * 60)
    lines.append("TOP PROBLEMAS ENCONTRADOS:")
    for tipo, count in resultado['estatisticas'].most_common():
        lines.append(f"  - {tipo}: {count}")
    lines.append("=" * 60)
    lines.append("\nDETALHAMENTO DAS QUESTÕES:\n")
    
    # Ordena para mostrar CRITICO primeiro
    ordem = {"CRITICO": 0, "ATENCAO": 1, "INFO": 2}
    questoes_ord = sorted(resultado['problematicas'], key=lambda x: ordem[x['nivel']])
    
    for item in questoes_ord:
        lines.append(f"[{item['nivel']}] Questão ID: {item['id']}")
        for p in item['problemas']:
            lines.append(f"   > {p['msg']}")
        lines.append(f"   Contexto (Comando): {item['preview_comando']}")
        lines.append(f"   Contexto (Enunciado): {item['preview_enunciado']}")
        lines.append("-" * 40)
        
    return "\n".join(lines)

def salvar_questoes_problematicas(resultado, caminho):
    """Salva apenas as questões ruins em um JSON separado para debug."""
    apenas_ids = [q['id'] for q in resultado['problematicas']]
    # Podemos salvar a estrutura completa ou só os IDs. 
    # Aqui salvaremos o relatório de erros estruturado.
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(resultado['problematicas'], f, indent=4, ensure_ascii=False)

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    # Permite passar o arquivo JSON como argumento
    arquivo_json = sys.argv[1] if len(sys.argv) > 1 else CAMINHO_JSON_PADRAO
    
    print(f"Iniciando análise para Língua Portuguesa...")
    
    if not Path(arquivo_json).exists():
        print(f"ERRO: Arquivo não encontrado: {arquivo_json}")
        sys.exit(1)
    
    # Carrega o JSON
    print(f"Carregando: {arquivo_json}")
    with open(arquivo_json, 'r', encoding='utf-8') as f:
        questoes = json.load(f)
    
    print(f"Questões carregadas: {len(questoes)}")
    
    # Executa a revisão
    print("Executando verificações heurísticas...")
    resultado = revisar_questoes(questoes)
    
    # Gera e salva o relatório TXT
    relatorio = gerar_relatorio_texto(resultado)
    with open(RELATORIO_SAIDA, 'w', encoding='utf-8') as f:
        f.write(relatorio)
    
    # Salva JSON com problemáticas
    if resultado["problematicas"]:
        salvar_questoes_problematicas(resultado, JSON_PROBLEMATICAS)
    
    print("\n" + "=" * 60)
    print("RESUMO DA ANÁLISE")
    print("=" * 60)
    total = resultado["total"]
    problematicas = len(resultado["problematicas"])
    
    print(f"  Total Processado: {total}")
    print(f"  Aprovadas (Sem alertas): {total - problematicas}")
    print(f"  Com Alertas: {problematicas}")
    print("-" * 60)
    print(f"Detalhes salvos em: {RELATORIO_SAIDA}")
    if problematicas > 0:
        print(f"JSON para debug salvo em: {JSON_PROBLEMATICAS}")