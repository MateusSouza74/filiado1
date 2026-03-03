"""
telegram_listener.py - Monitoramento de canais Telegram via Telethon.

Responsabilidades:
  - Conectar como usuário (não bot) usando API_ID/API_HASH
  - Escutar mensagens em múltiplos canais configuráveis
  - Orquestrar o pipeline: parse -> conversão -> postagem
  - Tratar erros por mensagem sem derrubar o processo

Fluxo por mensagem recebida:
  1. Extrai texto e mídia
  2. Parseia para encontrar URL e dados do produto
  3. Verifica duplicata
  4. Converte link para afiliado
  5. Consulta preço online (opcional)
  6. Formata mensagem
  7. Posta no canal destino
  8. Registra no histórico

Arquitetura de updates MTProto (canais broadcast):
  O servidor Telegram só empurra UpdateNewChannelMessage para clientes
  que têm channel_pts registrado E são considerados "ativos" no canal.
  Para manter esse status sem depender do Telegram Desktop:
    - catch_up=True: ao reconectar, chama getChannelDifference por canal
    - get_messages na init: popula channel_pts e ativa subscription
    - Task de renovação periódica: mantém subscription ativa via readHistory
"""

import asyncio
import os
from typing import Optional

from telethon import TelegramClient, events
from telethon.errors import (
    ChannelPrivateError,
    ChatForbiddenError,
    FloodWaitError,
)

from config import Config
from link_converter import converter_link_afiliado
from logger import get_logger
from parser import MensagemParsed, formatar_mensagem, identificar_dominio, parsear_mensagem
from price_monitor import analisar_variacao_preco, consultar_preco_online
from telegram_poster import TelegramPoster
from utils import ja_foi_postado, normalizar_link_id, registrar_postagem

log = get_logger(__name__)

# Intervalo de renovação das subscriptions de canais (segundos).
# A cada N segundos, o bot faz get_messages(limit=1) em cada canal monitorado
# para manter o flag "cliente ativo" no servidor Telegram.
_INTERVALO_RENOVACAO_SUBSCRICOES = 15 * 60  # 15 minutos


# ==============================================================================
# 🤖 LISTENER PRINCIPAL
# ==============================================================================

