# -*- coding: utf-8 -*-
"""
Extrator de bolões via API (interceptação JSON) — Caixa.

Fluxo [1] AUTOMÁTICO (principal):
  1. Terminal pede: MODALIDADE + CONCURSO (antes de abrir o Edge)
  2. Edge abre — faça LOGIN, selecione modalidade e aplique filtros → APLICAR
  3. Volte ao terminal e pressione ENTER
  4. Script extrai pág. 1, 2, 3… (Seguinte) até o botão desabilitar
  5. JSON gravado em json-boloes/ em tempo real (KBs crescem a cada página)

Fluxo [2] MANUAL (opcional): ENTER a cada página / vários filtros na mesma sessão.
"""
from __future__ import annotations

import glob
import json
import os
import re
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional, Tuple

from selenium import webdriver

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from boloes_api_caixa import (
    LEGENDA_API,
    aguardar_capturas_api,
    aguardar_detalhes_visiveis,
    contar_respostas_detalhar,
    detalhar_pagina_ate_esperado,
    detectar_detalhes_pagina,
    instalar_interceptador_api,
    ler_capturas_api,
    ler_metadados_paginacao_api,
    limpar_capturas_api,
    limpar_marcas_detalhes_pagina,
    preparar_pagina_para_detalhes,
    resumo_capturas,
    salvar_capturas_brutas,
)
from boloes_modalidades import (
    TECLAS_ESPECIAIS,
    TODAS_MODALIDADES,
    extrair_concurso_de_boloes,
    extrair_modalidade_de_boloes,
    imprimir_menu_modalidades,
    nome_arquivo_consolidado_padrao,
    nome_arquivo_sessao,
    resolver_modalidade_menu,
)
from boloes_consolidar import (
    carregar_json_boloes,
    consolidar_sessao,
    hashes_de_lista,
    hashes_pagina,
    localizar_arquivo_sessao_existente,
    mesclar_listas,
    salvar_json_boloes,
    salvar_json_continuacao,
)
from boloes_pasta_bds import detectar_modalidade_site
from boloes_filtro_loterica import (
    FiltroLotericaConfig,
    _carregar_config_cache,
    bolao_atende_filtro,
    bolao_corresponde_loterica,
    cfg_qualquer_loterica,
    eh_ultima_pagina,
    gerar_arquivo_base,
    garantir_sessao_caixa,
    ler_config_extracao,
    ler_filtro_aplicado_site,
    parse_termo_loterica,
    aplicar_filtro_loterica,
    ir_proxima_pagina_lista,
    ir_para_pagina_lista,
    preparar_pagina_loterica,
    sessao_caixa_ativa,
    slug_loterica,
    ultima_pagina_detectada,
)

CONFERENCIAS_BOLOES_DIR = os.path.normpath(os.path.join(SCRIPT_DIR, '..'))
PASTA_JSON = os.path.join(CONFERENCIAS_BOLOES_DIR, 'json-boloes')
PASTA_CAPTURAS = os.path.join(CONFERENCIAS_BOLOES_DIR, 'capturas-api')
URL_BOLOES = 'https://www.loteriasonline.caixa.gov.br/silce-web/#/bolao-caixa'

MSG_ULTIMA_PAGINA = 'Última página — botão Seguinte desabilitado. Extração concluída.'

for _pasta in (CONFERENCIAS_BOLOES_DIR, PASTA_JSON, PASTA_CAPTURAS):
    os.makedirs(_pasta, exist_ok=True)

driver = None
FILTRO_LOTERICA: Optional[FiltroLotericaConfig] = None
ROTULO_ARQUIVO = None
ROTULO_NOME = 'modalidade atual'
SESSAO_AUTORIZADA = False

# ─────────────────────────────────────────────────────────────────────────────
# NOVO: coleta de modalidade + concurso ANTES de abrir o Edge
# ─────────────────────────────────────────────────────────────────────────────

MAPA_MODALIDADES_RAPIDO = {
    '1': 'MEGA_SENA',
    '2': 'QUINA',
    '3': 'LOTOFACIL',
    '4': 'LOTOMANIA',
    '5': 'TIMEMANIA',
    '6': 'DIA_DE_SORTE',
    '7': 'SUPER_SETE',
    '8': 'DUPLA_SENA',
    '9': 'MAIS_MILIONARIA',
}

    # Especiais: usa diretamente o TECLAS_ESPECIAIS já definido no seu código


def _separador(char='=', n=60):
    print(char * n, flush=True)


def _out(msg: str = '') -> None:
    """Print imediato no terminal."""
    print(msg, flush=True)


def _coletar_modalidade_pre_extracao() -> Optional[object]:
    """
    Pergunta a modalidade ANTES de abrir o Edge.
    Retorna objeto de modalidade ou None (auto-detectar depois).
    """
    _separador()
    _out('  PASSO 1 — MODALIDADE')
    _out('  Informe a modalidade que você vai extrair no site:')
    _out('')
    _out('  [1] Mega-Sena       [2] Quina         [3] Lotofácil')
    _out('  [4] Lotomania       [5] Timemania      [6] Dia de Sorte')
    _out('  [7] Super Sete      [8] Dupla Sena     [9] +Milionária')
    _out('  Especiais: QSJ | DSP | LTI | MSV | MS3')
    _out('  ENTER = detectar automaticamente no site')
    _separador('-')

    try:
        resp = input('  Modalidade: ').strip().upper()
    except EOFError:
        return None

    if not resp:
        _out('  [OK] Modalidade será detectada automaticamente ao iniciar.')
        return None

    # Número 1-9
    if resp in MAPA_MODALIDADES_RAPIDO:
        slug = MAPA_MODALIDADES_RAPIDO[resp]
        mod = resolver_modalidade_menu(slug)
        if mod:
            _out(f'  [OK] Modalidade: {mod.label}')
            return mod

    # Especiais: QSJ, DSP, LTI, etc. — usa o mesmo TECLAS_ESPECIAIS do seu código
    if resp in TECLAS_ESPECIAIS:
        mod = resolver_modalidade_menu(resp)
        if mod:
            _out(f'  [OK] Modalidade especial: {mod.label}')
            return mod

    # Texto livre (MEGA_SENA, QUINA, etc.)
    mod = resolver_modalidade_menu(resp)
    if mod:
        _out(f'  [OK] Modalidade: {mod.label}')
        return mod

    _out(f'  [AVISO] "{resp}" não reconhecido — será detectado automaticamente.')
    return None


def _coletar_concurso_pre_extracao() -> str:
    """
    Pergunta o número do concurso ANTES de abrir o Edge.
    Retorna string com dígitos ou '' para auto-detectar.
    """
    _separador()
    _out('  PASSO 2 — CONCURSO')
    _out('  Informe o número do concurso que você vai extrair:')
    _out('  Exemplo: 3024  |  ENTER = detectar automaticamente no site')
    _separador('-')

    try:
        resp = input('  Concurso nº: ').strip()
    except EOFError:
        return ''

    digits = re.sub(r'\D', '', resp)
    if digits:
        _out(f'  [OK] Concurso informado: {digits}')
        return digits

    _out('  [OK] Concurso será detectado automaticamente da primeira página.')
    return ''


def _exibir_resumo_pre_extracao(mod, concurso: str, cfg) -> None:
    """Mostra no terminal o resumo completo antes de abrir o Edge."""
    _separador()
    _out('  RESUMO — CONFIGURAÇÃO DA EXTRAÇÃO')
    _separador('-')
    _out(f'  Modalidade  : {mod.label if mod else "detectar automaticamente"}')
    _out(f'  Concurso    : {concurso if concurso else "detectar automaticamente"}')
    if cfg:
        if getattr(cfg, 'qualquer_loterica', False):
            _out(f'  Lotérica    : QUALQUER + {cfg.qtd_dezenas or 15} dezenas')
        elif cfg.termo:
            _out(f'  Lotérica    : {cfg.termo}')
        else:
            _out('  Lotérica    : filtro manual no site')
    _out(f'  Destino     : json-boloes/')
    _out(f'  Gravação    : tempo real (KBs crescem a cada página)')
    _separador()
    _out('')
    _out('  Agora:')
    _out('  1. O Edge vai abrir')
    _out('  2. Faça LOGIN na Caixa')
    _out(f'  3. Escolha a modalidade: {mod.label if mod else "(a mesma informada acima)"}')
    _out(f'  4. Informe o concurso nº {concurso if concurso else "(o mesmo informado acima)"}')
    _out('  5. Aplique os filtros → clique APLICAR → página 1 carregada')
    _out('  6. Volte aqui e pressione ENTER')
    _separador()


