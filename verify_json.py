#!/usr/bin/env python3
"""
Script de validação e correção de datasets de questões.

MODO 1: Validação (Gera arquivo de erros)
    python validate_json_before_load.py dataset.json

MODO 2: Correção (Aplica correções manuais)
    python validate_json_before_load.py dataset.json fix_dataset.json --fixer
"""

import json
import sys
import os
import argparse
from pathlib import Path

# Mapeamento de gabaritos aceitos
GABARITO_MAP = {
    'CERTO': 'CERTO', 'C': 'CERTO', 'V': 'CERTO', 'VERDADEIRO': 'CERTO', 'TRUE': 'CERTO',
    'ERRADO': 'ERRADO', 'E': 'ERRADO', 'F': 'ERRADO', 'FALSO': 'ERRADO', 'FALSE': 'ERRADO',
    'ANULADA': 'ANULADA', 'ANULADO': 'ANULADA', 'X': 'ANULADA'
}

def carregar_json(caminho):
    if not os.path.exists(caminho):
        print(f"❌ Erro: Arquivo '{caminho}' não encontrado.")
        sys.exit(1)
    try:
        with open(caminho, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Erro ao ler JSON: {e}")
        sys.exit(1)

def salvar_json(dados, caminho):
    try:
        with open(caminho, 'w', encoding='utf-8') as f:
            json.dump(dados, f, indent=4, ensure_ascii=False)
        print(f"💾 Arquivo salvo: {caminho}")
    except Exception as e:
        print(f"❌ Erro ao salvar JSON: {e}")

def validar_questao(q):
    """
    Retorna uma lista de strings descrevendo os erros. 
    Se a lista estiver vazia, a questão é válida.
    """
    erros = []
    
    # 1. Validação de ID
    id_tec = q.get('id_tec')
    if not id_tec:
        erros.append("id_tec ausente")
    
    # Se não tem ID, nem adianta checar o resto, pois não dá pra corrigir
    if not id_tec:
        return erros

    # 2. Validação de Campos Obrigatórios
    if not q.get('materia', '').strip() or q.get('materia') == "Geral":
        erros.append("materia inválida ou ausente")
        
    if not q.get('enunciado', '').strip():
        erros.append("enunciado vazio")
        
    if not q.get('comando', '').strip():
        erros.append("comando (html) vazio")

    # 3. Validação de Gabarito
    gabarito = q.get('gabarito', '').strip().upper()
    if gabarito not in GABARITO_MAP:
        erros.append(f"gabarito inválido: '{q.get('gabarito')}'")

    return erros

def modo_validacao(arquivo_entrada):
    print(f"🕵️  MODO AUDITORIA: Analisando '{arquivo_entrada}'...")
    
    dados = carregar_json(arquivo_entrada)
    questoes_com_erro = []
    ids_com_erro = set()
    
    total = len(dados)
    validos = 0

    print(f"📦 Total de registros: {total}")

    for q in dados:
        # Só valida se foi marcado como capturado (se tiver essa flag)
        # Se não tiver a flag 'capturado', assume que é pra validar tudo
        if 'capturado' in q and not q['capturado']:
            continue

        lista_erros = validar_questao(q)
        
        if lista_erros:
            # Adiciona metadados do erro para ajudar na correção manual
            q_copia = q.copy()
            q_copia['_ERROS_DETECTADOS'] = lista_erros 
            
            questoes_com_erro.append(q_copia)
            ids_com_erro.add(q.get('id_tec', 'sem_id'))
        else:
            validos += 1

    print("-" * 50)
    print(f"✅ Questões Válidas: {validos}")
    print(f"❌ Questões com Problemas: {len(questoes_com_erro)}")
    print("-" * 50)

    if questoes_com_erro:
        # Gera o nome do arquivo fix_
        pasta = os.path.dirname(arquivo_entrada)
        nome_arquivo = os.path.basename(arquivo_entrada)
        caminho_fix = os.path.join(pasta, f"fix_{nome_arquivo}")
        
        print(f"⚠️  Problemas detectados! Gerando arquivo para correção manual...")
        salvar_json(questoes_com_erro, caminho_fix)
        print(f"\n👉 PRÓXIMO PASSO: Abra '{caminho_fix}', corrija os campos e remova a chave '_ERROS_DETECTADOS'.")
    else:
        print("🎉 Nenhum erro encontrado. O dataset está limpo!")

def modo_fixer(arquivo_original, arquivo_correcao):
    print(f"🛠️  MODO CORREÇÃO: Aplicando fixes de '{arquivo_correcao}' em '{arquivo_original}'...")
    
    dataset = carregar_json(arquivo_original)
    correcoes = carregar_json(arquivo_correcao)
    
    # Cria um dicionário das correções para acesso rápido por ID
    # Remove a chave de metadados de erro se o usuário esqueceu
    mapa_correcoes = {}
    for item in correcoes:
        if '_ERROS_DETECTADOS' in item:
            del item['_ERROS_DETECTADOS']
        
        id_tec = item.get('id_tec')
        if id_tec:
            mapa_correcoes[id_tec] = item
    
    print(f"🔧 Carregadas {len(mapa_correcoes)} correções manuais.")
    
    substituidos = 0
    nao_encontrados = 0
    
    # Itera sobre o dataset original e substitui
    novo_dataset = []
    for q in dataset:
        id_tec = q.get('id_tec')
        
        if id_tec in mapa_correcoes:
            # Substitui pelo objeto corrigido
            novo_dataset.append(mapa_correcoes[id_tec])
            substituidos += 1
            # Remove do mapa para saber se sobrou algo
            del mapa_correcoes[id_tec]
        else:
            # Mantém o original
            novo_dataset.append(q)
            
    # Verifica se sobraram correções (IDs que não existiam no original)
    sobras = len(mapa_correcoes)
    
    print("-" * 50)
    print(f"✅ Substituições aplicadas: {substituidos}")
    
    if sobras > 0:
        print(f"⚠️  {sobras} itens no arquivo de correção não foram encontrados no original (IDs novos?). Eles foram ignorados.")
    
    # Salva o arquivo original sobrescrevendo-o (ou cria um _FINAL se preferir segurança)
    # Por segurança, vamos salvar no original mesmo conforme o fluxo pedido
    salvar_json(novo_dataset, arquivo_original)
    print(f"🎉 Dataset original atualizado com sucesso!")

def main():
    parser = argparse.ArgumentParser(description="Validador e Corretor de Datasets")
    
    parser.add_argument("arquivo_principal", help="O dataset completo original")
    parser.add_argument("arquivo_fix", nargs='?', help="O arquivo contendo apenas as correções (usado com --fixer)")
    parser.add_argument("--fixer", action="store_true", help="Ativa o modo de substituição/correção")
    
    args = parser.parse_args()

    if args.fixer:
        if not args.arquivo_fix:
            print("❌ Erro: Para usar --fixer, você precisa fornecer o arquivo de correção.")
            print("Exemplo: python script.py dataset.json fix_dataset.json --fixer")
            return
        modo_fixer(args.arquivo_principal, args.arquivo_fix)
    else:
        modo_validacao(args.arquivo_principal)

if __name__ == "__main__":
    main()