import pdfplumber
import os

# Caminho do arquivo de amostra (Ajuste se necessário)
ARQUIVO_ALVO = "../DC-amostra.pdf"

def diagnosticar_estrutura():
    if not os.path.exists(ARQUIVO_ALVO):
        print(f"❌ Arquivo não encontrado: {ARQUIVO_ALVO}")
        print("Verifique se o PDF está na pasta 'Direito Constitucional' e o script em 'tools'.")
        return

    print(f"🔍 Analisando estrutura de: {os.path.basename(ARQUIVO_ALVO)}")
    print("-" * 60)

    with pdfplumber.open(ARQUIVO_ALVO) as pdf:
        # Analisa apenas a primeira página para identificar o padrão
        pagina = pdf.pages[0]
        texto = pagina.extract_text()
        
        print("--- TEXTO BRUTO (PRIMEIROS 1000 CARACTERES) ---")
        print(texto[:1000])
        print("\n" + "-" * 60)
        
        print("--- ANÁLISE DE PADRÕES ---")
        
        # 1. Verifica Padrão de Início
        if "Questão 1" in texto:
            print("✅ Padrão Detectado: 'Questão X' (Estilo Clássico)")
        elif "1)" in texto or "1 )" in texto:
            print("✅ Padrão Detectado: 'X)' (Estilo Novo/Compacto)")
        else:
            print("⚠️ Padrão de numeração NÃO identificado claramente.")

        # 2. Verifica Metadados
        if "www.tecconcursos.com.br" in texto:
            print("✅ Links de ID presentes.")
        else:
            print("⚠️ Links de ID NÃO detectados (pode dificultar extração do ID).")

        # 3. Verifica Separação de Texto
        if "Texto associado" in texto or "Texto CB" in texto:
            print("ℹ️  Nota: Há indícios de 'Texto Associado' (Comando separado).")
        else:
            print("ℹ️  Nota: Parece ser enunciados diretos (Sem texto de apoio longo).")

if __name__ == "__main__":
    diagnosticar_estrutura()