# ─────────────────────────────────────────────────────────────────────────────
# Utilitários gerais
# ─────────────────────────────────────────────────────────────────────────────

def _driver_url(timeout: float = 6.0) -> str:
    if driver is None:
        return ''

    def _ler() -> str:
        try:
            return (driver.execute_script('return window.location.href || "";') or '').strip()
        except Exception:
            return (driver.current_url or '').strip()

    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(_ler).result(timeout=timeout)
    except FuturesTimeout:
        _out('  [AVISO] Edge não respondeu a tempo — clique na janela do navegador.')
        return ''
    except Exception:
        return ''


def _no_site_boloes() -> bool:
    url = _driver_url().lower()
    if not url:
        return driver is not None and sessao_caixa_ativa(driver)
    if any(x in url for x in ('login.caixa.gov.br', 'openid-connect', '/auth/realms/')):
        return False
    return 'loteriasonline.caixa.gov.br' in url or 'silce-web' in url


def _novo_painel_extracao() -> dict:
    return {
        'paginas_processadas': 0,
        'paginas_com_dados': 0,
        'paginas_vazias': 0,
        'capturas_api': 0,
        'descartados_loterica': 0,
        'por_pagina': {},
    }


def _imprimir_painel_pagina(pagina: int, n_novos: int, boloes: list, hashes: set, painel: dict) -> None:
    painel['paginas_processadas'] = pagina
    painel['por_pagina'][pagina] = n_novos
    if n_novos > 0:
        painel['paginas_com_dados'] += 1
    else:
        painel['paginas_vazias'] += 1

    pag_com = painel['paginas_com_dados']
    pag_vaz = painel['paginas_vazias']
    caps_pag = painel.get('capturas_ultima_pagina', 0)
    n_det = painel.get('detalhes_tela_pagina', 0)
    pend = painel.get('pendentes_pagina', 0)

    # Mostra tamanho do arquivo JSON em tempo real
    ab = painel.get('arquivo_base', '')
    kb_info = ''
    if ab:
        path_json = os.path.join(PASTA_JSON, f'{ab}.json')
        if os.path.isfile(path_json):
            kb = os.path.getsize(path_json) / 1024
            kb_info = f' | 💾 {kb:.1f} KB no disco'

    print('\n  ' + '-' * 56)
    print(f'  [PAINEL] Página {pagina} concluída{kb_info}')
    linha = f'    Nesta página : +{n_novos} registro(s) | {caps_pag} captura(s) API'
    if n_det:
        linha += f' | detalhes_tela={n_det}'
        if pend:
            linha += f' | faltam={pend}'
    print(linha)
    print(f'    Total sessão  : {len(boloes)} registro(s) | {len(hashes)} único(s)')
    print(f'    Páginas       : {pagina} processada(s) | {pag_com} com dados | {pag_vaz} vazia(s)')
    if painel['capturas_api']:
        print(f'    Capturas API  : {painel["capturas_api"]} acumulada(s) na sessão')
    if painel['descartados_loterica']:
        print(f'    Descartados   : {painel["descartados_loterica"]} (outra lotérica)')
    print('  ' + '-' * 56)


def _imprimir_resumo_final(
    boloes: list,
    hashes: set,
    painel: dict,
    arquivo_base: str,
    cfg,
    tempo_seg: int,
) -> None:
    path_sessao = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
    kb_final = os.path.getsize(path_sessao) / 1024 if os.path.isfile(path_sessao) else 0

    print('\n' + '=' * 60)
    print('  RESUMO FINAL DA EXTRAÇÃO')
    print('=' * 60)
    print(f'\n  Lotérica alvo      : {cfg.termo or ("QUALQUER" if cfg.qualquer_loterica else "(filtro manual)")}')
    print(f'  Páginas processadas: {painel["paginas_processadas"]}')
    print(f'  Páginas com dados  : {painel["paginas_com_dados"]}')
    print(f'  Páginas vazias     : {painel["paginas_vazias"]}')
    print(f'  Registros no arquivo : {len(boloes)} (modalidade + concurso — pronto p/ importar)')
    if painel.get('registros_loterica_alvo') is not None and cfg.termo:
        print(f'  Lotérica alvo (ref.) : {painel["registros_loterica_alvo"]} reg.')
    print(f'  Hashes únicos sessão : {len(hashes)}')
    cont = painel.get('continuidade')
    if cont:
        print(f'  Base preservada    : {cont["existentes"]} reg. em {cont["arquivo"]} ({cont.get("kb", "?")} KB)')
    if os.path.isfile(path_sessao):
        total_disco = len(carregar_json_boloes(path_sessao))
        novos_sessao = max(0, total_disco - (cont['existentes'] if cont else 0))
        print(f'  Total no arquivo   : {total_disco} reg. (+{novos_sessao} novo(s) nesta extração)')
    print(f'  Capturas API       : {painel["capturas_api"]} JSON(s)')
    if painel['descartados_loterica']:
        print(f'  Descartados        : {painel["descartados_loterica"]} (lotérica diferente)')
    if painel.get('descartados_modalidade'):
        print(f'  Descartados        : {painel["descartados_modalidade"]} (modalidade diferente)')
    print(f'  Tempo              : {tempo_seg // 60}min {tempo_seg % 60}s')
    print(f'  Arquivo            : {path_sessao}')
    print(f'  Tamanho final      : {kb_final:.1f} KB')

    if painel['por_pagina']:
        print('\n  Registros por página:')
        for pg in sorted(painel['por_pagina']):
            n = painel['por_pagina'][pg]
            barra = '#' * min(n, 40) if n else '(vazia)'
            print(f'    Pág {pg:>3}: {n:>4}  {barra}')
    print('=' * 60)


def _rotulo_nome() -> str:
    return ROTULO_ARQUIVO.label if ROTULO_ARQUIVO else 'modalidade atual'


def _rotulo_modalidade_menu() -> str:
    if not ROTULO_ARQUIVO:
        return '(não configurada)'
    m = ROTULO_ARQUIVO
    if getattr(m, 'especial', False) and m.tecla:
        return f'{m.tecla} — {m.label}'
    num = getattr(m, 'numero', None)
    if num and num <= 9:
        return f'[{num}] {m.label}'
    return m.label


def _imprimir_tabela_modalidades_resumida() -> None:
    _out('\n  OPCIONAL — forçar parser no terminal (senão usa API do site):')
    _out('  M1 Mega-Sena   M2 Quina        M3 Lotofácil')
    _out('  M4 Lotomania   M5 Timemania    M6 Dia de Sorte')
    _out('  M7 Super Sete  M8 Dupla Sena   M9 +Milionária')
    _out('  Especiais: DSP | QSJ | LTI | MSV | MS3')


def _imprimir_status_modalidade() -> None:
    if ROTULO_ARQUIVO:
        _out(f'\n  Parser terminal (opcional): {_rotulo_modalidade_menu()}')
    else:
        _out('\n  Modalidade: vem da API do site (MEGA_SENA, QUINA…) — não precisa M1.')


def _aplicar_modalidade(mod) -> bool:
    global ROTULO_ARQUIVO, ROTULO_NOME
    if not mod:
        return False
    ROTULO_ARQUIVO = mod
    ROTULO_NOME = _rotulo_nome()
    _out(f'\n>>> Modalidade: {_rotulo_modalidade_menu()}')
    if getattr(mod, 'especial', False):
        _out(f'>>> Base: {mod.base_label} | Época: {mod.epoca}')
    _out(f'>>> Extrai: {mod.extracao}')
    return True


def _trocar_modalidade_por_entrada(entrada: str) -> bool:
    mod = resolver_modalidade_menu(entrada)
    if not mod:
        return False
    return _aplicar_modalidade(mod)


# ─────────────────────────────────────────────────────────────────────────────
# Navegador
# ─────────────────────────────────────────────────────────────────────────────

