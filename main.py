"""
main.py - Ponto de entrada do Affiliate Bot.

Fluxo de inicialização:
  1. Valida configurações do .env
  2. Cria estrutura de diretórios necessária
  3. Verifica login do Mercado Livre (se configurado)
  4. Testa conexão com o bot do Telegram
  5. Inicia o listener de canais

Uso:
  python main.py              -> Modo normal
  python main.py --no-ml-check -> Pula verificação de login ML
  python main.py --test-bot   -> Testa conexão do bot e sai
"""

import argparse
import asyncio
import sys

# CRÍTICO no Windows: o ProactorEventLoop (padrão desde Python 3.8) não funciona
# corretamente com o layer de rede do Telethon — a conexão funciona mas updates
# nunca chegam. WindowsSelectorEventLoopPolicy resolve esse problema.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from config import Config, validar_config
from logger import get_logger
from utils import garantir_estrutura_dados, total_postagens_historico

log = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse dos argumentos de linha de comando."""
    parser = argparse.ArgumentParser(
        description="Affiliate Bot - Monitor e repostador de ofertas no Telegram"
    )
    parser.add_argument(
        "--no-ml-check",
        action="store_true",
        help="Pula a verificação de login do Mercado Livre",
    )
    parser.add_argument(
        "--test-bot",
        action="store_true",
        help="Testa a conexão do bot e encerra",
    )
    return parser.parse_args()


def banner() -> None:
    """Exibe o banner de inicialização."""
    log.info("=" * 60)
    log.info("  AFFILIATE BOT v2.0 - Monitor de Ofertas")
    log.info("  Canais monitorados: " + ", ".join(str(c) for c in Config.CANAIS_ORIGEM))
    log.info(f"  Canal destino: {Config.CANAL_DESTINO}")
    log.info(f"  Amazon tag: {Config.AMAZON_TAG or '(não configurado)'}")
    log.info(f"  Debug: {'ATIVO' if Config.DEBUG else 'inativo'}")
    log.info(f"  Histórico ativo: {total_postagens_historico()} links")
    log.info("=" * 60)


def main() -> None:
    """Função principal de inicialização e execução do bot."""
    args = parse_args()

    # 1. Garante que os diretórios de dados existem
    garantir_estrutura_dados()

    # 2. Valida configurações obrigatórias
    erros = validar_config()
    if erros:
        log.error("Configuração inválida. Corrija os problemas abaixo:")
        for erro in erros:
            log.error(f"  ❌ {erro}")
        log.error("Edite o arquivo .env e reinicie o bot.")
        sys.exit(1)

    banner()

    # Import tardio para evitar erros antes da validação
    from telegram_poster import TelegramPoster
    from telegram_listener import AffiliateListener

    # 3. Testa conexão do bot
    poster = TelegramPoster()
    if not poster.testar_conexao():
        log.error("Falha na conexão com o bot. Verifique BOT_TOKEN e tente novamente.")
        sys.exit(1)

    # Modo --test-bot: apenas verifica e sai
    if args.test_bot:
        log.info("Teste de bot bem-sucedido. Encerrando (--test-bot).")
        sys.exit(0)

    # 4. Inicializa listener
    listener = AffiliateListener()

    # 5. Verificação de login ML (opcional)
    if not args.no_ml_check and Config.LOMADEE_SOURCE_ID:
        # Só verifica ML se Lomadee não está configurado
        # (ML usa Selenium, Lomadee usa API simples)
        pass

    if not args.no_ml_check:
        try:
            listener.verificar_login_ml()
        except Exception as e:
            log.warning(f"[MAIN] Verificação ML falhou (não crítico): {e}")
            log.warning("[MAIN] Continuando sem verificação ML. Use --no-ml-check para suprimir este aviso.")

    # 6. Inicia monitoramento (bloqueia até Ctrl+C ou desconexão)
    try:
        log.info("[MAIN] Iniciando monitoramento. Pressione Ctrl+C para parar.")
        listener.run()
    except KeyboardInterrupt:
        log.info("[MAIN] Bot encerrado pelo usuário.")
    except Exception as e:
        log.critical(f"[MAIN] Erro fatal: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
