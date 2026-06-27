# -*- coding: utf-8 -*-
"""
Extração universal de popup de bolão — Caixa (Selenium).

Modalidades oficiais (apenas 9 — sem Federal e sem Loteca):
  Mega-Sena, Quina, Lotofácil, Lotomania, Timemania, Dia de Sorte,
  Super Sete, Dupla Sena, +Milionária.

Captura exatamente o que o popup exibe, sem assumir quantidade fixa de dezenas.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

MODALIDADES_OFICIAIS: Tuple[str, ...] = (
    'mega-sena', 'quina', 'lotofacil', 'lotomania', 'timemania',
    'dia-de-sorte', 'super-sete', 'dupla-sena', 'mais-milionaria',
)

_RE_APOSTA_NUM = re.compile(r'^(?:jogo|aposta)\s*(\d+)\b', re.I)
_RE_NUM = re.compile(r'\b(\d{1,2})\b')
_RE_DEZENAS_2D = re.compile(r'\b(\d{2})\b')
_RE_SUPER_SETE = re.compile(r'\b(\d)\b')
_RE_COLUNA = re.compile(r'(?:coluna|col\.?)\s*(\d)', re.I)

_CABECALHOS_FIM = (
    'nome da lot', 'cidade', 'valor da cota', 'tarifa', 'concurso',
    'quantidade', 'cotas dispon', 'cotas rest', 'total de cota', 'total de cotas',
    'fechar', 'comprar', 'voltar', 'valor total', 'disponível', 'disponivel',
    'time do cor', 'mês da sorte', 'mes da sorte', 'trevo', 'lotérica', 'loterica',
)

# Linhas de metadado — nunca viram dezenas
_META_NUM_SKIP = (
    'r$', 'cota', 'tarifa', 'concurso', 'quantidade', 'dispon', 'restant',
    'nome', 'cidade', 'lotérica', 'loterica', 'tarifa', 'serviço', 'servico',
)


def _regex_dezenas(cfg: ConfigModalidade) -> re.Pattern[str]:
    if cfg.slug == 'lotomania':
        return _RE_NUM
    if cfg.slug == 'super-sete':
        return _RE_SUPER_SETE
    return _RE_DEZENAS_2D


def _linha_metadado(linha: str) -> bool:
    ll = (linha or '').lower()
    return any(x in ll for x in _META_NUM_SKIP)


def _linha_indice_aposta(linha: str, aposta_num: Optional[int]) -> bool:
    """Popup Caixa às vezes quebra 'Aposta 1' em duas linhas — ignora o índice solto."""
    if aposta_num is None:
        return False
    s = (linha or '').strip()
    return s == str(aposta_num) or s == str(aposta_num).zfill(2)


@dataclass(frozen=True)
class ConfigModalidade:
    slug: str
    label: str
    min_val: int
    max_val: int
    min_dez: int
    max_dez: int
    keywords: Tuple[str, ...]


MODALIDADES: Dict[str, ConfigModalidade] = {
    'mega-sena': ConfigModalidade('mega-sena', 'Mega-Sena', 1, 60, 6, 20,
                                  ('mega-sena', 'mega sena')),
    'quina': ConfigModalidade('quina', 'Quina', 1, 80, 5, 15,
                              ('quina de sao joao', 'quina de são joão', 'quina')),
    'lotofacil': ConfigModalidade('lotofacil', 'Lotofácil', 1, 25, 15, 20,
                                  ('lotofacil', 'lotofácil', 'independencia', 'independência')),
    'lotomania': ConfigModalidade('lotomania', 'Lotomania', 0, 99, 50, 50,
                                  ('lotomania',)),
    'timemania': ConfigModalidade('timemania', 'Timemania', 1, 80, 10, 10,
                                  ('timemania',)),
    'dia-de-sorte': ConfigModalidade('dia-de-sorte', 'Dia de Sorte', 1, 31, 7, 15,
                                     ('dia de sorte',)),
    'super-sete': ConfigModalidade('super-sete', 'Super Sete', 0, 9, 7, 21,
                                   ('super sete', 'supersete')),
    'dupla-sena': ConfigModalidade('dupla-sena', 'Dupla Sena', 1, 50, 6, 15,
                                  ('dupla sena', 'dupla de pascoa', 'dupla de páscoa')),
    'mais-milionaria': ConfigModalidade('mais-milionaria', '+Milionária', 1, 50, 6, 12,
                                        ('milionaria', 'milionária', '+milion')),
}


def _norm(texto: str) -> str:
    if not texto:
        return ''
    t = unicodedata.normalize('NFD', texto)
    t = ''.join(c for c in t if unicodedata.category(c) != 'Mn')
    return re.sub(r'\s+', ' ', t.lower().strip())


def identificar_modalidade(texto: str) -> ConfigModalidade:
    blob = _norm(texto)
    if '+milion' in blob or 'mais milion' in blob:
        return MODALIDADES['mais-milionaria']
    if 'quina de sao joao' in blob or 'quina são joão' in blob:
        return MODALIDADES['quina']
    candidatos: List[Tuple[int, ConfigModalidade]] = []
    for cfg in MODALIDADES.values():
        for kw in cfg.keywords:
            nk = _norm(kw)
            if nk and nk in blob:
                candidatos.append((len(nk), cfg))
    if candidatos:
        candidatos.sort(key=lambda x: -x[0])
        return candidatos[0][1]
    return MODALIDADES['quina']


def _dedupe_ordem(nums: List[str]) -> List[str]:
    vistos = set()
    out: List[str] = []
    for n in nums:
        if n not in vistos:
            vistos.add(n)
            out.append(n)
    return out


def parse_numeros_linha(texto: str, cfg: ConfigModalidade) -> List[str]:
    """Extrai dezenas conforme faixa da modalidade (2 dígitos na Quina, etc.)."""
    if _linha_metadado(texto):
        return []

    nums: List[str] = []
    rx = _regex_dezenas(cfg)

    for m in rx.finditer(texto or ''):
        n = int(m.group(1))
        if cfg.min_val <= n <= cfg.max_val:
            if cfg.slug == 'lotomania':
                nums.append(str(n).zfill(2))
            elif cfg.slug == 'super-sete':
                nums.append(str(n))
            else:
                nums.append(str(n).zfill(2))
    return nums


def _linha_encerra_captura(linha: str) -> bool:
    ll = (linha or '').lower().strip()
    if not ll:
        return False
    return any(h in ll for h in _CABECALHOS_FIM)


def _montar_aposta(numero: int, label: str, dezenas: List[str], cfg: ConfigModalidade) -> Dict[str, Any]:
    dez = _dedupe_ordem(dezenas)
    if cfg.max_dez and len(dez) > cfg.max_dez:
        dez = dez[:cfg.max_dez]
    return {
        'numero': numero,
        'label': label or f'Aposta {numero}',
        'dezenas': dez,
        'qtd_dezenas': len(dez),
    }


def _adicionar_dezenas(dest: List[str], nums: List[str], cfg: ConfigModalidade) -> None:
    for n in nums:
        if cfg.max_dez and len(dest) >= cfg.max_dez:
            break
        dest.append(n)


def extrair_apostas_do_texto(linhas: List[str], cfg: ConfigModalidade) -> List[Dict[str, Any]]:
    """Aposta 1, 2, 3… — quantidade e dezenas exatamente como exibido."""
    apostas: List[Dict[str, Any]] = []
    atual_num: Optional[int] = None
    atual_label = ''
    atual_dezenas: List[str] = []
    capturando = False
    min_fallback = max(1, cfg.min_dez) if cfg.min_dez else 1

    def _fechar():
        nonlocal atual_num, atual_label, atual_dezenas, capturando
        if atual_num is not None and atual_dezenas:
            apostas.append(_montar_aposta(atual_num, atual_label, atual_dezenas, cfg))
        atual_num = None
        atual_label = ''
        atual_dezenas = []
        capturando = False

    for linha in linhas:
        m = _RE_APOSTA_NUM.match((linha or '').strip())
        if m:
            _fechar()
            atual_num = int(m.group(1))
            atual_label = (linha or '').strip()
            resto = re.sub(r'(?i)^(?:jogo|aposta)\s*\d+\s*', '', (linha or '').strip())
            if resto.strip():
                _adicionar_dezenas(atual_dezenas, parse_numeros_linha(resto, cfg), cfg)
            capturando = True
            continue

        if capturando:
            if _linha_encerra_captura(linha):
                _fechar()
                continue
            if _linha_indice_aposta(linha, atual_num):
                continue
            if cfg.max_dez and len(atual_dezenas) >= cfg.max_dez:
                _fechar()
                continue
            nums = parse_numeros_linha(linha, cfg)
            if nums:
                _adicionar_dezenas(atual_dezenas, nums, cfg)
                if cfg.max_dez and len(atual_dezenas) >= cfg.max_dez:
                    _fechar()
            elif atual_dezenas and not (linha or '').strip():
                _fechar()

    if atual_num is not None and atual_dezenas:
        apostas.append(_montar_aposta(atual_num, atual_label, atual_dezenas, cfg))

    if not apostas:
        blob = '\n'.join(linhas)
        partes = re.split(r'(?im)(?:^|\n)\s*(?:aposta|jogo)\s*(\d+)\b', blob)
        i = 1
        while i < len(partes) - 1:
            try:
                num = int(partes[i])
                corpo = partes[i + 1] if i + 1 < len(partes) else ''
                nums: List[str] = []
                for ln in corpo.split('\n'):
                    if _linha_encerra_captura(ln) or _linha_metadado(ln):
                        break
                    if _linha_indice_aposta(ln, num):
                        continue
                    nums.extend(parse_numeros_linha(ln, cfg))
                    if cfg.max_dez and len(nums) >= cfg.max_dez:
                        nums = nums[:cfg.max_dez]
                        break
                if len(nums) >= min_fallback:
                    apostas.append(_montar_aposta(num, f'Aposta {num}', nums, cfg))
            except (ValueError, TypeError):
                pass
            i += 2

    apostas.sort(key=lambda a: a['numero'])
    return apostas


def _valor_campo(linha: str, linhas: List[str], i: int) -> str:
    if ':' in linha:
        return linha.split(':', 1)[-1].strip()
    if i + 1 < len(linhas):
        return linhas[i + 1].strip()
    return ''


def _split_cidade_uf(raw: str) -> Tuple[str, str]:
    raw = (raw or '').strip()
    if '/' in raw:
        cidade, uf = raw.rsplit('/', 1)
        return cidade.strip(), uf.strip().upper()
    return raw, ''


def extrair_dados_especiais(linhas: List[str], cfg: ConfigModalidade) -> Dict[str, Any]:
    esp: Dict[str, Any] = {}

    if cfg.slug == 'timemania':
        for i, ln in enumerate(linhas):
            if 'time do cor' in ln.lower():
                esp['time_coracao'] = _valor_campo(ln, linhas, i)
                break

    if cfg.slug == 'dia-de-sorte':
        for i, ln in enumerate(linhas):
            ll = ln.lower()
            if 'mês da sorte' in ll or 'mes da sorte' in ll:
                esp['mes_sorte'] = _valor_campo(ln, linhas, i)
                break

    if cfg.slug == 'mais-milionaria':
        trevos: List[str] = []
        cfg_trevo = ConfigModalidade('t', 't', 1, 6, 1, 2, ('',))
        for ln in linhas:
            if 'trevo' in ln.lower():
                trevos.extend(parse_numeros_linha(ln, cfg_trevo))
        if trevos:
            esp['trevos'] = _dedupe_ordem(trevos)

    if cfg.slug == 'super-sete':
        colunas: Dict[str, List[str]] = {}
        for ln in linhas:
            m = _RE_COLUNA.search(ln)
            if m:
                col = m.group(1)
                nums = parse_numeros_linha(ln, cfg)
                if nums:
                    colunas[col] = nums
        if colunas:
            esp['colunas'] = colunas

    return esp


def assinatura_bolao(dados: Dict[str, Any]) -> str:
    """Assinatura para deduplicação: modalidade + concurso + apostas + especiais."""
    mod = (dados.get('modalidade') or 'BOLAO').upper().replace(' ', '-')
    partes = [mod, f"conc:{dados.get('concurso', '')}", f"ap:{dados.get('total_apostas', 0)}"]

    for ap in sorted(dados.get('apostas') or [], key=lambda x: x['numero']):
        partes.append(f"{ap['numero']}:{','.join(ap['dezenas'])}")

    esp = dados.get('dados_especiais') or {}
    if esp:
        partes.append('esp:' + json.dumps(esp, sort_keys=True, ensure_ascii=False))

    return '|'.join(partes)


def gerar_hash_bolao(dados: dict) -> str:
    raw = assinatura_bolao(dados)
    if not raw or raw.endswith('|ap:0'):
        raw = (dados.get('texto_completo') or '')[:2000]
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]


def parse_campos_popup(texto_popup: str) -> Dict[str, Any]:
    """JSON universal conforme especificação Caixa."""
    linhas = [l for l in (texto_popup or '').split('\n')]
    cfg = identificar_modalidade(texto_popup)

    dados: Dict[str, Any] = {
        'texto_completo': texto_popup,
        'modalidade': cfg.label,
        'modalidade_slug': cfg.slug,
        'nome_loterica': '',
        'cidade': '',
        'uf': '',
        'cidade_uf': '',
        'concurso': '',
        'valor_cota': '',
        'total_cotas': '',
        'tarifa_servico': '',
        'total_apostas': 0,
        'apostas': [],
        'dezenas_bolao': [],
        'assinatura_dezenas': '',
        'dados_especiais': {},
        'jogos': [],
        'total_jogos': 0,
    }

    for i, linha in enumerate(linhas):
        ll = linha.lower()
        if 'nome da lot' in ll:
            dados['nome_loterica'] = _valor_campo(linha, linhas, i)
        elif ll.startswith('cidade') or 'cidade/uf' in ll:
            raw = _valor_campo(linha, linhas, i)
            dados['cidade_uf'] = raw
            dados['cidade'], dados['uf'] = _split_cidade_uf(raw)
        elif 'valor da cota' in ll:
            dados['valor_cota'] = _valor_campo(linha, linhas, i)
        elif 'total de cota' in ll or 'quantidade de cota' in ll:
            dados['total_cotas'] = _valor_campo(linha, linhas, i)
        elif 'tarifa' in ll:
            dados['tarifa_servico'] = _valor_campo(linha, linhas, i)
        elif 'concurso' in ll and 'especial' not in ll:
            val = _valor_campo(linha, linhas, i)
            if val and not dados['concurso']:
                dados['concurso'] = val

    dados['dados_especiais'] = extrair_dados_especiais(linhas, cfg)

    apostas = extrair_apostas_do_texto(linhas, cfg)
    dados['apostas'] = apostas
    dados['total_apostas'] = len(apostas)
    dados['jogos'] = [a['dezenas'] for a in apostas]
    dados['total_jogos'] = len(apostas)
    dados['dezenas_bolao'] = sorted({n for a in apostas for n in a['dezenas']})
    dados['dezenas_aposta'] = apostas[0]['dezenas'] if apostas else []
    dados['qtd_dezenas_aposta_1'] = len(dados['dezenas_aposta'])

    dados['assinatura_dezenas'] = assinatura_bolao(dados)
    dados['hash_bolao'] = gerar_hash_bolao(dados)
    return dados


def extrair_jogos_do_texto(linhas: List[str]) -> List[List[str]]:
    cfg = identificar_modalidade('\n'.join(linhas))
    return [a['dezenas'] for a in extrair_apostas_do_texto(linhas, cfg)]


def assinatura_dezenas_apostas(apostas: List[Dict[str, Any]]) -> str:
    partes = []
    for ap in sorted(apostas, key=lambda x: x['numero']):
        partes.append(f"{ap['numero']}:{','.join(ap['dezenas'])}")
    return '|'.join(partes)