def iniciar_navegador() -> bool:
    global driver
    if driver is not None:
        return True
    try:
        _out('\nIniciando Edge (hook API)...')
        opts = webdriver.EdgeOptions()
        opts.page_load_strategy = 'eager'
        driver = webdriver.Edge(options=opts)
        driver.set_page_load_timeout(45)
        instalar_interceptador_api(driver)
        driver.get(URL_BOLOES)
        _out('Edge aberto — faça LOGIN no navegador.')
        _out('(Captura só começa após ENTER com sessão detectada.)')
        _out('')
        _out('  Aguardando login no Edge...')
        if not _aguardar_login_inicial():
            _out('  [AVISO] Login não detectado — extração pode falhar.')
        else:
            _out('  [OK] Login detectado — pronto para extrair.')
        return True
    except Exception as exc:
        print(f'\n>>> ERRO ao abrir Edge: {exc}')
        traceback.print_exc()
        driver = None
        return False


def _aguardar_login_inicial() -> bool:
    fim = time.time() + 180
    while time.time() < fim:
        try:
            if _usuario_logado_caixa() or _no_site_boloes():
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


def fechar_navegador() -> None:
    global driver
    if driver is not None:
        try:
            print('\nFechando navegador...')
            driver.quit()
        except Exception:
            pass
        driver = None


# ─────────────────────────────────────────────────────────────────────────────
# Configuração de lotérica e modalidade
# ─────────────────────────────────────────────────────────────────────────────

def configurar_modalidade_apenas() -> bool:
    global ROTULO_ARQUIVO, ROTULO_NOME
    try:
        from boloes_modalidades import ler_modalidade_terminal
        ROTULO_ARQUIVO = ler_modalidade_terminal()
        ROTULO_NOME = _rotulo_nome()
        print(f'\n>>> Modalidade: {ROTULO_NOME}')
        print('>>> Modo [2]: lotérica e dezenas você escolhe NO SITE a cada rodada.')
        return True
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f'\n>>> ERRO na modalidade: {exc}')
        return False


def configurar_loterica() -> bool:
    global FILTRO_LOTERICA, ROTULO_ARQUIVO, ROTULO_NOME
    try:
        FILTRO_LOTERICA, ROTULO_ARQUIVO = ler_config_extracao()
        ROTULO_NOME = _rotulo_nome()
        if not FILTRO_LOTERICA or not (FILTRO_LOTERICA.termo or '').strip():
            print('\n>>> Lotérica inválida ou vazia. Tente de novo (ex.: 9833).')
            FILTRO_LOTERICA = None
            return False
        print(f'\n>>> Config OK | Lotérica: {FILTRO_LOTERICA.termo} | Modalidade: {ROTULO_NOME}')
        return True
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f'\n>>> ERRO na configuração: {exc}')
        traceback.print_exc()
        return False


def _exigir_config_extracao(acao: str = 'extrair') -> bool:
    if FILTRO_LOTERICA and (
        (FILTRO_LOTERICA.termo or '').strip()
        or FILTRO_LOTERICA.codigo
        or FILTRO_LOTERICA.qualquer_loterica
    ):
        return True

    print('\n' + '=' * 60)
    print('  FILTRO NÃO CONFIGURADO')
    print('=' * 60)
    print(f'\n  Para {acao}, use [9]:')
    print('    · lotérica fixa (ex.: 9833), ou')
    print('    · * = QUALQUER lotérica + 15 dezenas')
    print('  Abrindo configuração agora (ou CTRL+C para cancelar)...\n')

    if configurar_loterica():
        return True

    print('\n>>> Sem filtro — use [9] no menu antes de [1].')
    return False


def _exigir_modalidade(acao: str = 'extrair') -> bool:
    if ROTULO_ARQUIVO:
        return True
    print('\n' + '=' * 60)
    print('  MODALIDADE NÃO CONFIGURADA')
    print('=' * 60)
    if configurar_modalidade_apenas():
        return bool(ROTULO_ARQUIVO)
    return False


def _cfg_filtro_site() -> FiltroLotericaConfig:
    qtd = 15
    if FILTRO_LOTERICA and FILTRO_LOTERICA.qtd_dezenas:
        qtd = FILTRO_LOTERICA.qtd_dezenas
    return cfg_qualquer_loterica(qtd)


def _inferir_cfg_de_boloes(boloes: list) -> FiltroLotericaConfig:
    if not boloes:
        return _cfg_filtro_site()
    b = boloes[0]
    nome = (b.get('nome_loterica') or '').strip()
    cod_raw = str(b.get('codigo_loterica') or '').strip()
    digits = re.sub(r'\D', '', cod_raw)
    cod = ''
    if digits:
        cod = digits[-4:] if len(digits) >= 4 else digits
    termo = cod or nome[:40] or 'manual'
    return FiltroLotericaConfig(termo=termo, codigo=cod or None, nome=nome or None)


# ─────────────────────────────────────────────────────────────────────────────
# Login / sessão
# ─────────────────────────────────────────────────────────────────────────────

def _payload_tem_usuario(node) -> bool:
    if isinstance(node, dict):
        if node.get('cpf') or node.get('nome'):
            return True
        for val in node.values():
            if _payload_tem_usuario(val):
                return True
    elif isinstance(node, list):
        for item in node:
            if _payload_tem_usuario(item):
                return True
    return False


def _usuario_logado_caixa() -> bool:
    if not _no_site_boloes():
        return False
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            ok = pool.submit(
                driver.execute_script,
                """
                try {
                    var body = (document.body && document.body.innerText) || '';
                    if (/Olá|Ola|Minha conta|Sair/i.test(body)) return true;
                    for (var i = 0; i < localStorage.length; i++) {
                        var k = localStorage.key(i) || '';
                        if (/token|auth|session|access/i.test(k)) {
                            var v = localStorage.getItem(k) || '';
                            if (v.length > 24) return true;
                        }
                    }
                } catch (e) {}
                return false;
                """,
            ).result(timeout=5)
            if ok:
                return True
    except Exception:
        pass
    try:
        for cap in ler_capturas_api(driver):
            url = (cap.get('url') or '').lower()
            if 'recuperar-dados' in url or 'dxn1yXJpb3' in url:
                if _payload_tem_usuario(cap.get('data')):
                    return True
    except Exception:
        pass
    return False


def aguardar_login_caixa() -> bool:
    print('\n' + '=' * 60)
    print('  FAÇA LOGIN (script pausado)')
    print('=' * 60)
    print('\n1. No Edge: LOGIN na Caixa')
    print('2. Abra Bolões Caixa / lista de bolões')
    print('\n3. Volte aqui e pressione ENTER após o login')

    while True:
        try:
            input('\n>>> ENTER após LOGIN no site... ')
        except EOFError:
            return False

        if _usuario_logado_caixa() or _no_site_boloes():
            _out('\n  Login OK.')
            return True

        print('\n  >>> Ainda na tela de login. Faça login e tente de novo.')


def aguardar_site_pronto() -> bool:
    """Um ENTER: usuário já fez login + modalidade + filtros no site."""
    print('\n' + '=' * 60)
    print('  PREPARE NO SITE — depois ENTER aqui')
    print('=' * 60)
    print('\n  Checklist:')
    print('  ✔ LOGIN feito')
    print('  ✔ Modalidade selecionada')
    print('  ✔ Concurso informado')
    print('  ✔ Filtros (estado, dezenas, lotérica…) aplicados → página 1 visível')
    print('')
    print('  O script clica Seguinte sozinho até desabilitar.')
    print(f'  JSON: {PASTA_JSON}  (cresce em tempo real)')
    print('=' * 60)

    while True:
        try:
            input('\n>>> ENTER para iniciar a extração... ')
        except EOFError:
            return False

        if not _no_site_boloes():
            print('\n  [ERRO] Ainda na tela de login Keycloak!')
            print('  Faça login no Edge e volte à página de bolões.')
            continue

        _out('\n  OK — iniciando extração...')
        return True


def aguardar_filtro_manual_pagina1(rodada: int = 1) -> bool:
    print('\n' + '=' * 60)
    if rodada == 1:
        print('  FILTRO NO SITE — página 1')
    else:
        print(f'  FILTRO {rodada} — troque no site (mesma sessão logada)')
    print('=' * 60)

    while True:
        try:
            input(f'\n>>> ENTER após filtro aplicado (rodada {rodada}, página 1)... ')
        except EOFError:
            return False
        _out('\n  OK — verificando página de bolões...')
        if _no_site_boloes():
            return True
        url = _driver_url() or '(sem resposta do Edge)'
        _out(f'\n  >>> Não está na lista de bolões. URL atual: {url}')
        _out('  Abra Bolões Caixa no Edge, aplique filtro e tente de novo.')


