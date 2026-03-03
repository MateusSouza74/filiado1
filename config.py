"""
config.py - Configuração central do bot via variáveis de ambiente.

Todas as configurações sensíveis são lidas do arquivo .env,
nunca hardcoded no código. Use .env.example como referência.
"""

import os
from dotenv import load_dotenv

# Carrega o arquivo .env do diretório raiz do projeto
load_dotenv()


class Config:
    """Configurações globais do bot. Lidas do .env."""

    # --- Credenciais Telegram (Telethon) ---
    API_ID: int = int(os.getenv("TELEGRAM_API_ID", "0"))
    API_HASH: str = os.getenv("TELEGRAM_API_HASH", "")
    SESSION_NAME: str = os.getenv("SESSION_NAME", "sessao_affiliate_bot")

    # --- Bot HTTP (para envio de mensagens) ---
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    CANAL_DESTINO: str = os.getenv("CANAL_DESTINO", "")  # Chat ID numérico ou @username

    # --- Canais de origem para monitorar ---
    # Ex no .env: CANAIS_ORIGEM=-1001234567890,-1009876543210,@username
    # IDs numéricos são preferíveis a @usernames para grupos privados
    CANAIS_ORIGEM: list = [
        int(c.strip()) if c.strip().lstrip("-").isdigit() else c.strip()
        for c in os.getenv("CANAIS_ORIGEM", "").split(",")
        if c.strip()
    ]

    # --- Códigos de afiliado ---
    AMAZON_TAG: str = os.getenv("AMAZON_TAG", "")
    LOMADEE_SOURCE_ID: str = os.getenv("LOMADEE_SOURCE_ID", "")
    SHOPEE_AFFILIATE_ID: str = os.getenv("SHOPEE_AFFILIATE_ID", "")

    # --- Lojas suportadas pela Lomadee ---
    LOJAS_LOMADEE: list[str] = [
        "terabyteshop.com.br", "kabum.com.br", "girafa.com.br",
        "fastshop.com.br", "casasbahia.com.br", "ponto.com.br",
        "extra.com.br", "lenovo.com", "motorola.com.br",
        "samsung.com", "acer.com", "nike.com.br", "netshoes.com.br",
    ]

    # --- Selenium / Chrome ---
    CHROME_PROFILE_PATH: str = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        os.getenv("CHROME_PROFILE_DIR", "ml_chrome_profile"),
    )

    # --- Arquivos de dados ---
    DATA_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    HISTORICO_FILE: str = os.path.join(DATA_DIR, "historico_duplicatas.json")
    PRICE_HISTORY_FILE: str = os.path.join(DATA_DIR, "historico_precos.json")

    # --- Comportamento ---
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    # Tempo (em horas) que um link fica no histórico de duplicatas
    DUPLICATA_TTL_HORAS: int = int(os.getenv("DUPLICATA_TTL_HORAS", "24"))
    # Pausa entre tentativas de download de mídia (segundos)
    MEDIA_DOWNLOAD_TIMEOUT: int = int(os.getenv("MEDIA_DOWNLOAD_TIMEOUT", "10"))


def validar_config() -> list[str]:
    """
    Valida as configurações obrigatórias.
    Retorna lista de erros encontrados (vazio = tudo OK).
    """
    erros = []

    if not Config.API_ID:
        erros.append("TELEGRAM_API_ID não configurado ou inválido.")
    if not Config.API_HASH:
        erros.append("TELEGRAM_API_HASH não configurado.")
    if not Config.BOT_TOKEN:
        erros.append("BOT_TOKEN não configurado.")
    if not Config.CANAL_DESTINO:
        erros.append("CANAL_DESTINO não configurado.")
    if not Config.CANAIS_ORIGEM:
        erros.append("CANAIS_ORIGEM não configurado (pelo menos um canal).")

    return erros
