"""
utils.py - Utilitários gerais do bot.

Responsabilidades:
  - Gerenciamento de histórico de links (deduplicação)
  - Funções auxiliares reutilizáveis
  - Criação de estrutura de diretórios de dados
"""

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from config import Config
from logger import get_logger

log = get_logger(__name__)


# ==============================================================================
# 📁 INICIALIZAÇÃO DE DIRETÓRIOS
# ==============================================================================

def garantir_estrutura_dados() -> None:
    """Cria os diretórios e arquivos de dados necessários se não existirem."""
    Path(Config.DATA_DIR).mkdir(parents=True, exist_ok=True)
    Path("logs").mkdir(exist_ok=True)

    for arquivo in [Config.HISTORICO_FILE, Config.PRICE_HISTORY_FILE]:
        if not os.path.exists(arquivo):
            _salvar_json(arquivo, {})
            log.debug(f"Arquivo criado: {arquivo}")


# ==============================================================================
# 🔧 HELPERS DE JSON
# ==============================================================================

def _carregar_json(caminho: str) -> dict:
    """Lê um arquivo JSON com tratamento de erro."""
    try:
        with open(caminho, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.warning(f"Não foi possível carregar {caminho}: {e}. Retornando vazio.")
        return {}


def _salvar_json(caminho: str, dados: dict) -> None:
    """Salva um dicionário como JSON com formatação legível."""
    with open(caminho, "w", encoding="utf-8") as f:
        json.dump(dados, f, indent=4, ensure_ascii=False)


# ==============================================================================
# 🚫 SISTEMA DE DEDUPLICAÇÃO
# ==============================================================================

def _limpar_duplicatas_expiradas(dados: dict) -> dict:
    """Remove entradas do histórico que já passaram do TTL configurado."""
    agora = datetime.now()
    ttl = timedelta(hours=Config.DUPLICATA_TTL_HORAS)

    dados_validos = {}
    for link, timestamp_str in dados.items():
        try:
            ts = datetime.fromisoformat(timestamp_str)
            if agora - ts < ttl:
                dados_validos[link] = timestamp_str
        except ValueError:
            log.warning(f"Timestamp inválido ignorado no histórico: {timestamp_str}")

    removidos = len(dados) - len(dados_validos)
    if removidos > 0:
        log.debug(f"Histórico: {removidos} entradas expiradas removidas.")

    return dados_validos


def ja_foi_postado(link_id: str) -> bool:
    """
    Verifica se um link já foi postado recentemente.

    Args:
        link_id: Identificador único do link (URL sem query params).

    Returns:
        True se o link já foi postado dentro do TTL, False caso contrário.
    """
    dados = _carregar_json(Config.HISTORICO_FILE)
    dados = _limpar_duplicatas_expiradas(dados)

    if link_id in dados:
        ts = datetime.fromisoformat(dados[link_id])
        log.info(f"[DUPLICATA] Link já postado em {ts.strftime('%d/%m %H:%M')}: {link_id[:60]}...")
        return True

    return False


def registrar_postagem(link_id: str) -> None:
    """
    Registra um link como já postado no histórico.

    Args:
        link_id: Identificador único do link.
    """
    dados = _carregar_json(Config.HISTORICO_FILE)
    dados = _limpar_duplicatas_expiradas(dados)
    dados[link_id] = datetime.now().isoformat()
    _salvar_json(Config.HISTORICO_FILE, dados)
    log.debug(f"[HISTÓRICO] Link registrado: {link_id[:60]}...")


def total_postagens_historico() -> int:
    """Retorna o número de links ativos no histórico."""
    dados = _carregar_json(Config.HISTORICO_FILE)
    dados = _limpar_duplicatas_expiradas(dados)
    return len(dados)


# ==============================================================================
# 🔗 HELPERS DE URL
# ==============================================================================

_PARAMS_TRACKING = frozenset({
    # UTM padrão
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    # Rastreamento de afiliados / ads
    "ref", "ref_", "tag", "linkcode", "camp", "creative", "fbclid",
    "gclid", "msclkid", "af_sub", "af_sub1", "af_sub2", "source_id",
    # Amazon específicos
    "linkcode", "creativeasin", "psc",
    # Outros comuns
    "mc_cid", "mc_eid", "_ga", "igshid",
})


def normalizar_link_id(url: str) -> str:
    """
    Gera ID único de um link para deduplicação.

    Remove:
      - Parâmetros UTM e tracking (utm_*, fbclid, gclid, ref, tag, etc.)
      - Fragmentos (#)
      - Barra final

    Mantém parâmetros que identificam o produto (ex: ASIN na Amazon).

    Ex: 'https://amzn.to/abc123?tag=x&utm_source=y' -> 'https://amzn.to/abc123'
    Ex: 'https://amazon.com.br/dp/B0ABC?th=1&tag=x'  -> 'https://amazon.com.br/dp/B0ABC?th=1'
    """
    from urllib.parse import urlparse, urlencode, parse_qs

    try:
        parsed = urlparse(url)
        params_originais = parse_qs(parsed.query, keep_blank_values=False)
        params_limpos = {
            k: v for k, v in params_originais.items()
            if k.lower() not in _PARAMS_TRACKING
        }
        query_limpa = urlencode(params_limpos, doseq=True)
        url_limpa = parsed._replace(query=query_limpa, fragment="").geturl()
        return url_limpa.rstrip("/")
    except Exception:
        # Fallback seguro se o parsing falhar
        return url.split("?")[0].split("#")[0].rstrip("/")


# ==============================================================================
# 🗂️ HISTÓRICO DE PREÇOS
# ==============================================================================

def carregar_historico_precos() -> dict:
    """Carrega o histórico de preços de todos os produtos monitorados."""
    return _carregar_json(Config.PRICE_HISTORY_FILE)


def salvar_historico_precos(dados: dict) -> None:
    """Persiste o histórico de preços."""
    _salvar_json(Config.PRICE_HISTORY_FILE, dados)


def registrar_preco(link_id: str, preco: float) -> Optional[float]:
    """
    Registra o preço atual de um produto e retorna o preço anterior (se existir).

    Args:
        link_id: Identificador do produto.
        preco: Preço atual.

    Returns:
        Preço anterior ou None se for o primeiro registro.
    """
    historico = carregar_historico_precos()
    entrada = historico.get(link_id, {})

    preco_anterior = entrada.get("preco_atual")

    historico[link_id] = {
        "preco_atual": preco,
        "preco_anterior": preco_anterior,
        "ultima_atualizacao": datetime.now().isoformat(),
    }

    salvar_historico_precos(historico)
    return preco_anterior