# ─────────────────────────────────────────────────────────────────────────────
# Filtros / modalidade
# ─────────────────────────────────────────────────────────────────────────────

def _modalidade_do_bolao_item(bolao: dict):
    for chave in ('modalidade_slug', 'modalidade'):
        mod = resolver_modalidade_menu(str(bolao.get(chave) or ''))
        if mod:
            return mod
    texto = str(bolao.get('texto_completo') or '')
    if len(texto) > 20:
        mod = resolver_modalidade_menu(texto[:600])
        if mod:
            return mod
    return None


def _filtrar_boloes_modalidade(boloes: list, mod_esperada) -> tuple[list, int]:
    if not mod_esperada or not boloes:
        return list(boloes), 0
    ok: list = []
    descartados = 0
    for b in boloes:
        mod = _modalidade_do_bolao_item(b)
        if mod is None:
            ok.append(b)
        elif mod.slug == mod_esperada.slug:
            ok.append(b)
        else:
            descartados += 1
    return ok, descartados


def _concurso_de_arquivo_base(arquivo_base: str) -> str:
    """Extrai concurso de boloes_3024_mega-sena → '3024'."""
    m = re.match(r'boloes_(\d+)_', (arquivo_base or '').strip())
    return m.group(1) if m else ''


def _filtrar_boloes_concurso(boloes: list, concurso_alvo: str) -> list:
    if not concurso_alvo:
        return list(boloes)
    alvo = re.sub(r'\D', '', str(concurso_alvo))
    if not alvo:
        return list(boloes)
    return [
        b for b in boloes
        if re.sub(r'\D', '', str(b.get('concurso') or '')) == alvo
    ]


def _boloes_para_json_arquivo(boloes: list, mod_esperada, concurso_alvo: str = '') -> list:
    """
    Bolões que entram em boloes_{concurso}_{modalidade}.json:
    modalidade + concurso — SEM filtro de lotérica (arquivo é da modalidade inteira).
    """
    filtrados, _ = _filtrar_boloes_modalidade(boloes, mod_esperada)
    return _filtrar_boloes_concurso(filtrados, concurso_alvo)


def _salvar_capturas_pagina_disco(pagina: int, rodada: int = 1) -> Optional[str]:
    """Persiste capturas API da página em capturas-api/ (backup + recuperação)."""
    if not driver:
        return None
    caminho = os.path.join(PASTA_CAPTURAS, f'api_r{rodada}_p{pagina}_{int(time.time())}.json')
    try:
        salvar_capturas_brutas(driver, caminho)
        return caminho
    except Exception:
        return None


def _modalidade_extracao(driver=None):
    if ROTULO_ARQUIVO:
        _out(f'  Parser terminal: {ROTULO_ARQUIVO.label}')
        return ROTULO_ARQUIVO
    if driver is not None:
        slug = detectar_modalidade_site(driver)
        if slug:
            mod = resolver_modalidade_menu(slug)
            if mod:
                _out(f'  Modalidade no site: {mod.label}')
                return mod
    _out('  Modalidade: lida da API de cada bolão (campo MEGA_SENA, QUINA…)')
    return None


def _validar_modalidade_coerencia(mod_esperada, boloes: list) -> None:
    if not boloes:
        return
    mod_json = extrair_modalidade_de_boloes(boloes)
    label_json = mod_json.label if mod_json else str(boloes[0].get('modalidade') or '?')
    label_site = mod_esperada.label if mod_esperada else '(não definida)'
    concurso = extrair_concurso_de_boloes(boloes)

    if mod_esperada and mod_json and mod_esperada.slug != mod_json.slug:
        _out(f'\n  ERRO: Modalidade site/terminal ({label_site}) difere da gravada no JSON ({label_json}).')

    if mod_esperada and mod_json:
        arq_ok = nome_arquivo_consolidado_padrao(concurso, mod_esperada)
        arq_json = nome_arquivo_consolidado_padrao(concurso, mod_json)
        if arq_ok != arq_json:
            _out(f'  ERRO: Nome do arquivo ({arq_json}) não bate com modalidade do site ({arq_ok}).')
        else:
            _out(f'  OK modalidade: {label_site} | concurso {concurso} | {arq_ok}')


def _renomear_json_sessao(arquivo_base: str, boloes: list, mod) -> str:
    if not boloes:
        return arquivo_base
    novo = nome_arquivo_sessao(extrair_concurso_de_boloes(boloes), extrair_modalidade_de_boloes(boloes) or mod)
    if novo == arquivo_base:
        return arquivo_base
    antigo = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
    destino = os.path.join(PASTA_JSON, f'{novo}.json')
    if os.path.isfile(antigo) and antigo != destino:
        if os.path.isfile(destino):
            existentes = carregar_json_boloes(destino)
            sessao_antigo = carregar_json_boloes(antigo)
            final, _ = mesclar_listas(existentes, sessao_antigo + boloes)
            salvar_json_boloes(destino, final)
            os.remove(antigo)
        else:
            os.rename(antigo, destino)
        _out(f'  Arquivo renomeado: {os.path.basename(destino)}')
    return novo


def _iniciar_continuidade_inteligente(
    arquivo_base: str,
    mod_esperada,
    painel: dict,
) -> Tuple[set, str]:
    mod_slug = mod_esperada.slug if mod_esperada else ''
    path, existentes = localizar_arquivo_sessao_existente(PASTA_JSON, arquivo_base, mod_slug)
    if not existentes:
        return set(), arquivo_base

    hashes = hashes_de_lista(existentes)
    arquivo_efetivo = os.path.splitext(os.path.basename(path))[0]
    kb = os.path.getsize(path) / 1024 if path else 0
    painel['continuidade'] = {
        'path': path,
        'arquivo': os.path.basename(path),
        'existentes': len(existentes),
        'kb': round(kb, 1),
    }
    _out(f'  [CONTINUIDADE] {os.path.basename(path)} — {len(existentes)} reg. ({kb:.1f} KB) serão preservados.')
    _out('  [CONTINUIDADE] Apenas bolões inéditos serão acrescentados.')
    return hashes, arquivo_efetivo


def preparar_login_unico() -> bool:
    global SESSAO_AUTORIZADA
    SESSAO_AUTORIZADA = False
    if not iniciar_navegador():
        return False
    print('\n  Edge aberto — faça LOGIN (script aguarda, nada roda ainda).')
    if not aguardar_login_caixa():
        return False
    if not _usuario_logado_caixa():
        print('\n>>> Login não confirmado. Extração cancelada.')
        return False
    print('\n  Sessão logada — pronta para configurar filtros no site.')
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Salvar parcial (tempo real) — exibe KBs no terminal
# ─────────────────────────────────────────────────────────────────────────────

def salvar_parcial(boloes, arquivo_base, pagina: int = 0):
    path = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
    if not boloes:
        if os.path.isfile(path):
            kb = os.path.getsize(path) / 1024
            _out(
                f'  [SAVE] Pág {pagina or "?"}: 0 novos nesta leva — '
                f'arquivo mantém {len(carregar_json_boloes(path))} reg. ({kb:.1f} KB).'
            )
        else:
            _out(f'  [SAVE] Pág {pagina or "?"}: 0 reg. — arquivo ainda não criado.')
        return path

    sem_hash = sum(1 for b in boloes if not b.get('hash_bolao'))
    if sem_hash:
        _out(f'  [SAVE AVISO] {sem_hash} bolão(ões) sem hash — não entram no JSON.')

    final, novos, anteriores = salvar_json_continuacao(path, boloes)
    kb = os.path.getsize(path) / 1024 if os.path.isfile(path) else 0
    _out(
        f'  💾 SALVO pág {pagina or "?"}: {len(final)} reg. total (+{novos} novos) | '
        f'{kb:.1f} KB | {os.path.basename(path)}'
    )
    return path


