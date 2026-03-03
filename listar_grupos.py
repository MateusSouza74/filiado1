"""
listar_grupos.py - Lista todos os grupos e canais do Telegram.

Usa as credenciais do .env mas uma sessão própria para não conflitar
com o bot principal que pode estar rodando ao mesmo tempo.
Execute com: python listar_grupos.py
"""

import shutil
import os
from telethon import TelegramClient
from config import Config

# Sessão separada para não travar o arquivo do bot principal
SESSION_LISTAR = "sessao_listar_grupos"

# Se a sessão do bot já existe, copia ela para não precisar logar de novo
SESSION_ORIGEM = Config.SESSION_NAME + ".session"
SESSION_DESTINO = SESSION_LISTAR + ".session"

if os.path.exists(SESSION_ORIGEM) and not os.path.exists(SESSION_DESTINO):
    shutil.copy2(SESSION_ORIGEM, SESSION_DESTINO)
    print(f"Sessão copiada de {SESSION_ORIGEM} -> {SESSION_DESTINO}")

client = TelegramClient(SESSION_LISTAR, Config.API_ID, Config.API_HASH)


MONITORADOS = set(Config.CANAIS_ORIGEM)


async def main():
    print("Conectando...")
    await client.start()
    print("Conectado! Listando grupos e canais:\n")

    grupos = []
    async for dialog in client.iter_dialogs():
        if dialog.is_channel or dialog.is_group:
            grupos.append((dialog.name, dialog.id))

    if not grupos:
        print("Nenhum grupo ou canal encontrado.")
        return

    print(f"{'MONITORADO':<12} {'NOME':<40} {'ID'}")
    print("-" * 70)
    for nome, id_ in sorted(grupos, key=lambda x: x[0].lower()):
        status = "  [SIM]" if id_ in MONITORADOS else "  [nao]"
        print(f"{status:<12} {nome:<40} {id_}")

    print(f"\nTotal: {len(grupos)} grupos/canais encontrados.")
    print(f"Monitorados: {sum(1 for _, id_ in grupos if id_ in MONITORADOS)}/{len(grupos)}")


with client:
    client.loop.run_until_complete(main())
