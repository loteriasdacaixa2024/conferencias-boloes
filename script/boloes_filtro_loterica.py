# -*- coding: utf-8 -*-
"""Filtros de lotérica e modalidade na extração de bolões — Caixa (Selenium)."""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Tuple

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select, WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


@dataclass
class FiltroLotericaConfig:
    termo: str
    codigo: Optional[str] = None
    nome: Optional[str] = None
    qtd_dezenas: Optional[int] = None
    varrer_dezenas: bool = False
    qualquer_loterica: bool = False


from boloes_modalidades import (  # noqa: E402
    CONCURSOS_ESPECIAIS,
    MODALIDADES_MENU,
    ModalidadeMenu as ModalidadeBolaoConfig,
    TODAS_MODALIDADES,
    hint_filtro_dezenas,
    imprimir_menu_modalidades,
    ler_modalidade_terminal,
    resolver_modalidade_menu,
)

CATALOGO_MODALIDADES = TODAS_MODALIDADES

LogFn = Optional[Callable[[str], None]]

_CONFIG_CACHE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'ultima_config_boloes.json',
)


def _salvar_config_cache(loterica: FiltroLotericaConfig, modalidade: Optional[ModalidadeBolaoConfig]) -> None:
    try:
        payload = {
            'termo': loterica.termo,
            'codigo': loterica.codigo,
            'nome': loterica.nome,
            'qtd_dezenas': loterica.qtd_dezenas,
            'varrer_dezenas': loterica.varrer_dezenas,
            'qualquer_loterica': loterica.qualquer_loterica,
            'modalidade_numero': modalidade.numero if modalidade else None,
            'rotulo_slug': modalidade.slug if modalidade else None,
            'rotulo_label': modalidade.label if modalidade else None,
            'parser_slug': modalidade.parser_slug if modalidade else None,
            'extracao': modalidade.extracao if modalidade else None,
            'base_label': modalidade.base_label if modalidade else None,
            'epoca': modalidade.epoca if modalidade else None,
            'tecla': modalidade.tecla if modalidade else None,
        }
        with open(_CONFIG_CACHE, 'w', encoding='utf-8') as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def _carregar_config_cache() -> Optional[Tuple[FiltroLotericaConfig, Optional[ModalidadeBolaoConfig]]]:
    if not os.path.isfile(_CONFIG_CACHE):
        return None
    try:
        with open(_CONFIG_CACHE, encoding='utf-8') as f:
            data = json.load(f)
        loterica = FiltroLotericaConfig(
            termo=data['termo'],
            codigo=data.get('codigo'),
            nome=data.get('nome'),
            qtd_dezenas=data.get('qtd_dezenas'),
            varrer_dezenas=bool(data.get('varrer_dezenas')),
            qualquer_loterica=bool(data.get('qualquer_loterica')),
        )
        modalidade = None
        if data.get('rotulo_slug'):
            modalidade = resolver_modalidade_menu(
                data.get('tecla') or str(data.get('modalidade_numero') or data['rotulo_slug']),
            )
            if modalidade is None:
                modalidade = ModalidadeBolaoConfig(
                    numero=int(data.get('modalidade_numero') or 0),
                    slug=data['rotulo_slug'],
                    parser_slug=data.get('parser_slug') or data['rotulo_slug'],
                    label=data.get('rotulo_label') or data['rotulo_slug'],
                    extracao=data.get('extracao') or '',
                    base_label=data.get('base_label') or '',
                    epoca=data.get('epoca') or '',
                    tecla=data.get('tecla') or '',
                    especial=bool(int(data.get('modalidade_numero') or 0) > 100),
                )
        return loterica, modalidade
    except Exception:
        return None


def _log(msg: str, log_fn: LogFn = None) -> None:
    if log_fn:
        log_fn(msg)
    else:
        print(msg)