def _atualizar_arquivo_base_concurso(arquivo_base: str, concurso: str, mod_esperada) -> str:
    """Renomeia boloes_sem-concurso_* → boloes_{concurso}_* assim que o concurso for detectado."""
    conc = re.sub(r'\D', '', str(concurso or ''))
    if not conc or not mod_esperada:
        return arquivo_base
    novo = nome_arquivo_sessao(conc, mod_esperada)
    if novo == arquivo_base:
        return arquivo_base
    antigo = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
    destino = os.path.join(PASTA_JSON, f'{novo}.json')
    if os.path.isfile(antigo) and antigo != destino:
        if os.path.isfile(destino):
            existentes = carregar_json_boloes(destino)
            sessao = carregar_json_boloes(antigo)
            final, _ = mesclar_listas(existentes, sessao)
            salvar_json_boloes(destino, final)
            os.remove(antigo)
        else:
            os.rename(antigo, destino)
        _out(f'  [ARQUIVO] Renomeado → {novo}.json')
    return novo


def _persistir_json_pagina(
    pagina: int,
    rodada: int,
    arquivo_base: str,
    painel: dict,
    mod_esperada,
    parser_slug: str,
    hashes: set,
    boloes: list,
) -> Tuple[int, str]:
    """
    Gravação garantida após cada página:
    1) salva capturas API em disco
    2) extrai bolões do arquivo de captura
    3) mescla no JSON de sessão (modalidade + concurso)
    """
    from boloes_consolidar import boloes_de_capturas_api
    from boloes_api_caixa import coletar_boloes_das_capturas

    path_cap = _salvar_capturas_pagina_disco(pagina, rodada)
    candidatos: list = []

    if path_cap and os.path.isfile(path_cap):
        candidatos = boloes_de_capturas_api([path_cap])

    if not candidatos and driver:
        candidatos = coletar_boloes_das_capturas(
            driver, set(), None, None, parser_slug, filtrar_dezenas=False,
        )

    conc = painel.get('concurso_alvo') or _concurso_de_arquivo_base(arquivo_base)
    alvo = _boloes_para_json_arquivo(candidatos, mod_esperada, conc)

    if not conc and alvo:
        conc = extrair_concurso_de_boloes(alvo)
        painel['concurso_alvo'] = conc
        alvo = _boloes_para_json_arquivo(candidatos, mod_esperada, conc)

    if conc and mod_esperada:
        arquivo_base = _atualizar_arquivo_base_concurso(arquivo_base, conc, mod_esperada)
        painel['arquivo_base'] = arquivo_base

    if not alvo:
        path = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
        total = len(carregar_json_boloes(path))
        kb = os.path.getsize(path) / 1024 if os.path.isfile(path) else 0
        caps = os.path.basename(path_cap) if path_cap else '—'
        _out(
            f'  [SAVE] Pág {pagina}: 0 bolões parseáveis (captura: {caps}) | '
            f'arquivo: {total} reg. ({kb:.1f} KB)'
        )
        return 0, arquivo_base

    for b in alvo:
        b['pagina'] = pagina
        b['rodada_filtro'] = rodada
        if painel.get('uf_varredura'):
            b['uf_varredura'] = painel['uf_varredura']

    hashes_antes = set(hashes)
    novos_gravar = [b for b in alvo if (b.get('hash_bolao') or '') not in hashes_antes]

    salvar_parcial(alvo, arquivo_base, pagina)

    for b in novos_gravar:
        h = b.get('hash_bolao')
        if h:
            hashes.add(h)
        b['indice'] = len(boloes) + 1
        boloes.append(b)

    return len(novos_gravar), arquivo_base


# ─────────────────────────────────────────────────────────────────────────────
# Captura de página
# ─────────────────────────────────────────────────────────────────────────────

def _capturas_da_rodada(rodada: int) -> list[str]:
    pat = os.path.join(PASTA_CAPTURAS, f'api_r{rodada}_p*.json')
    return sorted(glob.glob(pat))


def _recuperar_boloes_das_capturas(
    cfg,
    parser_slug,
    mod_slug,
    arquivo_base,
    rodada=1,
    mod_esperada=None,
    concurso_alvo: str = '',
    aplicar_filtro_loterica: bool = False,
):
    """Recupera bolões das capturas em disco → JSON de sessão (modalidade+concurso)."""
    from boloes_consolidar import boloes_de_capturas_api

    arquivos = _capturas_da_rodada(rodada)
    if not arquivos:
        arquivos = sorted(glob.glob(os.path.join(PASTA_CAPTURAS, 'api_r*_p*.json')))
    if not arquivos:
        return []

    conc = concurso_alvo or _concurso_de_arquivo_base(arquivo_base)
    cod_lot = cfg.codigo if (aplicar_filtro_loterica and not cfg.qualquer_loterica) else None
    qtd_dez = cfg.qtd_dezenas if aplicar_filtro_loterica else None
    brutos = boloes_de_capturas_api(arquivos, cod_lot, qtd_dez)
    boloes = _boloes_para_json_arquivo(brutos, mod_esperada, conc)
    if aplicar_filtro_loterica:
        boloes = _boloes_do_filtro(boloes, cfg)
    elif not boloes and brutos:
        _out(f'  [RECUPERO] {len(brutos)} bolão(ões) na API, mas 0 para modalidade/concurso alvo.')

    if boloes:
        path = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
        final, novos, anteriores = salvar_json_continuacao(path, boloes)
        mod_b = extrair_modalidade_de_boloes(boloes)
        consolidar_sessao(
            PASTA_JSON,
            conc or extrair_concurso_de_boloes(boloes),
            mod_b.slug if mod_b else mod_slug,
            boloes,
        )
        kb = os.path.getsize(path) / 1024 if os.path.isfile(path) else 0
        _out(
            f'\n  [RECUPERO] {len(final)} reg. no arquivo (+{novos} novos) | '
            f'{kb:.1f} KB | {len(arquivos)} captura(s) API.'
        )
        return boloes
    return []


def _diagnosticar_capturas_sem_filtro(cfg, parser_slug) -> None:
    if not driver:
        return
    from boloes_api_caixa import coletar_boloes_das_capturas

    todos = coletar_boloes_das_capturas(driver, set(), print, None, parser_slug, filtrar_dezenas=False)
    if not todos:
        _out('  [DIAG] Nenhum bolão parseável nas capturas API desta página.')
        return
    lotericas = {}
    for b in todos:
        nome = (b.get('nome_loterica') or '?')[:40]
        lotericas[nome] = lotericas.get(nome, 0) + 1
    _out(f'  [DIAG] API tem {len(todos)} bolão(ões) SEM filtro de lotérica:')
    for nome, q in sorted(lotericas.items(), key=lambda x: -x[1])[:6]:
        _out(f'         · {q}× {nome}')
    if cfg and cfg.termo:
        _out(f'  [DIAG] Filtro ativo: {cfg.termo} — confira se bate com a lotérica no site.')


def _boloes_do_filtro(boloes: list, cfg: FiltroLotericaConfig) -> list:
    if not cfg:
        return list(boloes)
    if cfg.qualquer_loterica or (
        not (cfg.termo or '').strip() and not cfg.codigo and cfg.qtd_dezenas is not None
    ):
        return [b for b in boloes if bolao_atende_filtro(b, cfg)]
    if not cfg.termo and not cfg.codigo:
        return []
    if cfg.qtd_dezenas is not None:
        return [b for b in boloes if bolao_atende_filtro(b, cfg)]
    return [b for b in boloes if bolao_corresponde_loterica(b, cfg)]


