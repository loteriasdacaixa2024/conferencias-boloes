# -*- coding: utf-8 -*-
"""
Captura chamadas XHR da API de bolões (silce-servico-rest) enquanto você usa o site.

Uso:
  1. python conferencias-boloes/script/boloes_capturar_api.py
  2. Faça login, aplique filtro, abra 1 popup de bolão, mude de página
  3. Volte ao terminal e pressione ENTER
  4. Veja o arquivo gerado em conferencias-boloes/api_capturada_*.json

Objetivo: descobrir URLs exatas (lista + detalhe) para extrair via JSON em vez de popup.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.edge.options import Options as EdgeOptions

URL_BOLOES = 'https://www.loteriasonline.caixa.gov.br/silce-web/#/bolao-caixa'
API_PREFIX = 'silce-servico-rest'
DEST_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _criar_driver():
    opts = EdgeOptions()
    opts.set_capability('ms:loggingPrefs', {'performance': 'ALL', 'browser': 'ALL'})
    opts.add_argument('--disable-gpu')
    return webdriver.Edge(options=opts)


def _extrair_requisicoes(logs) -> list[dict]:
    vistos: set[str] = set()
    saida: list[dict] = []

    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
        except (KeyError, json.JSONDecodeError, TypeError):
            continue
        if msg.get('method') != 'Network.responseReceived':
            continue

        params = msg.get('params', {})
        resp = params.get('response', {})
        url = resp.get('url', '')
        if API_PREFIX not in url:
            continue

        mime = (resp.get('mimeType') or '').lower()
        if 'json' not in mime and 'javascript' not in mime and 'text' not in mime:
            continue

        req_id = params.get('requestId', '')
        chave = f"{resp.get('status')}|{url}"
        if chave in vistos:
            continue
        vistos.add(chave)

        parsed = urlparse(url)
        partes = [p for p in parsed.path.split('/') if p]
        recurso = partes[-2] if len(partes) >= 2 else (partes[-1] if partes else '')
        saida.append({
            'url': url,
            'status': resp.get('status'),
            'mimeType': resp.get('mimeType'),
            'recurso': recurso,
            'requestId': req_id,
        })

    return saida


def _agrupar_por_recurso(requisicoes: list[dict]) -> dict:
    grupos: dict[str, list] = {}
    for r in requisicoes:
        k = r.get('recurso') or 'outros'
        grupos.setdefault(k, []).append(r['url'])
    return {k: sorted(set(v)) for k, v in grupos.items()}


def main():
    print('=' * 60)
    print('  CAPTURADOR DE API — Bolões Caixa (silce-servico-rest)')
    print('=' * 60)
    print('\n1. Edge abrirá o site de bolões')
    print('2. Faça LOGIN')
    print('3. Aplique filtro (lotérica + dezenas + Aplicar)')
    print('4. Abra 1 popup "Detalhes" de um bolão')
    print('5. (Opcional) Clique Seguinte para página 2')
    print('6. Volte aqui e pressione ENTER\n')

    driver = _criar_driver()
    driver.get(URL_BOLOES)

    input('>>> ENTER quando terminar de navegar no site... ')

    logs = driver.get_log('performance')
    requisicoes = _extrair_requisicoes(logs)
    grupos = _agrupar_por_recurso(requisicoes)

    amostras: list[dict] = []
    for req in requisicoes[:15]:
        body = None
        try:
            body = driver.execute_cdp_cmd('Network.getResponseBody', {
                'requestId': req['requestId'],
            })
            texto = body.get('body', '')
            if body.get('base64Encoded'):
                import base64
                texto = base64.b64decode(texto).decode('utf-8', errors='replace')
            req['body_preview'] = texto[:4000]
            if len(texto) > 4000:
                req['body_truncado'] = True
            amostras.append(req)
        except Exception as exc:
            req['body_erro'] = str(exc)
            amostras.append(req)

    resultado = {
        'capturado_em': datetime.now().isoformat(),
        'total_requisicoes_api': len(requisicoes),
        'base_api': f'https://www.loteriasonline.caixa.gov.br/{API_PREFIX}/rest/v1/',
        'urls_por_recurso': grupos,
        'todas_urls': [r['url'] for r in requisicoes],
        'amostras_resposta': amostras,
        'dica': {
            'detalhe_popup': 'Geralmente GET .../rest/v1/bolao/{id_criptografado}',
            'lista': 'Procure URL POST/GET com pesquisa, consulta, listar ou paginação',
            'auth': 'Requer cookies de sessão do login (JSESSIONID etc.)',
        },
    }

    arquivo = os.path.join(
        DEST_DIR,
        f"api_capturada_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
    )
    with open(arquivo, 'w', encoding='utf-8') as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f'\n  Requisições API capturadas: {len(requisicoes)}')
    print('  Recursos encontrados:')
    for nome, urls in grupos.items():
        print(f'    - {nome}: {len(urls)} URL(s)')
        for u in urls[:3]:
            print(f'        {u[:100]}...' if len(u) > 100 else f'        {u}')
    print(f'\n  Arquivo salvo: {arquivo}')
    print('\n  Abra o JSON e veja "amostras_resposta" — é o JSON do popup/lista.')
    print('  Feche o navegador quando quiser.')
    input('\n>>> ENTER para fechar o Edge... ')
    driver.quit()


if __name__ == '__main__':
    main()
