#!/usr/bin/env python3
"""
Script de validação do JSON de questões (sem conexão ao banco).
Útil para verificar a integridade dos dados antes da carga.
"""

import json
import sys
from pathlib import Path
from collections import Counter

# Mapeamento de gabaritos aceitos
GABARITO_MAP = {
    'CERTO': 'CERTO', 'C': 'CERTO', 'V': 'CERTO', 'VERDADEIRO': 'CERTO', 'TRUE': 'CERTO',
    'ERRADO': 'ERRADO', 'E': 'ERRADO', 'F': 'ERRADO', 'FALSO': 'ERRADO', 'FALSE': 'ERRADO',
}

def validar_questao(q, idx):
    """Valida uma questão e retorna lista de erros."""
    erros = []
    
    if not q.get('id_tec'):
        erros.append(f"[{idx}] id_tec ausente")
    
    if not q.get('materia', '').strip():
        erros.append(f"[{idx}] matéria ausente")
    
    if not q.get('enunciado', '').strip():
        erros.append(f"[{idx}] enunciado ausente")
    
    gabarito = q.get('gabarito', '').strip().upper()
    if gabarito not in GABARITO_MAP:
        erros.append(f"[{idx}] gabarito inválido: '{q.get('gabarito')}'")
    
    return erros

def main():
    if len(sys.argv) < 2:
        print("Uso: python validar_json.py arquivo.json")
        sys.exit(1)
    
    arquivo = Path(sys.argv[1])
    if not arquivo.exists():
        print(f"Erro: Arquivo não encontrado: {arquivo}")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"VALIDAÇÃO DE JSON - Rinha de Concurseiro")
    print(f"{'='*60}")
    print(f"Arquivo: {arquivo.name}\n")
    
    # Carregar JSON
    with open(arquivo, 'r', encoding='utf-8') as f:
        questoes = json.load(f)
    
    total = len(questoes)
    print(f"Total de questões: {total}\n")
    
    # Estatísticas
    materias = Counter()
    assuntos = Counter()
    gabaritos = Counter()
    ids_tec = set()
    duplicados = []
    erros = []
    
    for i, q in enumerate(questoes, 1):
        # Verificar duplicados
        id_tec = q.get('id_tec')
        if id_tec in ids_tec:
            duplicados.append(id_tec)
        else:
            ids_tec.add(id_tec)
        
        # Validar
        erros.extend(validar_questao(q, i))
        
        # Contadores
        materias[q.get('materia', 'N/A')] += 1
        assuntos[q.get('assunto', 'N/A')] += 1
        gabaritos[q.get('gabarito', 'N/A').upper()] += 1
    
    # Relatório
    print(f"{'='*60}")
    print("MATÉRIAS ENCONTRADAS")
    print(f"{'='*60}")
    for mat, count in materias.most_common():
        print(f"  {count:>5}x  {mat}")
    
    print(f"\n{'='*60}")
    print("GABARITOS")
    print(f"{'='*60}")
    for gab, count in gabaritos.most_common():
        status = "✓" if gab in GABARITO_MAP else "✗"
        print(f"  {count:>5}x  {gab} {status}")
    
    print(f"\n{'='*60}")
    print("RESUMO")
    print(f"{'='*60}")
    print(f"Total de questões:     {total:>6}")
    print(f"IDs únicos:            {len(ids_tec):>6}")
    print(f"Duplicados:            {len(duplicados):>6}")
    print(f"Matérias distintas:    {len(materias):>6}")
    print(f"Assuntos distintos:    {len(assuntos):>6}")
    print(f"Erros de validação:    {len(erros):>6}")
    
    # Gabaritos válidos vs inválidos
    validos = sum(c for g, c in gabaritos.items() if g in GABARITO_MAP)
    invalidos = total - validos
    print(f"Gabaritos válidos:     {validos:>6}")
    print(f"Gabaritos inválidos:   {invalidos:>6}")
    
    if duplicados:
        print(f"\n{'='*60}")
        print("IDs DUPLICADOS")
        print(f"{'='*60}")
        for dup in duplicados[:10]:
            print(f"  - {dup}")
        if len(duplicados) > 10:
            print(f"  ... e mais {len(duplicados) - 10}")
    
    if erros:
        print(f"\n{'='*60}")
        print("ERROS DE VALIDAÇÃO")
        print(f"{'='*60}")
        for erro in erros[:20]:
            print(f"  - {erro}")
        if len(erros) > 20:
            print(f"  ... e mais {len(erros) - 20}")
    
    print(f"\n{'='*60}")
    if invalidos == 0 and len(erros) == 0:
        print("✓ JSON VÁLIDO - Pronto para carga")
    else:
        print("✗ JSON COM PROBLEMAS - Verifique os erros acima")
    print(f"{'='*60}\n")

if __name__ == '__main__':
    main()