def _capturar_pagina_atual(
    cfg, parser_slug, hashes, pagina, boloes, manual, painel, mod_esperada=None, arquivo_base='',
) -> int:
    if not SESSAO_AUTORIZADA:
        print('  [SESSÃO] Captura bloqueada — conclua login + filtro manual antes.')
        return -1
    if not garantir_sessao_caixa(driver, pagina, print):
        print('  [SESSÃO] Extração interrompida — faça login e rode de novo.')
        return -1

    if pagina == 1:
        print('  [FILTRO] Página 1 — aguardando botões Detalhes...')
        n_det = aguardar_detalhes_visiveis(driver, minimo=1, timeout=12, log_fn=print)
        if n_det:
            print(f'  [TELA] {n_det} botão(ões) Detalhes visíveis.')
        else:
            print('  [TELA] Nenhum botão Detalhes detectado — confira filtro no site.')
        time.sleep(0.8)
    else:
        meta_preservar = ler_metadados_paginacao_api(driver)
        if meta_preservar:
            painel['paginacao_api'] = meta_preservar
        limpar_capturas_api(driver)
        if not manual:
            print(f'  [PÁGINA] Avançando para página {pagina} (Seguinte)...')
            if not ir_proxima_pagina_lista(driver, print):
                if cfg.termo:
                    if not preparar_pagina_loterica(driver, cfg, pagina, print):
                        print('  [FILTRO] Falha ao preparar página.')
                        return -1
                elif ultima_pagina_detectada(driver) or eh_ultima_pagina(driver):
                    return -2
                else:
                    meta_nav = ler_metadados_paginacao_api(driver)
                    ultima = (meta_nav or {}).get('ultima_pagina') or 0
                    if pagina <= ultima and ir_para_pagina_lista(driver, pagina, print):
                        print(f'  [PÁGINA] Navegou para página {pagina} (fallback Angular).')
                    elif ultima_pagina_detectada(driver) or eh_ultima_pagina(driver):
                        return -2
                    else:
                        print(f'  [PÁGINA] Seguinte falhou ao ir para página {pagina}.')
                        return -1
            time.sleep(1.2)
            n_det = aguardar_detalhes_visiveis(driver, minimo=1, timeout=12)
            if n_det:
                print(f'  [TELA] Página {pagina}: {n_det} botão(ões) Detalhes visíveis.')
        else:
            print(f'  [FILTRO] Página {pagina} — modo manual (você navegou).')

    aguardar_capturas_api(driver, minimo=1, timeout=12)
    preparar_pagina_para_detalhes(driver, log_fn=print)
    meta = detectar_detalhes_pagina(driver, cfg, 55, preparar=False, log_fn=print)
    n_esperado = meta['n_esperado']
    codigos = meta['codigos']

    if n_esperado:
        print(f'  [TELA] Meta desta página: {n_esperado} bolão(ões).')
        print('  [TELA] Iniciando cliques em Detalhes...')
    else:
        print('  [TELA] Nenhum Detalhes visível — tentando lista API interceptada...')

    # ── Callback: grava no JSON em tempo real a cada bloco de detalhes ───────
    # IMPORTANTE: NÃO faz boloes.append aqui — isso é feito pelo loop principal
    # depois que detalhar_pagina_ate_esperado retorna. O callback só grava no disco.
    concurso_alvo = painel.get('concurso_alvo') or _concurso_de_arquivo_base(arquivo_base)

    def _salvar_tempo_real(boloes_parciais):
        if not arquivo_base or not boloes_parciais:
            return
        ca = painel.get('concurso_alvo') or concurso_alvo
        alvo = _boloes_para_json_arquivo(boloes_parciais, mod_esperada, ca)
        if alvo:
            for b in alvo:
                b['pagina'] = pagina
                b['rodada_filtro'] = painel.get('rodada_filtro', 1)
            salvar_parcial(alvo, painel.get('arquivo_base') or arquivo_base, pagina)

    detalhar_pagina_ate_esperado(
        driver, cfg, parser_slug, hashes, n_esperado, codigos, print,
        on_progresso=_salvar_tempo_real if arquivo_base else None,
    )

    n_caps = len(ler_capturas_api(driver))
    painel['capturas_ultima_pagina'] = n_caps
    painel['capturas_api'] += n_caps
    meta_pag = ler_metadados_paginacao_api(driver)
    if meta_pag:
        painel['paginacao_api'] = meta_pag
    painel['detalhes_tela_pagina'] = n_esperado

    ab = painel.get('arquivo_base') or arquivo_base
    n_gravados, ab = _persistir_json_pagina(
        pagina, painel.get('rodada_filtro', 1), ab, painel, mod_esperada, parser_slug, hashes, boloes,
    )
    painel['arquivo_base'] = ab

    novos_loterica = _boloes_do_filtro(
        [b for b in boloes if b.get('pagina') == pagina], cfg,
    )
    if cfg.termo and n_gravados and len(novos_loterica) != n_gravados:
        _out(
            f'  [FILTRO] Lotérica alvo nesta pág.: {len(novos_loterica)} de {n_gravados} '
            f'(todos {n_gravados} foram gravados no JSON da modalidade).'
        )

    if not n_gravados and n_caps > 0:
        _diagnosticar_capturas_sem_filtro(cfg, parser_slug)

    painel['pendentes_pagina'] = max(0, n_esperado - n_gravados) if n_esperado else 0
    if n_esperado and n_gravados < n_esperado:
        print(f'  [AVISO] Página incompleta: {n_gravados}/{n_esperado} bolões gravados no JSON.')

    return n_gravados


# ─────────────────────────────────────────────────────────────────────────────
# Loop principal de páginas
# ─────────────────────────────────────────────────────────────────────────────

def _loop_extracao_paginas(
    cfg, parser_slug, mod_slug, arquivo_base,
    manual_paginas, rodada_filtro=1, voce_encerra=False,
    painel_extra=None, mod_esperada=None, concurso_alvo: str = '',
):
    boloes: list = []
    hashes: set = set()
    hashes_pagina_anterior: set = set()
    painel = _novo_painel_extracao()
    painel['rodada_filtro'] = rodada_filtro
    painel['arquivo_base'] = arquivo_base
    painel['concurso_alvo'] = concurso_alvo or _concurso_de_arquivo_base(arquivo_base)
    if painel_extra:
        painel.update(painel_extra)
    inicio = time.time()
    pagina = 1

    limpar_capturas_api(driver)
    _out('  [API] Capturas anteriores limpas — só dados desta extração.')

    hashes_base, arquivo_base = _iniciar_continuidade_inteligente(arquivo_base, mod_esperada, painel)
    hashes.update(hashes_base)
    painel['arquivo_base'] = arquivo_base
    if not painel.get('concurso_alvo'):
        painel['concurso_alvo'] = _concurso_de_arquivo_base(arquivo_base)

    dez = cfg.qtd_dezenas or 'qualquer'
    lot_txt = 'QUALQUER lotérica' if cfg.qualquer_loterica else (cfg.termo or '(filtro manual no site)')
    conc_txt = painel.get('concurso_alvo') or 'auto'
    print('\n  [PAINEL] Contadores: páginas | registros/página | total | únicos')
    print(f'  Filtro lotérica: {lot_txt} | dezenas: {dez} (painel/resumo)')
    print(f'  JSON arquivo  : json-boloes/{arquivo_base}.json  (modalidade + concurso {conc_txt})')
    print('  Gravação      : tempo real — KBs crescem a cada página com bolões novos')
    if mod_esperada:
        print(f'  Modalidade alvo: {mod_esperada.label}')

    while True:
        if manual_paginas and pagina > 1:
            try:
                resp = input(
                    f'\n>>> [{cfg.termo}] PÁGINA {pagina} no site — '
                    f'navegue e ENTER | FIM=acabou este filtro: '
                ).strip().upper()
            except EOFError:
                break
            if resp == 'FIM':
                print('  Fim deste filtro (você encerrou).')
                break

        print(f'\n>>> Processando PÁGINA {pagina}...')
        n_novos = _capturar_pagina_atual(
            cfg, parser_slug, hashes, pagina, boloes, manual_paginas, painel, mod_esperada,
            arquivo_base=arquivo_base,
        )
        arquivo_base = painel.get('arquivo_base') or arquivo_base
        if n_novos == -2:
            print(f'\n  {MSG_ULTIMA_PAGINA}')
            break
        if n_novos < 0:
            print('\n  Extração interrompida (sessão).')
            break

        page_boloes = [b for b in boloes if b.get('pagina') == pagina]
        page_loterica = _boloes_do_filtro(page_boloes, cfg)
        h_pag = hashes_pagina(page_boloes)
        if n_novos and h_pag and h_pag == hashes_pagina_anterior:
            print('  [AVISO] Página igual à anterior — confira navegação.')
        hashes_pagina_anterior = h_pag

        _imprimir_painel_pagina(pagina, len(page_boloes), boloes, hashes, painel)
        if page_loterica and cfg.termo:
            print(f'  [FILTRO] Lotérica alvo nesta pág.: {len(page_loterica)} de {len(page_boloes)}')

        conc = painel.get('concurso_alvo') or _concurso_de_arquivo_base(arquivo_base)
        subset_arquivo = _boloes_para_json_arquivo(boloes, mod_esperada, conc)
        if not conc and subset_arquivo:
            conc = extrair_concurso_de_boloes(subset_arquivo)
            painel['concurso_alvo'] = conc
            subset_arquivo = _boloes_para_json_arquivo(boloes, mod_esperada, conc)

        if subset_arquivo:
            novo_base = _renomear_json_sessao(arquivo_base, subset_arquivo, mod_esperada)
            if novo_base != arquivo_base:
                arquivo_base = novo_base
                painel['arquivo_base'] = arquivo_base
                if not painel.get('concurso_alvo'):
                    painel['concurso_alvo'] = _concurso_de_arquivo_base(arquivo_base)

        path_json = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
        total_disco = len(carregar_json_boloes(path_json))
        if total_disco:
            kb = os.path.getsize(path_json) / 1024
            _out(f'  📁 Arquivo: {total_disco} reg. | {kb:.1f} KB | {os.path.basename(path_json)}')

        if subset_arquivo or os.path.isfile(path_json):
            _consolidar_e_resumir(
                carregar_json_boloes(path_json) or subset_arquivo, mod_esperada,
            )

        if voce_encerra:
            print(
                f'\n  Página {pagina} concluída ({len(page_boloes)} reg. no JSON | '
                f'{len(page_loterica)} da lotérica alvo). '
                f'Arquivo: {total_disco} reg.'
            )
            print(f'  Próxima página? Navegue no site e ENTER. Era a última? Digite FIM.')

        if not voce_encerra:
            meta_pag = ler_metadados_paginacao_api(driver) or painel.get('paginacao_api')
            if meta_pag:
                pa = int(meta_pag.get('pagina_atual') or pagina)
                up = int(meta_pag.get('ultima_pagina') or pagina)
                print(f'  [PÁGINA] API: página {pa} de {up} ({meta_pag.get("total_registros", "?")} bolões).')
            if ultima_pagina_detectada(driver):
                print(f'\n  {MSG_ULTIMA_PAGINA}')
                break

        pagina += 1

    tempo = int(time.time() - inicio)
    conc = painel.get('concurso_alvo') or _concurso_de_arquivo_base(arquivo_base)
    recuperados = _recuperar_boloes_das_capturas(
        cfg, parser_slug, mod_slug, arquivo_base, rodada_filtro,
        mod_esperada=mod_esperada, concurso_alvo=conc,
    )
    path_json = os.path.join(PASTA_JSON, f'{arquivo_base}.json')
    subset_final = carregar_json_boloes(path_json)
    if recuperados:
        boloes = recuperados
    elif not subset_final:
        subset_final = _boloes_para_json_arquivo(boloes, mod_esperada, conc)

    subset_loterica = _boloes_do_filtro(boloes, cfg)
    painel['registros_loterica_alvo'] = len(subset_loterica)

    _imprimir_resumo_final(subset_final, hashes, painel, arquivo_base, cfg, tempo)
    if subset_final:
        _out(f'\n  Arquivo final: {path_json}')
    elif painel.get('capturas_api', 0) > 0:
        _out('\n  [AVISO] Extração vazia apesar de capturas API — veja [DIAG] acima.')
    return subset_final, hashes, painel, arquivo_base


