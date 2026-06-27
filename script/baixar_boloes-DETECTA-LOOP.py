"""
Extrator de Boloes da Caixa - Microsoft Edge
Versao AUTOMATICA - Extrai todos os boloes de todas as paginas
COM DETECÇÃO AUTOMÁTICA DE LOOP ROBUSTA

Modalidade: selecione MANUALMENTE no site.
O script mantém o filtro de lotérica ativo a cada página.
"""
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from boloes_extrair_popup import parse_campos_popup
from boloes_filtro_loterica import (
    FiltroLotericaConfig,
    aplicar_filtro_loterica,
    avancar_para_pagina_filtrada,
    bolao_atende_filtro,
    bolao_corresponde_loterica,
    cfg_com_qtd,
    fila_qtd_dezenas,
    garantir_sessao_caixa,
    gerar_arquivo_base,
    ir_proxima_pagina_lista,
    ler_config_extracao,
    manter_sessao_ativa,
    preparar_extracao_pagina,
    preparar_pagina_filtrada,
    tem_proxima_pagina,
)

DEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

URL_BOLOES = "https://www.loteriasonline.caixa.gov.br/silce-web/#/bolao-caixa"

if not os.path.exists(DEST_DIR):
    os.makedirs(DEST_DIR, exist_ok=True)

driver = None
FILTRO_LOTERICA: Optional[FiltroLotericaConfig] = None
ROTULO_ARQUIVO = None
ROTULO_NOME = 'modalidade atual'


def _rotulo_nome() -> str:
    return ROTULO_ARQUIVO.label if ROTULO_ARQUIVO else 'modalidade atual'


def iniciar_navegador() -> bool:
    """Abre Edge + site da Caixa (só uma vez por sessão)."""
    global driver
    if driver is not None:
        return True
    try:
        print("\nIniciando Edge...")
        driver = webdriver.Edge()
        print("Edge aberto!")
        print("Navegando para o site da Caixa...")
        driver.get(URL_BOLOES)
        print("Site carregado!")
        return True
    except Exception as exc:
        print(f"\n>>> ERRO ao abrir Edge: {exc}")
        traceback.print_exc()
        driver = None
        return False


def fechar_navegador() -> None:
    global driver
    if driver is not None:
        try:
            print("\nFechando navegador...")
            driver.quit()
        except Exception:
            pass
        driver = None


def configurar_loterica() -> bool:
    """Pergunta lotérica, dezenas e rótulo — sem encerrar o processo."""
    global FILTRO_LOTERICA, ROTULO_ARQUIVO, ROTULO_NOME
    try:
        FILTRO_LOTERICA, ROTULO_ARQUIVO = ler_config_extracao()
        ROTULO_NOME = _rotulo_nome()
        return True
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f"\n>>> ERRO na configuracao: {exc}")
        traceback.print_exc()
        return False


def aguardar_login_caixa() -> None:
    print("\n" + "=" * 60)
    print("  AGUARDANDO LOGIN E MODALIDADE")
    print("=" * 60)
    print("\n1. Faca login no site da Caixa")
    print("2. Selecione a MODALIDADE desejada (Quina de Sao Joao, Mega, etc.)")
    if FILTRO_LOTERICA:
        print(f"3. Lotérica alvo: {FILTRO_LOTERICA.termo} (script aplica filtro — nao precisa digitar de novo)")
    print("4. Pressione ENTER — o script aplica lotérica + dezenas + Aplicar e extrai")
    input("\n>>> ENTER para continuar...")


def preparar_sessao_extracao() -> bool:
    """Navegador + login antes de extrair."""
    if not FILTRO_LOTERICA:
        print("\n>>> Configure a lotérica primeiro (opcao 9).")
        return False
    if not iniciar_navegador():
        return False
    aguardar_login_caixa()
    return True


def extrair_dados_popup():
    """Extrai os dados do popup do bolao"""
    if driver is None:
        return None
    try:
        time.sleep(1.5)
        popup = WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".modal-content, .modal, [class*='modal'], [role='dialog']"))
        )
        return parse_campos_popup(popup.text)
    except Exception:
        return None


def fechar_popup():
    if driver is None:
        return False
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
            except Exception:
                pass
    except Exception:
        pass

    try:
        driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE)
        time.sleep(0.5)
        return True
    except Exception:
        pass

    return False


def encontrar_botoes_boloes():
    if driver is None:
        return []
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
        except Exception:
            pass

    return todos_botoes


