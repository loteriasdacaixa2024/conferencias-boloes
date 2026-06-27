# -*- coding: utf-8 -*-
"""Destino dos JSONs no Bolões da Sorte — subpasta por modalidade."""
from __future__ import annotations

import json
import os
import re
from typing import Any, List, Optional

from boloes_modalidades import TODAS_MODALIDADES, resolver_modalidade_menu

# Slug do extrator / nome do arquivo → pasta em conferencias-boloes-da-sorte/
SLUG_EXTRATOR_PARA_PASTA_BDS: dict[str, str] = {
    'mega-sena': 'megasena',
    'mega-virada': 'mega-virada',
    'mega-30-anos': 'mega-virada',
    'quina': 'quina',
    'quina-sao-joao': 'quina-sao-joao',
    'lotofacil': 'lotofacil',
    'lotofacil-independencia': 'lotofacil-independencia',
    'dupla-sena': 'duplasena',
    'dupla-pascoa': 'dupla-pascoa',
    'lotomania': 'lotomania',
    'timemania': 'timemania',
    'dia-de-sorte': 'dia-de-sorte',
    'dia-sorte-natal': 'dia-sorte-natal',
    'super-sete': 'supersete',
    'mais-milionaria': 'mais-milionaria',
}

PASTAS_BDS_PADRAO = sorted(set(SLUG_EXTRATOR_PARA_PASTA_BDS.values()))


def slug_extrator_para_pasta(slug: str) -> str:
    s = (slug or '').strip().lower()
    return SLUG_EXTRATOR_PARA_PASTA_BDS.get(s, s)


def _slug_no_nome_arquivo(nome_arquivo: str) -> Optional[str]:
    base = (nome_arquivo or '').lower()
    # Novo padrão: boloes_{concurso}_{modalidade}_CONSOLIDADO.json
    m = re.match(r'boloes_\d+_([a-z0-9\-]+)(?:_consolidado)?\.json', base)
    if m:
        return m.group(1)
    candidatos = sorted(SLUG_EXTRATOR_PARA_PASTA_BDS.keys(), key=len, reverse=True)
    for slug in candidatos:
        if re.search(rf'_{re.escape(slug)}(?:_\d{{8}}|_consolidado)', base):
            return slug
        if f'_{slug}_' in base:
            return slug
    return None


def _slug_do_json(dados: List[Any]) -> Optional[str]:
    if not dados or not isinstance(dados[0], dict):
        return None
    item = dados[0]
    if item.get('modalidade_slug'):
        return str(item['modalidade_slug']).lower()
    mod_txt = str(item.get('modalidade') or '').strip()
    if mod_txt:
        res = resolver_modalidade_menu(mod_txt)
        if res:
            return res.slug
    texto = item.get('texto_completo') or ''
    if isinstance(texto, str) and texto.strip().startswith('{'):
        try:
            payload = json.loads(texto)
            mod_api = payload.get('modalidade') or payload.get('nomeModalidade') or ''
            if isinstance(mod_api, dict):
                mod_api = mod_api.get('nome') or mod_api.get('descricao') or ''
            res = resolver_modalidade_menu(str(mod_api))
            if res:
                return res.slug
        except (json.JSONDecodeError, TypeError):
            pass
    return None