def _consolidar_e_resumir(boloes_sessao, mod_esperada):
    if not boloes_sessao:
        return None, []
    mod_json = extrair_modalidade_de_boloes(boloes_sessao) or mod_esperada
    concurso = extrair_concurso_de_boloes(boloes_sessao)
    mod_ref = mod_json or mod_esperada
    mod_slug = mod_ref.slug if mod_ref else 'boloes'
    _validar_modalidade_coerencia(mod_esperada, boloes_sessao)
    path, final, novos = consolidar_sessao(PASTA_JSON, concurso, mod_slug, boloes_sessao)
    print(f'\n  CONSOLIDADO: {path}')
    print(f'  Sessão: {len(boloes_sessao)} | +{novos} novos | total único: {len(final)}')
    return path, final


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO AUTOMÁTICA — fluxo [1] com pergunta pré-Edge
# ─────────────────────────────────────────────────────────────────────────────

def extrair_automatico() -> Tuple[list, Optional[str]]:
    """
    [1] Fluxo completo:
        Terminal → pede MODALIDADE + CONCURSO
        Edge abre → usuário faz login + configura filtros → ENTER
        Script extrai todas as páginas automaticamente
        JSON gravado em tempo real
    """
    global SESSAO_AUTORIZADA, ROTULO_ARQUIVO, ROTULO_NOME

    # ── PASSO 1 e 2: coletar ANTES de abrir o Edge ──────────────────────────
    mod_pre = _coletar_modalidade_pre_extracao()
    if mod_pre:
        ROTULO_ARQUIVO = mod_pre
        ROTULO_NOME = mod_pre.label

    concurso_pre = _coletar_concurso_pre_extracao()

    # Mostra o resumo e instrui o usuário
    cfg_atual = FILTRO_LOTERICA or _cfg_filtro_site()
    _exibir_resumo_pre_extracao(mod_pre or ROTULO_ARQUIVO, concurso_pre, cfg_atual)

    # ── Abre o Edge ─────────────────────────────────────────────────────────
    if driver is None:
        if not iniciar_navegador():
            return [], None
    elif not _no_site_boloes():
        try:
            driver.get(URL_BOLOES)
            time.sleep(2)
        except Exception:
            pass

    SESSAO_AUTORIZADA = False
    if not aguardar_site_pronto():
        return [], None

    SESSAO_AUTORIZADA = True

    # ── Lê filtros do site ───────────────────────────────────────────────────
    _out('\n  Lendo filtros do site...')
    cfg = ler_filtro_aplicado_site(driver, _out) or cfg_atual

    # Modalidade: preferência ao que o usuário digitou no terminal
    mod = ROTULO_ARQUIVO or _modalidade_extracao(driver)
    mod_slug = mod.slug if mod else 'boloes'
    parser_slug = mod.parser_slug if mod else ''

    # Concurso: preferência ao digitado; fallback = detectar da API
    concurso_final = concurso_pre  # já foi digitado antes

    arquivo_base = gerar_arquivo_base(cfg, mod, concurso_final)

    print('\n' + '=' * 60)
    print('  EXTRAÇÃO AUTOMÁTICA — INICIANDO')
    print('=' * 60)
    print(f'  Modalidade : {mod.label if mod else "auto-detectar"}')
    print(f'  Concurso   : {concurso_final if concurso_final else "auto-detectar"}')
    print(f'  Arquivo    : {arquivo_base}.json (gravado em tempo real)')
    print(LEGENDA_API)

    boloes, _, _, ab = _loop_extracao_paginas(
        cfg, parser_slug, mod_slug, arquivo_base,
        manual_paginas=False, mod_esperada=mod,
        concurso_alvo=concurso_final,
    )
    if boloes:
        mod_final = extrair_modalidade_de_boloes(boloes) or mod
        ab = _renomear_json_sessao(ab, boloes, mod_final)
        _validar_modalidade_coerencia(mod_final, boloes)
    return boloes, ab


# ─────────────────────────────────────────────────────────────────────────────
# EXTRAÇÃO MANUAL — fluxo [2]
# ─────────────────────────────────────────────────────────────────────────────

def _resolver_cfg_filtro_rodada():
    _out('\n  Lendo filtro aplicado no site...')
    cfg = ler_filtro_aplicado_site(driver, _out)
    if cfg and (cfg.termo or cfg.codigo or cfg.qualquer_loterica):
        return cfg

    _out('\n' + '-' * 60)
    _out('  Filtro no site não lido automaticamente.')
    if FILTRO_LOTERICA and FILTRO_LOTERICA.qualquer_loterica:
        _out(f'  [ENTER] = qualquer lotérica + {FILTRO_LOTERICA.qtd_dezenas or 15} dezenas')
    elif FILTRO_LOTERICA and FILTRO_LOTERICA.termo:
        _out(f'  [ENTER] = usar config salva ({FILTRO_LOTERICA.termo})')
    _out('  * = qualquer + 15 dez | ou código/nome | X = menu')
    _out('-' * 60)
    try:
        resp = input('>>> ').strip()
    except EOFError:
        return None
    if not resp:
        if FILTRO_LOTERICA:
            return FILTRO_LOTERICA
        return cfg_qualquer_loterica(15)
    if resp.upper() == 'X':
        return None
    if resp in ('*', '-', 'todas', 'qualquer', 'QUALQUER', 'TODAS'):
        qtd = FILTRO_LOTERICA.qtd_dezenas if FILTRO_LOTERICA and FILTRO_LOTERICA.qtd_dezenas else 15
        return cfg_qualquer_loterica(qtd)
    codigo, nome = parse_termo_loterica(resp)
    qtd = FILTRO_LOTERICA.qtd_dezenas if FILTRO_LOTERICA else None
    return FiltroLotericaConfig(termo=resp, codigo=codigo, nome=nome, qtd_dezenas=qtd)


