"""
Extrator de Boloes da Caixa - Microsoft Edge
Versao AUTOMATICA - Extrai todos os boloes de todas as paginas
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import os
import time
from datetime import datetime

# MEGA SENA - DEST_DIR = r'I:\Meu Drive\LoteriasCaixaJogos\JOGOS\Jogos\Boloes\Json'
DEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URL_BOLOES = "https://www.loteriasonline.caixa.gov.br/silce-web/#/bolao-caixa"

if not os.path.exists(DEST_DIR):
    os.makedirs(DEST_DIR, exist_ok=True)

print("Iniciando Edge...")
driver = webdriver.Edge()
print("Edge aberto!")

print("Navegando para o site da Caixa...")
driver.get(URL_BOLOES)
print("Site carregado!")

print("\n" + "="*60)
print("  AGUARDANDO LOGIN")
print("="*60)
print("\n1. Faca login no site da Caixa")
print("2. Navegue ate a pagina de boloes")
print("3. Selecione a modalidade desejada (Mega da Virada, etc)")
print("4. Pressione ENTER aqui quando estiver pronto")
input("\n>>> ENTER para continuar...")


def extrair_dados_popup():
    """Extrai os dados do popup do bolao"""
    dados = {}
    try:
        time.sleep(1.5)
        popup = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".modal-content, .modal, [class*='modal'], [role='dialog']"))
        )
        texto_popup = popup.text
        dados['texto_completo'] = texto_popup

        linhas = texto_popup.split('\n')
        for i, linha in enumerate(linhas):
            linha_lower = linha.lower()
            if 'nome da lot' in linha_lower:
                if ':' in linha:
                    dados['nome_loterica'] = linha.split(':', 1)[-1].strip()
                elif i+1 < len(linhas):
                    dados['nome_loterica'] = linhas[i+1].strip()
            elif 'cidade' in linha_lower:
                if ':' in linha:
                    dados['cidade_uf'] = linha.split(':', 1)[-1].strip()
                elif i+1 < len(linhas):
                    dados['cidade_uf'] = linhas[i+1].strip()
            elif 'valor da cota' in linha_lower:
                if ':' in linha:
                    dados['valor_cota'] = linha.split(':', 1)[-1].strip()
                elif i+1 < len(linhas):
                    dados['valor_cota'] = linhas[i+1].strip()
            elif 'tarifa' in linha_lower:
                if ':' in linha:
                    dados['tarifa_servico'] = linha.split(':', 1)[-1].strip()
                elif i+1 < len(linhas):
                    dados['tarifa_servico'] = linhas[i+1].strip()
            elif 'concurso' in linha_lower:
                if ':' in linha:
                    dados['concurso'] = linha.split(':', 1)[-1].strip()

        # Extrair jogos
        jogos = []
        jogo_atual = []
        capturando = False
        for linha in linhas:
            if 'jogo' in linha.lower():
                if jogo_atual:
                    jogos.append(jogo_atual)
                jogo_atual = []
                capturando = True
            elif capturando:
                nums = [p.strip().zfill(2) for p in linha.split() if p.strip().isdigit() and 1 <= int(p.strip()) <= 60]
                jogo_atual.extend(nums)
        if jogo_atual:
            jogos.append(jogo_atual)
        dados['jogos'] = jogos
        dados['total_jogos'] = len(jogos)
        return dados
    except Exception as e:
        return None


def fechar_popup():
    """Fecha o popup atual"""
    try:
        close_btns = driver.find_elements(By.CSS_SELECTOR,
            "button.close, .btn-close, [class*='close'], button[aria-label='Close'], "
            ".modal-header button, [class*='modal'] .close")
        for btn in close_btns:
            try:
                if btn.is_displayed():
                    btn.click()
                    time.sleep(0.5)
                    return True
            except:
                pass
    except:
        pass

    try:
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        return True
    except:
        pass

    return False


def encontrar_botoes_boloes():
    """Encontra todos os botoes de boloes na pagina"""
    seletores = [
        "button.btn-primary",
        "button.btn-success",
        "button[class*='btn'][class*='primary']",
        "button[class*='btn'][class*='success']",
        ".card button",
        "[class*='bolao'] button",
        "button[class*='apostar']",
        "button[class*='comprar']",
        "button[class*='ver']",
    ]

    todos_botoes = []
    for seletor in seletores:
        try:
            botoes = driver.find_elements(By.CSS_SELECTOR, seletor)
            for btn in botoes:
                if btn not in todos_botoes and btn.is_displayed():
                    texto = btn.text.lower()
                    if any(palavra in texto for palavra in ['ver', 'detalh', 'comprar', 'apostar', 'cotas', 'jogo']):
                        todos_botoes.append(btn)
        except:
            pass

    return todos_botoes


def ir_proxima_pagina():
    """Tenta ir para a proxima pagina"""
    try:
        seletores_prox = [
            "button[aria-label*='proxim']",
            "button[aria-label*='next']",
            "a[aria-label*='proxim']",
            "a[aria-label*='next']",
            ".pagination .next",
            ".pagination li:last-child a",
            "button[class*='next']",
            "[class*='pagination'] button:last-child",
            "button[class*='arrow-right']",
            "button[class*='chevron-right']",
            ".page-item:last-child .page-link",
        ]

        for seletor in seletores_prox:
            try:
                botoes = driver.find_elements(By.CSS_SELECTOR, seletor)
                for btn in botoes:
                    if btn.is_displayed() and btn.is_enabled():
                        classes = btn.get_attribute('class') or ''
                        if 'disabled' not in classes:
                            btn.click()
                            time.sleep(2)
                            return True
            except:
                pass

        return False
    except:
        return False


def get_primeiro_bolao(driver):
    """Retorna identificador unico do primeiro bolao da pagina"""
    try:
        # Pegar nome + cidade do primeiro bolao
        primeiro = driver.find_element(By.CSS_SELECTOR, ".bolao-item:first-child")
        nome = primeiro.find_element(By.CSS_SELECTOR, ".nome-loterica").text
        cidade = primeiro.find_element(By.CSS_SELECTOR, ".cidade").text
        return f"{nome}|{cidade}"
    except:
        return None


def extrair_pagina_atual(boloes_extraidos, textos_ja_extraidos, pagina_num):
    """Extrai todos os boloes da pagina atual"""
    print(f"\n{'='*60}")
    print(f"  PAGINA {pagina_num}")
    print(f"{'='*60}")

    # Scroll para carregar todos os elementos
    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    # Encontrar botoes
    botoes = encontrar_botoes_boloes()
    print(f"\nBotoes encontrados nesta pagina: {len(botoes)}")

    if len(botoes) == 0:
        print(">>> AVISO: Nenhum botao de bolao encontrado!")
        try:
            all_buttons = driver.find_elements(By.CSS_SELECTOR, "button")
            print(f"    Total de botoes na pagina: {len(all_buttons)}")
            for btn in all_buttons[:10]:
                try:
                    if btn.is_displayed():
                        texto = btn.text.strip()
                        if texto and len(texto) < 50:
                            print(f"    - '{texto}'")
                except:
                    pass
        except:
            pass
        return 0, 0

    extraidos_pagina = 0
    duplicados_pagina = 0

    for i, botao in enumerate(botoes):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao)
            time.sleep(0.3)

            botao.click()
            time.sleep(1.5)

            dados = extrair_dados_popup()

            if dados and dados.get('texto_completo'):
                texto = dados.get('texto_completo', '')

                # Verificar duplicata
                if texto in textos_ja_extraidos:
                    duplicados_pagina += 1
                    print(f"  [{i+1}/{len(botoes)}] DUPLICADO - ja extraido anteriormente")
                else:
                    # Novo bolao!
                    textos_ja_extraidos.add(texto)
                    dados['pagina'] = pagina_num
                    dados['indice'] = len(boloes_extraidos) + 1
                    boloes_extraidos.append(dados)
                    extraidos_pagina += 1

                    loterica = dados.get('nome_loterica', 'N/A')[:35]
                    cidade = dados.get('cidade_uf', '')[:20]
                    print(f"  [{i+1}/{len(botoes)}] NOVO #{len(boloes_extraidos)}: {loterica} - {cidade}")

            fechar_popup()
            time.sleep(0.5)

        except Exception as e:
            fechar_popup()
            continue

    print(f"\n  Resumo pagina {pagina_num}:")
    print(f"    - Novos: {extraidos_pagina}")
    print(f"    - Duplicados: {duplicados_pagina}")
    print(f"    - Total acumulado: {len(boloes_extraidos)}")

    return extraidos_pagina, duplicados_pagina


def salvar_parcial(boloes, arquivo_base):
    """Salva arquivo parcial a cada pagina"""
    if not boloes:
        return
    arquivo = os.path.join(DEST_DIR, f"{arquivo_base}.json")
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(boloes, f, ensure_ascii=False, indent=2)
    print(f"  >>> Salvo parcial: {len(boloes)} boloes")


def extrair_todos_boloes():
    """Extrai todos os boloes de todas as paginas"""
    boloes = []
    textos_ja_extraidos = set()  # Para verificar duplicatas rapidamente
    pagina = 1
    max_paginas = 50
    paginas_sem_novos = 0
    
    # VARIAVEL PARA DETECAO DE LOOP (Opcao 5 - Detectar Primeiro Bolao Repetido)
    primeiro_bolao_pagina1 = None
    
    # Nome base do arquivo (sera atualizado a cada pagina)
    arquivo_base = f"boloes_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print("\n" + "="*60)
    print("  INICIANDO EXTRACAO AUTOMATICA")
    print("="*60)
    print("\nO script vai:")
    print("  1. Clicar em cada bolao")
    print("  2. Extrair os dados")
    print("  3. SALVAR a cada pagina (backup automatico)")
    print("  4. Ir para proxima pagina")
    print("  5. Repetir ate acabar")
    print(f"\nArquivo: {arquivo_base}.json")
    print("\nAguarde...\n")

    inicio = time.time()

    while pagina <= max_paginas:
        novos, duplicados = extrair_pagina_atual(boloes, textos_ja_extraidos, pagina)

        # SALVAR A CADA PAGINA
        if novos > 0:
            salvar_parcial(boloes, arquivo_base)

        # OPCAO 5 - DETECTAR PRIMEIRO BOLAO REPETIDO (MAIS SEGURA)
        # Comparar o primeiro bolao da pagina atual com o da pagina 1
        primeiro_bolao_atual = get_primeiro_bolao(driver)
        
        # Salvar referencia da pagina 1
        if pagina == 1:
            primeiro_bolao_pagina1 = primeiro_bolao_atual
            print(f"\n>>> Primeiro bolao da pagina 1: {primeiro_bolao_pagina1}")
        
        # Detectar loop (voltou a pagina 1)
        elif primeiro_bolao_atual == primeiro_bolao_pagina1 and primeiro_bolao_pagina1 is not None:
            print(f"\n{'='*60}")
            print("  LOOP DETECTADO!")
            print(f"{'='*60}")
            print(f"   O primeiro bolao da pagina {pagina} e igual ao da pagina 1:")
            print(f"   >>> {primeiro_bolao_atual}")
            print(f"   Total de paginas processadas: {pagina - 1}")
            print(f"   Total de boloes extraidos: {len(boloes)}")
            print(">>> Finalizando extracao!")
            break

        # VERIFICAR SE TODOS SAO DUPLICATAS (verificacao secundaria)
        if duplicados > 0 and novos == 0:
            print("\n" + "="*60)
            print("  LOOP DETECTADO (verificacao secundaria)!")
            print("="*60)
            print("Todos os boloes desta pagina ja foram extraidos.")
            print("Provavelmente voltou para a pagina 1.")
            print(">>> Finalizando extracao!")
            break

        # Se nao encontrou nenhum bolao (pagina vazia)
        if novos == 0 and duplicados == 0:
            paginas_sem_novos += 1
            if paginas_sem_novos >= 2:
                print(f"\n>>> {paginas_sem_novos} paginas consecutivas sem boloes.")
                print(">>> Provavelmente chegou ao fim!")
                break
        else:
            paginas_sem_novos = 0

        # Tentar ir para proxima pagina
        print(f"\nTentando ir para pagina {pagina + 1}...")
        if not ir_proxima_pagina():
            print("\n" + "="*60)
            print("  FIM DA PAGINACAO")
            print("="*60)
            print("Nao ha mais paginas ou botao de proxima nao encontrado.")
            break

        pagina += 1
        time.sleep(1)

    # Tempo total
    tempo_total = time.time() - inicio
    minutos = int(tempo_total // 60)
    segundos = int(tempo_total % 60)

    print("\n" + "="*60)
    print("  EXTRACAO CONCLUIDA!")
    print("="*60)
    print(f"\n  Total de boloes extraidos: {len(boloes)}")
    print(f"  Paginas processadas: {pagina}")
    print(f"  Tempo total: {minutos}min {segundos}seg")
    print(f"  Arquivo: {arquivo_base}.json")
    print("="*60)

    return boloes, arquivo_base


def extrair_por_paginas():
    """Extrai boloes pagina por pagina com confirmacao do usuario"""
    boloes = []
    textos_ja_extraidos = set()
    pagina = 1
    primeiro_bolao_pagina1 = None
    
    arquivo_base = f"boloes_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    print("\n" + "="*60)
    print("  EXTRACAO PAGINA POR PAGINA")
    print("="*60)
    print("\nO script vai:")
    print("  1. Extrair todos boloes da pagina atual")
    print("  2. SALVAR automaticamente")
    print("  3. AGUARDAR sua confirmacao para proxima pagina")
    print(f"\nArquivo: {arquivo_base}.json")
    print("\nIniciando...\n")

    inicio = time.time()

    while True:
        novos, duplicados = extrair_pagina_atual(boloes, textos_ja_extraidos, pagina)

        # SALVAR A CADA PAGINA
        if novos > 0:
            salvar_parcial(boloes, arquivo_base)

        # Verificar loop
        primeiro_bolao_atual = get_primeiro_bolao(driver)
        
        if pagina == 1:
            primeiro_bolao_pagina1 = primeiro_bolao_atual
        elif primeiro_bolao_atual == primeiro_bolao_pagina1 and primeiro_bolao_pagina1 is not None:
            print(f"\n{'='*60}")
            print("  LOOP DETECTADO!")
            print(f"{'='*60}")
            print("  O sistema detectou que voltou para a pagina 1.")
            print("  Todas as paginas foram processadas!")
            break

        if duplicados > 0 and novos == 0:
            print("\n" + "="*60)
            print("  AVISO: Todos boloes desta pagina sao duplicados!")
            print("="*60)

        # SOLICITAR CONFIRMACAO DO USUARIO
        print("\n" + "-"*60)
        print("  OPCOES:")
        print("  [ENTER] - Continuar para proxima pagina")
        print("  [sair]  - Finalizar extracao")
        print("-"*60)
        
        comando = input(">>> ").strip().lower()
        
        if comando == 'sair':
            print("\n>>> Finalizando extracao por solicitacao do usuario...")
            break

        # Tentar ir para proxima pagina
        print(f"\nTentando ir para pagina {pagina + 1}...")
        if not ir_proxima_pagina():
            print("\n" + "="*60)
            print("  FIM DA PAGINACAO")
            print("="*60)
            print("  Nao ha mais paginas disponiveis.")
            break

        pagina += 1
        time.sleep(1)

    # Tempo total
    tempo_total = time.time() - inicio
    minutos = int(tempo_total // 60)
    segundos = int(tempo_total % 60)

    print("\n" + "="*60)
    print("  EXTRACAO CONCLUIDA!")
    print("="*60)
    print(f"\n  Total de boloes extraidos: {len(boloes)}")
    print(f"  Paginas processadas: {pagina}")
    print(f"  Tempo total: {minutos}min {segundos}seg")
    print(f"  Arquivo: {arquivo_base}.json")
    print("="*60)

    return boloes, arquivo_base


def salvar_dados(boloes):
    """Salva os dados em JSON"""
    if not boloes:
        print("\nNenhum bolao extraido.")
        return None

    arquivo = os.path.join(DEST_DIR, f"boloes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(boloes, f, ensure_ascii=False, indent=2)

    print(f"\n" + "="*60)
    print(f"  ARQUIVO SALVO!")
    print(f"="*60)
    print(f"\n  Local: {arquivo}")
    print(f"  Total: {len(boloes)} boloes")
    print("="*60)

    return arquivo


# Menu principal
while True:
    print("\n" + "="*60)
    print("  MENU PRINCIPAL")
    print("="*60)
    print("\n[1] Extrair TODOS automaticamente (todas paginas)")
    print("[2] Extrair POR PAGINAS (com confirmacao)")
    print("[3] Extrair MANUAL (um por um)")
    print("[0] Sair")
    print("-"*60)

    opcao = input("Opcao: ").strip()

    if opcao == "1":
        boloes, arquivo_base = extrair_todos_boloes()
        if boloes:
            arquivo_final = os.path.join(DEST_DIR, f"{arquivo_base}.json")
            print(f"\n  Arquivo final: {arquivo_final}")
            print(f"  Total: {len(boloes)} boloes")

    elif opcao == "2":
        boloes, arquivo_base = extrair_por_paginas()
        if boloes:
            arquivo_final = os.path.join(DEST_DIR, f"{arquivo_base}.json")
            print(f"\n  Arquivo final: {arquivo_final}")
            print(f"  Total: {len(boloes)} boloes")

    elif opcao == "3":
        boloes = []
        textos_manual = set()
        print("\n" + "="*60)
        print("  MODO MANUAL")
        print("="*60)
        print("\n1. Clique em um bolao para abrir o popup")
        print("2. Volte aqui e pressione ENTER")
        print("3. Digite 'sair' para terminar")
        print("-"*60)

        while True:
            comando = input("\n[ENTER] extrair | [sair] terminar: ").strip().lower()
            if comando == 'sair':
                break
            dados = extrair_dados_popup()
            if dados:
                texto = dados.get('texto_completo', '')
                if texto in textos_manual:
                    print("  >>> DUPLICADO! Este bolao ja foi extraido.")
                else:
                    textos_manual.add(texto)
                    boloes.append(dados)
                    print(f"  Loterica: {dados.get('nome_loterica', 'N/A')}")
                    print(f"  >>> Total: {len(boloes)}")
            else:
                print("  Popup nao encontrado.")

        salvar_dados(boloes)

    elif opcao == "0":
        break

print("\nFechando navegador...")
driver.quit()
print("Fim!")