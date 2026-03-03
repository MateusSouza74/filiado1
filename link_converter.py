"""
link_converter.py - Injeção de código de afiliado por marketplace.

Estrutura extensível: cada marketplace tem sua própria classe
que implementa a interface base `MarketplaceConverter`.

Para adicionar um novo marketplace:
  1. Crie uma classe herdando de MarketplaceConverter
  2. Implemente os métodos `suporta()` e `converter()`
  3. Registre no dicionário CONVERSORES no final do arquivo
"""

import re
import time
import urllib.parse
from abc import ABC, abstractmethod
from typing import Optional

import requests

from config import Config
from logger import get_logger

log = get_logger(__name__)


# ==============================================================================
# 🔗 DESENCURTADOR DE LINKS
# ==============================================================================

def desencurtar_link(url: str, timeout: int = 8) -> str:
    """
    Segue redirects de URLs encurtadas para obter a URL real.

    Args:
        url: URL potencialmente encurtada (amzn.to, bit.ly, etc.).
        timeout: Tempo máximo de espera em segundos.

    Returns:
        URL real após seguir todos os redirects.
    """
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.head(url, allow_redirects=True, headers=headers, timeout=timeout)
        url_real = resp.url

        log.debug(f"[DESENCURTAR] {url[:50]} -> {url_real[:70]}")
        return url_real
    except requests.RequestException as e:
        log.warning(f"[DESENCURTAR] Falha ao desencurtar {url}: {e}")
        return url


# ==============================================================================
# 🏗️ INTERFACE BASE
# ==============================================================================

class MarketplaceConverter(ABC):
    """Interface que todo conversor de afiliado deve implementar."""

    @abstractmethod
    def suporta(self, dominio: str) -> bool:
        """Retorna True se este conversor suporta o domínio fornecido."""
        ...

    @abstractmethod
    def converter(self, url: str) -> str:
        """
        Converte a URL para incluir o código de afiliado.

        Args:
            url: URL limpa (já desencurtada).

        Returns:
            URL com código de afiliado injetado.
        """
        ...

    def nome(self) -> str:
        return self.__class__.__name__


# ==============================================================================
# 🛒 AMAZON
# ==============================================================================

class AmazonConverter(MarketplaceConverter):
    """
    Injeta a tag de afiliado Amazon.

    Estratégia: Remove qualquer tag existente e injeta a nossa.
    Funciona com amazon.com.br, amzn.to (após desencurtar), etc.
    """

    DOMINIOS = ["amazon.com", "amzn.to", "amzn.com"]

    def suporta(self, dominio: str) -> bool:
        return any(d in dominio for d in self.DOMINIOS)

    def converter(self, url: str) -> str:
        if not Config.AMAZON_TAG:
            log.warning("[AMAZON] AMAZON_TAG não configurada. Retornando link original.")
            return url

        # Remove tag existente
        url = re.sub(r"([?&])tag=[^&]+", "", url)
        url = url.rstrip("?&")

        # Injeta nossa tag
        separador = "&" if "?" in url else "?"
        url_final = f"{url}{separador}tag={Config.AMAZON_TAG}"

        log.info(f"[AMAZON] Tag injetada: ...{url_final[-40:]}")
        return url_final


# ==============================================================================
# 🛍️ MERCADO LIVRE (Selenium)
# ==============================================================================

class MercadoLivreConverter(MarketplaceConverter):
    """
    Gera link de afiliado Mercado Livre via painel de afiliados (Selenium).

    O ML não tem API pública de afiliados, então usamos o painel web
    com um perfil Chrome persistente onde o usuário faz login uma vez.
    """

    DOMINIOS = ["mercadolivre.com", "mercadolibre.com", "ml.com.br", "meli.com", "meli.la"]

    def suporta(self, dominio: str) -> bool:
        return any(d in dominio for d in self.DOMINIOS)

    def converter(self, url: str) -> str:
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.support.ui import WebDriverWait
            from webdriver_manager.chrome import ChromeDriverManager
        except ImportError:
            log.error("[ML] Selenium não instalado. Retornando link original.")
            return url

        log.info("[ML] Iniciando Chrome headless para gerar link de afiliado...")
        driver = None

        try:
            options = Options()
            options.add_argument(f"user-data-dir={Config.CHROME_PROFILE_PATH}")
            options.add_argument("--headless=new")
            options.add_argument("--disable-gpu")
            options.add_argument("--no-sandbox")
            options.add_argument("--log-level=3")
            options.add_argument("--disable-dev-shm-usage")

            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
            driver.set_page_load_timeout(20)

            driver.get("https://www.mercadolivre.com.br/afiliados/linkbuilder")
            wait = WebDriverWait(driver, 12)

            try:
                campo = wait.until(
                    EC.presence_of_element_located(
                        (By.XPATH, "//input[@type='text' or contains(@placeholder, 'https')]")
                    )
                )
            except Exception:
                log.error("[ML] Painel de afiliados não acessível. Login pode ter expirado.")
                return url

            campo.clear()
            campo.send_keys(url)
            time.sleep(1)

            # Clica no botão de gerar link
            botoes = driver.find_elements(By.TAG_NAME, "button")
            clicou = False
            for btn in botoes:
                if any(texto in btn.text for texto in ["Gerar", "Criar", "Confirmar"]):
                    btn.click()
                    clicou = True
                    break

            if not clicou:
                log.warning("[ML] Botão 'Gerar' não encontrado.")
                return url

            time.sleep(2)

            # Extrai o link gerado
            inputs = driver.find_elements(By.TAG_NAME, "input")
            for inp in inputs:
                val = inp.get_attribute("value") or ""
                if "mercadolivre.com.br/sec" in val or "meli.com" in val:
                    log.info(f"[ML] Link afiliado gerado: {val[:60]}...")
                    return val

            log.warning("[ML] Link afiliado não encontrado no painel. Retornando original.")
            return url

        except Exception as e:
            log.error(f"[ML] Erro inesperado no Selenium: {e}", exc_info=Config.DEBUG)
            return url
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass


# ==============================================================================
# 🏪 LOMADEE (Múltiplas lojas)
# ==============================================================================

class LomadeeConverter(MarketplaceConverter):
    """
    Gera link de afiliado via plataforma Lomadee.

    Cobre: Kabum, TeraByte, Casas Bahia, Extra, Ponto, Nike, Netshoes, etc.
    A lista completa está em Config.LOJAS_LOMADEE.
    """

    def suporta(self, dominio: str) -> bool:
        return any(loja in dominio for loja in Config.LOJAS_LOMADEE)

    def converter(self, url: str) -> str:
        if not Config.LOMADEE_SOURCE_ID:
            log.warning("[LOMADEE] LOMADEE_SOURCE_ID não configurado. Retornando link original.")
            return url

        url_encoded = urllib.parse.quote(url, safe="")
        link_final = (
            f"https://redirect.lomadee.com/v2/deeplink"
            f"?sourceId={Config.LOMADEE_SOURCE_ID}&url={url_encoded}"
        )

        log.info(f"[LOMADEE] Link gerado para {url[:40]}...")
        return link_final


# ==============================================================================
# 🛒 SHOPEE
# ==============================================================================

class ShopeeConverter(MarketplaceConverter):
    """
    Injeta o ID de afiliado Shopee na URL.

    O programa de afiliados Shopee usa parâmetro 'af_sub1' ou estrutura
    de deeplink. Adapte conforme seu tipo de conta no programa.
    """

    DOMINIOS = ["shopee.com.br", "shope.ee"]

    def suporta(self, dominio: str) -> bool:
        return any(d in dominio for d in self.DOMINIOS)

    def converter(self, url: str) -> str:
        if not Config.SHOPEE_AFFILIATE_ID:
            log.warning("[SHOPEE] SHOPEE_AFFILIATE_ID não configurado. Retornando link original.")
            return url

        # Remove parâmetros de afiliado existentes
        url = re.sub(r"([?&])af_sub\d=[^&]+", "", url)
        url = url.rstrip("?&")

        separador = "&" if "?" in url else "?"
        url_final = f"{url}{separador}af_sub1={Config.SHOPEE_AFFILIATE_ID}"

        log.info(f"[SHOPEE] Afiliado injetado: ...{url_final[-40:]}")
        return url_final


# ==============================================================================
# 🔄 MOTOR DE CONVERSÃO
# ==============================================================================

# Registro de todos os conversores disponíveis (ordem importa para prioridade)
_CONVERSORES: list[MarketplaceConverter] = [
    AmazonConverter(),
    MercadoLivreConverter(),
    LomadeeConverter(),
    ShopeeConverter(),
]


def converter_link_afiliado(url_original: str, dominio: str) -> str:
    """
    Ponto de entrada principal para conversão de links.

    Fluxo:
    1. Desencurta o link se necessário
    2. Identifica o marketplace pelo domínio
    3. Aplica o conversor correspondente
    4. Retorna o link original se nenhum conversor suportar

    Args:
        url_original: URL bruta extraída da mensagem.
        dominio: Domínio já identificado pelo parser.

    Returns:
        URL com código de afiliado ou original se não suportado.
    """
    # Desencurta primeiro para garantir que temos a URL real
    url_real = desencurtar_link(url_original)

    # Reavalia o domínio após desencurtar (ex: amzn.to -> amazon.com.br)
    from parser import identificar_dominio
    dominio_real = identificar_dominio(url_real)

    for conversor in _CONVERSORES:
        if conversor.suporta(dominio_real):
            log.info(f"[CONVERSOR] Usando {conversor.nome()} para '{dominio_real}'")
            try:
                return conversor.converter(url_real)
            except Exception as e:
                log.error(f"[CONVERSOR] Erro em {conversor.nome()}: {e}", exc_info=Config.DEBUG)
                return url_real

    log.info(f"[CONVERSOR] Nenhum conversor encontrado para '{dominio_real}'. Link original mantido.")
    return url_real