def ir_proxima_pagina():
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
            except Exception:
                pass

        return False
    except Exception:
        return False


def extrair_pagina_atual(
    boloes_extraidos,
    textos_ja_extraidos,
    pagina_num,
    filtro_cfg,
    boloes_pagina1=None,
    navegacao_manual=False,
):
    if driver is None:
        return 0, 0, [], 0

    if pagina_num <= 1 or not navegacao_manual:
        print(f"\n>>> Preparando pagina {pagina_num}...")
        if not preparar_extracao_pagina(
            driver, filtro_cfg, pagina_num, navegacao_manual=navegacao_manual,
        ):
            print(f">>> ERRO: nao foi possivel preparar pagina {pagina_num}.")
            return 0, 0, [], 0
    else:
        print(f"\n>>> Pagina {pagina_num}: extraindo (sem clique automatico)...")

    print(f"\n{'='*60}")
    print(f"  PAGINA {pagina_num}")
    print(f"{'='*60}")

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    botoes = encontrar_botoes_boloes()
    print(f"\nBotoes encontrados nesta pagina: {len(botoes)}")

    if len(botoes) == 0:
        print(">>> AVISO: Nenhum botao de bolao encontrado!")
        return 0, 0, [], 0

    extraidos_pagina = 0
    duplicados_pagina = 0
    rejeitados_loterica = 0
    rejeitados_dezenas = 0
    textos_pagina_atual = []

    for i, botao in enumerate(botoes):
        try:
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", botao)
            time.sleep(0.3)

            botao.click()
            time.sleep(1.5)

            dados = extrair_dados_popup()

            if dados and dados.get('hash_bolao'):
                if not bolao_corresponde_loterica(dados, filtro_cfg):
                    rejeitados_loterica += 1
                    lot_out = (dados.get('nome_loterica') or 'N/A')[:35]
                    print(f"  [{i+1}/{len(botoes)}] IGNORADO (outra loterica): {lot_out}")
                    fechar_popup()
                    time.sleep(0.3)
                    continue

                if not bolao_atende_filtro(dados, filtro_cfg):
                    rejeitados_dezenas += 1
                    q1 = dados.get('qtd_dezenas_aposta_1') or len(dados.get('dezenas_aposta') or [])
                    esperado = filtro_cfg.qtd_dezenas or '?'
                    lot_out = (dados.get('nome_loterica') or 'N/A')[:30]
                    print(f"  [{i+1}/{len(botoes)}] IGNORADO ({q1} dez., filtro={esperado}): {lot_out}")
                    fechar_popup()
                    time.sleep(0.3)
                    continue

                assinatura = dados.get('hash_bolao')
                textos_pagina_atual.append(assinatura)

                if assinatura in textos_ja_extraidos:
                    duplicados_pagina += 1
                    dez = dados.get('dezenas_aposta') or []
                    n_ap = dados.get('total_apostas') or len(dados.get('apostas') or [])
                    preview = ' '.join(dez[:6]) + ('...' if len(dez) > 6 else '')
                    print(f"  [{i+1}/{len(botoes)}] DUPLICADO (mesmas dezenas): ap={n_ap} | {preview}")
                else:
                    textos_ja_extraidos.add(assinatura)
                    dados['pagina'] = pagina_num
                    dados['indice'] = len(boloes_extraidos) + 1
                    if filtro_cfg.qtd_dezenas is not None:
                        dados['filtro_qtd_dezenas'] = filtro_cfg.qtd_dezenas
                    boloes_extraidos.append(dados)
                    extraidos_pagina += 1

                    loterica = dados.get('nome_loterica', 'N/A')[:35]
                    cidade = dados.get('cidade_uf', '')[:20]
                    n_ap = dados.get('total_apostas') or 0
                    mod = (dados.get('modalidade') or '')[:12]
                    q1 = dados.get('qtd_dezenas_aposta_1') or len(dados.get('dezenas_aposta') or [])
                    print(f"  [{i+1}/{len(botoes)}] NOVO #{len(boloes_extraidos)}: {mod} | {n_ap} ap. | Ap.1={q1} dez.")

            fechar_popup()
            time.sleep(0.5)

            if (i + 1) % 5 == 0:
                manter_sessao_ativa(driver)

        except Exception:
            fechar_popup()
            continue

    print(f"\n  Resumo pagina {pagina_num}:")
    print(f"    - Novos: {extraidos_pagina}")
    print(f"    - Duplicados: {duplicados_pagina}")
    print(f"    - Ignorados (outra loterica): {rejeitados_loterica}")
    print(f"    - Ignorados (qtd dezenas): {rejeitados_dezenas}")
    print(f"    - Total acumulado: {len(boloes_extraidos)}")

    return extraidos_pagina, duplicados_pagina, textos_pagina_atual, rejeitados_loterica + rejeitados_dezenas


