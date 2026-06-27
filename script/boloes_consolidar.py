# -*- coding: utf-8 -*-
"""Consolida bolões em um único JSON (deduplicação por hash_bolao)."""

from __future__ import annotations

import glob
import json
import os
import re
from typing import Any, Dict, List, Optional, Set, Tuple

from boloes_api_parser import extrair_todos_boloes_json


def _hash_de(bolao: dict) -> Optional[str]:
    return bolao.get('hash_bolao') or None


def mesclar_listas(
    existentes: List[dict],
    novos: List[dict],
) -> Tuple[List[dict], int]:
    """Une listas deduplicando por hash_bolao. Retorna (lista, qtd_novos)."""
    por_hash: Dict[str, dict] = {}
    ordem: List[str] = []

    for b in existentes + novos:
        h = _hash_de(b)
        if not h:
            continue
        if h not in por_hash:
            ordem.append(h)
        por_hash[h] = b

    antes = len({ _hash_de(b) for b in existentes if _hash_de(b) })
    saida: List[dict] = []
    for i, h in enumerate(ordem, 1):
        b = dict(por_hash[h])
        b['indice'] = i
        saida.append(b)

    novos_count = len(saida) - antes
    return saida, max(0, novos_count)


def carregar_json_boloes(path: str) -> List[dict]:
    if not path or not os.path.isfile(path):
        return []
    try:
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def salvar_json_boloes(path: str, boloes: List[dict]) -> bool:
    """Grava JSON. Retorna False se vazio (não sobrescreve arquivo com dados)."""
    if not boloes:
        existentes = carregar_json_boloes(path)
        if existentes:
            return False
        return False
    os.makedirs(os.path.dirname(path) or '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(boloes, f, ensure_ascii=False, indent=2)
    return True


def nome_arquivo_consolidado(concurso: str, mod_slug: str) -> str:
    """boloes_{concurso}_{modalidade}_CONSOLIDADO.json"""
    conc = re.sub(r'\D', '', str(concurso or '')) or 'sem-concurso'
    mod = re.sub(r'[^a-z0-9\-]+', '-', (mod_slug or 'boloes').lower()).strip('-') or 'boloes'
    return f'boloes_{conc}_{mod}_CONSOLIDADO.json'


def consolidar_sessao(
    pasta_json: str,
    concurso: str,
    mod_slug: str,
    boloes_sessao: List[dict],
) -> Tuple[str, List[dict], int]:
    """
    Mescla bolões da sessão no CONSOLIDADO do concurso/modalidade.
    Retorna (caminho, lista_final, qtd_novos_no_consolidado).
    """
    nome = nome_arquivo_consolidado(concurso, mod_slug)
    path = os.path.join(pasta_json, nome)
    anteriores = carregar_json_boloes(path)
    final, novos = mesclar_listas(anteriores, boloes_sessao)
    salvar_json_boloes(path, final)
    return path, final, novos


def boloes_de_capturas_api(
    arquivos: List[str],
    codigo_loterica: Optional[str] = None,
    qtd_dezenas: Optional[int] = None,
) -> List[dict]:
    """Extrai bolões únicos de arquivos api_capturada_*.json."""
    por_hash: Dict[str, dict] = {}
    for path in arquivos:
        try:
            with open(path, encoding='utf-8') as f:
                caps = json.load(f)
        except Exception:
            continue
        if not isinstance(caps, list):
            continue
        pag = 0
        base = os.path.basename(path)
        if '_p' in base:
            try:
                pag = int(base.split('_p')[1].split('_')[0])
            except ValueError:
                pag = 0
        for cap in caps:
            for b in extrair_todos_boloes_json(cap.get('data'), somente_com_dezenas=True):
                if codigo_loterica and str(b.get('codigo_loterica') or '') != str(codigo_loterica):
                    continue
                if qtd_dezenas is not None:
                    from boloes_filtro_loterica import bolao_apostas_todas_com_n_dezenas
                    if not bolao_apostas_todas_com_n_dezenas(b, qtd_dezenas):
                        continue
                h = _hash_de(b)
                if h and h not in por_hash:
                    b['pagina'] = pag
                    por_hash[h] = b

    saida = list(por_hash.values())
    for i, b in enumerate(saida, 1):
        b['indice'] = i
    return saida


def consolidar_capturas_pasta(
    pasta_capturas: str,
    pasta_json: str,
    concurso: str,
    mod_slug: str,
    codigo_loterica: Optional[str] = None,
    qtd_dezenas: Optional[int] = None,
) -> Tuple[str, int]:
    """Mescla capturas API da pasta no CONSOLIDADO."""
    padroes = (
        os.path.join(pasta_capturas, 'api_capturada_p*.json'),
        os.path.join(pasta_capturas, 'api_r*_p*.json'),
    )
    arquivos: List[str] = []
    for pat in padroes:
        arquivos.extend(glob.glob(pat))
    arquivos = sorted(set(arquivos))
    boloes = boloes_de_capturas_api(arquivos, codigo_loterica, qtd_dezenas)
    if boloes:
        from boloes_modalidades import extrair_concurso_de_boloes, extrair_modalidade_de_boloes
        if not concurso or concurso == 'sem-concurso':
            concurso = extrair_concurso_de_boloes(boloes)
        mod = extrair_modalidade_de_boloes(boloes)
        if mod:
            mod_slug = mod.slug
    path, final, novos = consolidar_sessao(pasta_json, concurso, mod_slug, boloes)
    return path, len(final)


def consolidar_arquivos_captura(
    arquivos: List[str],
    pasta_json: str,
    concurso: str,
    mod_slug: str,
    codigo_loterica: Optional[str] = None,
    qtd_dezenas: Optional[int] = None,
) -> Tuple[str, List[dict], int]:
    """Mescla lista explícita de arquivos de captura."""
    boloes = boloes_de_capturas_api(arquivos, codigo_loterica, qtd_dezenas)
    if boloes:
        from boloes_modalidades import extrair_concurso_de_boloes, extrair_modalidade_de_boloes
        if not concurso or concurso == 'sem-concurso':
            concurso = extrair_concurso_de_boloes(boloes)
        mod = extrair_modalidade_de_boloes(boloes)
        if mod:
            mod_slug = mod.slug
    return consolidar_sessao(pasta_json, concurso, mod_slug, boloes)


def hashes_pagina(boloes: List[dict]) -> Set[str]:
    return {h for b in boloes if (h := _hash_de(b))}


def hashes_de_lista(boloes: List[dict]) -> Set[str]:
    """Todos os hash_bolao de uma lista (continuidade / deduplicação)."""
    return hashes_pagina(boloes)


def caminho_json_sessao(pasta_json: str, arquivo_base: str) -> str:
    """Caminho completo do JSON de sessão (sem extensão no arquivo_base)."""
    base = (arquivo_base or '').removesuffix('.json')
    return os.path.join(pasta_json, f'{base}.json')


def _concurso_norm(concurso: Any) -> str:
    return re.sub(r'\D', '', str(concurso or '')) or 'sem-concurso'


def localizar_arquivo_sessao_existente(
    pasta_json: str,
    arquivo_base: str = '',
    mod_slug: str = '',
    concurso: str = '',
) -> Tuple[Optional[str], List[dict]]:
    """
    Localiza o JSON de sessão já gravado para continuidade inteligente.
    Prioridade: nome exato → concurso+modalidade → maior arquivo boloes_*_{mod}.json.
    """
    candidatos: List[str] = []
    vistos: Set[str] = set()

    def _add(path: str) -> None:
        norm = os.path.normcase(os.path.abspath(path))
        if norm not in vistos:
            vistos.add(norm)
            candidatos.append(path)

    if arquivo_base:
        _add(caminho_json_sessao(pasta_json, arquivo_base))

    conc = _concurso_norm(concurso) if concurso else ''
    mod = re.sub(r'[^a-z0-9\-]+', '-', (mod_slug or '').lower()).strip('-')
    if conc and conc != 'sem-concurso' and mod:
        _add(caminho_json_sessao(pasta_json, f'boloes_{conc}_{mod}'))

    if mod:
        for path in glob.glob(os.path.join(pasta_json, f'boloes_*_{mod}.json')):
            if '_CONSOLIDADO' in os.path.basename(path):
                continue
            _add(path)

    melhor_path: Optional[str] = None
    melhor_dados: List[dict] = []
    conc_alvo = conc if conc and conc != 'sem-concurso' else ''

    for path in candidatos:
        if not os.path.isfile(path):
            continue
        dados = carregar_json_boloes(path)
        if not dados:
            continue
        if conc_alvo:
            base = os.path.basename(path)
            m = re.match(r'boloes_(\d+)_', base)
            if m and m.group(1) != conc_alvo:
                continue
        if len(dados) >= len(melhor_dados):
            melhor_path = path
            melhor_dados = dados

    return melhor_path, melhor_dados


def salvar_json_continuacao(
    path: str,
    boloes_sessao: List[dict],
) -> Tuple[List[dict], int, int]:
    """
    Continuidade inteligente: mescla bolões da sessão com o arquivo existente.
    Retorna (lista_final, qtd_novos, qtd_anteriores).
    Nunca apaga registros já armazenados; ignora duplicados por hash_bolao.
    """
    anteriores = carregar_json_boloes(path)
    total_anterior = len(anteriores)
    if not boloes_sessao:
        return anteriores, 0, total_anterior
    final, novos = mesclar_listas(anteriores, boloes_sessao)
    if final:
        salvar_json_boloes(path, final)
    return final, novos, total_anterior
