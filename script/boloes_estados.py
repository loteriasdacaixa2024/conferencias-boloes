# -*- coding: utf-8 -*-
"""Estados (UF) para varredura automática de bolões — ordem SP primeiro."""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class EstadoUF:
    sigla: str
    nome: str
    codigo_ibge: int

    @property
    def slug(self) -> str:
        return self.sigla.lower()


# Códigos IBGE (mesmos usados pela API Caixa: codigoUF / idUF)
_TODOS: List[EstadoUF] = [
    EstadoUF('AC', 'ACRE', 12),
    EstadoUF('AL', 'ALAGOAS', 27),
    EstadoUF('AM', 'AMAZONAS', 13),
    EstadoUF('AP', 'AMAPA', 16),
    EstadoUF('BA', 'BAHIA', 29),
    EstadoUF('CE', 'CEARA', 23),
    EstadoUF('DF', 'DISTRITO FEDERAL', 53),
    EstadoUF('ES', 'ESPIRITO SANTO', 32),
    EstadoUF('GO', 'GOIAS', 52),
    EstadoUF('MA', 'MARANHAO', 21),
    EstadoUF('MG', 'MINAS GERAIS', 31),
    EstadoUF('MS', 'MATO GROSSO DO SUL', 50),
    EstadoUF('MT', 'MATO GROSSO', 51),
    EstadoUF('PA', 'PARA', 15),
    EstadoUF('PB', 'PARAIBA', 25),
    EstadoUF('PE', 'PERNAMBUCO', 26),
    EstadoUF('PI', 'PIAUI', 22),
    EstadoUF('PR', 'PARANA', 41),
    EstadoUF('RJ', 'RIO DE JANEIRO', 33),
    EstadoUF('RN', 'RIO GRANDE DO NORTE', 24),
    EstadoUF('RO', 'RONDONIA', 11),
    EstadoUF('RR', 'RORAIMA', 14),
    EstadoUF('RS', 'RIO GRANDE DO SUL', 43),
    EstadoUF('SC', 'SANTA CATARINA', 42),
    EstadoUF('SE', 'SERGIPE', 28),
    EstadoUF('SP', 'SAO PAULO', 35),
    EstadoUF('TO', 'TOCANTINS', 17),
]

_POR_SIGLA = {e.sigla: e for e in _TODOS}


def estados_varredura(inicio_sigla: str = 'SP') -> List[EstadoUF]:
    """SP primeiro; demais UFs em ordem alfabética de sigla."""
    inicio = (inicio_sigla or 'SP').upper().strip()
    primeiro = _POR_SIGLA.get(inicio)
    resto = sorted([e for e in _TODOS if e.sigla != inicio], key=lambda x: x.sigla)
    if primeiro:
        return [primeiro] + resto
    return resto


def resolver_estado(termo: str) -> Optional[EstadoUF]:
    t = (termo or '').strip().upper()
    if not t:
        return None
    if t in _POR_SIGLA:
        return _POR_SIGLA[t]
    for e in _TODOS:
        if t in e.nome or e.nome.startswith(t):
            return e
    return None


def imprimir_fila_estados(inicio: str = 'SP') -> None:
    fila = estados_varredura(inicio)
    print('\n  Varredura de estados (ordem):')
    print('  ' + ' → '.join(e.sigla for e in fila))
    print(f'  Total: {len(fila)} UFs | Início: {fila[0].nome} ({fila[0].sigla})')
