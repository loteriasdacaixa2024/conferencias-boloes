# -*- coding: utf-8 -*-
"""Converte JSON da API silce-servico-rest (Caixa) para o formato do extrator."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Set

from boloes_extrair_popup import MODALIDADES, gerar_hash_bolao, identificar_modalidade

_CHAVES_LISTA = (
    'content', 'lista', 'itens', 'boloes', 'resultado', 'data',
    'listaBoloes', 'boloesDisponiveis', 'registros', 'elements',
    'listaBolao', 'bolaoDisponivel', 'listaProdutos',
)


def _fmt_trevos(nums: Any) -> List[str]:
    out: List[str] = []
    for n in nums or []:
        try:
            out.append(str(int(n)))
        except (TypeError, ValueError):
            s = str(n).strip()
            if s:
                out.append(s)
    return out


def _fmt_dezenas(nums: Any, parser_slug: str = '') -> List[str]:
    out: List[str] = []
    for n in nums or []:
        try:
            iv = int(n)
            if parser_slug == 'lotomania':
                out.append(str(iv).zfill(2))
            elif parser_slug == 'super-sete':
                out.append(str(iv))
            else:
                out.append(f'{iv:02d}')
        except (TypeError, ValueError):
            s = str(n).strip()
            if s.isdigit():
                if parser_slug == 'super-sete':
                    out.append(s)
                else:
                    out.append(s.zfill(2) if len(s) <= 2 else s)
    return out


def _unwrap_payload(data: Any) -> Any:
    if not isinstance(data, dict):
        return data
    for chave in ('payload', 'dados', 'data', 'resultado'):
        inner = data.get(chave)
        if isinstance(inner, (dict, list)):
            return inner
    return data


def _cidade_uf(payload: dict) -> tuple[str, str, str]:
    mun = payload.get('municipioCota') or payload.get('municipio') or {}
    uf = payload.get('uf') or {}
    if isinstance(mun, dict):
        cidade = (mun.get('nome') or mun.get('descricao') or '').strip()
    else:
        cidade = str(mun or '').strip()
    sigla = ''
    if isinstance(uf, dict):
        sigla = (uf.get('sigla') or uf.get('nome') or '').strip()
    else:
        sigla = str(uf or '').strip()
    cidade_uf = f'{cidade} - {sigla}' if cidade and sigla else cidade or sigla
    return cidade, sigla, cidade_uf


def _parse_apostas_api(raw_apostas: Any, parser_slug: str = '') -> List[Dict[str, Any]]:
    apostas: List[Dict[str, Any]] = []
    if not isinstance(raw_apostas, list):
        return apostas
    for i, ap in enumerate(raw_apostas, 1):
        if not isinstance(ap, dict):
            continue
        dez = _fmt_dezenas(
            ap.get('dezenas') or ap.get('numeros') or ap.get('listaDezenas') or [],
            parser_slug,
        )
        if not dez and not ap.get('colunas'):
            continue
        num = ap.get('numero') or ap.get('indice') or ap.get('sequencial') or i
        try:
            num = int(num)
        except (TypeError, ValueError):
            num = i
        item: Dict[str, Any] = {
            'numero': num,
            'label': f'Aposta {num}',
            'dezenas': dez,
            'qtd_dezenas': len(dez),
        }
        trevos = _fmt_trevos(ap.get('trevos') or ap.get('listaTrevos'))
        if trevos:
            item['trevos'] = trevos
        colunas = ap.get('colunas') or ap.get('dezenasPorColuna')
        if isinstance(colunas, dict):
            item['colunas'] = {
                str(k): _fmt_dezenas(v, 'super-sete') for k, v in colunas.items()
            }
        elif isinstance(colunas, list):
            item['colunas'] = {
                str(j + 1): _fmt_dezenas(col, 'super-sete') for j, col in enumerate(colunas)
            }
        apostas.append(item)
    apostas.sort(key=lambda a: a['numero'])
    return apostas


def _extrair_dados_especiais_api(payload: dict, apostas: List[Dict[str, Any]], parser_slug: str) -> Dict[str, Any]:
    esp: Dict[str, Any] = {}

    time_nome = (
        payload.get('nomeTimeCoracao') or payload.get('timeCoracao')
        or payload.get('descricaoTimeCoracao')
    )
    if isinstance(time_nome, dict):
        time_nome = time_nome.get('nome') or time_nome.get('descricao')
    if time_nome:
        esp['time_coracao'] = str(time_nome).strip()

    mes = payload.get('mesSorte') or payload.get('numeroMesSorte') or payload.get('mesDaSorte')
    if isinstance(mes, dict):
        mes = mes.get('nome') or mes.get('numero') or mes.get('descricao')
    if mes is not None and str(mes).strip():
        esp['mes_sorte'] = str(mes).strip()

    trevos: List[str] = []
    for ap in apostas:
        trevos.extend(ap.get('trevos') or [])
    if not trevos:
        trevos = _fmt_trevos(payload.get('trevos') or payload.get('listaTrevos'))
    if trevos:
        esp['trevos'] = trevos

    if parser_slug == 'super-sete':
        cols: Dict[str, List[str]] = {}
        for ap in apostas:
            for k, v in (ap.get('colunas') or {}).items():
                cols[str(k)] = v
        if cols:
            esp['colunas'] = cols

    return esp


def _texto_modalidade_payload(payload: dict) -> str:
    """Lê nome da modalidade direto do JSON da API."""
    for chave in (
        'nomeModalidade', 'modalidade', 'descricaoModalidade',
        'tipoModalidade', 'nomeProduto', 'descricaoProduto',
    ):
        val = payload.get(chave)
        if isinstance(val, dict):
            val = val.get('nome') or val.get('descricao') or val.get('label') or ''
        if val and str(val).strip() and str(val).upper() not in ('BOLAO', 'BOLÃO'):
            return str(val).strip()
    return ''


def _resolver_modalidade_bolao(
    payload: dict,
    parser_slug_hint: str = '',
    log_fn=None,
) -> tuple[str, str, str]:
    """
    Retorna (catalog_slug, parser_slug, label).
    Prioridade: API Caixa (MEGA_SENA…) > terminal escolhido > trevos > fallback.
    """
    from boloes_modalidades import TODAS_MODALIDADES, resolver_modalidade_api, resolver_modalidade_menu

    modalidade_txt = _texto_modalidade_payload(payload)

    if modalidade_txt:
        mod = resolver_modalidade_api(modalidade_txt)
        if mod:
            if parser_slug_hint and log_fn:
                hint_mod = next(
                    (m for m in TODAS_MODALIDADES
                     if m.slug == parser_slug_hint or m.parser_slug == parser_slug_hint),
                    None,
                )
                if hint_mod and hint_mod.slug != mod.slug:
                    log_fn(
                        f'  [API] Modalidade {mod.label} ({modalidade_txt}) '
                        f'— terminal tinha {hint_mod.label}, usando API.'
                    )
            return mod.slug, mod.parser_slug, mod.label

    if parser_slug_hint:
        for m in TODAS_MODALIDADES:
            if m.slug == parser_slug_hint or m.parser_slug == parser_slug_hint:
                if log_fn:
                    log_fn(f'  [TERMINAL] Modalidade: {m.label}')
                return m.slug, m.parser_slug, m.label

    if payload.get('trevos') or payload.get('listaTrevos'):
        for ap in payload.get('apostas') or []:
            if isinstance(ap, dict) and (ap.get('trevos') or ap.get('listaTrevos')):
                mod = resolver_modalidade_menu('mais-milionaria') or resolver_modalidade_menu('9')
                if mod:
                    return mod.slug, mod.parser_slug, mod.label

    parser_slug = _resolver_parser_slug(payload, modalidade_txt)
    mod = resolver_modalidade_api(modalidade_txt) or resolver_modalidade_menu(parser_slug)
    if mod:
        return mod.slug, mod.parser_slug, mod.label
    cfg = MODALIDADES.get(parser_slug)
    label = cfg.label if cfg else (modalidade_txt or 'BOLAO')
    return parser_slug, parser_slug, label


def _resolver_parser_slug(payload: dict, modalidade_txt: str) -> str:
    from boloes_modalidades import CONCURSOS_ESPECIAIS, MODALIDADES_MENU

    blob = (modalidade_txt or '') + json.dumps(payload, ensure_ascii=False)[:800]
    norm = blob.upper()
    for mod in CONCURSOS_ESPECIAIS:
        for kw in mod.keywords:
            if kw.upper() in norm or mod.label.upper() in norm:
                return mod.parser_slug
    for mod in MODALIDADES_MENU:
        if mod.label.upper() in norm:
            return mod.parser_slug
    mod_u = (modalidade_txt or '').upper()
    for slug, cfg in MODALIDADES.items():
        if cfg.label.upper() in mod_u or slug.replace('-', ' ').upper() in mod_u:
            return slug
    return identificar_modalidade(blob).slug


def _loterica_codigo(payload: dict) -> str:
    for chave in ('loterica', 'codigoLoterica', 'numeroLoterica', 'codLoterica'):
        val = payload.get(chave)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ''


def _parece_bolao(payload: dict) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get('apostas'):
        return True
    if _loterica_codigo(payload) and (
        payload.get('nomeLoterica') or payload.get('nomeRazaoSocial')
    ):
        return True
    return False


def parse_bolao_api(
    data: Any,
    fonte: str = 'api',
    parser_slug_hint: str = '',
    log_fn=None,
) -> Optional[Dict[str, Any]]:
    """Converte um objeto JSON de bolão para o dict do extrator."""
    if not isinstance(data, dict):
        return None

    payload = _unwrap_payload(data)
    if not isinstance(payload, dict):
        payload = data

    catalog_slug, parser_slug, modalidade_label = _resolver_modalidade_bolao(
        payload, parser_slug_hint, log_fn,
    )
    apostas = _parse_apostas_api(payload.get('apostas'), parser_slug)
    cod_lot = _loterica_codigo(payload)

    if not apostas and not cod_lot:
        return None

    cidade, uf, cidade_uf = _cidade_uf(payload)
    vr_cota = (
        payload.get('vrUltimaCotaComTarifa') or payload.get('vrCotaComTarifa')
        or payload.get('valorCota')
    )
    tarifa = payload.get('vrTarifaServicoUltimaCota') or payload.get('vrTarifaServico')

    dados: Dict[str, Any] = {
        'fonte': fonte,
        'modalidade': modalidade_label,
        'modalidade_slug': catalog_slug,
        'parser_slug': parser_slug,
        'nome_loterica': (
            payload.get('nomeLoterica') or payload.get('nomeRazaoSocial')
            or payload.get('razaoSocial') or ''
        ).strip(),
        'codigo_loterica': cod_lot,
        'cidade': cidade,
        'uf': uf,
        'cidade_uf': cidade_uf,
        'concurso': str(payload.get('concurso') or payload.get('numeroConcurso') or ''),
        'valor_cota': str(vr_cota) if vr_cota is not None else '',
        'total_cotas': str(
            payload.get('qtdCotaTotal') or payload.get('qtdCotaDigital') or '',
        ),
        'cotas_disponiveis': payload.get('qtdCotaDisponivel'),
        'tarifa_servico': str(tarifa) if tarifa is not None else '',
        'apostas': apostas,
        'total_apostas': len(apostas),
        'jogos': [a['dezenas'] for a in apostas],
        'total_jogos': len(apostas),
        'dezenas_aposta': apostas[0]['dezenas'] if apostas else [],
        'qtd_dezenas_aposta_1': len(apostas[0]['dezenas']) if apostas else 0,
        'dezenas_bolao': sorted({d for a in apostas for d in a['dezenas']}),
        'dados_especiais': _extrair_dados_especiais_api(payload, apostas, parser_slug),
        'id_bolao_api': (
            payload.get('id') or payload.get('idProdutoBolao')
            or payload.get('codigoBolao') or payload.get('hashBolao')
        ),
        'texto_completo': json.dumps(payload, ensure_ascii=False)[:8000],
    }

    dados['hash_bolao'] = gerar_hash_bolao(dados)
    return dados


def extrair_todos_boloes_json(
    data: Any,
    somente_com_dezenas: bool = True,
    parser_slug_hint: str = '',
) -> List[Dict[str, Any]]:
    """Varre JSON aninhado (lista recuperar-boloes-disponiveis, detalhar-bolao, etc.)."""
    saida: List[Dict[str, Any]] = []
    vistos: Set[str] = set()

    def registrar(obj: dict) -> None:
        b = parse_bolao_api(obj, parser_slug_hint=parser_slug_hint, log_fn=print)
        if not b:
            return
        if somente_com_dezenas and not b.get('apostas'):
            return
        h = b.get('hash_bolao')
        if not h or h in vistos:
            return
        vistos.add(h)
        saida.append(b)

    def walk(node: Any, depth: int = 0) -> None:
        if depth > 14:
            return
        if isinstance(node, dict):
            if _parece_bolao(node):
                registrar(node)
            for val in node.values():
                walk(val, depth + 1)
        elif isinstance(node, list):
            for item in node:
                walk(item, depth + 1)

    walk(_unwrap_payload(data))
    walk(data)
    return saida


def parse_lista_boloes_api(data: Any, parser_slug_hint: str = '') -> List[Dict[str, Any]]:
    """Lista paginada — várias estruturas possíveis da Caixa."""
    encontrados = extrair_todos_boloes_json(data, somente_com_dezenas=True, parser_slug_hint=parser_slug_hint)
    if encontrados:
        return encontrados

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        root = _unwrap_payload(data)
        if isinstance(root, list):
            items = root
        else:
            items = None
            if isinstance(root, dict):
                for chave in _CHAVES_LISTA:
                    if isinstance(root.get(chave), list):
                        items = root[chave]
                        break
            if items is None and isinstance(data, dict):
                for chave in _CHAVES_LISTA:
                    if isinstance(data.get(chave), list):
                        items = data[chave]
                        break
            if items is None:
                items = [root] if isinstance(root, dict) else []
    else:
        return []

    saida: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            b = parse_bolao_api(item, parser_slug_hint=parser_slug_hint)
            if b and b.get('apostas'):
                saida.append(b)
    return saida
