"""
teste_minimal.py - Diagnóstico mínimo do Telethon (sem dependências do projeto).

Testa se o bot consegue receber mensagens de forma headless, sem Telegram Desktop.

Uso:
    python teste_minimal.py

Após iniciar, feche o Telegram Desktop e envie mensagens nos canais.
Se aparecerem [MSG] no terminal → funcionando headless.
Se aparecer só [TELETHON-RAW] UpdateUserStatus → subscription não ativada.
Se não aparecer nada → problema de event loop ou sessão.
"""

import asyncio
import os
import sys

# DEVE ser a primeira linha antes de qualquer import do Telethon
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from dotenv import load_dotenv
from telethon import TelegramClient, events

load_dotenv()

API_ID   = int(os.getenv("TELEGRAM_API_ID", "0"))
API_HASH = os.getenv("TELEGRAM_API_HASH", "")
SESSION  = os.getenv("SESSION_NAME", "sessao_affiliate_bot")

CANAIS_STR = os.getenv("CANAIS_ORIGEM", "")
CANAIS: set = set()
for c in CANAIS_STR.split(","):
    c = c.strip()
    if c.lstrip("-").isdigit():
        CANAIS.add(int(c))
    elif c:
        CANAIS.add(c)

INTERVALO_RENOVACAO = 15 * 60  # 15 minutos


async def main() -> None:
    loop_type = type(asyncio.get_event_loop()).__name__
    print(f"[TESTE] Python {sys.version.split()[0]} | Event loop: {loop_type}")
    print(f"[TESTE] Sessão: {SESSION} | API_ID: {API_ID}")
    print(f"[TESTE] Canais monitorados: {CANAIS}")
    print()

    # catch_up=True: ao conectar, busca mensagens perdidas via getChannelDifference
    client = TelegramClient(SESSION, API_ID, API_HASH, catch_up=True)

    @client.on(events.Raw())
    async def on_raw(update) -> None:
        print(f"[TELETHON-RAW] {type(update).__name__}")

    @client.on(events.NewMessage())
    async def on_message(event) -> None:
        chat_id  = event.chat_id
        monit    = chat_id in CANAIS
        texto    = (event.message.message or "")[:80]
        print(f"[MSG] chat_id={chat_id} | monitorado={monit} | '{texto}'")

    await client.start()
    me = await client.get_me()
    print(f"[TESTE] Autenticado: {me.first_name} (@{me.username or 'sem_username'})")

    print("[TESTE] Sincronizando dialogs...")
    await client.get_dialogs()
    print("[TESTE] Sincronizado!")

    # Ativa subscription por canal via get_messages
    entidades: dict = {}
    print("[TESTE] Ativando subscriptions...")
    for canal_id in CANAIS:
        try:
            entity = await client.get_entity(canal_id)
            await client.get_messages(entity, limit=1)
            entidades[canal_id] = entity
            print(f"[TESTE] Ativo: '{getattr(entity, 'title', canal_id)}'")
        except Exception as e:
            print(f"[TESTE] ERRO {canal_id}: {e}")

    async def renovar_subscricoes() -> None:
        """Mantém subscriptions ativas sem Telegram Desktop."""
        while True:
            await asyncio.sleep(INTERVALO_RENOVACAO)
            print(f"[TESTE] Renovando {len(entidades)} subscription(s)...")
            for cid, ent in list(entidades.items()):
                try:
                    await client.get_messages(ent, limit=1)
                except asyncio.CancelledError:
                    return
                except Exception:
                    pass

    task = asyncio.create_task(renovar_subscricoes())

    print()
    print("=" * 60)
    print("TESTE HEADLESS: feche o Telegram Desktop agora.")
    print("Envie mensagens nos canais monitorados.")
    print("[MSG] deve aparecer mesmo com Telegram fechado.")
    print("Ctrl+C para parar.")
    print("=" * 60)

    try:
        await client.run_until_disconnected()
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    asyncio.run(main())
