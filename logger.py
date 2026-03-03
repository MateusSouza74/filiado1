"""
logger.py - Sistema de logging estruturado e configurável.

Uso:
    from logger import get_logger
    log = get_logger(__name__)
    log.info("Mensagem")
    log.debug("Detalhe debug")
    log.error("Erro crítico", exc_info=True)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """
    Retorna um logger configurado para o módulo informado.

    - Saída no console (stdout) com nível INFO (ou DEBUG se DEBUG=true).
    - Saída em arquivo rotativo em logs/affiliate_bot.log.
    - Formato legível com timestamp, nível e módulo.
    """
    logger = logging.getLogger(name)

    # Evita adicionar handlers duplicados se o logger já foi configurado
    if logger.handlers:
        return logger

    # Nível global: DEBUG se a variável de ambiente estiver ativa
    from config import Config
    level = logging.DEBUG if Config.DEBUG else logging.INFO
    logger.setLevel(level)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # --- Handler de Console ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # --- Handler de Arquivo Rotativo ---
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)

    file_handler = RotatingFileHandler(
        filename=log_dir / "affiliate_bot.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB por arquivo
        backupCount=5,              # Mantém até 5 arquivos de backup
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)  # Arquivo sempre captura tudo
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