def extrair_sessao_multi_filtros() -> None:
    global SESSAO_AUTORIZADA

    print('\n' + '=' * 60)
    print('  MODO FILTRO MANUAL — MESMA SESSÃO LOGADA')
    print('=' * 60)
    print('\n  Login 1x → filtro no site → ENTER → baixa pág. 1')
    print('  Mesmo filtro: pág. 2, 3… → ENTER a cada página → FIM')
    print('  Novo filtro: aplique no site → ENTER → repete')
    print(LEGENDA_API)

    if driver is None:
        if not preparar_login_unico():
            return
    elif not _usuario_logado_caixa():
        if _no_site_boloes():
            print('\n  [AVISO] Login não confirmado, mas site de bolões aberto — continuando.')
        else:
            print('\n  Sessão expirada — faça login de novo.')
            if not preparar_login_unico():
                return

    mod_slug = ROTULO_ARQUIVO.slug if ROTULO_ARQUIVO else 'quina'
    parser_slug = ROTULO_ARQUIVO.parser_slug if ROTULO_ARQUIVO else 'quina'

    rodada = 1
    resumos_rodadas: list = []

    while True:
        if not aguardar_filtro_manual_pagina1(rodada=rodada):
            break

        cfg = _resolver_cfg_filtro_rodada()
        if not cfg or not (cfg.termo or cfg.codigo or cfg.qualquer_loterica):
            _out('\n  Rodada cancelada — voltando ao menu.')
            break

        mod = _modalidade_extracao(driver)
        mod_slug = mod.slug if mod else mod_slug
        parser_slug = mod.parser_slug if mod else parser_slug

        SESSAO_AUTORIZADA = True
        limpar_capturas_api(driver)
        arquivo_base = gerar_arquivo_base(cfg, mod)

        print(f'\n  Iniciando rodada {rodada}...')
        boloes, hashes, painel, arquivo_base = _loop_extracao_paginas(
            cfg, parser_slug, mod_slug, arquivo_base,
            manual_paginas=True, rodada_filtro=rodada,
            voce_encerra=True, mod_esperada=mod,
        )

        resumos_rodadas.append({
            'rodada': rodada,
            'loterica': cfg.termo,
            'dezenas': cfg.qtd_dezenas or 'qualquer',
            'registros': len(boloes),
            'arquivo': f'{arquivo_base}.json',
        })

        print('\n' + '-' * 60)
        print(f'  RODADA {rodada} CONCLUÍDA — {len(boloes)} reg. | filtro {cfg.termo}')
        print('-' * 60)

        try:
            resp = input('\n>>> Aplicar OUTRO filtro no site? [S/n] ').strip().lower()
        except EOFError:
            break
        if resp == 'n':
            break
        rodada += 1

    if resumos_rodadas:
        print('\n' + '=' * 60)
        print('  RESUMO — TODOS OS FILTROS DESTA SESSÃO')
        print('=' * 60)
        total = 0
        for r in resumos_rodadas:
            print(f"  Rodada {r['rodada']}: {r['registros']:>4} reg. | {r['loterica']} | {r['arquivo']}")
            total += r['registros']
        print(f'\n  Total: {total} reg. em {len(resumos_rodadas)} filtro(s).')
        print('=' * 60)


# ─────────────────────────────────────────────────────────────────────────────
# Configurações iniciais / menu
# ─────────────────────────────────────────────────────────────────────────────

def _carregar_config_inicio() -> bool:
    global FILTRO_LOTERICA, ROTULO_ARQUIVO, ROTULO_NOME
    cached = _carregar_config_cache()
    if not cached:
        return False
    FILTRO_LOTERICA, _mod_cache = cached
    ROTULO_ARQUIVO = None
    ROTULO_NOME = 'modalidade atual'
    return bool(FILTRO_LOTERICA)


def configurar_loterica() -> bool:
    global FILTRO_LOTERICA, ROTULO_ARQUIVO, ROTULO_NOME
    try:
        FILTRO_LOTERICA, ROTULO_ARQUIVO = ler_config_extracao()
        ROTULO_NOME = _rotulo_nome()
        if not FILTRO_LOTERICA or not (FILTRO_LOTERICA.termo or '').strip():
            print('\n>>> Lotérica inválida ou vazia.')
            FILTRO_LOTERICA = None
            return False
        print(f'\n>>> Config OK | Lotérica: {FILTRO_LOTERICA.termo} | Modalidade: {ROTULO_NOME}')
        return True
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        print(f'\n>>> ERRO: {exc}')
        traceback.print_exc()
        return False


def _menu_consolidar_capturas() -> None:
    from boloes_consolidar import consolidar_capturas_pasta

    mod_slug = ROTULO_ARQUIVO.slug if ROTULO_ARQUIVO else 'quina'
    path, total = consolidar_capturas_pasta(
        PASTA_CAPTURAS, PASTA_JSON, 'sem-concurso', mod_slug,
        FILTRO_LOTERICA.codigo if FILTRO_LOTERICA else None,
        FILTRO_LOTERICA.qtd_dezenas if FILTRO_LOTERICA else None,
    )
    print(f'\n>>> Consolidado a partir de capturas-api/: {path}')
    print(f'>>> Total único: {total}')


def menu_principal() -> None:
    global FILTRO_LOTERICA, ROTULO_ARQUIVO, ROTULO_NOME

    while True:
        try:
            print('\n' + '=' * 60)
            print('  EXTRATOR DE BOLÕES — Caixa (API)')
            print('=' * 60)
            _imprimir_status_modalidade()
            _imprimir_tabela_modalidades_resumida()
            print(f'\n  JSON: {PASTA_JSON}')
            print('\n[1] EXTRAIR AUTOMÁTICO')
            print('    → Terminal: modalidade + concurso → Edge abre → login + filtros → ENTER')
            print('    → Seguinte automático até desabilitar → JSON cresce em tempo real')
            print('[2] EXTRAIR MANUAL (ENTER a cada página / vários filtros)')
            print('[3] Consolidar capturas-api/')
            print('[M] Tabela completa de modalidades')
            print('[0] Fechar navegador')
            print('-' * 60)
            print('  Opcional: M1-M9 | QSJ | DSP — só para forçar parser')
            print('-' * 60)

            opcao = input('Opção: ').strip().upper()

            if not opcao:
                continue
            if opcao.startswith('M') and len(opcao) == 2 and opcao[1].isdigit():
                if _trocar_modalidade_por_entrada(opcao[1]):
                    continue
            if opcao == 'M':
                imprimir_menu_modalidades()
                continue
            if opcao in TECLAS_ESPECIAIS:
                _trocar_modalidade_por_entrada(opcao)
                continue
            if opcao in ('4', '5', '6', '7', '8', '9'):
                if _trocar_modalidade_por_entrada(opcao):
                    continue
            if opcao not in ('0', '1', '2', '3', 'M'):
                mod_direto = resolver_modalidade_menu(opcao)
                if mod_direto:
                    _aplicar_modalidade(mod_direto)
                    continue
            if opcao == '1':
                extrair_automatico()
            elif opcao == '2':
                extrair_sessao_multi_filtros()
            elif opcao == '3':
                _menu_consolidar_capturas()
            elif opcao == '0':
                fechar_navegador()
                print('\n>>> Navegador fechado. CTRL+C para sair.')
            else:
                print('\n>>> Opção inválida.')

        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f'\n>>> ERRO: {exc}')
            traceback.print_exc()


def main() -> None:
    global FILTRO_LOTERICA, ROTULO_ARQUIVO, ROTULO_NOME
    _carregar_config_inicio()
    menu_principal()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\n\nEncerrado pelo usuário (CTRL+C).')
    finally:
        fechar_navegador()
        print('Fim!')
