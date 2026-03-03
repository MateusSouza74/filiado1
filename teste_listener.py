"""
teste_listener.py - Script MÍNIMO de diagnóstico do Telethon.

Propósito: verificar se o Telethon consegue receber QUALQUER update,
           sem nenhuma lógica de afiliado ou filtragem.

Execute: python teste_listener.py
Pare com: Ctrl+C

O que deve aparecer quando funcionar:
  [UPDATE] chat_id=... | texto='...' | midia=True/False
"""

import asyncio
from dotenv import load_dotenv
import os

load_dotenv()

API_ID   = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION  = os.getenv("SESSION_NAME", "sessao_affiliate_bot")

from telethon import TelegramClient, events


async def main():
    print(f"Conectando com sessao: {SESSION}")
    client = TelegramClient(SESSION, API_ID, API_HASH)

    await client.start()
    me = await client.get_me()
    print(f"Autenticado como: {me.first_name} (ID: {me.id})")

    # Sincroniza estado antes de escutar
    print("Sincronizando dialogs com o servidor...")
    dialogs = await client.get_dialogs()
    print(f"Dialogs carregados: {len(dialogs)}")

    print("\n=== ESCUTANDO TODOS OS UPDATES. ENVIE UMA MENSAGEM EM QUALQUER CHAT ===\n")

    @client.on(events.NewMessage())
    async def handler(event):
        print(f"[UPDATE] chat_id={event.chat_id} | "
              f"texto={repr(event.message.message[:60]) if event.message.message else '(sem texto)'} | "
              f"midia={bool(event.message.media)}")

    await client.run_until_disconnected()


asyncio.run(main())