def detectar_loop_por_conteudo(textos_pagina1, textos_pagina_atual):
    if not textos_pagina1 or not textos_pagina_atual:
        return False

    boloes_identicos = sum(1 for texto in textos_pagina_atual if texto in textos_pagina1)
    percentual_identico = boloes_identicos / len(textos_pagina_atual) if textos_pagina_atual else 0

    return percentual_identico >= 0.8


def salvar_parcial(boloes, arquivo_base):
    if not boloes:
        return
    arquivo = os.path.join(DEST_DIR, f"{arquivo_base}.json")
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(boloes, f, ensure_ascii=False, indent=2)
    print(f"  >>> Salvo parcial: {len(boloes)} boloes")


def extrair_todos_boloes():
    """Extrai todos os boloes de todas as paginas COM DETECÇÃO AUTOMÁTICA DE LOOP"""
    boloes = []
    textos_ja_extraidos = set()
    max_paginas = 50

    arquivo_base = gerar_arquivo_base(FILTRO_LOTERICA, ROTULO_ARQUIVO)
    mod_slug = ROTULO_ARQUIVO.slug if ROTULO_ARQUIVO else 'quina'
    filas_dez = fila_qtd_dezenas(FILTRO_LOTERICA, mod_slug)

    print("\n" + "="*60)
    print("  INICIANDO EXTRACAO AUTOMATICA")
    print("="*60)
    print("\nO script vai:")
    print("  1. Extrair TODAS as paginas da loterica (1, 2, 3, 4...)")
    print("  2. Pagina 1: aplica filtro | Pagina 2+: so clica Seguinte (sem resetar)")
    print("  3. Parar somente quando nao houver mais paginas")
    if FILTRO_LOTERICA.varrer_dezenas:
        print(f"  4. Varrer qtd. de dezenas: {' → '.join(str(q) for q in filas_dez)}")
    print(f"\nArquivo: {arquivo_base}.json")
    print(f"Lotérica: {FILTRO_LOTERICA.termo}")
    print(f"Modalidade: {ROTULO_NOME} (selecionada por voce no site)")
    print("\nAguarde...\n")

    inicio = time.time()

    for idx_dez, qtd in enumerate(filas_dez, 1):
        cfg = cfg_com_qtd(FILTRO_LOTERICA, qtd)
        pagina = 1
        paginas_sem_novos = 0
        textos_pagina1 = []

        print("\n" + "#"*60)
        print(f"  FILTRO DEZENAS: {qtd or 'qualquer'} ({idx_dez}/{len(filas_dez)})")
        print("#"*60)

        while pagina <= max_paginas:
            if not garantir_sessao_caixa(driver, pagina):
                print(f"\n  FIM — sessao perdida na pagina {pagina}.")
                return boloes, arquivo_base

            novos, duplicados, textos_pagina_atual, rejeitados = extrair_pagina_atual(
                boloes, textos_ja_extraidos, pagina, cfg, textos_pagina1
            )

            if pagina == 1:
                textos_pagina1 = textos_pagina_atual.copy()

            if novos > 0:
                salvar_parcial(boloes, arquivo_base)

            print(f"\n>>> Pagina {pagina} concluida: +{novos} novos | total {len(boloes)} boloes")

            if pagina > 1 and novos == 0 and duplicados > 0 and rejeitados == 0:
                print("  >>> Muitos duplicados — verifique se as dezenas foram lidas (Aposta 1).")

            if pagina > 2 and detectar_loop_por_conteudo(textos_pagina1, textos_pagina_atual):
                print(f"\n  LOOP detectado na pagina {pagina} — encerrando este filtro de dezenas.")
                break

            if novos == 0 and duplicados == 0 and rejeitados == 0:
                paginas_sem_novos += 1
                if paginas_sem_novos >= 2:
                    print(f"\n  {paginas_sem_novos} paginas vazias seguidas — fim deste filtro.")
                    break
            else:
                paginas_sem_novos = 0

            if not tem_proxima_pagina(driver):
                print(f"\n  FIM filtro {qtd} dezenas — ultima pagina: {pagina}")
                break

            pagina += 1
            manter_sessao_ativa(driver)
            time.sleep(0.5)

        print(f"\n>>> Filtro {qtd} dezenas concluido | total acumulado: {len(boloes)} boloes")

    tempo_total = time.time() - inicio
    minutos = int(tempo_total // 60)
    segundos = int(tempo_total % 60)

    print(f"\n{'='*60}")
    print("  EXTRACAO CONCLUIDA!")
    print(f"{'='*60}")
    print(f"\n  Total de boloes extraidos: {len(boloes)}")
    print(f"  Loterica filtrada: {FILTRO_LOTERICA.termo}")
    print(f"  Filtros de dezenas: {len(filas_dez)}")
    print(f"  Tempo total: {minutos}min {segundos}seg")
    print(f"  Arquivo: {arquivo_base}.json")
    print(f"  Local: {DEST_DIR}")
    print("="*60)

    return boloes, arquivo_base


def extrair_por_paginas():
    """Extrai boloes pagina por pagina com confirmacao do usuario"""
    boloes = []
    textos_ja_extraidos = set()
    pagina = 1
    textos_pagina1 = []

    arquivo_base = gerar_arquivo_base(FILTRO_LOTERICA, ROTULO_ARQUIVO)

    print("\n" + "="*60)
    print("  EXTRACAO PAGINA POR PAGINA")
    print("="*60)
    print(f"\nArquivo: {arquivo_base}.json")
    print(f"Lotérica: {FILTRO_LOTERICA.termo}")
    print("\n  Pagina 1: script aplica filtro")
    print("  Pagina 2+: VOCE navega no site | script NAO clica em Seguinte")
    print("\nIniciando...\n")

    if not aplicar_filtro_loterica(driver, FILTRO_LOTERICA):
        print("\n>>> AVISO: Filtro automatico falhou — aplique manualmente e ENTER...")
        input()

    inicio = time.time()

    while True:
        if not garantir_sessao_caixa(driver, pagina):
            break

        if pagina > 1:
            print("\n" + "="*60)
            print(f"  ANTES DA PAGINA {pagina}")
            print("="*60)
            print("  1. No navegador: clique Seguinte (ou no numero) ate a pagina certa")
            print("  2. O script NAO vai clicar — so vai extrair os boloes")
            print("  3. Quando estiver na pagina certa, pressione ENTER aqui")
            try:
                input("\n>>> ENTER quando estiver na pagina certa... ")
            except EOFError:
                break

        novos, duplicados, textos_pagina_atual, _rejeitados = extrair_pagina_atual(
            boloes, textos_ja_extraidos, pagina, FILTRO_LOTERICA, textos_pagina1,
            navegacao_manual=(pagina > 1),
        )

        if pagina == 1:
            textos_pagina1 = textos_pagina_atual.copy()

        if novos > 0:
            salvar_parcial(boloes, arquivo_base)

        if pagina > 1 and detectar_loop_por_conteudo(textos_pagina1, textos_pagina_atual):
            print("\n  LOOP DETECTADO — extracao encerrada.")
            break

        if duplicados > 0 and novos == 0:
            print("\n  AVISO: Todos boloes desta pagina sao duplicados!")

        print("\n" + "-"*60)
        print("  [ENTER] Continuar  |  [sair] Finalizar")
        print("  (na proxima volta voce navega manualmente para a pagina seguinte)")
        print("-"*60)

        comando = input(">>> ").strip().lower()
        if comando == 'sair':
            break

        if not tem_proxima_pagina(driver):
            print("\n  FIM DA PAGINACAO")
            break

        pagina += 1
        time.sleep(0.5)

    tempo_total = time.time() - inicio
    minutos = int(tempo_total // 60)
    segundos = int(tempo_total % 60)

    print(f"\n  Total: {len(boloes)} boloes | {pagina} pagina(s) | {minutos}min {segundos}seg")
    print(f"  Arquivo: {arquivo_base}.json")

    return boloes, arquivo_base


def salvar_dados(boloes):
    if not boloes:
        print("\nNenhum bolao extraido.")
        return None

    arquivo = os.path.join(DEST_DIR, f"boloes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(boloes, f, ensure_ascii=False, indent=2)

    print(f"\n  Arquivo salvo: {arquivo} ({len(boloes)} boloes)")
    return arquivo


def menu_principal() -> None:
    """Menu em loop — processo permanece ativo até CTRL+C."""
    global FILTRO_LOTERICA, ROTULO_ARQUIVO, ROTULO_NOME

    while True:
        try:
            lot = FILTRO_LOTERICA.termo if FILTRO_LOTERICA else '(nao configurada)'
            dez = FILTRO_LOTERICA.qtd_dezenas if FILTRO_LOTERICA and FILTRO_LOTERICA.qtd_dezenas else 'qualquer'
            varrer = FILTRO_LOTERICA.varrer_dezenas if FILTRO_LOTERICA else False
            mod_slug = ROTULO_ARQUIVO.slug if ROTULO_ARQUIVO else 'quina'

            print("\n" + "=" * 60)
            print("  MENU PRINCIPAL")
            print("=" * 60)
            print(f"\n  Lotérica: {lot}")
            print(f"  Dezenas:  {dez}  |  Varrer todas: {'sim' if varrer else 'nao'}")
            if FILTRO_LOTERICA and varrer:
                fila = fila_qtd_dezenas(FILTRO_LOTERICA, mod_slug)
                print(f"  Sequencia: {' -> '.join(str(q) for q in fila)}")
            print(f"  Modalidade: {ROTULO_NOME} (selecione no site da Caixa)")
            print("\n  Pagina 1: script aplica filtro (lotérica + dezenas + Aplicar).")
            print("  Pagina 2+: [1] tenta 1 clique Seguinte | [2] VOCE navega, script so extrai.")
            print("\n[1] Extrair TODOS (automatico — 1 clique Seguinte por pagina)")
            print("[2] Extrair POR PAGINAS (recomendado se paginacao falhar)")
            print("[3] Extrair MANUAL (um popup por vez)")
            print("[9] Configurar / trocar lotérica e dezenas")
            print("[0] Fechar navegador (menu continua | CTRL+C para sair)")
            print("-" * 60)

            opcao = input("Opcao: ").strip()

            if opcao == "1":
                if not preparar_sessao_extracao():
                    continue
                boloes, arquivo_base = extrair_todos_boloes()
                if boloes:
                    print(f"\n  Arquivo final: {os.path.join(DEST_DIR, arquivo_base + '.json')}")

            elif opcao == "2":
                if not preparar_sessao_extracao():
                    continue
                boloes, arquivo_base = extrair_por_paginas()
                if boloes:
                    print(f"\n  Arquivo final: {os.path.join(DEST_DIR, arquivo_base + '.json')}")

            elif opcao == "3":
                if not preparar_sessao_extracao():
                    continue
                boloes = []
                textos_manual = set()
                print("\n  MODO MANUAL — clique no bolao no site, volte e pressione ENTER")

                while True:
                    comando = input("\n[ENTER] extrair | [sair] terminar: ").strip().lower()
                    if comando == 'sair':
                        break
                    dados = extrair_dados_popup()
                    if dados:
                        texto = dados.get('texto_completo', '')
                        if texto in textos_manual:
                            print("  >>> DUPLICADO!")
                        else:
                            textos_manual.add(texto)
                            boloes.append(dados)
                            print(f"  Loterica: {dados.get('nome_loterica', 'N/A')} | Total: {len(boloes)}")
                    else:
                        print("  Popup nao encontrado.")

                salvar_dados(boloes)

            elif opcao == "9":
                configurar_loterica()

            elif opcao == "0":
                fechar_navegador()
                print("\n>>> Navegador fechado. Processo continua — Press CTRL+C to quit")

            else:
                print("\n>>> Opcao invalida.")

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"\n>>> ERRO: {exc}")
            traceback.print_exc()
            print(">>> Voltando ao menu...\n")


def main() -> None:
    print("=" * 60)
    print("  EXTRATOR DE BOLOES DA CAIXA (Terminal)")
    print("=" * 60)
    print(f"\n  Pasta JSON: {DEST_DIR}")
    print("\n  * Serving extrator (modo terminal)")
    print("  * Press CTRL+C to quit\n")
    print("=" * 60)

    if not configurar_loterica():
        print("\n>>> Configure a lotérica pelo menu (opcao 9).")

    menu_principal()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nEncerrado pelo usuario (CTRL+C).")
    finally:
        fechar_navegador()
        print("Fim!")