def normalizar_texto(texto: str) -> str:
    if not texto:
        return ''
    texto = unicodedata.normalize('NFD', texto)
    texto = ''.join(c for c in texto if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', texto.lower().strip())


def parse_termo_loterica(termo: str) -> Tuple[Optional[str], Optional[str]]:
    termo = (termo or '').strip()
    if not termo:
        return None, None
    if termo.isdigit():
        return termo, None
    match = re.match(r'^(\d{3,6})\s*[-–]?\s*(.*)$', termo)
    if match:
        nome = match.group(2).strip() or None
        return match.group(1), nome
    return None, termo


def resolver_modalidade(termo: str) -> Optional[ModalidadeBolaoConfig]:
    return resolver_modalidade_menu(termo)


def modalidade_por_slug(slug: str) -> Optional[ModalidadeBolaoConfig]:
    slug = (slug or '').strip().lower()
    for mod in CATALOGO_MODALIDADES:
        if mod.slug == slug:
            return mod
    return None


def parse_modalidades_input(raw: str) -> List[ModalidadeBolaoConfig]:
    """Ex: '1' | '1,*' | 'Quina de São João,*' | '1,6,7'"""
    raw = (raw or '').strip()
    if not raw:
        return []

    varrer_resto = False
    if raw.endswith(',*') or raw.endswith('+') or raw.lower().endswith(',varrer'):
        varrer_resto = True
        raw = re.sub(r',(\*|varrer|\+)$', '', raw, flags=re.I).strip()

    if raw in ('*', 'todas', 'TODAS'):
        varrer_resto = True
        raw = ''

    resultado: List[ModalidadeBolaoConfig] = []
    vistos = set()

    def _add(mod: Optional[ModalidadeBolaoConfig]):
        if mod and mod.slug not in vistos:
            resultado.append(mod)
            vistos.add(mod.slug)

    if raw:
        for parte in raw.split(','):
            parte = parte.strip()
            if not parte or parte == '*':
                continue
            _add(resolver_modalidade(parte))

    if varrer_resto:
        for mod in CATALOGO_MODALIDADES:
            _add(mod)

    return resultado


def cfg_qualquer_loterica(qtd_dezenas: Optional[int] = 15) -> FiltroLotericaConfig:
    """Todas as lotéricas da lista/página — filtra só pela qtd. de dezenas por aposta."""
    return FiltroLotericaConfig(
        termo='',
        codigo=None,
        nome=None,
        qtd_dezenas=qtd_dezenas,
        varrer_dezenas=False,
        qualquer_loterica=True,
    )


def cfg_varredura_automatica(
    modalidade: Optional[ModalidadeBolaoConfig],
    qtd_override: Optional[int] = None,
) -> FiltroLotericaConfig:
    """Modo [1] automático: qualquer lotérica + dezenas conforme a modalidade."""
    from boloes_modalidades import dezena_filtro_varredura

    qtd = dezena_filtro_varredura(modalidade, qtd_override)
    return cfg_qualquer_loterica(qtd)


def bolao_apostas_todas_com_n_dezenas(dados: dict, n: int) -> bool:
    """True se cada aposta do bolão tem exatamente n dezenas (ex.: 2×15, 1×15)."""
    apostas = dados.get('apostas') or []
    if apostas:
        for ap in apostas:
            if not isinstance(ap, dict):
                continue
            dz = ap.get('dezenas') or []
            if len(dz) != int(n):
                return False
        return True
    dz = dados.get('dezenas_aposta') or []
    if dz:
        return len(dz) == int(n)
    q1 = dados.get('qtd_dezenas_aposta_1')
    return q1 is not None and int(q1) == int(n)


def _ler_filtro_loterica_terminal(modalidade: ModalidadeBolaoConfig) -> FiltroLotericaConfig:
    print('\n' + '=' * 60)
    print('  FILTRO DE LOTERICA')
    print('=' * 60)
    print('  * ou ENTER vazio = QUALQUER lotérica (só filtra dezenas)')
    print('  (codigo ex: 9833 — NAO digite 0 do menu aqui)')
    termo = input('\nLotérica (* = qualquer): ').strip()
    while termo == '0':
        print('>>> "0" e opcao do MENU (fechar Edge). Informe a loterica ou *')
        termo = input('Lotérica (* = qualquer): ').strip()

    hint = hint_filtro_dezenas(modalidade)
    dezenas_raw = input(f'Quant. de dezenas [{hint}]: ').strip()
    qtd_dezenas = None
    if dezenas_raw:
        try:
            qtd_dezenas = int(dezenas_raw)
        except ValueError:
            qtd_dezenas = None

    if termo in ('*', '-', 'todas', 'qualquer', 'QUALQUER', 'TODAS'):
        varrer_raw = input('Varrer faixa de dezenas? [n] (recomendado: n para fixar 15): ').strip().lower()
        varrer_dezenas = varrer_raw == 's'
        if qtd_dezenas is None:
            qtd_dezenas = 15
        return cfg_qualquer_loterica(qtd_dezenas)

    varrer_raw = input('Varrer faixa de dezenas desta modalidade? [S/n]: ').strip().lower()
    varrer_dezenas = varrer_raw != 'n'

    codigo, nome = parse_termo_loterica(termo)
    return FiltroLotericaConfig(
        termo=termo, codigo=codigo, nome=nome,
        qtd_dezenas=qtd_dezenas, varrer_dezenas=varrer_dezenas,
    )


def _imprimir_menu_modalidades() -> None:
    imprimir_menu_modalidades()


def ler_modalidades_terminal() -> List[ModalidadeBolaoConfig]:
    mod = ler_modalidade_terminal()
    return [mod]


def ler_config_extracao() -> Tuple[FiltroLotericaConfig, Optional[ModalidadeBolaoConfig]]:
    """Lotérica + modalidade (menu 1–9 / teclas DSP QSJ LTI MSV MS3). Mesma modalidade no site."""
    cached = _carregar_config_cache()
    if cached:
        loterica, modalidade = cached
        dez = loterica.qtd_dezenas or 'qualquer'
        varrer = 'sim' if loterica.varrer_dezenas else 'nao'
        mod_nome = modalidade.label if modalidade else '(nao definida)'
        print('\n' + '=' * 60)
        print('  CONFIG ANTERIOR ENCONTRADA')
        print('=' * 60)
        print(f'\n  Modalidade: {mod_nome}')
        if loterica.qualquer_loterica:
            print(f'  Lotérica: QUALQUER | dezenas: {dez} | varrer: {varrer}')
        else:
            print(f'  Lotérica: {loterica.termo} | dezenas: {dez} | varrer: {varrer}')
        print('\n  (n = reconfigurar — menu 1-9 + DSP QSJ LTI MSV MS3)')
        reuse = input('\nUsar esta config? [S/n]: ').strip().lower()
        if reuse != 'n':
            if modalidade:
                print(f'>>> Modalidade: {modalidade.label} ({modalidade.extracao})')
                if modalidade.especial:
                    print(f'>>> Tecla: {modalidade.tecla} | Base: {modalidade.base_label} | Epoca: {modalidade.epoca}')
            return loterica, modalidade

    modalidade = ler_modalidade_terminal()
    loterica = _ler_filtro_loterica_terminal(modalidade)
    dez = loterica.qtd_dezenas or 'qualquer'
    varrer = 'sim' if loterica.varrer_dezenas else 'nao'
    print(f'\n>>> Modalidade: {modalidade.label} | Lotérica: ', end='')
    if loterica.qualquer_loterica:
        print(f'QUALQUER (todas na página)')
    else:
        print(loterica.termo)
    print(f'>>> Dezenas: {dez} | varrer: {varrer}')
    lot_slug = 'todas_lotericas' if loterica.qualquer_loterica else slug_loterica(loterica)
    print(f'>>> Arquivo: boloes_{lot_slug}_{modalidade.slug}_...')
    _salvar_config_cache(loterica, modalidade)
    return loterica, modalidade


def ler_config_terminal() -> FiltroLotericaConfig:
    """Compatibilidade — lotérica + modalidade padrão Quina."""
    mod = resolver_modalidade_menu('2') or MODALIDADES_MENU[1]
    return _ler_filtro_loterica_terminal(mod)


def config_from_api(loterica: str, qtd_dezenas=None, varrer_dezenas: bool = False) -> Optional[FiltroLotericaConfig]:
    termo = (loterica or '').strip()
    if not termo:
        return None
    qtd = None
    if qtd_dezenas is not None and str(qtd_dezenas).strip() != '':
        try:
            qtd = int(qtd_dezenas)
        except (TypeError, ValueError):
            qtd = None
    codigo, nome = parse_termo_loterica(termo)
    return FiltroLotericaConfig(
        termo=termo, codigo=codigo, nome=nome,
        qtd_dezenas=qtd, varrer_dezenas=bool(varrer_dezenas),
    )


def resolver_slug_parser(modalidade_slug: str) -> str:
    """Slug do catálogo → chave do parser (9 modalidades)."""
    s = (modalidade_slug or 'quina').lower()
    if 'quina' in s:
        return 'quina'
    if 'lotofacil' in s or 'independencia' in s or 'independência' in s:
        return 'lotofacil'
    if 'mega' in s:
        return 'mega-sena'
    if 'lotomania' in s:
        return 'lotomania'
    if 'timemania' in s:
        return 'timemania'
    if 'dia-de-sorte' in s or 'dia de sorte' in s:
        return 'dia-de-sorte'
    if 'super-sete' in s or 'super sete' in s:
        return 'super-sete'
    if 'dupla' in s:
        return 'dupla-sena'
    if 'milion' in s:
        return 'mais-milionaria'
    return s if s in ('mega-sena', 'quina', 'lotofacil', 'lotomania', 'timemania',
                      'dia-de-sorte', 'super-sete', 'dupla-sena', 'mais-milionaria') else 'quina'


def fila_qtd_dezenas(cfg: FiltroLotericaConfig, modalidade_slug: str = 'quina') -> List[Optional[int]]:
    """
    Fila de filtros de dezenas. Com varrer_dezenas=True: 15→14→…→min da modalidade (Quina: até 5).
    """
    if not cfg or not cfg.varrer_dezenas:
        return [cfg.qtd_dezenas if cfg else None]

    from boloes_extrair_popup import MODALIDADES

    key = resolver_slug_parser(modalidade_slug)
    mod = MODALIDADES.get(key, MODALIDADES['quina'])
    inicio = cfg.qtd_dezenas if cfg.qtd_dezenas is not None else mod.max_dez
    inicio = min(max(inicio, mod.min_dez), mod.max_dez)
    return list(range(inicio, mod.min_dez - 1, -1))


def cfg_com_qtd(cfg: FiltroLotericaConfig, qtd: Optional[int]) -> FiltroLotericaConfig:
    return FiltroLotericaConfig(
        termo=cfg.termo, codigo=cfg.codigo, nome=cfg.nome,
        qtd_dezenas=qtd, varrer_dezenas=cfg.varrer_dezenas,
        qualquer_loterica=cfg.qualquer_loterica,
    )


def modalidades_from_api(modalidade_slug: str, varrer_resto: bool = False,
                         modalidades_extra: Optional[List[str]] = None) -> List[ModalidadeBolaoConfig]:
    resultado: List[ModalidadeBolaoConfig] = []
    vistos = set()

    def _add(mod: Optional[ModalidadeBolaoConfig]):
        if mod and mod.slug not in vistos:
            resultado.append(mod)
            vistos.add(mod.slug)

    if modalidades_extra:
        for slug in modalidades_extra:
            _add(modalidade_por_slug(slug))

    _add(modalidade_por_slug(modalidade_slug) or resolver_modalidade(modalidade_slug))

    if varrer_resto:
        for mod in CATALOGO_MODALIDADES:
            _add(mod)

    return resultado


def slug_loterica(cfg: FiltroLotericaConfig) -> str:
    if cfg.qualquer_loterica or (not (cfg.termo or '').strip() and not cfg.codigo):
        return 'todas_lotericas'
    if cfg.codigo:
        return cfg.codigo
    slug = normalizar_texto(cfg.nome or cfg.termo)
    slug = re.sub(r'[^a-z0-9]+', '_', slug).strip('_')
    return (slug[:40] or 'loterica')


def gerar_arquivo_base(
    cfg: FiltroLotericaConfig,
    modalidade: Optional[ModalidadeBolaoConfig] = None,
    concurso: str = '',
) -> str:
    """boloes_{concurso}_{modalidade} — ex.: boloes_364_mais-milionaria"""
    from boloes_modalidades import nome_arquivo_sessao
    return nome_arquivo_sessao(concurso or 'sem-concurso', modalidade)


def gerar_arquivo_base_estado(
    cfg: FiltroLotericaConfig,
    modalidade: Optional[ModalidadeBolaoConfig],
    estado,
) -> str:
    """Nome de arquivo incluindo UF — ex.: boloes_sp_todas_lotericas_d15_quina-sao-joao_..."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    lot = slug_loterica(cfg)
    mod = modalidade.slug if modalidade else 'boloes'
    dez = f'_d{cfg.qtd_dezenas}' if cfg.qtd_dezenas else ''
    uf = getattr(estado, 'sigla', '') or ''
    uf_part = f'{uf.lower()}_' if uf else ''
    return f'boloes_{uf_part}{lot}{dez}_{mod}_{ts}'


def bolao_corresponde_loterica(dados: dict, cfg: FiltroLotericaConfig) -> bool:
    if not cfg or not cfg.termo:
        return True

    nome = dados.get('nome_loterica') or ''
    cod_api = str(dados.get('codigo_loterica') or '').strip()
    texto = dados.get('texto_completo') or ''
    haystack = normalizar_texto(f'{nome} {texto} {cod_api}')
    raw = f'{nome} {texto} {cod_api}'
    digits = re.sub(r'\D', '', raw)

    if cfg.codigo:
        codigo = cfg.codigo.strip()
        if cod_api and (cod_api == codigo or codigo in cod_api):
            return True
        # Caixa: "LOTERIA ALDEOTA - 05.009833-0" → 9833 está em 009833
        if codigo in digits:
            return True
        if re.search(r'(?:^|\D)' + re.escape(codigo) + r'(?:\D|$)', raw):
            return True
        if re.search(r'[\d\.]+' + re.escape(codigo) + r'(?:\D|$)', raw):
            return True
        if cfg.nome and normalizar_texto(cfg.nome) in haystack:
            return True
        return False

    alvo = normalizar_texto(cfg.nome or cfg.termo)
    if alvo in haystack:
        return True
    palavras = [p for p in alvo.split() if len(p) >= 3] or [alvo]
    return sum(1 for p in palavras if p in haystack) >= min(2, len(palavras))


def bolao_atende_filtro(dados: dict, cfg: FiltroLotericaConfig) -> bool:
    """Lotérica (se houver) + exatamente N dezenas em cada aposta."""
    if cfg.qualquer_loterica or (not (cfg.termo or '').strip() and not cfg.codigo):
        if cfg.qtd_dezenas is None:
            return True
        return bolao_apostas_todas_com_n_dezenas(dados, cfg.qtd_dezenas)
    if not bolao_corresponde_loterica(dados, cfg):
        return False
    if cfg.qtd_dezenas is None:
        return True
    return bolao_apostas_todas_com_n_dezenas(dados, cfg.qtd_dezenas)


def _ler_qtd_dezenas_do_site(driver) -> Optional[int]:
    """Lê quantidade de dezenas selecionada no filtro do site."""
    try:
        raw = driver.execute_script("""
            function parseDez(t) {
                t = (t || '').trim();
                if (!t) return null;
                var m = t.match(/^(\\d+)\\s*dezena/i);
                if (m) return parseInt(m[1], 10);
                if (/^\\d+$/.test(t)) return parseInt(t, 10);
                var nums = t.match(/\\d+/g);
                if (nums && nums.length === 1) return parseInt(nums[0], 10);
                return null;
            }
            var sels = document.querySelectorAll('select');
            for (var i = 0; i < sels.length; i++) {
                var sel = sels[i];
                if (!sel.offsetParent) continue;
                var opt = sel.options[sel.selectedIndex];
                if (!opt) continue;
                var n = parseDez(opt.text) || parseDez(opt.value);
                if (n) return n;
            }
            if (typeof angular !== 'undefined') {
                var sc = angular.element(document.body).scope();
                for (var d = 0; d < 14 && sc; d++) {
                    var q = sc.qtdNumeros || sc.qtdDezenas || sc.quantidadeDezenas;
                    if (q != null && q !== '') return parseInt(q, 10);
                    if (sc.filtro && sc.filtro.qtdNumeros != null) return parseInt(sc.filtro.qtdNumeros, 10);
                    sc = sc.$parent;
                }
            }
            return null;
        """)
        if raw is not None and int(raw) > 0:
            return int(raw)
    except Exception:
        pass
    return None


_JS_LER_LOTERICA_PAGINA = """
function codigoDeTexto(t) {
  t = (t || '').trim();
  if (!t) return '';
  if (/^\\d{3,6}$/.test(t)) return t;
  var m = t.match(/(\\d{2})\\.(\\d{6})/);
  if (m) {
    var seis = m[2];
    return seis.length >= 4 ? seis.slice(-4) : seis;
  }
  m = t.match(/LOTERIA[^\\d]*(\\d{4,6})/i);
  if (m) return m[1].slice(-4);
  m = t.match(/\\b(\\d{4})\\b/);
  if (m) return m[1];
  return t;
}
function pushTermo(list, t) {
  t = (t || '').trim();
  if (!t || t.length < 3) return;
  if (list.indexOf(t) < 0) list.push(t);
}
var candidatos = [];
try {
  var inp = document.getElementById('nomeCodigoLoterica');
  if (inp && inp.value) pushTermo(candidatos, inp.value.trim());
} catch (e) {}
document.querySelectorAll('input[type="text"], input:not([type])').forEach(function (inp) {
  if (!inp.offsetParent) return;
  var ph = (inp.placeholder || '').toLowerCase();
  var ng = (inp.getAttribute('ng-model') || '').toLowerCase();
  if (ph.indexOf('loter') >= 0 || ng.indexOf('loter') >= 0) {
    if (inp.value) pushTermo(candidatos, inp.value.trim());
  }
});
document.querySelectorAll(
  '[class*="loteria"], [class*="Loteria"], .ui-state-active, .filtro-ativo, aside li, aside div, .sidebar *'
).forEach(function (el) {
  if (!el || !el.offsetParent) return;
  var t = (el.innerText || el.textContent || '').trim();
  if (t.length > 120 || t.length < 4) return;
  if (/loteria|loteric|\\d{2}\\.\\d{6}|\\b\\d{4}\\b/i.test(t)) {
    if (/loteria/i.test(t) || /\\d{2}\\.\\d{6}/.test(t)) pushTermo(candidatos, t);
  }
});
document.querySelectorAll('.card, [class*="bolao"], [class*="Bolao"]').forEach(function (card) {
  if (!card || !card.offsetParent) return;
  var t = (card.innerText || '').trim();
  if (/loteria/i.test(t)) {
    var linhas = t.split(/\\n/);
    for (var i = 0; i < linhas.length; i++) {
      if (/loteria/i.test(linhas[i])) { pushTermo(candidatos, linhas[i].trim()); break; }
    }
  }
});
if (typeof angular !== 'undefined') {
  try {
    var nodes = document.querySelectorAll('[ng-controller], [ng-repeat], .card, [class*="bolao"]');
    for (var ni = 0; ni < nodes.length; ni++) {
      var sc = angular.element(nodes[ni]).scope();
      for (var d = 0; d < 16 && sc; d++) {
        var vals = [
          sc.nomeCodigoLoterica, sc.nomeLoterica, sc.lotericaFiltro,
          sc.lotericaSelecionada, sc.codigoLoterica
        ];
        for (var vi = 0; vi < vals.length; vi++) {
          if (vals[vi] && String(vals[vi]).trim()) pushTermo(candidatos, String(vals[vi]).trim());
        }
        if (sc.filtro) {
          if (sc.filtro.nomeCodigoLoterica) pushTermo(candidatos, String(sc.filtro.nomeCodigoLoterica).trim());
          if (sc.filtro.loterica) pushTermo(candidatos, String(sc.filtro.loterica).trim());
        }
        if (sc.loterica && typeof sc.loterica === 'object') {
          var lf = sc.loterica.nomeFantasia || sc.loterica.nome || sc.loterica.codigo;
          if (lf) pushTermo(candidatos, String(lf).trim());
        }
        sc = sc.$parent;
      }
    }
  } catch (e) {}
}
return candidatos.length ? candidatos[0] : '';
"""


def _ler_loterica_texto_pagina(driver) -> str:
    try:
        raw = driver.execute_script(_JS_LER_LOTERICA_PAGINA)
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    except Exception:
        pass
    return ''


def _ler_loterica_da_lista_api(driver) -> str:
    """Apos Aplicar, o campo pode esvaziar — loterica vem da lista/API ou dos cards."""
    try:
        from boloes_api_caixa import ler_capturas_api, _eh_url_lista_boloes
    except ImportError:
        return ''

    lotericas: dict = {}

    def registrar(item: dict) -> None:
        if not isinstance(item, dict) or not item.get('codigoBolao'):
            return
        fmt = item.get('lotericaFormatada') or {}
        termo = ''
        if isinstance(fmt, dict):
            termo = (
                fmt.get('nomeFantasia') or fmt.get('nomeRazaoSocial')
                or fmt.get('codigo') or fmt.get('numeroFormatado') or ''
            ).strip()
        if not termo:
            lot = item.get('loterica') or item.get('codigoLoterica')
            if lot is not None:
                termo = str(lot)
        if termo:
            lotericas[termo] = lotericas.get(termo, 0) + 1

    def walk(node, depth: int = 0) -> None:
        if depth > 14:
            return
        if isinstance(node, dict):
            if node.get('codigoBolao'):
                registrar(node)
            for val in node.values():
                walk(val, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    for cap in reversed(ler_capturas_api(driver)):
        if not _eh_url_lista_boloes(cap.get('url') or ''):
            continue
        walk(cap.get('data'))
        if lotericas:
            break

    if not lotericas:
        return ''

    return max(lotericas.items(), key=lambda x: x[1])[0]


def ler_filtro_aplicado_site(driver, log_fn: LogFn = None) -> Optional[FiltroLotericaConfig]:
    """
    Lê o filtro que VOCE aplicou no site (campo lotérica + dezenas).
    O script usa isso para baixar SOMENTE bolões deste filtro.
    """
    _scroll_para_filtros(driver)
    termo = ''
    fonte = ''
    try:
        el = _find_input_loterica(driver)
        if el:
            termo = (el.get_attribute('value') or '').strip()
            if termo:
                fonte = 'campo lotérica'
    except Exception:
        pass
    if not termo:
        try:
            termo = (driver.execute_script("""
                var inp = document.getElementById('nomeCodigoLoterica');
                if (inp && inp.value) return inp.value.trim();
                if (typeof angular !== 'undefined') {
                    var sc = angular.element(document.body).scope();
                    for (var d = 0; d < 14 && sc; d++) {
                        var v = sc.nomeCodigoLoterica || sc.nomeLoterica || sc.lotericaFiltro;
                        if (v && String(v).trim()) return String(v).trim();
                        if (sc.filtro && sc.filtro.nomeCodigoLoterica)
                            return String(sc.filtro.nomeCodigoLoterica).trim();
                        sc = sc.$parent;
                    }
                }
                return '';
            """) or '').strip()
            if termo:
                fonte = 'angular/campo'
        except Exception:
            pass

    if not termo:
        termo = _ler_loterica_texto_pagina(driver)
        if termo:
            fonte = 'texto da pagina (sidebar/cards)'

    if not termo:
        termo = _ler_loterica_da_lista_api(driver)
        if termo:
            fonte = 'lista API (apos Aplicar)'

    if not termo:
        qtd_dezenas = _ler_qtd_dezenas_do_site(driver)
        if qtd_dezenas:
            cfg = cfg_qualquer_loterica(qtd_dezenas)
            _log(
                f'  [FILTRO DETECTADO] Qualquer lotérica | Dezenas: {qtd_dezenas} | via: site (sem lotérica)',
                log_fn,
            )
            _log('  → Baixando bolões de TODAS as lotéricas visíveis com essa qtd. de dezenas.', log_fn)
            return cfg
        _log('  [FILTRO] Nao detectei lotérica no site.', log_fn)
        _log('  → No site: só 15 dezenas + estado (ex. SP), sem lotérica — ou digite * no terminal.', log_fn)
        return None

    qtd_dezenas = _ler_qtd_dezenas_do_site(driver)
    codigo, nome = parse_termo_loterica(termo)
    cfg = FiltroLotericaConfig(
        termo=termo, codigo=codigo, nome=nome, qtd_dezenas=qtd_dezenas,
    )
    dez_txt = str(qtd_dezenas) if qtd_dezenas else 'qualquer'
    _log(f'  [FILTRO DETECTADO] Lotérica: {termo} | Dezenas: {dez_txt} | via: {fonte}', log_fn)
    _log('  → Baixando SOMENTE bolões deste filtro.', log_fn)
    return cfg


def sessao_caixa_ativa(driver) -> bool:
    try:
        url = (driver.current_url or '').lower()
        if any(x in url for x in ('login.caixa.gov.br', 'openid-connect', '/auth/realms/')):
            return False
        if 'loteriasonline.caixa.gov.br' not in url and 'silce-web' not in url:
            return False
        if 'bolao-caixa' in url or '#/bolao' in url:
            return True
        try:
            logado = driver.execute_script("""
                try {
                    var body = (document.body && document.body.innerText) || '';
                    if (/Olá|Ola|Minha conta|Sair/i.test(body)) return true;
                } catch (e) {}
                return false;
            """)
            if logado:
                return True
        except Exception:
            pass
        for sel in ('#kc-form-login', '.login-pf-page'):
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if el.is_displayed():
                    return False
        return True
    except Exception:
        return False


def manter_sessao_ativa(driver) -> None:
    try:
        driver.execute_script("""
            try {
                window.dispatchEvent(new Event('focus'));
                window.dispatchEvent(new Event('mousemove'));
            } catch (e) {}
        """)
    except Exception:
        pass


def garantir_sessao_caixa(
    driver,
    pagina_atual: int = 1,
    log_fn: LogFn = None,
    modo_web: bool = False,
    estado_check: Optional[dict] = None,
) -> bool:
    if sessao_caixa_ativa(driver):
        manter_sessao_ativa(driver)
        return True

    _log('', log_fn)
    _log('  *** SESSAO CAIXA EXPIROU (Keycloak / login) ***', log_fn)
    _log('  Verifique internet (login.caixa.gov.br deve abrir no navegador).', log_fn)
    _log(f'  1. Refaca login no Edge', log_fn)
    _log(f'  2. Volte a modalidade e lista de boloes', log_fn)
    _log(f'  3. Continuara da pagina {pagina_atual}', log_fn)

    if modo_web:
        _log('  Aguardando relogin (ate 3 min)...', log_fn)
        for _ in range(36):
            if estado_check and estado_check.get('status') != 'rodando':
                return False
            time.sleep(5)
            if sessao_caixa_ativa(driver):
                _log('  Sessao restaurada — continuando.', log_fn)
                return True
        _log('  Tempo esgotado aguardando relogin.', log_fn)
        return False

    _log('  Pressione ENTER apos relogin...', log_fn)
    try:
        input('\n>>> ENTER apos relogin e voltar aos boloes... ')
    except EOFError:
        pass
    time.sleep(1)
    ok = sessao_caixa_ativa(driver)
    if ok:
        _log('  Sessao OK — continuando.', log_fn)
    else:
        _log('  Ainda sem sessao ativa.', log_fn)
    return ok


def _dismiss_overlays(driver) -> None:
    try:
        driver.execute_script("""
            document.querySelectorAll(
                'div[style*="position:fixed"], div[style*="position: fixed"]'
            ).forEach(function(el) {
                if (el.closest('.modal, [role="dialog"], .modal-content')) return;
                var st = window.getComputedStyle(el);
                var z = parseInt(st.zIndex || '0', 10);
                var top = parseFloat(st.top || '999');
                if (z >= 100000 || (st.position === 'fixed' && top <= 20 && z >= 1000)) {
                    el.style.pointerEvents = 'none';
                    el.style.visibility = 'hidden';
                }
            });
            document.querySelectorAll('.modal-backdrop').forEach(function(el) {
                if (!document.querySelector('.modal.show, .modal.in, [role="dialog"][style*="display: block"]')) {
                    el.style.display = 'none';
                }
            });
        """)
    except Exception:
        pass

    for xp in (
        "//button[contains(.,'Aceitar') or contains(.,'Concordo') or contains(.,'Fechar')]",
        "//button[@aria-label='Close' or @aria-label='Fechar']",
        "//*[contains(@class,'close') and (self::button or self::a)]",
    ):
        try:
            for btn in driver.find_elements(By.XPATH, xp):
                if btn.is_displayed():
                    try:
                        driver.execute_script('arguments[0].click();', btn)
                    except Exception:
                        pass
                    time.sleep(0.2)
        except Exception:
            pass


def _scroll_para_filtros(driver) -> None:
    try:
        for sel in ('#nomeCodigoLoterica', 'input[placeholder*="lotérica"]', 'input[placeholder*="loterica"]'):
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if els:
                driver.execute_script(
                    'arguments[0].scrollIntoView({block: "center", inline: "nearest"});',
                    els[0],
                )
                time.sleep(0.4)
                return
        driver.execute_script('window.scrollTo(0, 280);')
        time.sleep(0.3)
    except Exception:
        pass


def _click_seguro(driver, el) -> bool:
    try:
        driver.execute_script(
            'arguments[0].scrollIntoView({block: "center", inline: "nearest"});',
            el,
        )
        time.sleep(0.2)
        _dismiss_overlays(driver)
        try:
            el.click()
            return True
        except Exception:
            driver.execute_script('arguments[0].click();', el)
            return True
    except Exception:
        try:
            driver.execute_script('arguments[0].click();', el)
            return True
        except Exception:
            return False


def _preencher_input_angular(driver, el, texto: str) -> None:
    driver.execute_script("""
        var el = arguments[0], val = arguments[1];
        el.focus();
        el.value = val;
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
        el.dispatchEvent(new Event('keyup', {bubbles: true}));
        if (typeof angular !== 'undefined') {
            try {
                angular.element(el).triggerHandler('input');
                angular.element(el).triggerHandler('keyup');
            } catch (e) {}
        }
    """, el, texto)


def _expandir_painel_filtros(driver) -> None:
    """Abre painéis colapsados (Filtrar / Lotéricas) antes de buscar o campo."""
    xpaths = (
        "//*[contains(translate(.,'ÉÊÃÕéêãõFILTRAR','EEAAeeaaFiltrar'),'Filtr')]",
        "//*[contains(.,'Lotéric') or contains(.,'Loteric')]",
        "//button[contains(@class,'filter') or contains(@class,'filtro')]",
        "//a[contains(@class,'filter') or contains(@class,'filtro')]",
    )
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if not el.is_displayed():
                    continue
                tag = (el.tag_name or '').lower()
                if tag in ('input', 'select', 'textarea'):
                    continue
                driver.execute_script('arguments[0].click();', el)
                time.sleep(0.35)
        except Exception:
            pass


def aguardar_lista_boloes(driver, log_fn: LogFn = None, timeout: float = 45.0) -> bool:
    """Espera tela de bolões (campo lotérica) após login — evita filtro cedo demais."""
    _log('  Aguardando lista de bolões carregar...', log_fn)
    fim = time.time() + timeout
    while time.time() < fim:
        if not sessao_caixa_ativa(driver):
            time.sleep(0.5)
            continue
        if _find_input_loterica(driver):
            time.sleep(1.2)
            _log('  Lista de bolões pronta.', log_fn)
            return True
        time.sleep(0.5)
    _log('  [AVISO] Campo de lotérica ainda não apareceu — tente ENTER de novo se falhar.', log_fn)
    return False


def _find_input_loterica(driver):
    seletores = [
        (By.ID, 'nomeCodigoLoterica'),
        (By.CSS_SELECTOR, 'input[placeholder*="lotérica"], input[placeholder*="loterica"]'),
        (By.CSS_SELECTOR, 'input[ng-model*="Loterica"], input[ng-model*="loterica"]'),
        (By.CSS_SELECTOR, 'input[name*="loterica"], input[id*="loterica"]'),
    ]
    for by, sel in seletores:
        try:
            for el in driver.find_elements(by, sel):
                if el.is_displayed() and el.is_enabled():
                    return el
        except Exception:
            pass

    xpaths = [
        "//input[contains(translate(@placeholder,'ÉÊÃÕéêãõ','EEAAeeaa'),'loter')]",
        "//label[contains(.,'Lotéric') or contains(.,'Loteric')]/following::input[1]",
        "//*[contains(text(),'Lotéricas')]/ancestor::div[1]//input",
    ]
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if el.is_displayed() and el.is_enabled():
                    return el
        except Exception:
            pass

    try:
        el = driver.execute_script("""
            var inputs = document.querySelectorAll('input[type="text"], input:not([type])');
            for (var i = 0; i < inputs.length; i++) {
                var inp = inputs[i];
                if (!inp.offsetParent) continue;
                var ph = (inp.placeholder || '').toLowerCase();
                var ng = (inp.getAttribute('ng-model') || '').toLowerCase();
                var id = (inp.id || '').toLowerCase();
                var nm = (inp.name || '').toLowerCase();
                if (ph.indexOf('loter') >= 0 || ng.indexOf('loter') >= 0
                    || id.indexOf('loter') >= 0 || nm.indexOf('loter') >= 0)
                    return inp;
            }
            return null;
        """)
        if el:
            return el
    except Exception:
        pass
    return None


def _texto_busca_autocomplete(cfg: FiltroLotericaConfig) -> str:
    if cfg.codigo:
        return cfg.codigo
    termo = (cfg.nome or cfg.termo or '').strip()
    if len(termo) <= 5:
        return termo
    return termo[:5]


def _coletar_itens_autocomplete(driver) -> List:
    itens = []
    seletores = [
        'ul.ui-autocomplete li.ui-menu-item',
        'ul.ui-autocomplete li',
        'ul.ui-menu li.ui-menu-item',
        '.ui-autocomplete .ui-menu-item',
        "[role='listbox'] [role='option']",
    ]
    for css in seletores:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR, css):
                if el.is_displayed() and (el.text or '').strip():
                    if el not in itens:
                        itens.append(el)
        except Exception:
            pass
    return itens


def _melhor_item_autocomplete(itens: List, cfg: FiltroLotericaConfig):
    if not itens:
        return None

    melhor = None
    melhor_score = -1

    for item in itens:
        txt = (item.text or '').strip()
        norm = normalizar_texto(txt)
        score = 0

        if cfg.codigo:
            cod = cfg.codigo
            if txt.startswith(f'{cod} -') or txt.startswith(f'{cod}-'):
                score = 200
            elif re.search(r'\b' + re.escape(cod) + r'\b', txt):
                score = 120
            elif cod in txt:
                score = 80
        else:
            alvo = normalizar_texto(cfg.nome or cfg.termo)
            palavras = [p for p in alvo.split() if len(p) >= 3] or [alvo]
            score = sum(30 for p in palavras if p in norm)

        if score > melhor_score:
            melhor = item
            melhor_score = score

    if melhor_score > 0:
        return melhor
    return itens[0]


def _aguardar_autocomplete(driver, timeout: int = 8) -> List:
    fim = time.time() + timeout
    while time.time() < fim:
        itens = _coletar_itens_autocomplete(driver)
        if itens:
            return itens
        time.sleep(0.3)
    return []


def _limpar_campo_loterica(campo) -> None:
    try:
        campo.click()
        time.sleep(0.15)
        campo.send_keys(Keys.CONTROL, 'a')
        campo.send_keys(Keys.DELETE)
        time.sleep(0.15)
    except Exception:
        pass


def _digitar_busca_loterica(campo, texto: str) -> None:
    _limpar_campo_loterica(campo)
    campo.send_keys(texto)
    time.sleep(0.2)
    campo.send_keys(' ')
    campo.send_keys(Keys.BACKSPACE)
    time.sleep(0.1)


def _selecionar_autocomplete(driver, cfg: FiltroLotericaConfig, log_fn: LogFn = None) -> bool:
    itens = _aguardar_autocomplete(driver, timeout=8)
    if not itens:
        _log('  [FILTRO] Lista autocomplete não apareceu.', log_fn)
        return False

    alvo = _melhor_item_autocomplete(itens, cfg)
    if not alvo:
        return False

    txt = (alvo.text or '').strip()[:60]
    _click_seguro(driver, alvo)
    time.sleep(0.8)
    _log(f'  [FILTRO] Selecionado: {txt}', log_fn)
    return True


def _aguardar_lista_apos_aplicar(driver, timeout: int = 10) -> None:
    fim = time.time() + timeout
    while time.time() < fim:
        try:
            botoes = driver.find_elements(
                By.CSS_SELECTOR,
                "button.btn-primary, button.btn-success, .card button, [class*='bolao'] button",
            )
            if any(b.is_displayed() for b in botoes):
                return
        except Exception:
            pass
        time.sleep(0.4)
    time.sleep(1.5)


def _scroll_para_paginacao(driver) -> None:
    try:
        driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
        time.sleep(0.5)
    except Exception:
        pass


def _botao_pagina_clicavel(btn) -> bool:
    if btn is None:
        return False
    try:
        if not btn.is_displayed():
            return False
        classes = (btn.get_attribute('class') or '').lower()
        aria = (btn.get_attribute('aria-disabled') or '').lower()
        if 'disabled' in classes or aria == 'true':
            return False
        return btn.is_enabled()
    except Exception:
        return False


def _texto_e_botao_seguinte(btn) -> bool:
    try:
        ng = (btn.get_attribute('ng-click') or '').lower()
        txt = normalizar_texto(btn.text or '')
        if 'anterior' in txt or 'previous' in txt:
            return False
        if 'funcaoproxima' in ng:
            return True
        return 'seguinte' in txt or 'proxima' in txt or 'proximo' in txt
    except Exception:
        return False


def _encontrar_botoes_seguinte(driver, apenas_visiveis: bool = True) -> List:
    """Localiza botão Seguinte/Próxima (habilitado ou desabilitado)."""
    seletores = [
        (By.CSS_SELECTOR, "button.btn-pesquisa[ng-click*='funcaoProxima']"),
        (By.CSS_SELECTOR, "button[ng-click*='funcaoProxima']"),
        (By.XPATH, "//button[contains(@ng-click,'funcaoProxima')]"),
        (By.XPATH, "//button[contains(@class,'btn-pesquisa') and contains(.,'Seguinte')]"),
        (By.XPATH, "//button[contains(normalize-space(.),'Seguinte')]"),
        (By.XPATH, "//button[contains(normalize-space(.),'Próxim') or contains(normalize-space(.),'Proxim')]"),
    ]
    candidatos: List = []
    for by, sel in seletores:
        try:
            for btn in driver.find_elements(by, sel):
                if apenas_visiveis and not btn.is_displayed():
                    continue
                if not _texto_e_botao_seguinte(btn):
                    continue
                if btn not in candidatos:
                    candidatos.append(btn)
        except Exception:
            pass
    candidatos.sort(
        key=lambda b: 0 if 'funcaoProxima' in (b.get_attribute('ng-click') or '') else 1,
    )
    return candidatos


def _localizar_botao_seguinte(driver, apenas_habilitado: bool = True):
    """Botão oficial Caixa: Seguinte — retorna None se só existir desabilitado."""
    for btn in _encontrar_botoes_seguinte(driver):
        if apenas_habilitado and not _botao_pagina_clicavel(btn):
            continue
        return btn
    return None


def _estado_botao_seguinte(driver) -> str:
    """
    'habilitado' | 'desabilitado' | 'ausente'
    Desabilitado: classe disabled, aria-disabled, cursor not-allowed, azul claro.
    """
    botoes = _encontrar_botoes_seguinte(driver)
    if not botoes:
        try:
            raw = driver.execute_script("""
                var sels = [
                    "button[ng-click*='funcaoProxima']",
                    "button.btn-pesquisa"
                ];
                for (var si = 0; si < sels.length; si++) {
                    var nodes = document.querySelectorAll(sels[si]);
                    for (var i = 0; i < nodes.length; i++) {
                        var b = nodes[i];
                        var t = (b.textContent || '').toLowerCase();
                        if (t.indexOf('seguinte') < 0 && t.indexOf('proxim') < 0) continue;
                        if (t.indexOf('anterior') >= 0) continue;
                        var st = window.getComputedStyle(b);
                        var off = !b.offsetParent;
                        var dis = b.disabled || b.getAttribute('aria-disabled') === 'true'
                            || (b.className || '').toLowerCase().indexOf('disabled') >= 0
                            || st.pointerEvents === 'none' || st.cursor === 'not-allowed';
                        return dis ? 'desabilitado' : 'habilitado';
                    }
                }
                return 'ausente';
            """)
            if raw in ('habilitado', 'desabilitado', 'ausente'):
                return raw
        except Exception:
            pass
        return 'ausente'

    for btn in botoes:
        if _botao_pagina_clicavel(btn):
            return 'habilitado'
    return 'desabilitado'


def _assinatura_lista_visivel(driver) -> str:
    """Primeiros bolões visíveis — detecta se a pagina realmente mudou."""
    try:
        partes: List[str] = []
        for btn in driver.find_elements(By.CSS_SELECTOR, 'button'):
            if not btn.is_displayed():
                continue
            txt = (btn.text or '').lower()
            if not any(p in txt for p in ('detalh', 'ver', 'comprar', 'apostar')):
                continue
            try:
                card = btn.find_element(
                    By.XPATH,
                    './ancestor::*[contains(@class,"card") or contains(@class,"bolao")][1]',
                )
                t = (card.text or '').strip().replace('\n', ' ')[:120]
            except Exception:
                t = (btn.text or '').strip()[:80]
            if t and len(t) > 12:
                partes.append(t)
            if len(partes) >= 3:
                break
        if partes:
            return '||'.join(partes)
        for sel in ('.card', 'tr', '[class*="bolao"]'):
            for el in driver.find_elements(By.CSS_SELECTOR, sel):
                if not el.is_displayed():
                    continue
                t = (el.text or '').strip().replace('\n', ' ')[:100]
                if t and len(t) > 15:
                    partes.append(t)
                if len(partes) >= 3:
                    break
            if partes:
                break
        return '||'.join(partes)
    except Exception:
        return ''


def _ler_pagina_atual_ui(driver) -> Optional[int]:
    """Índice da página atual no Angular ou no botão numérico ativo."""
    try:
        raw = driver.execute_script("""
            try {
                if (typeof angular !== 'undefined') {
                    var btn = document.querySelector("button[ng-click*='funcaoProxima']")
                        || document.querySelector("button.btn-pesquisa");
                    if (btn) {
                        var scope = angular.element(btn).scope();
                        for (var j = 0; j < 10 && scope; j++) {
                            if (typeof scope.paginaAtual === 'number') return scope.paginaAtual;
                            if (typeof scope.pagina === 'number') return scope.pagina;
                            if (scope.vm && typeof scope.vm.paginaAtual === 'number') return scope.vm.paginaAtual;
                            if (scope.vm && typeof scope.vm.pagina === 'number') return scope.vm.pagina;
                            if (typeof scope.currentPage === 'number') return scope.currentPage;
                            scope = scope.$parent;
                        }
                    }
                }
            } catch (e) {}
            var ativos = document.querySelectorAll(
                '.pagination .active, .page-item.active, [class*="pagina"][class*="ativa"]'
            );
            for (var i = 0; i < ativos.length; i++) {
                var n = parseInt((ativos[i].textContent || '').trim(), 10);
                if (!isNaN(n) && n > 0) return n;
            }
            return null;
        """)
        return int(raw) if raw else None
    except Exception:
        return None


def _invoke_funcao_proxima_angular(driver, btn) -> bool:
    """Chama funcaoProxima só no scope do botão Seguinte (sem varrer a árvore Angular)."""
    try:
        return bool(driver.execute_script("""
            var btn = arguments[0];
            try {
                if (typeof angular === 'undefined') return false;
                var el = angular.element(btn);
                var scope = el.scope() || (el.isolateScope && el.isolateScope());
                for (var j = 0; j < 12 && scope; j++) {
                    if (typeof scope.funcaoProxima === 'function') {
                        scope.funcaoProxima();
                        if (!scope.$$phase) scope.$apply();
                        return true;
                    }
                    if (scope.vm && typeof scope.vm.funcaoProxima === 'function') {
                        scope.vm.funcaoProxima();
                        if (!scope.$$phase) scope.$apply();
                        return true;
                    }
                    scope = scope.$parent;
                }
            } catch (e) {}
            return false;
        """, btn))
    except Exception:
        return False


def _clicar_elemento_nativo(driver, el) -> None:
    _dismiss_overlays(driver)
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center", inline:"nearest"});', el,
    )
    time.sleep(0.35)
    try:
        ActionChains(driver).move_to_element(el).pause(0.25).click(el).perform()
    except Exception:
        try:
            el.click()
        except Exception:
            driver.execute_script('arguments[0].click();', el)


def _clicar_seguinte_caixa(driver, btn, log_fn: LogFn = None) -> None:
    """Um único acionamento de Seguinte — evita pular várias páginas."""
    _dismiss_overlays(driver)
    driver.execute_script(
        'arguments[0].scrollIntoView({block:"center", inline:"nearest"});', btn,
    )
    time.sleep(0.4)

    if _invoke_funcao_proxima_angular(driver, btn):
        _log('  [PAGINA] Seguinte via Angular (1 clique).', log_fn)
        time.sleep(1.8)
        return

    _clicar_elemento_nativo(driver, btn)
    _log('  [PAGINA] Seguinte via clique nativo (1 clique).', log_fn)
    time.sleep(1.8)


def _clicar_pagina_numero(driver, numero: int, log_fn: LogFn = None) -> bool:
    """Clica no número da página (ex.: botão '2') na barra de paginação."""
    alvo = str(numero)
    xpaths = [
        f"//button[normalize-space()='{alvo}']",
        f"//a[normalize-space()='{alvo}']",
        f"//*[contains(@class,'pagination')]//button[normalize-space()='{alvo}']",
        f"//*[contains(@class,'pagination')]//a[normalize-space()='{alvo}']",
        f"//*[contains(@class,'paginacao')]//*[normalize-space()='{alvo}']",
    ]
    for xp in xpaths:
        try:
            for el in driver.find_elements(By.XPATH, xp):
                if not _botao_pagina_clicavel(el):
                    continue
                _clicar_elemento_nativo(driver, el)
                _log(f'  [PAGINA] Clicou no número {numero}.', log_fn)
                return True
        except Exception:
            pass
    return False


def _angular_ir_para_pagina(driver, numero: int, log_fn: LogFn = None) -> bool:
    try:
        ok = driver.execute_script("""
            var n = arguments[0];
            try {
                if (typeof angular === 'undefined') return false;
                var inj = angular.element(document.body).injector();
                if (!inj) return false;
                var tentar = function(scope, depth) {
                    if (!scope || depth > 18) return false;
                    var candidatos = [scope, scope.vm].filter(Boolean);
                    for (var i = 0; i < candidatos.length; i++) {
                        var s = candidatos[i];
                        if (typeof s.funcaoIrParaPagina === 'function') {
                            s.funcaoIrParaPagina(n);
                            if (!scope.$$phase) scope.$apply();
                            return true;
                        }
                        if (typeof s.irPagina === 'function') {
                            s.irPagina(n);
                            if (!scope.$$phase) scope.$apply();
                            return true;
                        }
                        if ('paginaAtual' in s) {
                            s.paginaAtual = n;
                            if (typeof s.funcaoPesquisar === 'function') s.funcaoPesquisar();
                            else if (typeof s.pesquisar === 'function') s.pesquisar();
                            else if (typeof scope.funcaoProxima === 'function') {}
                            if (!scope.$$phase) scope.$apply();
                            return true;
                        }
                    }
                    var c = scope.$$childHead;
                    while (c) {
                        if (tentar(c, depth + 1)) return true;
                        c = c.$$nextSibling;
                    }
                    return tentar(scope.$parent, depth + 1);
                };
                return tentar(inj.get('$rootScope'), 0);
            } catch (e) { return false; }
        """, numero)
        if ok:
            _log(f'  [PAGINA] Angular — indo para página {numero}.', log_fn)
            time.sleep(2.5)
        return bool(ok)
    except Exception:
        return False


def _aguardar_paginacao_manual(pagina: int, log_fn: LogFn = None) -> bool:
    _log(
        f'\n  *** PAGINAÇÃO MANUAL (página {pagina}) ***\n'
        f'  O script NÃO vai clicar em Seguinte.\n'
        f'  No navegador: vá até a página {pagina} (você controla).\n'
        f'  Quando estiver na página certa, pressione ENTER aqui...',
        log_fn,
    )
    try:
        input()
        return True
    except EOFError:
        return False


def _ir_para_pagina(driver, destino: int, log_fn: LogFn = None) -> bool:
    """Avança de uma em uma página até destino (1 clique Seguinte por passo)."""
    if destino <= 1:
        return True

    atual = _ler_pagina_atual_ui(driver) or 1
    passos = 0
    while atual < destino and passos < destino + 2:
        if not _ir_proxima_pagina_lista(driver, log_fn):
            break
        time.sleep(0.8)
        atual = _ler_pagina_atual_ui(driver) or (atual + 1)
        passos += 1

    return atual >= destino


def _pagina_avancou(driver, assinatura_antes: str, pagina_antes: Optional[int]) -> bool:
    pagina_depois = _ler_pagina_atual_ui(driver)
    if pagina_antes is not None and pagina_depois is not None and pagina_depois > pagina_antes:
        return True
    assinatura_depois = _assinatura_lista_visivel(driver)
    return bool(assinatura_depois and assinatura_depois != assinatura_antes)


def _ir_proxima_pagina_lista(driver, log_fn: LogFn = None) -> bool:
    """Avança exatamente UMA página — um único clique em Seguinte (com retentativas)."""
    for tentativa in range(1, 5):
        if tentativa > 1:
            _log(f'  [PAGINA] Retentativa {tentativa}/4...', log_fn)
            time.sleep(1.0 + tentativa * 0.6)

        _scroll_para_paginacao(driver)
        _dismiss_overlays(driver)

        assinatura_antes = _assinatura_lista_visivel(driver)
        pagina_antes = _ler_pagina_atual_ui(driver)

        btn = _localizar_botao_seguinte(driver)
        if not btn:
            _log('  [PAGINA] Botão Seguinte não encontrado.', log_fn)
            continue

        try:
            _clicar_seguinte_caixa(driver, btn, log_fn)
            time.sleep(2.0)
            _aguardar_lista_apos_aplicar(driver, timeout=12)

            if _pagina_avancou(driver, assinatura_antes, pagina_antes):
                pagina_depois = _ler_pagina_atual_ui(driver)
                if pagina_depois:
                    _log(
                        f'  [PAGINA] OK — {pagina_antes or "?"} → {pagina_depois}.',
                        log_fn,
                    )
                else:
                    _log('  [PAGINA] OK — lista mudou.', log_fn)
                return True

            _log('  [PAGINA] Seguinte clicado mas a lista não mudou.', log_fn)
        except Exception as exc:
            _log(f'  [PAGINA] Erro ao clicar Seguinte: {exc}', log_fn)

    pagina_antes = _ler_pagina_atual_ui(driver)
    destino = (pagina_antes or 0) + 1
    if destino > 1 and _angular_ir_para_pagina(driver, destino, log_fn):
        time.sleep(2.0)
        _aguardar_lista_apos_aplicar(driver, timeout=10)
        if _ler_pagina_atual_ui(driver) == destino:
            _log(f'  [PAGINA] OK — Angular direto para página {destino}.', log_fn)
            return True

    try:
        from boloes_api_caixa import ler_metadados_paginacao_api
        meta = ler_metadados_paginacao_api(driver)
        if meta:
            destino = int(meta['pagina_atual']) + 1
            if destino <= int(meta['ultima_pagina']):
                if _angular_ir_para_pagina(driver, destino, log_fn):
                    time.sleep(2.0)
                    _aguardar_lista_apos_aplicar(driver, timeout=10)
                    _log(f'  [PAGINA] OK — API indicou ir para página {destino}.', log_fn)
                    return True
                if _clicar_pagina_numero(driver, destino, log_fn):
                    time.sleep(2.0)
                    _aguardar_lista_apos_aplicar(driver, timeout=10)
                    return True
    except Exception:
        pass

    return False


def _tem_proxima_pagina(driver) -> bool:
    _scroll_para_paginacao(driver)
    return _estado_botao_seguinte(driver) == 'habilitado'


def eh_ultima_pagina(driver) -> bool:
    """True quando Seguinte existe desabilitado ou não há próxima página."""
    _scroll_para_paginacao(driver)
    estado = _estado_botao_seguinte(driver)
    return estado in ('desabilitado', 'ausente')


def _filtro_loterica_no_campo(valor_campo: str, cfg: FiltroLotericaConfig) -> bool:
    """Evita redigitar 9833 se o usuário já selecionou a lotérica no site."""
    raw = (valor_campo or '').strip()
    if not raw:
        return False
    if cfg.codigo and re.search(r'(?:^|\D)' + re.escape(cfg.codigo) + r'(?:\D|$)', raw):
        return True
    nome = normalizar_texto(cfg.nome or '')
    if nome and len(nome) >= 4 and nome in normalizar_texto(raw):
        return True
    return False


def _opcao_dezenas_corresponde(txt: str, ov: str, qtd: int) -> bool:
    valor = str(qtd)
    t = (txt or '').strip()
    o = (ov or '').strip()
    if t == valor or o == valor:
        return True
    if t.startswith(valor + ' ') or t.startswith(valor + 'dezena'):
        return True
    if re.match(rf'^{qtd}\s*dezena', t, re.I):
        return True
    nums = re.findall(r'\d+', t)
    return len(nums) == 1 and nums[0] == valor


def _selecionar_qtd_dezenas(driver, qtd: int, log_fn: LogFn = None) -> bool:
    valor = str(qtd)

    def tentar_select(sel) -> bool:
        try:
            if not sel.is_displayed():
                return False
            dropdown = Select(sel)
            for opt in dropdown.options:
                txt = (opt.text or '').strip()
                ov = (opt.get_attribute('value') or '').strip()
                if not _opcao_dezenas_corresponde(txt, ov, qtd):
                    continue
                try:
                    dropdown.select_by_visible_text(txt)
                except Exception:
                    dropdown.select_by_value(ov or txt)
                driver.execute_script("""
                    var el = arguments[0], v = arguments[1];
                    el.value = v;
                    el.dispatchEvent(new Event('change', {bubbles: true}));
                    el.dispatchEvent(new Event('input', {bubbles: true}));
                    if (typeof angular !== 'undefined') {
                        try {
                            angular.element(el).triggerHandler('change');
                            angular.element(el).triggerHandler('input');
                        } catch (e) {}
                    }
                """, sel, ov or txt)
                time.sleep(0.5)
                _log(f'  [FILTRO] Dezenas no site: {txt or ov}', log_fn)
                return True
        except Exception:
            pass
        return False

    for sel in driver.find_elements(By.TAG_NAME, 'select'):
        if tentar_select(sel):
            return True

    for xp in (
        "//*[contains(translate(.,'ÉÊÃÕéêãõ','EEAAeeaa'),'Quant') and contains(.,'Dezenas')]/following::select[1]",
        "//*[contains(.,'Qtd') and contains(.,'Dezenas')]/following::select[1]",
        "//label[contains(.,'Dezenas')]/following::select[1]",
        "//select[contains(@ng-model,'dezena') or contains(@ng-model,'Dezenas')]",
        "//select[contains(@id,'dezena') or contains(@name,'dezena')]",
    ):
        try:
            for sel in driver.find_elements(By.XPATH, xp):
                if tentar_select(sel):
                    return True
        except Exception:
            pass

    _log(f'  [FILTRO] AVISO: nao foi possivel selecionar {valor} dezenas no site.', log_fn)
    return False


def _clicar_aplicar(driver) -> bool:
    for xp in (
        "//button[normalize-space()='Aplicar']",
        "//button[contains(.,'Aplicar') and not(contains(.,'Limpar'))]",
        "//*[contains(@ng-click,'aplicar') or contains(@ng-click,'Aplicar')]",
        "//input[@type='button' and contains(@value,'Aplicar')]",
        "//a[contains(.,'Aplicar') and not(contains(.,'Limpar'))]",
    ):
        try:
            for btn in driver.find_elements(By.XPATH, xp):
                if btn.is_displayed() and btn.is_enabled() and 'limpar' not in (btn.text or '').lower():
                    _click_seguro(driver, btn)
                    time.sleep(2.5)
                    return True
        except Exception:
            pass
    return False


def aplicar_filtro_somente_dezenas(
    driver,
    cfg: FiltroLotericaConfig,
    log_fn: LogFn = None,
) -> bool:
    """Aplica só qtd. de dezenas no site (sem lotérica) — varredura por estado/páginas."""
    if not cfg or not cfg.qtd_dezenas:
        _log('  [FILTRO] Modo qualquer lotérica — sem alterar filtros no site.', log_fn)
        return True
    try:
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(0.4)
        _dismiss_overlays(driver)
        _expandir_painel_filtros(driver)
        _scroll_para_filtros(driver)
        if _selecionar_qtd_dezenas(driver, cfg.qtd_dezenas, log_fn):
            if _clicar_aplicar(driver):
                _aguardar_lista_apos_aplicar(driver)
            _log(f'  [FILTRO] Aplicado: {cfg.qtd_dezenas} dezenas (qualquer lotérica)', log_fn)
        else:
            _log('  [FILTRO] Dezenas no site não alteradas — use filtro manual no Edge.', log_fn)
        return True
    except Exception as exc:
        _log(f'  [FILTRO] Erro (somente dezenas): {exc}', log_fn)
        return True


def aplicar_filtro_loterica(
    driver,
    cfg: FiltroLotericaConfig,
    log_fn: LogFn = None,
    somente_loterica: bool = False,
) -> bool:
    """
    Lotérica + Aplicar. Com somente_loterica=True: nao mexe em qtd de dezenas.
    Se o campo já tiver a lotérica certa, NÃO redigita.
    """
    if cfg and cfg.qualquer_loterica:
        if somente_loterica:
            return True
        return aplicar_filtro_somente_dezenas(driver, cfg, log_fn)
    if not cfg or not cfg.termo:
        return True
    try:
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(0.4)
        _dismiss_overlays(driver)
        _expandir_painel_filtros(driver)
        _scroll_para_filtros(driver)

        campo = None
        for _ in range(24):
            campo = _find_input_loterica(driver)
            if campo:
                break
            time.sleep(0.5)

        if not campo:
            if not sessao_caixa_ativa(driver):
                _log('  [FILTRO] Sessao expirada — campo de loterica sumiu.', log_fn)
            else:
                _log('  [FILTRO] Campo de lotérica não encontrado.', log_fn)
            return False

        valor_atual = (campo.get_attribute('value') or '').strip()
        if _filtro_loterica_no_campo(valor_atual, cfg):
            _log(f'  [FILTRO] Lotérica já no campo — sem redigitar ({valor_atual[:55]})', log_fn)
        else:
            busca = _texto_busca_autocomplete(cfg)
            _log(f'  [FILTRO] Digitando: {busca}', log_fn)
            _digitar_busca_loterica(campo, busca)
            time.sleep(1.5)
            if not _selecionar_autocomplete(driver, cfg, log_fn):
                try:
                    campo.send_keys(Keys.ARROW_DOWN)
                    time.sleep(0.3)
                    campo.send_keys(Keys.ENTER)
                    time.sleep(0.5)
                except Exception:
                    pass

        if not somente_loterica and cfg.qtd_dezenas:
            _selecionar_qtd_dezenas(driver, cfg.qtd_dezenas, log_fn)

        loteria_ok = _filtro_loterica_no_campo(valor_atual, cfg) or _filtro_loterica_no_campo(
            (campo.get_attribute('value') or '').strip(), cfg,
        )
        if not _clicar_aplicar(driver):
            if somente_loterica and loteria_ok:
                _log('  [FILTRO] Aplicar ausente — lotérica já no campo, continuando.', log_fn)
            else:
                _log('  [FILTRO] Botão Aplicar não encontrado.', log_fn)
                return False
        else:
            _aguardar_lista_apos_aplicar(driver)

        if somente_loterica:
            _log(f'  [FILTRO] Lotérica aplicada: {cfg.termo}', log_fn)
        else:
            dez = f' | {cfg.qtd_dezenas} dez.' if cfg.qtd_dezenas else ''
            _log(f'  [FILTRO] Aplicado: {cfg.termo}{dez}', log_fn)
        return True
    except Exception as exc:
        _log(f'  [FILTRO] Erro: {exc}', log_fn)
        return False


def preparar_pagina_loterica(
    driver,
    cfg: FiltroLotericaConfig,
    pagina: int,
    log_fn: LogFn = None,
    modo_web: bool = False,
    estado_check: Optional[dict] = None,
) -> bool:
    """
    Página 2+: reaplica só o nome da lotérica + Aplicar, depois navega até a página.
    Reaplicar sempre volta à página 1 — depois avança com Seguinte.
    """
    if pagina < 1:
        pagina = 1

    _log(f'\n  >>> Preparando página {pagina} (lotérica + navegação)...', log_fn)

    if not garantir_sessao_caixa(driver, pagina, log_fn, modo_web, estado_check):
        return False

    if not aplicar_filtro_loterica(driver, cfg, log_fn, somente_loterica=True):
        if not sessao_caixa_ativa(driver):
            if garantir_sessao_caixa(driver, pagina, log_fn, modo_web, estado_check):
                if not aplicar_filtro_loterica(driver, cfg, log_fn, somente_loterica=True):
                    return False
            else:
                return False
        else:
            return False

    time.sleep(1.0)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    time.sleep(0.4)
    driver.execute_script('window.scrollTo(0, 0);')
    time.sleep(0.5)

    for i in range(pagina - 1):
        _scroll_para_paginacao(driver)
        if not _ir_proxima_pagina_lista(driver, log_fn):
            _log(f'  [FILTRO] Não foi possível avançar para página {pagina} (passo {i + 1}).', log_fn)
            return pagina == 1
        time.sleep(0.8)

    _log(f'  [FILTRO] Página {pagina} pronta (lotérica {cfg.termo}).', log_fn)
    return True


def preparar_pagina_filtrada(
    driver,
    cfg: FiltroLotericaConfig,
    pagina: int,
    log_fn: LogFn = None,
    modo_web: bool = False,
    estado_check: Optional[dict] = None,
) -> bool:
    """
    Garante filtro completo (lotérica + dezenas) NA página correta.
    Reaplicar filtro sempre volta à página 1 — depois avança até a página desejada.
    """
    if pagina < 1:
        pagina = 1

    _log(f'\n  >>> Preparando página {pagina} (filtro + navegação)...', log_fn)

    if not garantir_sessao_caixa(driver, pagina, log_fn, modo_web, estado_check):
        return False

    if not aplicar_filtro_loterica(driver, cfg, log_fn):
        if not sessao_caixa_ativa(driver):
            if garantir_sessao_caixa(driver, pagina, log_fn, modo_web, estado_check):
                if not aplicar_filtro_loterica(driver, cfg, log_fn):
                    return False
            else:
                return False
        else:
            return False

    time.sleep(1.0)
    driver.execute_script('window.scrollTo(0, document.body.scrollHeight);')
    time.sleep(0.4)
    driver.execute_script('window.scrollTo(0, 0);')
    time.sleep(0.5)

    for i in range(pagina - 1):
        _scroll_para_paginacao(driver)
        if not _ir_proxima_pagina_lista(driver, log_fn):
            _log(f'  [FILTRO] Não foi possível avançar para página {pagina} (passo {i + 1}).', log_fn)
            return pagina == 1
        time.sleep(0.8)

    _log(f'  [FILTRO] Página {pagina} pronta.', log_fn)
    return True


def preparar_extracao_pagina(
    driver,
    cfg: FiltroLotericaConfig,
    pagina: int,
    log_fn: LogFn = None,
    modo_web: bool = False,
    estado_check: Optional[dict] = None,
    navegacao_manual: bool = False,
) -> bool:
    """
    Prepara a página para extração.

    Página 1: aplica filtro + Aplicar.
    Página 2+ manual: NÃO clica — usuário já navegou.
    Página 2+ auto: UM clique Seguinte (sem cascata).
    """
    if pagina <= 1:
        return preparar_pagina_filtrada(driver, cfg, 1, log_fn, modo_web, estado_check)

    if navegacao_manual:
        _log(f'\n  >>> Página {pagina}: extração sem clique automático (você controla).', log_fn)
        return True

    _log(f'\n  >>> Página {pagina}: 1 clique Seguinte (automático)...', log_fn)

    if not garantir_sessao_caixa(driver, pagina, log_fn, modo_web, estado_check):
        return False

    _scroll_para_paginacao(driver)
    if _ir_proxima_pagina_lista(driver, log_fn):
        _log(f'  [FILTRO] Página {pagina} pronta.', log_fn)
        return True

    _log(
        f'  [FILTRO] Seguinte automático falhou na página {pagina}.\n'
        f'  Use opção [2] Por Páginas — lá VOCÊ navega e o script só extrai.',
        log_fn,
    )
    return False


def reforcar_filtro_antes_da_pagina(
    driver,
    cfg: FiltroLotericaConfig,
    pagina: int,
    log_fn: LogFn = None,
) -> bool:
    return preparar_pagina_filtrada(driver, cfg, pagina, log_fn)


def _texto_modalidade_casa(el_texto: str, mod: ModalidadeBolaoConfig) -> bool:
    linhas = [normalizar_texto(l) for l in (el_texto or '').split('\n') if l.strip()]
    blob = linhas[0] if linhas else normalizar_texto(el_texto)
    if not blob:
        return False

    na_label = normalizar_texto(mod.label)

    if mod.slug == 'quina':
        return blob == 'quina' or (blob.startswith('quina') and 'sao joao' not in blob and 'são joão' not in (el_texto or '').lower())

    if blob == na_label:
        return True
    if len(na_label.split()) >= 2 and na_label in blob:
        return True
    for kw in mod.keywords:
        na = normalizar_texto(kw)
        if na and (blob == na or (len(na.split()) >= 2 and na in blob)):
            return True
    return False


def selecionar_modalidade_bolao(driver, mod: ModalidadeBolaoConfig, log_fn: LogFn = None) -> bool:
    try:
        driver.execute_script('window.scrollTo(0, 0);')
        time.sleep(0.5)

        # Cards horizontais "Modalidades" no topo da página de bolões
        seletores = [
            'div[class*="card"]',
            'button[class*="card"]',
            '[class*="modalidade"]',
            '[role="tab"]',
            'button',
            'a',
        ]

        melhor = None
        melhor_score = 0

        for css in seletores:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, css):
                    if not el.is_displayed():
                        continue
                    txt = (el.text or '').strip()
                    if not txt or len(txt) > 120:
                        continue
                    if not _texto_modalidade_casa(txt, mod):
                        continue
                    score = len(normalizar_texto(mod.label))
                    if score > melhor_score:
                        melhor = el
                        melhor_score = score
            except Exception:
                pass

        if melhor:
            driver.execute_script('arguments[0].scrollIntoView({block: "center", inline: "center"});', melhor)
            time.sleep(0.4)
            try:
                melhor.click()
            except Exception:
                driver.execute_script('arguments[0].click();', melhor)
            time.sleep(2.2)
            _log(f'  [MODALIDADE] Selecionada: {mod.label}', log_fn)
            return True

        # Fallback XPath por label
        for frag in [mod.label] + mod.keywords[:2]:
            frag_esc = frag.replace("'", " ")
            for xp in (
                f"//*[contains(@class,'card')][contains(., '{frag_esc}')]",
                f"//button[contains(., '{frag_esc}')]",
            ):
                try:
                    for el in driver.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            driver.execute_script('arguments[0].scrollIntoView({block: "center"});', el)
                            time.sleep(0.3)
                            el.click()
                            time.sleep(2.2)
                            _log(f'  [MODALIDADE] Selecionada: {mod.label}', log_fn)
                            return True
                except Exception:
                    pass

        _log(f'  [MODALIDADE] Card não encontrado: {mod.label}', log_fn)
        return False
    except Exception as exc:
        _log(f'  [MODALIDADE] Erro: {exc}', log_fn)
        return False


def _estado_no_texto(texto: str, estado) -> bool:
    if not texto or not estado:
        return False
    t = normalizar_texto(texto)
    sigla = estado.sigla.upper()
    nome = normalizar_texto(estado.nome)
    if sigla == t or f' {sigla} ' in f' {t} ':
        return True
    if nome in t or t.startswith(nome[:8]):
        return True
    if 'SAO PAULO' in t and estado.sigla == 'SP':
        return True
    return False


def selecionar_estado_bolao(driver, estado, log_fn: LogFn = None) -> bool:
    """Seleciona UF no filtro do site (dropdown ou lista)."""
    if not estado:
        return False
    try:
        _dismiss_overlays(driver)
        _expandir_painel_filtros(driver)
        _scroll_para_filtros(driver)
        time.sleep(0.4)

        alvos_txt = [
            estado.nome,
            estado.nome.replace('SAO', 'SÃO'),
            f'{estado.sigla} -',
            estado.sigla,
        ]

        for sel_el in driver.find_elements(By.TAG_NAME, 'select'):
            if not sel_el.is_displayed():
                continue
            try:
                dropdown = Select(sel_el)
                for opt in dropdown.options:
                    txt = (opt.text or '').strip()
                    if not txt:
                        continue
                    if _estado_no_texto(txt, estado):
                        dropdown.select_by_visible_text(txt)
                        time.sleep(0.5)
                        _log(f'  [ESTADO] Selecionado: {txt} ({estado.sigla})', log_fn)
                        return True
                    for alvo in alvos_txt:
                        if alvo and alvo.upper() in txt.upper():
                            dropdown.select_by_visible_text(txt)
                            time.sleep(0.5)
                            _log(f'  [ESTADO] Selecionado: {txt} ({estado.sigla})', log_fn)
                            return True
                    if str(estado.codigo_ibge) == (opt.get_attribute('value') or '').strip():
                        dropdown.select_by_value(str(estado.codigo_ibge))
                        time.sleep(0.5)
                        _log(f'  [ESTADO] Selecionado por código IBGE {estado.codigo_ibge}', log_fn)
                        return True
            except Exception:
                continue

        xpaths = (
            f"//*[contains(@class,'estado') or contains(@id,'estado') or contains(@ng-model,'estado')]"
            f"//*[contains(., '{estado.nome.title()}') or contains(., '{estado.sigla}')]",
            f"//label[contains(.,'Estado')]/following::*[contains(., '{estado.sigla}')][1]",
            f"//*[self::li or self::button or self::a][contains(., '{estado.nome.title()}')]",
            f"//*[self::li or self::button or self::a][contains(., 'São Paulo')]" if estado.sigla == 'SP' else '',
        )
        for xp in xpaths:
            if not xp:
                continue
            try:
                for el in driver.find_elements(By.XPATH, xp):
                    if not el.is_displayed():
                        continue
                    txt = (el.text or '').strip()
                    if txt and _estado_no_texto(txt, estado):
                        driver.execute_script('arguments[0].scrollIntoView({block: "center"});', el)
                        time.sleep(0.3)
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script('arguments[0].click();', el)
                        time.sleep(0.8)
                        _log(f'  [ESTADO] Clique: {txt[:40]} ({estado.sigla})', log_fn)
                        return True
            except Exception:
                pass

        ok_js = driver.execute_script("""
            var estado = arguments[0];
            function norm(t) {
                return (t || '').toUpperCase().replace(/\\s+/g, ' ').trim();
            }
            var alvos = [estado.nome, 'SAO PAULO', estado.sigla];
            var sels = document.querySelectorAll('select');
            for (var i = 0; i < sels.length; i++) {
                var sel = sels[i];
                if (!sel.offsetParent) continue;
                for (var j = 0; j < sel.options.length; j++) {
                    var opt = sel.options[j];
                    var txt = norm(opt.text);
                    for (var k = 0; k < alvos.length; k++) {
                        if (alvos[k] && txt.indexOf(norm(alvos[k])) >= 0) {
                            sel.selectedIndex = j;
                            sel.dispatchEvent(new Event('change', {bubbles: true}));
                            if (typeof angular !== 'undefined') {
                                try { angular.element(sel).triggerHandler('change'); } catch(e) {}
                            }
                            return opt.text.trim();
                        }
                    }
                    if (String(opt.value) === String(estado.codigo_ibge)) {
                        sel.selectedIndex = j;
                        sel.dispatchEvent(new Event('change', {bubbles: true}));
                        return opt.text.trim();
                    }
                }
            }
            if (typeof angular !== 'undefined') {
                var sc = angular.element(document.body).scope();
                for (var d = 0; d < 16 && sc; d++) {
                    if (sc.idUF != null) { sc.idUF = estado.codigo_ibge; sc.$applyAsync(); return 'angular-idUF'; }
                    if (sc.estado != null) { sc.estado = estado.codigo_ibge; sc.$applyAsync(); return 'angular-estado'; }
                    if (sc.filtro && sc.filtro.idUF != null) {
                        sc.filtro.idUF = estado.codigo_ibge; sc.$applyAsync(); return 'angular-filtro-idUF';
                    }
                    sc = sc.$parent;
                }
            }
            return null;
        """, {'nome': estado.nome, 'sigla': estado.sigla, 'codigo_ibge': estado.codigo_ibge})
        if ok_js:
            time.sleep(0.8)
            _log(f'  [ESTADO] Aplicado via script: {estado.nome} ({estado.sigla})', log_fn)
            return True

        _log(f'  [ESTADO] Não encontrado no site: {estado.nome} — selecione manualmente se necessário.', log_fn)
        return False
    except Exception as exc:
        _log(f'  [ESTADO] Erro: {exc}', log_fn)
        return False


def aplicar_filtro_varredura_automatica(
    driver,
    cfg: FiltroLotericaConfig,
    modalidade_cfg: ModalidadeBolaoConfig,
    estado,
    log_fn: LogFn = None,
) -> bool:
    """
    Modo [1] por UF: modalidade no site + dezenas + estado + Aplicar → página 1.
    """
    _log(f'\n  [VARREDURA] Preparando {estado.sigla} — {modalidade_cfg.label} | {cfg.qtd_dezenas} dez.', log_fn)
    selecionar_modalidade_bolao(driver, modalidade_cfg, log_fn)
    time.sleep(1.0)
    _dismiss_overlays(driver)
    _scroll_para_filtros(driver)

    try:
        el = _find_input_loterica(driver)
        if el and (el.get_attribute('value') or '').strip():
            _preencher_input_angular(driver, el, '')
            time.sleep(0.3)
    except Exception:
        pass

    selecionar_estado_bolao(driver, estado, log_fn)
    time.sleep(0.5)

    if cfg.qtd_dezenas:
        _selecionar_qtd_dezenas(driver, cfg.qtd_dezenas, log_fn)

    if _clicar_aplicar(driver):
        _aguardar_lista_apos_aplicar(driver)
        _log(f'  [VARREDURA] Filtro aplicado — {estado.sigla} | pagina 1', log_fn)
        return True

    _log('  [VARREDURA] Botão Aplicar não encontrado — confira filtros no Edge.', log_fn)
    return False


def aplicar_filtros_completos(
    driver,
    loterica_cfg: FiltroLotericaConfig,
    modalidade_cfg: ModalidadeBolaoConfig,
    log_fn: LogFn = None,
) -> bool:
    """Legado — preferir modalidade manual + aplicar_filtro_loterica."""
    ok_mod = selecionar_modalidade_bolao(driver, modalidade_cfg, log_fn)
    time.sleep(0.5)
    _dismiss_overlays(driver)
    _scroll_para_filtros(driver)
    ok_lot = aplicar_filtro_loterica(driver, loterica_cfg, log_fn)
    return ok_mod and ok_lot


def tem_proxima_pagina(driver) -> bool:
    try:
        _scroll_para_paginacao(driver)
    except Exception:
        pass
    return _tem_proxima_pagina(driver)


def ultima_pagina_detectada(driver) -> bool:
    """True quando Seguinte está desabilitado ou ausente (fim das páginas no site)."""
    for espera in (0, 1.2, 2.0):
        if espera:
            time.sleep(espera)
        _scroll_para_paginacao(driver)
        if _estado_botao_seguinte(driver) == 'habilitado':
            return False
    return eh_ultima_pagina(driver)


def ir_para_pagina_lista(driver, destino: int, log_fn: LogFn = None) -> bool:
    """Vai para a página destino (Seguinte passo a passo ou Angular)."""
    if destino <= 1:
        return True
    atual = _ler_pagina_atual_ui(driver)
    if atual == destino:
        return True
    if atual and atual < destino:
        if _ir_para_pagina(driver, destino, log_fn):
            return True
    if _angular_ir_para_pagina(driver, destino, log_fn):
        time.sleep(2.0)
        _aguardar_lista_apos_aplicar(driver, timeout=10)
        return (_ler_pagina_atual_ui(driver) or 0) >= destino
    return _clicar_pagina_numero(driver, destino, log_fn)


def ir_proxima_pagina_lista(driver, log_fn: LogFn = None) -> bool:
    """Avança uma página clicando em Seguinte (Caixa)."""
    return _ir_proxima_pagina_lista(driver, log_fn)


def avancar_para_pagina_filtrada(
    driver,
    cfg: FiltroLotericaConfig,
    pagina_destino: int,
    log_fn: LogFn = None,
    modo_web: bool = False,
    estado_check: Optional[dict] = None,
    navegacao_manual: bool = False,
) -> bool:
    """Chamado ao TERMINAR uma página — avança para pagina_destino."""
    _log(f'\n  >>> Pagina concluida — indo para pagina {pagina_destino}...', log_fn)
    return preparar_extracao_pagina(
        driver, cfg, pagina_destino, log_fn, modo_web, estado_check, navegacao_manual,
    )


def reforcar_filtros_antes_da_pagina(
    driver,
    loterica_cfg: FiltroLotericaConfig,
    modalidade_cfg: ModalidadeBolaoConfig,
    pagina: int,
    log_fn: LogFn = None,
) -> bool:
    """Legado — use preparar_pagina_filtrada (só lotérica)."""
    return preparar_pagina_filtrada(driver, loterica_cfg, pagina, log_fn)
