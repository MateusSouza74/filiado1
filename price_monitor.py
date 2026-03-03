"""
price_monitor.py - Monitoramento e rastreamento de preços.

Responsabilidades:
  - Tentar extrair o preço atual de uma URL via scraping leve
  - Comparar com preço anterior registrado
  - Detectar quedas de preço para alertas
  - Persistir histórico de preços

Nota: Scraping de preço é best-effort. Sites com proteção anti-bot
podem falhar — o bot continua funcionando sem o preço atualizado.
"""

import re
from typing import Optional

import requests

from logger import get_logger
from utils import registrar_preco

log = get_logger(__name__)

# Headers simulando browser real para evitar bloqueios básicos
HEADERS_SCRAPING = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Timeout de scraping (segundos)
SCRAPING_TIMEOUT = 10

# Limiar de queda de preço para considerar "oferta ativa" (%)
LIMIAR_QUEDA_PERCENTUAL = 5.0


# ==============================================================================
# 🔍 SCRAPERS POR MARKETPLACE
# ==============================================================================

def _scrape_amazon(url: str) -> Optional[float]:
    """
    Tenta extrair preço da Amazon via HTML.

    Amazon tem proteção forte — funciona de forma intermitente.
    Em produção, considere usar a API Product Advertising.
    """
    try:
        resp = requests.get(url, headers=HEADERS_SCRAPING, timeout=SCRAPING_TIMEOUT)
        html = resp.text

        # Padrões comuns de preço na Amazon BR
        padroes = [
            r'"priceAmount":\s*([\d.]+)',
            r'class="a-price-whole"[^>]*>([0-9.,]+)',
            r'"price":\s*"R\$\s*([\d.,]+)"',
        ]

        for padrao in padroes:
            match = re.search(padrao, html)
            if match:
                valor_str = match.group(1).replace(".", "").replace(",", ".")
                return float(valor_str)

    except Exception as e:
        log.debug(f"[PRICE/AMAZON] Falha no scraping: {e}")

    return None


def _scrape_mercadolivre(url: str) -> Optional[float]:
    """Tenta extrair preço do Mercado Livre via HTML."""
    try:
        resp = requests.get(url, headers=HEADERS_SCRAPING, timeout=SCRAPING_TIMEOUT)
        html = resp.text

        padroes = [
            r'"price":\s*([\d.]+)',
            r'class="andes-money-amount__fraction"[^>]*>([0-9.]+)',
            r'"amount":\s*([\d.]+)',
        ]

        for padrao in padroes:
            match = re.search(padrao, html)
            if match:
                valor_str = match.group(1).replace(".", "").replace(",", ".")
                return float(valor_str)

    except Exception as e:
        log.debug(f"[PRICE/ML] Falha no scraping: {e}")

    return None


# ==============================================================================
# 🎯 DISPATCHER DE PREÇO
# ==============================================================================

_SCRAPERS = {
    "amazon.com": _scrape_amazon,
    "mercadolivre.com": _scrape_mercadolivre,
    "mercadolibre.com": _scrape_mercadolivre,
}


def consultar_preco_online(url: str, dominio: str) -> Optional[float]:
    """
    Tenta obter o preço atual de um produto online.

    Args:
        url: URL do produto (já desencurtada).
        dominio: Domínio identificado pelo parser.

    Returns:
        Preço float ou None se não conseguiu extrair.
    """
    for dominio_chave, scraper_fn in _SCRAPERS.items():
        if dominio_chave in dominio:
            log.debug(f"[PRICE] Consultando preço de {dominio}...")
            preco = scraper_fn(url)
            if preco:
                log.info(f"[PRICE] Preço encontrado: R$ {preco:,.2f} em {dominio}")
            return preco

    log.debug(f"[PRICE] Sem scraper configurado para '{dominio}'.")
    return None


# ==============================================================================
# 📊 ANÁLISE DE VARIAÇÃO
# ==============================================================================

def analisar_variacao_preco(
    link_id: str,
    preco_novo: float,
) -> dict:
    """
    Registra o preço e analisa se houve variação relevante.

    Args:
        link_id: Identificador único do produto.
        preco_novo: Preço atual capturado.

    Returns:
        Dict com:
          - preco_anterior: float ou None
          - variacao_percentual: float ou None
          - houve_queda: bool
          - houve_alta: bool
          - texto_variacao: str formatado para exibição
    """
    preco_anterior = registrar_preco(link_id, preco_novo)

    resultado = {
        "preco_anterior": preco_anterior,
        "variacao_percentual": None,
        "houve_queda": False,
        "houve_alta": False,
        "texto_variacao": "",
    }

    if preco_anterior is None:
        resultado["texto_variacao"] = "📊 Primeiro registro de preço"
        return resultado

    if preco_anterior == 0:
        return resultado

    variacao = ((preco_novo - preco_anterior) / preco_anterior) * 100
    resultado["variacao_percentual"] = round(variacao, 2)

    if variacao <= -LIMIAR_QUEDA_PERCENTUAL:
        resultado["houve_queda"] = True
        resultado["texto_variacao"] = (
            f"📉 Preço CAIU {abs(variacao):.1f}% "
            f"(era R$ {preco_anterior:,.2f})".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        log.info(f"[PRICE] Queda detectada: {variacao:.1f}% para {link_id[:50]}")

    elif variacao >= LIMIAR_QUEDA_PERCENTUAL:
        resultado["houve_alta"] = True
        resultado["texto_variacao"] = (
            f"📈 Preço SUBIU {variacao:.1f}% "
            f"(era R$ {preco_anterior:,.2f})".replace(",", "X").replace(".", ",").replace("X", ".")
        )
        log.info(f"[PRICE] Alta detectada: +{variacao:.1f}% para {link_id[:50]}")

    else:
        resultado["texto_variacao"] = f"↔️ Preço estável ({variacao:+.1f}%)"

    return resultado
