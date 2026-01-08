#!/usr/bin/env python3
"""
Revisor de Questões Extraídas
=============================
Analisa o JSON gerado pelo extrator e identifica questões que precisam
de revisão manual.

Uso:
    python revisor_questoes.py

Configuração:
    Altere a variável CAMINHO_JSON para o arquivo a ser revisado.

Autor: Bruno
Versão: 1.1 - Limite de comando aumentado + severidade ajustada
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

CAMINHO_JSON = "questoes_extraidas.json"
RELATORIO_SAIDA = "revisao_questoes.txt"
JSON_PROBLEMATICAS = "questoes_para_revisar.json"

# Limites para detecção de problemas (ajustados na v1.1)
COMANDO_MAX_CHARS = 400      # Aumentado de 300 para 400 (comandos com citação legal)
ENUNCIADO_MIN_CHARS = 30     # Enunciado menor que isso pode estar incompleto
ENUNCIADO_MAX_CHARS = 1500   # Enunciado maior que isso pode ter lixo

# =============================================================================
# FUNÇÕES DE VERIFICAÇÃO
# =============================================================================

def verificar_comando_vazio(questao: dict) -> str | None:
    """
    Verifica se o comando está vazio.
    
    v1.1: Diferencia entre CRÍTICO (comando vazou para enunciado) 
    e INFO (questão sem comando explícito - pode ser intencional).
    """
    if not questao.get("comando", "").strip():
        enunciado = questao.get("enunciado", "").lower()
        
        # Se o enunciado contém "julgue", o comando deveria ter sido extraído
        # Isso indica falha na separação
        if "julgue" in enunciado[:100]:
            return "COMANDO_VAZIO_CRITICO: Texto 'julgue' encontrado no enunciado"
        
        # Se o enunciado começa com introdução típica, também é crítico
        introducoes = ['no que se refere', 'em relação', 'a respeito', 
                       'com relação', 'acerca de', 'com base', 'considerando']
        for intro in introducoes:
            if enunciado.startswith(intro):
                return f"COMANDO_VAZIO_CRITICO: Enunciado inicia com '{intro}'"
        
        # Caso contrário, é uma questão sem comando explícito (pode ser intencional)
        return "COMANDO_VAZIO_INFO: Questão sem comando explícito (verificar se intencional)"
    
    return None


def verificar_comando_longo(questao: dict) -> str | None:
    """Verifica se o comando está muito longo."""
    comando = questao.get("comando", "")
    if len(comando) > COMANDO_MAX_CHARS:
        return f"COMANDO_LONGO: {len(comando)} caracteres (máx: {COMANDO_MAX_CHARS})"
    return None


def verificar_enunciado_curto(questao: dict) -> str | None:
    """Verifica se o enunciado está muito curto."""
    enunciado = questao.get("enunciado", "")
    if len(enunciado) < ENUNCIADO_MIN_CHARS:
        return f"ENUNCIADO_CURTO: {len(enunciado)} caracteres (mín: {ENUNCIADO_MIN_CHARS})"
    return None


def verificar_enunciado_longo(questao: dict) -> str | None:
    """Verifica se o enunciado está muito longo."""
    enunciado = questao.get("enunciado", "")
    if len(enunciado) > ENUNCIADO_MAX_CHARS:
        return f"ENUNCIADO_LONGO: {len(enunciado)} caracteres (máx: {ENUNCIADO_MAX_CHARS})"
    return None


def verificar_certo_errado_no_enunciado(questao: dict) -> str | None:
    """Verifica se 'Certo' ou 'Errado' ficou no enunciado."""
    enunciado = questao.get("enunciado", "")
    
    # Verifica se termina com Certo/Errado (não deveria)
    if re.search(r'\b(Certo|Errado)\s*$', enunciado):
        return "LIMPEZA_FALHOU: Enunciado termina com 'Certo' ou 'Errado'"
    
    # Verifica "Certo Errado" em qualquer lugar
    if "Certo Errado" in enunciado:
        return "LIMPEZA_FALHOU: Enunciado contém 'Certo Errado'"
    
    return None


def verificar_materia_vazia(questao: dict) -> str | None:
    """Verifica se a matéria está vazia."""
    if not questao.get("materia", "").strip():
        return "MATERIA_VAZIA: Campo matéria não foi extraído"
    return None


def verificar_assunto_vazio(questao: dict) -> str | None:
    """Verifica se o assunto está vazio."""
    if not questao.get("assunto", "").strip():
        return "ASSUNTO_VAZIO: Campo assunto não foi extraído"
    return None


def verificar_gabarito_invalido(questao: dict) -> str | None:
    """Verifica se o gabarito é válido."""
    gabarito = questao.get("gabarito", "").strip()
    if gabarito not in ["Certo", "Errado"]:
        return f"GABARITO_INVALIDO: '{gabarito}' (esperado: Certo ou Errado)"
    return None


def verificar_caracteres_estranhos(questao: dict) -> str | None:
    """Verifica se há caracteres estranhos (problemas de encoding)."""
    campos = ["comando", "enunciado", "materia", "assunto"]
    
    # Padrões que indicam problema de encoding
    padroes_estranhos = [
        r'Ã[£¡¢¤§©ª]',     # Padrão típico de UTF-8 mal interpretado
        r'Ã[³²´µ¶¸¹º»]',   # Mais padrões
        r'â€[œ™""]',       # Aspas corrompidas
        r'Â[º§°]',         # Símbolos corrompidos
    ]
    
    for campo in campos:
        texto = questao.get(campo, "")
        for padrao in padroes_estranhos:
            if re.search(padrao, texto):
                return f"ENCODING: Caracteres corrompidos no campo '{campo}' (ex: Ã£ em vez de ã)"
    
    return None


def verificar_numero_no_enunciado(questao: dict) -> str | None:
    """Verifica se o número da questão ficou no início do enunciado."""
    enunciado = questao.get("enunciado", "")
    if re.match(r'^\d+\)', enunciado):
        return "NUMERO_NO_ENUNCIADO: Número da questão não foi removido"
    return None


def verificar_link_no_texto(questao: dict) -> str | None:
    """Verifica se há links vazados no comando ou enunciado."""
    campos = ["comando", "enunciado"]
    
    for campo in campos:
        texto = questao.get(campo, "")
        if "tecconcursos.com.br" in texto:
            return f"LINK_VAZADO: Link encontrado no campo '{campo}'"
    
    return None


# =============================================================================
# FUNÇÃO PRINCIPAL DE REVISÃO
# =============================================================================

def revisar_questoes(questoes: list) -> dict:
    """
    Revisa todas as questões e retorna um relatório.
    
    Returns:
        Dicionário com:
        - total: número total de questões
        - problematicas: lista de questões com problemas
        - estatisticas: contagem por tipo de problema
        - ids_duplicados: lista de IDs que aparecem mais de uma vez
    """
    
    # Lista de todas as funções de verificação
    verificacoes = [
        verificar_comando_vazio,
        verificar_comando_longo,
        verificar_enunciado_curto,
        verificar_enunciado_longo,
        verificar_certo_errado_no_enunciado,
        verificar_materia_vazia,
        verificar_assunto_vazio,
        verificar_gabarito_invalido,
        verificar_caracteres_estranhos,
        verificar_numero_no_enunciado,
        verificar_link_no_texto,
    ]
    
    problematicas = []
    estatisticas = Counter()
    
    # Verificar duplicatas de ID
    ids = [q.get("id_tec", "") for q in questoes]
    contador_ids = Counter(ids)
    ids_duplicados = [id_tec for id_tec, count in contador_ids.items() if count > 1]
    
    # Revisar cada questão
    for questao in questoes:
        problemas = []
        
        # Executa todas as verificações
        for verificacao in verificacoes:
            resultado = verificacao(questao)
            if resultado:
                problemas.append(resultado)
                # Extrai o tipo do problema (antes do ":")
                tipo = resultado.split(":")[0]
                estatisticas[tipo] += 1
        
        # Verifica se é ID duplicado
        if questao.get("id_tec", "") in ids_duplicados:
            problemas.append("ID_DUPLICADO: Este ID aparece mais de uma vez")
            estatisticas["ID_DUPLICADO"] += 1
        
        # Se tem problemas, adiciona à lista
        if problemas:
            problematicas.append({
                "questao": questao,
                "problemas": problemas
            })
    
    return {
        "total": len(questoes),
        "problematicas": problematicas,
        "estatisticas": dict(estatisticas),
        "ids_duplicados": ids_duplicados
    }


# =============================================================================
# FUNÇÕES DE RELATÓRIO
# =============================================================================

def gerar_relatorio_texto(resultado: dict) -> str:
    """Gera o relatório em formato texto."""
    linhas = []
    
    linhas.append("=" * 70)
    linhas.append("RELATÓRIO DE REVISÃO DE QUESTÕES")
    linhas.append("=" * 70)
    
    # Resumo
    total = resultado["total"]
    problematicas = len(resultado["problematicas"])
    ok = total - problematicas
    
    linhas.append(f"\nRESUMO:")
    linhas.append(f"  Total de questões: {total}")
    linhas.append(f"  Questões OK: {ok} ({100*ok/total:.1f}%)")
    linhas.append(f"  Questões com problemas: {problematicas} ({100*problematicas/total:.1f}%)")
    
    # Estatísticas por tipo (separando críticos de informativos)
    if resultado["estatisticas"]:
        linhas.append(f"\nPROBLEMAS ENCONTRADOS:")
        
        # Primeiro os críticos
        criticos = {k: v for k, v in resultado["estatisticas"].items() 
                   if 'CRITICO' in k or k not in ['COMANDO_VAZIO_INFO']}
        if criticos:
            linhas.append("  [CRÍTICOS]")
            for tipo, count in sorted(criticos.items(), key=lambda x: -x[1]):
                if 'INFO' not in tipo:
                    linhas.append(f"    {tipo}: {count}")
        
        # Depois os informativos
        informativos = {k: v for k, v in resultado["estatisticas"].items() 
                       if 'INFO' in k}
        if informativos:
            linhas.append("  [INFORMATIVOS]")
            for tipo, count in sorted(informativos.items(), key=lambda x: -x[1]):
                linhas.append(f"    {tipo}: {count}")
    
    # IDs duplicados
    if resultado["ids_duplicados"]:
        linhas.append(f"\nIDs DUPLICADOS ({len(resultado['ids_duplicados'])}):")
        for id_tec in resultado["ids_duplicados"]:
            linhas.append(f"  - {id_tec}")
    
    # Detalhamento das questões problemáticas
    if resultado["problematicas"]:
        linhas.append(f"\n{'=' * 70}")
        linhas.append("DETALHAMENTO DAS QUESTÕES COM PROBLEMAS")
        linhas.append("=" * 70)
        
        for item in resultado["problematicas"]:
            questao = item["questao"]
            problemas = item["problemas"]
            
            linhas.append(f"\n--- Questão {questao.get('numero', '?')} (ID: {questao.get('id_tec', '?')}) ---")
            linhas.append(f"Link: {questao.get('link', '')}")
            
            linhas.append(f"\nProblemas encontrados:")
            for problema in problemas:
                # Marca críticos com ❌ e informativos com ℹ️
                if 'CRITICO' in problema:
                    linhas.append(f"  ❌ {problema}")
                elif 'INFO' in problema:
                    linhas.append(f"  ℹ️  {problema}")
                else:
                    linhas.append(f"  ⚠️  {problema}")
            
            # Mostra os campos para facilitar revisão
            linhas.append(f"\nCampos:")
            linhas.append(f"  Matéria: {questao.get('materia', '')[:80]}...")
            linhas.append(f"  Assunto: {questao.get('assunto', '')[:80]}...")
            
            comando = questao.get('comando', '')
            if comando:
                linhas.append(f"  Comando: {comando[:100]}...")
            else:
                linhas.append(f"  Comando: (vazio)")
            
            linhas.append(f"  Enunciado: {questao.get('enunciado', '')[:100]}...")
            linhas.append(f"  Gabarito: {questao.get('gabarito', '')}")
    
    return "\n".join(linhas)


def salvar_questoes_problematicas(resultado: dict, caminho: str):
    """Salva apenas as questões problemáticas em JSON."""
    questoes = [item["questao"] for item in resultado["problematicas"]]
    
    # Adiciona os problemas como campo extra
    for i, item in enumerate(resultado["problematicas"]):
        questoes[i]["_problemas"] = item["problemas"]
    
    with open(caminho, 'w', encoding='utf-8') as f:
        json.dump(questoes, f, ensure_ascii=False, indent=2)
    
    print(f"JSON com questões problemáticas salvo: {caminho}")


# =============================================================================
# EXECUÇÃO PRINCIPAL
# =============================================================================

def main():
    """Função principal do revisor."""
    print("=" * 60)
    print("REVISOR DE QUESTÕES EXTRAÍDAS v1.1")
    print("=" * 60)
    
    # Verifica se o arquivo existe
    if not Path(CAMINHO_JSON).exists():
        print(f"ERRO: Arquivo não encontrado: {CAMINHO_JSON}")
        sys.exit(1)
    
    # Carrega o JSON
    print(f"\nCarregando: {CAMINHO_JSON}")
    with open(CAMINHO_JSON, 'r', encoding='utf-8') as f:
        questoes = json.load(f)
    
    print(f"Questões carregadas: {len(questoes)}")
    
    # Executa a revisão
    print("\nExecutando verificações...")
    resultado = revisar_questoes(questoes)
    
    # Gera e salva o relatório
    relatorio = gerar_relatorio_texto(resultado)
    
    with open(RELATORIO_SAIDA, 'w', encoding='utf-8') as f:
        f.write(relatorio)
    
    print(f"\nRelatório salvo: {RELATORIO_SAIDA}")
    
    # Salva JSON com problemáticas (se houver)
    if resultado["problematicas"]:
        salvar_questoes_problematicas(resultado, JSON_PROBLEMATICAS)
    
    # Exibe resumo no console
    print("\n" + "=" * 60)
    print("RESUMO")
    print("=" * 60)
    
    total = resultado["total"]
    problematicas = len(resultado["problematicas"])
    
    print(f"  Total: {total}")
    print(f"  OK: {total - problematicas}")
    print(f"  Para revisar: {problematicas}")
    
    if resultado["estatisticas"]:
        print(f"\n  Tipos de problemas:")
        for tipo, count in sorted(resultado["estatisticas"].items(), key=lambda x: -x[1]):
            indicador = "❌" if 'CRITICO' in tipo else ("ℹ️" if 'INFO' in tipo else "⚠️")
            print(f"    {indicador} {tipo}: {count}")
    
    print("=" * 60)


if __name__ == "__main__":
    main()
