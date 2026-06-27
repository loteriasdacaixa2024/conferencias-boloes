# -*- coding: utf-8 -*-
"""
Catálogo híbrido — 9 modalidades Caixa + concursos especiais.

Usado pelo extrator API e popup para menu, faixa de dezenas e parser.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, List, Optional

from boloes_extrair_popup import MODALIDADES, ConfigModalidade


@dataclass
class ModalidadeMenu:
    numero: int
    slug: str
    parser_slug: str
    label: str
    extracao: str
    keywords: List[str] = field(default_factory=list)
    especial: bool = False
    base_label: str = ''
    epoca: str = ''
    tecla: str = ''

    @property
    def cfg(self) -> ConfigModalidade:
        return MODALIDADES[self.parser_slug]


# Menu principal 1–9 (Federal e Loteca fora de escopo)
MODALIDADES_MENU: List[ModalidadeMenu] = [
    ModalidadeMenu(1, 'mega-sena', 'mega-sena', 'Mega-Sena',
                   'dezenas (6–20)', ['mega-sena', 'mega sena']),
    ModalidadeMenu(2, 'quina', 'quina', 'Quina',
                   'dezenas (5–15)', ['quina']),
    ModalidadeMenu(3, 'lotofacil', 'lotofacil', 'Lotofácil',
                   'dezenas (15–20)', ['lotofacil', 'lotofácil']),
    ModalidadeMenu(4, 'lotomania', 'lotomania', 'Lotomania',
                   '50 dezenas (00–99)', ['lotomania']),
    ModalidadeMenu(5, 'timemania', 'timemania', 'Timemania',
                   '10 dezenas + time', ['timemania']),
    ModalidadeMenu(6, 'dia-de-sorte', 'dia-de-sorte', 'Dia de Sorte',
                   'dezenas (7–15) + mês', ['dia de sorte']),
    ModalidadeMenu(7, 'super-sete', 'super-sete', 'Super Sete',
                   'colunas (7×1–3)', ['super sete']),
    ModalidadeMenu(8, 'dupla-sena', 'dupla-sena', 'Dupla Sena',
                   'dezenas (6–15)', ['dupla sena']),
    ModalidadeMenu(9, 'mais-milionaria', 'mais-milionaria', '+Milionária',
                   'dezenas + trevos', ['milionaria', 'milionária', '+milion']),
]

# Concursos especiais oficiais (Caixa) — parser usa a modalidade base
CONCURSOS_ESPECIAIS: List[ModalidadeMenu] = [
    ModalidadeMenu(
        101, 'dupla-pascoa', 'dupla-sena', 'Dupla de Páscoa',
        'dezenas (6–15)', ['dupla de pascoa', 'dupla de páscoa', 'dupla pascoa', 'dsp'],
        especial=True, base_label='Dupla Sena', epoca='Páscoa', tecla='DSP',
    ),
    ModalidadeMenu(
        102, 'quina-sao-joao', 'quina', 'Quina de São João',
        'dezenas (5–15)', ['quina de sao joao', 'quina são joão', 'quina sao joao', 'qsj'],
        especial=True, base_label='Quina', epoca='Junho', tecla='QSJ',
    ),
    ModalidadeMenu(
        103, 'lotofacil-independencia', 'lotofacil', 'Lotofácil da Independência',
        'dezenas (15–20)',
        ['lotofacil da independencia', 'lotofácil da independência', 'independencia', 'lti'],
        especial=True, base_label='Lotofácil', epoca='Setembro', tecla='LTI',
    ),
    ModalidadeMenu(
        104, 'mega-virada', 'mega-sena', 'Mega da Virada',
        'dezenas (6–20)', ['mega da virada', 'mega virada', 'msv'],
        especial=True, base_label='Mega-Sena', epoca='31 de dezembro', tecla='MSV',
    ),
    ModalidadeMenu(
        105, 'mega-30-anos', 'mega-sena', 'Mega Sena 30 Anos',
        'dezenas (6–20)', ['mega sena 30 anos', 'mega 30 anos', '30 anos', 'ms3'],
        especial=True, base_label='Mega-Sena', epoca='Especial', tecla='MS3',
    ),
]

TECLAS_ESPECIAIS = {m.tecla.upper(): m for m in CONCURSOS_ESPECIAIS if m.tecla}

# Códigos oficiais da API Caixa (campo "modalidade" no JSON)
CODIGOS_API_CAIXA: dict[str, str] = {
    'MEGA_SENA': 'mega-sena',
    'MEGASENA': 'mega-sena',
    'QUINA': 'quina',
    'LOTOFACIL': 'lotofacil',
    'LOTOMANIA': 'lotomania',
    'TIMEMANIA': 'timemania',
    'DIA_DE_SORTE': 'dia-de-sorte',
    'DIADESORTE': 'dia-de-sorte',
    'SUPER_SETE': 'super-sete',
    'SUPERSETE': 'super-sete',
    'DUPLA_SENA': 'dupla-sena',
    'DUPLASENA': 'dupla-sena',
    'MAIS_MILIONARIA': 'mais-milionaria',
    'MAISMILIONARIA': 'mais-milionaria',
    '+MILIONARIA': 'mais-milionaria',
}

TODAS_MODALIDADES: List[ModalidadeMenu] = MODALIDADES_MENU + CONCURSOS_ESPECIAIS


def imprimir_menu_modalidades() -> None:
    print('\n' + '=' * 60)
    print('  MODALIDADE — selecione aqui E no site da Caixa')
    print('=' * 60)
    print(f'\n  {"#":<3} {"Modalidade":<18} O que extrai')
    print('  ' + '-' * 54)
    for mod in MODALIDADES_MENU:
        print(f'  [{mod.numero}] {mod.label:<16} {mod.extracao}')
    print('\n  Concursos especiais (selecione aqui E no site da Caixa):')
    print(f'  {"Tecla":<5} {"Modalidade":<26} {"Base":<14} Epoca')
    print('  ' + '-' * 58)
    for mod in CONCURSOS_ESPECIAIS:
        print(f'  {mod.tecla:<5} {mod.label:<24} {mod.base_label:<14} {mod.epoca}')
    print('\n  Ex.: 2 | QSJ | quina | Dupla de Pascoa')


def _norm_busca(termo: str) -> str:
    if not termo:
        return ''
    t = unicodedata.normalize('NFD', termo)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    t = re.sub(r'[\s_\-]+', ' ', t.lower().strip())
    return re.sub(r'\s+', ' ', t)


def resolver_modalidade_api(termo: str) -> Optional[ModalidadeMenu]:
    """MEGA_SENA, QUINA… — códigos do JSON da API Caixa."""
    raw = (termo or '').strip()
    if not raw:
        return None
    chave = re.sub(r'[\s\-]+', '_', raw.upper())
    chave_compact = re.sub(r'[^A-Z0-9+]', '', raw.upper())
    slug = CODIGOS_API_CAIXA.get(chave) or CODIGOS_API_CAIXA.get(chave_compact)
    if slug:
        return modalidade_por_slug(slug)
    slug_hifen = raw.lower().replace('_', '-')
    mod = modalidade_por_slug(slug_hifen)
    if mod:
        return mod
    return resolver_modalidade_menu(raw)


def resolver_modalidade_menu(termo: str) -> Optional[ModalidadeMenu]:
    termo = (termo or '').strip()
    if not termo:
        return None

    up = termo.upper()
    if up in TECLAS_ESPECIAIS:
        return TECLAS_ESPECIAIS[up]

    if termo.isdigit():
        n = int(termo)
        for mod in TODAS_MODALIDADES:
            if mod.numero == n:
                return mod
        return None

    norm = _norm_busca(termo)
    norm_sub = norm.replace(' ', '')
    candidatos = []
    for mod in TODAS_MODALIDADES:
        for alvo in (mod.label, mod.tecla, mod.slug.replace('-', ' ')) + tuple(mod.keywords):
            if not alvo:
                continue
            na = _norm_busca(str(alvo))
            na_sub = na.replace(' ', '')
            if na and (na == norm or norm in na or na in norm or na_sub == norm_sub):
                is_exact = (na == norm or na_sub == norm_sub)
                candidatos.append((is_exact, len(na), mod))
    if candidatos:
        candidatos.sort(key=lambda x: (x[0], x[1]), reverse=True)
        return candidatos[0][2]
    return None


def ler_modalidade_terminal() -> ModalidadeMenu:
    imprimir_menu_modalidades()
    while True:
        raw = input('\nModalidade [1-9 | DSP QSJ LTI MSV MS3 | nome]: ').strip()
        mod = resolver_modalidade_menu(raw)
        if mod:
            print(f'\n>>> Modalidade: {mod.label}')
            if mod.especial:
                print(f'>>> Tecla: {mod.tecla} | Base: {mod.base_label} | Epoca: {mod.epoca}')
            print(f'>>> Extrai: {mod.extracao}')
            print('>>> Selecione a MESMA modalidade no site da Caixa antes de extrair.')
            return mod
        print('>>> Informe 1–9, tecla (DSP/QSJ/...) ou nome da modalidade.')


def modalidade_por_slug(slug: str) -> Optional[ModalidadeMenu]:
    s = (slug or '').strip().lower()
    if not s:
        return None
    for mod in TODAS_MODALIDADES:
        if mod.slug == s or mod.parser_slug == s:
            return mod
    return None


def concurso_para_arquivo(concurso: Any) -> str:
    """Normaliza concurso para nome de arquivo — ex.: 364, 4482."""
    digits = re.sub(r'\D', '', str(concurso or ''))
    return digits or 'sem-concurso'


def slug_modalidade_arquivo(mod) -> str:
    """Slug da modalidade no nome do arquivo (ex.: mais-milionaria, quina-sao-joao)."""
    if mod is None:
        return 'boloes'
    return getattr(mod, 'slug', None) or getattr(mod, 'parser_slug', None) or 'boloes'


def nome_arquivo_sessao(concurso: Any, mod) -> str:
    """boloes_{concurso}_{modalidade} — sem extensão."""
    return f'boloes_{concurso_para_arquivo(concurso)}_{slug_modalidade_arquivo(mod)}'


def nome_arquivo_consolidado_padrao(concurso: Any, mod) -> str:
    """boloes_{concurso}_{modalidade}_CONSOLIDADO.json"""
    return f'{nome_arquivo_sessao(concurso, mod)}_CONSOLIDADO.json'


def extrair_concurso_de_boloes(boloes: list) -> str:
    """Concurso mais frequente na lista de bolões."""
    if not boloes:
        return 'sem-concurso'
    from collections import Counter
    vals = [concurso_para_arquivo(b.get('concurso')) for b in boloes if b.get('concurso')]
    if not vals:
        return 'sem-concurso'
    return Counter(vals).most_common(1)[0][0]


def extrair_modalidade_de_boloes(boloes: list) -> Optional[ModalidadeMenu]:
    """Modalidade mais frequente nos bolões extraídos."""
    if not boloes:
        return None
    from collections import Counter
    slugs: list[str] = []
    for b in boloes:
        for chave in ('modalidade_slug', 'modalidade'):
            mod = resolver_modalidade_menu(str(b.get(chave) or ''))
            if mod:
                slugs.append(mod.slug)
                break
    if not slugs:
        return None
    top = Counter(slugs).most_common(1)[0][0]
    return modalidade_por_slug(top)


def hint_filtro_dezenas(mod: ModalidadeMenu) -> str:
    cfg = mod.cfg
    if mod.parser_slug == 'lotomania':
        return '50 fixas (Enter = qualquer)'
    if mod.parser_slug == 'timemania':
        return f'{cfg.min_dez} dez. + time (Enter = qualquer)'
    if mod.parser_slug == 'super-sete':
        return f'colunas / {cfg.min_dez}–{cfg.max_dez} dez. (Enter = qualquer)'
    if mod.parser_slug == 'mais-milionaria':
        return f'{cfg.min_dez}–{cfg.max_dez} dez. + trevos (Enter = qualquer)'
    if mod.parser_slug == 'dia-de-sorte':
        return f'{cfg.min_dez}–{cfg.max_dez} dez. + mês (Enter = qualquer)'
    return f'{cfg.min_dez}–{cfg.max_dez} dez. (Enter = qualquer)'


def dezena_filtro_varredura(
    mod: Optional[ModalidadeMenu],
    override: Optional[int] = None,
) -> Optional[int]:
    """
    Dezenas por aposta no modo automático [1] — qualquer lotérica, varredura por estado/páginas.
    Usa override do terminal se informado; senão o teto usual da modalidade (ex. Quina/QJS 15, Mega 20).
    """
    if override is not None:
        return int(override)
    if not mod:
        return None
    c = mod.cfg
    if c.min_dez == c.max_dez:
        return c.min_dez
    return c.max_dez


def imprimir_tabela_varredura_automatica() -> None:
    """Referência: filtro de dezenas do modo [1] automático por modalidade."""
    print('\n  Modo [1] AUTOMÁTICO — qualquer lotérica | dezenas/aposta por modalidade:')
    print(f'  {"#":<3} {"Modalidade":<22} {"Dez. filtro":<10} Faixa Caixa')
    print('  ' + '-' * 52)
    for mod in MODALIDADES_MENU:
        c = mod.cfg
        dz = dezena_filtro_varredura(mod)
        faixa = f'{c.min_dez}–{c.max_dez}' if c.min_dez != c.max_dez else str(c.min_dez)
        print(f'  [{mod.numero}] {mod.label:<20} {dz or "—":<10} {faixa}')
    for mod in CONCURSOS_ESPECIAIS:
        c = mod.cfg
        dz = dezena_filtro_varredura(mod)
        faixa = f'{c.min_dez}–{c.max_dez}' if c.min_dez != c.max_dez else str(c.min_dez)
        print(f'  {mod.tecla:<4} {mod.label:<20} {dz or "—":<10} {faixa}')
    print('  (No site: modalidade + estado + essa qtd. de dezenas — sem lotérica)')


def menu_para_legacy(mod: ModalidadeMenu):
    return mod


def legacy_para_menu(legacy) -> Optional[ModalidadeMenu]:
    if legacy is None:
        return None
    return resolver_modalidade_menu(getattr(legacy, 'slug', '') or str(getattr(legacy, 'numero', '')))