class AffiliateListener:
    """
    Listener Telethon que monitora canais e orquestra o pipeline de afiliados.
    """

    def __init__(self) -> None:
        # IMPORTANTE: cliente criado em iniciar() para garantir event loop correto.
        # Criar TelegramClient antes de asyncio.run() vincula ao loop errado (Python 3.10+).
        self.client: TelegramClient = None
        self.poster = TelegramPoster()
        self._handler_registrado = False
        self._entidades_canal: dict = {}  # canal_id → entity (cache para renovação)

    # --------------------------------------------------------------------------
    # 🔐 LOGIN INTERATIVO (ML)
    # --------------------------------------------------------------------------

    def verificar_login_ml(self) -> None:
        """
        Abre o Chrome visível para verificar/fazer login no painel de afiliados ML.
        Deve ser chamado UMA VEZ antes de iniciar o bot.
        Após login, fecha o navegador e libera o perfil para uso headless.
        """
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.common.by import By
            from webdriver_manager.chrome import ChromeDriverManager
            import time
        except ImportError:
            log.warning("[ML-LOGIN] Selenium não instalado. Pulando verificação de login ML.")
            return

        log.info("[ML-LOGIN] Verificando login do Mercado Livre...")

        options = Options()
        options.add_argument(f"user-data-dir={Config.CHROME_PROFILE_PATH}")
        options.add_argument("--start-maximized")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)

        try:
            driver.get("https://www.mercadolivre.com.br/afiliados/linkbuilder")

            while True:
                try:
                    driver.find_element(
                        By.XPATH,
                        "//input[@type='text' or contains(@placeholder, 'https')]",
                    )
                    log.info("[ML-LOGIN] Login detectado! Continuando...")
                    time.sleep(2)
                    break
                except Exception:
                    log.warning(
                        "[ML-LOGIN] Login necessário! Faça login na janela do Chrome "
                        "e marque 'Lembrar-me'. Aguardando..."
                    )
                    time.sleep(5)
        finally:
            driver.quit()
            log.info("[ML-LOGIN] Navegador fechado. Robô assumirá em headless.")

    # --------------------------------------------------------------------------
    # ⚙️ PIPELINE DE PROCESSAMENTO
    # --------------------------------------------------------------------------

    async def _processar_mensagem(
        self,
        texto: str,
        tem_midia: bool,
        canal_nome: str,
        baixar_midia_fn,
    ) -> None:
        """
        Pipeline completo de processamento de uma mensagem.

        Args:
            texto: Texto bruto da mensagem.
            tem_midia: Se a mensagem tem imagem/vídeo.
            canal_nome: Nome do canal de origem (para logs).
            baixar_midia_fn: Coroutine para baixar mídia se necessário.
        """
        log.info(f"[LISTENER] Nova mensagem de '{canal_nome}'")

        # 1. Parseia a mensagem
        parsed: MensagemParsed = await asyncio.get_running_loop().run_in_executor(
            None, parsear_mensagem, texto, tem_midia
        )

        if not parsed.valida:
            log.debug("[LISTENER] Mensagem sem URL válida. Ignorando.")
            return

        # 2. Deduplicação (usando URL sem query params como chave)
        link_id = normalizar_link_id(parsed.url_principal)
        if ja_foi_postado(link_id):
            return

        # 3. Converte link para afiliado (operação bloqueante no executor)
        link_afiliado = await asyncio.get_running_loop().run_in_executor(
            None,
            converter_link_afiliado,
            parsed.url_principal,
            parsed.dominio,
        )

        # 4. Consulta preço online (opcional, best-effort)
        preco_online: Optional[float] = None
        variacao_info: Optional[dict] = None

        # Usa o domínio do link convertido (após desencurtamento) para o scraper,
        # pois links curtos como meli.la viram mercadolivre.com.br após conversão.
        dominio_efetivo = identificar_dominio(link_afiliado) or parsed.dominio

        if dominio_efetivo:
            preco_online = await asyncio.get_running_loop().run_in_executor(
                None, consultar_preco_online, link_afiliado, dominio_efetivo
            )

            if preco_online:
                # Usa o preço online se o parser não extraiu do texto
                if not parsed.preco:
                    parsed.preco = preco_online

                variacao_info = await asyncio.get_running_loop().run_in_executor(
                    None, analisar_variacao_preco, link_id, preco_online
                )

        # 5. Formata a mensagem com template rotativo + desconto calculado
        msg_formatada = formatar_mensagem(parsed, link_afiliado, variacao_info)

        # 6. Baixa mídia se disponível
        caminho_midia: Optional[str] = None
        if tem_midia:
            try:
                caminho_midia = await baixar_midia_fn()
                log.debug(f"[LISTENER] Mídia baixada: {caminho_midia}")
            except Exception as e:
                log.warning(f"[LISTENER] Falha ao baixar mídia: {e}")

        # 7. Posta no canal destino
        sucesso = await asyncio.get_running_loop().run_in_executor(
            None,
            self.poster.enviar,
            msg_formatada,
            caminho_midia,
        )

        # 8. Registra no histórico se postou com sucesso
        if sucesso:
            registrar_postagem(link_id)
            log.info(f"[LISTENER] Postagem realizada com sucesso! Domínio: {parsed.dominio}")
        else:
            log.error("[LISTENER] Falha no envio da mensagem para o canal destino.")

        # 9. Limpa arquivo de mídia temporário
        if caminho_midia and os.path.exists(caminho_midia):
            try:
                os.remove(caminho_midia)
            except OSError:
                pass

    # --------------------------------------------------------------------------
    # 🔄 RENOVAÇÃO PERIÓDICA DE SUBSCRIPTIONS
    # --------------------------------------------------------------------------

    async def _renovar_subscricoes(self) -> None:
        """
        Task em background: renova subscriptions dos canais broadcast a cada
        _INTERVALO_RENOVACAO_SUBSCRICOES segundos.

        Por que isso é necessário:
          O servidor Telegram usa um flag "cliente ativo" por canal para decidir
          se envia UpdateNewChannelMessage a este cliente. Esse flag é ativado
          quando o cliente faz qualquer chamada relacionada ao canal (readHistory,
          getHistory, etc.). Sem renovação periódica, o servidor para de enviar
          updates para canais que o cliente não acessou recentemente, tornando o
          bot dependente do Telegram Desktop estar aberto.

          Essa task replica o comportamento do app Telegram, mantendo o flag
          ativo para todos os canais monitorados de forma contínua e headless.
        """
        while True:
            await asyncio.sleep(_INTERVALO_RENOVACAO_SUBSCRICOES)

            log.debug(
                f"[LISTENER] Renovando subscriptions de {len(self._entidades_canal)} canal(is)..."
            )

            for canal_id, entity in list(self._entidades_canal.items()):
                try:
                    await self.client.get_messages(entity, limit=1)
                    log.debug(
                        f"[LISTENER] Subscription renovada: "
                        f"'{getattr(entity, 'title', canal_id)}'"
                    )
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    log.debug(f"[LISTENER] Falha ao renovar {canal_id}: {e}")

            log.debug("[LISTENER] Renovação concluída.")

    # --------------------------------------------------------------------------
    # 📡 HANDLER DE EVENTOS
    # --------------------------------------------------------------------------

    def _registrar_handler(self) -> None:
        """Registra o handler de novas mensagens nos canais configurados."""

        if self._handler_registrado:
            return

        # Usa set para lookup O(1). Evita filtro chats= do Telethon que requer
        # resolução de entidade e falha silenciosamente com IDs numéricos.
        canais_monitorados = set(Config.CANAIS_ORIGEM)
        log.info(f"[LISTENER] Monitorando IDs: {canais_monitorados}")

        @self.client.on(events.Raw())
        async def raw_handler(update) -> None:
            """Captura QUALQUER update do Telegram. Usado só em DEBUG para confirmar que
            o Telethon está recebendo dados do servidor antes de filtrar por tipo."""
            if Config.DEBUG:
                log.debug(f"[TELETHON-RAW] {type(update).__name__}")

        @self.client.on(events.NewMessage())
        async def handler(event: events.NewMessage.Event) -> None:
            # Em modo debug, loga TODOS os updates recebidos para diagnóstico
            if Config.DEBUG:
                log.debug(
                    f"[RAW] chat_id={event.chat_id} | "
                    f"monitorado={event.chat_id in canais_monitorados} | "
                    f"tem_texto={bool(event.message.message)} | "
                    f"tem_midia={bool(event.message.media)}"
                )

            # Filtra manualmente: event.chat_id é o ID direto do evento, sem resolução
            if event.chat_id not in canais_monitorados:
                return

            if not event.message.message:
                log.debug(f"[LISTENER] Mensagem sem texto em '{event.chat_id}'. Ignorando.")
                return

            canal_nome = getattr(event.chat, "title", str(event.chat_id))
            texto = event.message.message
            tem_midia = bool(event.message.media)

            async def baixar_midia():
                return await self.client.download_media(
                    event.message,
                    file="temp_midia",
                )

            try:
                await self._processar_mensagem(texto, tem_midia, canal_nome, baixar_midia)
            except FloodWaitError as e:
                log.warning(f"[LISTENER] FloodWait: aguardando {e.seconds}s...")
                await asyncio.sleep(e.seconds)
            except (ChannelPrivateError, ChatForbiddenError) as e:
                log.error(f"[LISTENER] Sem acesso ao canal: {e}")
            except Exception as e:
                log.error(f"[LISTENER] Erro inesperado ao processar mensagem: {e}", exc_info=Config.DEBUG)

        self._handler_registrado = True
        log.info(f"[LISTENER] Handler registrado para {len(Config.CANAIS_ORIGEM)} canal(is).")

    # --------------------------------------------------------------------------
    # 🚀 INICIALIZAÇÃO
    # --------------------------------------------------------------------------

    async def iniciar(self) -> None:
        """Inicia o listener e bloqueia até desconexão."""
        # catch_up=True: ao reconectar, Telethon chama automaticamente getDifference
        # (para atualizações globais) e getChannelDifference (para cada canal com pts
        # armazenado na sessão), garantindo que mensagens enviadas enquanto o bot
        # estava offline sejam processadas ao voltar.
        self.client = TelegramClient(
            Config.SESSION_NAME,
            Config.API_ID,
            Config.API_HASH,
            catch_up=True,
        )

        log.info("=" * 60)
        log.info("      AFFILIATE BOT - Iniciando Monitoramento")
        log.info(f"      Canais: {', '.join(str(c) for c in Config.CANAIS_ORIGEM)}")
        log.info("=" * 60)

        log.info("[LISTENER] Conectando ao Telegram...")
        await self.client.start()

        me = await self.client.get_me()
        log.info(f"[LISTENER] Autenticado como: {me.first_name} (ID: {me.id} | @{me.username or 'sem_username'})")

        # Sincroniza pts/qts/date/seq global da sessão com o servidor.
        # Essencial para que o Telegram saiba a partir de qual ponto enviar updates.
        log.info("[LISTENER] Sincronizando estado de updates com o servidor...")
        await self.client.get_dialogs()
        log.info("[LISTENER] Sincronização concluída.")

        # Ativa subscriptions por canal:
        # get_messages(limit=1) faz uma chamada de histórico que:
        #   1. Popula o channel_pts na sessão do Telethon
        #   2. Registra "este cliente acompanha este canal" no servidor
        #   3. Faz o servidor começar a enviar UpdateNewChannelMessage para este canal
        # Sem isso, o bot só recebe mensagens do canal aberto no Telegram Desktop.
        log.info("[LISTENER] Ativando subscriptions dos canais monitorados...")
        for canal_id in Config.CANAIS_ORIGEM:
            try:
                entity = await self.client.get_entity(canal_id)
                nome = getattr(entity, "title", str(canal_id))
                await self.client.get_messages(entity, limit=1)
                self._entidades_canal[canal_id] = entity
                log.info(f"[LISTENER] Canal ativo: '{nome}' ({canal_id})")
            except Exception as e:
                log.warning(f"[LISTENER] Canal {canal_id} não pôde ser ativado: {e}")

        self._registrar_handler()

        # Task de renovação periódica: mantém subscriptions ativas sem Telegram Desktop.
        # Roda em background e renova a cada _INTERVALO_RENOVACAO_SUBSCRICOES segundos.
        task_renovar = asyncio.create_task(self._renovar_subscricoes())

        log.info(
            f"[LISTENER] Aguardando mensagens. "
            f"Renovação automática a cada {_INTERVALO_RENOVACAO_SUBSCRICOES // 60} min."
        )

        try:
            await self.client.run_until_disconnected()
        finally:
            task_renovar.cancel()
            try:
                await task_renovar
            except asyncio.CancelledError:
                pass

    def run(self) -> None:
        """Ponto de entrada síncrono (usado pelo main.py)."""
        asyncio.run(self.iniciar())
