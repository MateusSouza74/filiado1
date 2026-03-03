"""
telegram_poster.py - Envio de mensagens via Telegram Bot API (HTTP).

Responsabilidades:
  - Enviar texto e foto para o canal destino
  - Tratar erros de API com retry automático
  - Respeitar rate limits do Telegram
  - Logar resultado de cada envio

Por que Bot API HTTP em vez de Telethon para envio?
  O Telethon (user account) é usado APENAS para escutar canais públicos.
  O Bot API é usado para postar no canal destino, mantendo a separação
  de responsabilidades e evitando banimento da conta principal.
"""

import time
from typing import Optional

import requests

from config import Config
from logger import get_logger

log = get_logger(__name__)

# Configurações de retry
MAX_TENTATIVAS = 3
PAUSA_ENTRE_TENTATIVAS = 2  # segundos
TIMEOUT_REQUEST = 15  # segundos

# URL base da Bot API
BOT_API_BASE = f"https://api.telegram.org/bot{{}}"


class TelegramPoster:
    """
    Encapsula o envio de mensagens via Telegram Bot API.

    Uso:
        poster = TelegramPoster()
        poster.enviar("Texto da mensagem")
        poster.enviar("Texto com foto", "/caminho/foto.jpg")
    """

    def __init__(self) -> None:
        if not Config.BOT_TOKEN:
            log.error("[POSTER] BOT_TOKEN não configurado!")

        self._base_url = BOT_API_BASE.format(Config.BOT_TOKEN)
        self._chat_id = Config.CANAL_DESTINO

    def _fazer_request(
        self,
        endpoint: str,
        metodo: str = "POST",
        dados: Optional[dict] = None,
        arquivos: Optional[dict] = None,
    ) -> Optional[dict]:
        """
        Executa um request para a Bot API com retry automático.

        Args:
            endpoint: Ex: 'sendMessage', 'sendPhoto'
            metodo: 'POST' ou 'GET'
            dados: Parâmetros do request
            arquivos: Arquivos para upload (ex: foto)

        Returns:
            Dict da resposta JSON ou None em caso de falha total.
        """
        url = f"{self._base_url}/{endpoint}"

        for tentativa in range(1, MAX_TENTATIVAS + 1):
            try:
                if metodo == "POST":
                    if arquivos:
                        resp = requests.post(url, data=dados, files=arquivos, timeout=TIMEOUT_REQUEST)
                    else:
                        resp = requests.post(url, json=dados, timeout=TIMEOUT_REQUEST)
                else:
                    resp = requests.get(url, params=dados, timeout=TIMEOUT_REQUEST)

                dados_resp = resp.json()

                if resp.status_code == 200 and dados_resp.get("ok"):
                    return dados_resp

                # Trata rate limit (erro 429)
                if resp.status_code == 429:
                    retry_after = dados_resp.get("parameters", {}).get("retry_after", 5)
                    log.warning(f"[POSTER] Rate limit! Aguardando {retry_after}s...")
                    time.sleep(retry_after)
                    continue

                log.warning(
                    f"[POSTER] Tentativa {tentativa}/{MAX_TENTATIVAS} falhou. "
                    f"Status: {resp.status_code} | Resposta: {dados_resp.get('description', '')}"
                )

            except requests.Timeout:
                log.warning(f"[POSTER] Timeout na tentativa {tentativa}/{MAX_TENTATIVAS}.")
            except requests.RequestException as e:
                log.warning(f"[POSTER] Erro de rede na tentativa {tentativa}: {e}")

            if tentativa < MAX_TENTATIVAS:
                time.sleep(PAUSA_ENTRE_TENTATIVAS)

        log.error(f"[POSTER] Falha total após {MAX_TENTATIVAS} tentativas em '{endpoint}'.")
        return None

    def enviar_texto(self, texto: str) -> bool:
        """
        Envia mensagem de texto puro (com HTML) para o canal destino.

        Args:
            texto: Mensagem formatada em HTML.

        Returns:
            True se enviado com sucesso.
        """
        payload = {
            "chat_id": self._chat_id,
            "text": texto,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        resultado = self._fazer_request("sendMessage", dados=payload)

        if resultado:
            msg_id = resultado.get("result", {}).get("message_id", "?")
            log.info(f"[POSTER] Texto enviado. message_id={msg_id}")
            return True

        return False

    def enviar_foto(self, texto: str, caminho_foto: str) -> bool:
        """
        Envia foto com legenda para o canal destino.

        Args:
            texto: Legenda formatada em HTML.
            caminho_foto: Caminho local do arquivo de imagem.

        Returns:
            True se enviado com sucesso.
        """
        payload = {
            "chat_id": self._chat_id,
            "caption": texto,
            "parse_mode": "HTML",
        }

        try:
            with open(caminho_foto, "rb") as foto:
                resultado = self._fazer_request(
                    "sendPhoto",
                    dados=payload,
                    arquivos={"photo": foto},
                )
        except FileNotFoundError:
            log.warning(f"[POSTER] Arquivo de foto não encontrado: {caminho_foto}. Enviando só texto.")
            return self.enviar_texto(texto)

        if resultado:
            msg_id = resultado.get("result", {}).get("message_id", "?")
            log.info(f"[POSTER] Foto enviada. message_id={msg_id}")
            return True

        return False

    def enviar(self, texto: str, caminho_foto: Optional[str] = None) -> bool:
        """
        Método principal de envio. Decide automaticamente entre foto e texto.

        Args:
            texto: Mensagem formatada em HTML.
            caminho_foto: Caminho da imagem (opcional).

        Returns:
            True se enviado com sucesso.
        """
        if not self._chat_id:
            log.error("[POSTER] CANAL_DESTINO não configurado. Abortando envio.")
            return False

        if caminho_foto:
            return self.enviar_foto(texto, caminho_foto)

        return self.enviar_texto(texto)

    def testar_conexao(self) -> bool:
        """
        Verifica se o bot está funcional consultando getMe.

        Returns:
            True se o token é válido e o bot está ativo.
        """
        resultado = self._fazer_request("getMe", metodo="GET")
        if resultado:
            username = resultado.get("result", {}).get("username", "desconhecido")
            log.info(f"[POSTER] Bot conectado: @{username}")
            return True
        log.error("[POSTER] Falha ao conectar com o bot. Verifique o BOT_TOKEN.")
        return False