def detectar_modalidade_site(driver) -> Optional[str]:
    """
    Lê a modalidade ATIVA no site (popup aberto, card selecionado).
    Não varre o body inteiro — evita falso positivo (ex.: Dia de Sorte na barra lateral).
    """
    if driver is None:
        return None
    try:
        texto = driver.execute_script("""
            function visivel(el) {
                if (!el) return false;
                var st = window.getComputedStyle(el);
                return st.display !== 'none' && st.visibility !== 'hidden' && el.offsetParent !== null;
            }
            function textoCard(el) {
                var t = (el.innerText || el.textContent || '').trim();
                return t && t.length < 120 ? t : '';
            }
            // 1) Popup/modal aberto com "Bolão ..."
            var dialogs = document.querySelectorAll(
                '[role="dialog"], .modal, [class*="modal"], [class*="Modal"], [class*="popup"]'
            );
            for (var i = 0; i < dialogs.length; i++) {
                var d = dialogs[i];
                if (!visivel(d)) continue;
                var t = (d.innerText || '').slice(0, 400);
                var tl = t.toLowerCase();
                if (tl.indexOf('bolão') >= 0 || tl.indexOf('bolao') >= 0) return t;
            }
            // 2) Card de modalidade ativo/selecionado
            var ativos = document.querySelectorAll(
                '[class*="card"][class*="active"], [class*="card"][class*="selected"], ' +
                '[class*="card"][class*="ativo"], [class*="modalidade"][class*="active"], ' +
                '[class*="modalidade"][class*="selected"], [aria-selected="true"]'
            );
            for (var j = 0; j < ativos.length; j++) {
                var txt = textoCard(ativos[j]);
                if (txt) return txt;
            }
            // 3) Botão "Compre seu bolão" — card pai com destaque
            var btns = document.querySelectorAll(
                'button.btn-compre-seu-bolao-new-card-modalidade-bolao, ' +
                '.btn-compre-seu-bolao-new-card-modalidade-bolao'
            );
            for (var k = 0; k < btns.length; k++) {
                var card = btns[k].closest('[class*="card"]') || btns[k].parentElement;
                for (var up = 0; up < 6 && card; up++) {
                    var cls = (card.className || '').toLowerCase();
                    if (cls.indexOf('active') >= 0 || cls.indexOf('selected') >= 0 ||
                        cls.indexOf('ativo') >= 0 || cls.indexOf('selecion') >= 0) {
                        var ct = textoCard(card);
                        if (ct) return ct;
                    }
                    card = card.parentElement;
                }
            }
            // 4) Título/filtro visível da página de bolões
            var titulos = document.querySelectorAll('h1, h2, h3, .titulo, [class*="titulo"]');
            for (var n = 0; n < titulos.length; n++) {
                if (!visivel(titulos[n])) continue;
                var ht = textoCard(titulos[n]);
                if (ht && ht.length < 60) return ht;
            }
            return '';
        """) or ''
        if texto:
            mod = resolver_modalidade_menu(str(texto))
            if mod:
                return mod.slug
    except Exception:
        pass
    return None


def detectar_slug_pasta_bds(
    path_sessao: str,
    dados: Optional[List[Any]] = None,
    rotulo_arquivo=None,
    driver=None,
) -> str:
    """
    Define a subpasta BDS (prioridade):
    1) slug no nome do arquivo (boloes_364_mais-milionaria_...)
    2) campo modalidade / modalidade_slug do JSON
    3) modalidade escolhida no terminal
    4) modalidade lida no site
    """
    slug_arq = _slug_no_nome_arquivo(os.path.basename(path_sessao or ''))
    if slug_arq:
        return slug_extrator_para_pasta(slug_arq)

    if dados:
        slug_json = _slug_do_json(dados)
        if slug_json:
            return slug_extrator_para_pasta(slug_json)

    if rotulo_arquivo and getattr(rotulo_arquivo, 'slug', None):
        return slug_extrator_para_pasta(rotulo_arquivo.slug)

    slug_site = detectar_modalidade_site(driver)
    if slug_site:
        return slug_extrator_para_pasta(slug_site)

    return 'quina'


def garantir_subpastas_bds(pasta_root: str) -> None:
    os.makedirs(pasta_root, exist_ok=True)
    for nome in PASTAS_BDS_PADRAO:
        os.makedirs(os.path.join(pasta_root, nome), exist_ok=True)


def caminho_import_bds(
    path_sessao: str,
    pasta_root: str,
    dados: Optional[List[Any]] = None,
    rotulo_arquivo=None,
    driver=None,
) -> str:
    slug_pasta = detectar_slug_pasta_bds(path_sessao, dados, rotulo_arquivo, driver)
    pasta_mod = os.path.join(pasta_root, slug_pasta)
    os.makedirs(pasta_mod, exist_ok=True)
    return os.path.join(pasta_mod, os.path.basename(path_sessao))
