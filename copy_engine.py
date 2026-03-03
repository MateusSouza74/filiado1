"""
copy_engine.py - Sistema de copy rotativa para mensagens de oferta.

Responsabilidades:
  - Gerar mensagens HTML atraentes com estrutura variada
  - Rotacionar entre 4 templates para evitar padrão repetitivo
  - Calcular % de desconto automaticamente quando possível
  - Usar alertas e CTAs variados por template
"""

import random
from typing import Optional

from logger import get_logger

log = get_logger(__name__)


# ==============================================================================
# 📋 TEMPLATES
# ==============================================================================
# Cada template tem: alerta, corpo com bloco_preco, CTA
# {alerta}, {titulo}, {bloco_preco}, {link}, {cta} são obrigatórios

_TEMPLATES = [
    # A — Urgência
    (
        "🔥 <b>{alerta}</b>\n\n"
        "📦 <b>{titulo}</b>\n\n"
        "{bloco_preco}"
        "⚡ <i>Estoque limitado!</i>\n\n"
        "👉 <a href='{link}'>{cta}</a>"
    ),
    # B — Oportunidade
    (
        "💥 <b>{alerta}</b>\n\n"
        "📦 <b>{titulo}</b>\n\n"
        "{bloco_preco}"
        "🛒 <a href='{link}'>{cta}</a>"
    ),
    # C — Preço caiu
    (
        "📉 <b>{alerta}</b>\n\n"
        "📦 <b>{titulo}</b>\n\n"
        "{bloco_preco}"
        "🔥 <i>Aproveite antes que o preço suba!</i>\n\n"
        "💳 <a href='{link}'>{cta}</a>"
    ),
    # D — Achado
    (
        "🎯 <b>{alerta}</b>\n\n"
        "📦 <b>{titulo}</b>\n\n"
        "{bloco_preco}"
        "✅ <i>Confira disponibilidade!</i>\n\n"
        "🛍️ <a href='{link}'>{cta}</a>"
    ),
]

_ALERTAS = [
    # Para template A (urgência)
    ["OFERTA RELÂMPAGO", "PROMOÇÃO IMPERDÍVEL", "OFERTA DO DIA", "PREÇO HISTÓRICO"],
    # Para template B (oportunidade)
    ["ACHADO DO DIA", "QUE NEGÓCIO!", "MELHOR PREÇO", "OFERTA ESPECIAL"],
    # Para template C (preço caiu)
    ["PREÇO CAIU!", "QUEDA DE PREÇO!", "PREÇO BAIXOU", "BAIXOU O PREÇO!"],
    # Para template D (achado)
    ["QUE ACHADO!", "PREÇO INCRÍVEL", "SUPER OFERTA", "OPORTUNIDADE ÚNICA"],
]

_CTAS = [
    # Para template A
    ["GARANTIR AGORA", "PEGAR A OFERTA", "QUERO ESSA OFERTA", "APROVEITAR AGORA"],
    # Para template B
    ["VER OFERTA", "CONFERIR PREÇO", "ACESSAR OFERTA", "VER MAIS"],
    # Para template C
    ["COMPRAR COM DESCONTO", "APROVEITAR DESCONTO", "IR À LOJA", "COMPRAR AGORA"],
    # Para template D
    ["PEGAR O MEU", "QUERO O MEU", "GARANTIR O MEU", "IR COMPRAR"],
]


# ==============================================================================
# 🔧 HELPERS
# ==============================================================================

def _fmt_brl(valor: float) -> str:
    """Formata float como moeda brasileira: 1.299,99"""
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _calcular_desconto_pct(preco: float, preco_original: float) -> int:
    """Calcula % de desconto entre dois preços. Retorna inteiro."""
    if preco_original <= 0 or preco >= preco_original:
        return 0
    return round(((preco_original - preco) / preco_original) * 100)


def _bloco_preco(
    preco: Optional[float],
    preco_original: Optional[float],
    desconto_pct: Optional[int],
    parcelamento: Optional[str],
    cupom: Optional[str],
) -> str:
    """Monta o bloco de preço formatado em HTML."""
    linhas = []

    tem_desconto_real = (
        preco_original
        and preco
        and preco_original > preco
    )

    if tem_desconto_real:
        linhas.append(f"<s>De: R$ {_fmt_brl(preco_original)}</s>")
        linhas.append(f"💸 <b>Por: R$ {_fmt_brl(preco)}</b>")
    elif preco:
        linhas.append(f"💰 <b>R$ {_fmt_brl(preco)}</b>")

    if desconto_pct and desconto_pct >= 5:
        linhas.append(f"📉 <b>{desconto_pct}% OFF</b>")

    if parcelamento:
        linhas.append(f"💳 {parcelamento}")

    if cupom:
        linhas.append(f"🎟️ Cupom: <code>{cupom}</code>")

    return "\n".join(linhas) + "\n\n" if linhas else ""


# ==============================================================================
# 🎨 GERADOR PRINCIPAL
# ==============================================================================

def gerar_mensagem(
    titulo: str,
    preco: Optional[float],
    preco_original: Optional[float],
    desconto_pct: Optional[int],
    parcelamento: Optional[str],
    cupom: Optional[str],
    link: str,
    preco_anterior_historico: Optional[float] = None,
) -> tuple[str, str]:
    """
    Gera mensagem HTML com template rotativo.

    Prioridade para preco_original:
      1. Extraído diretamente do texto da mensagem (mais confiável)
      2. Preço anterior do histórico (se queda > 5%)

    Args:
        titulo: Nome do produto.
        preco: Preço atual.
        preco_original: Preço "de" extraído do texto (opcional).
        desconto_pct: % desconto extraído do texto (opcional).
        parcelamento: String de parcelamento (opcional).
        cupom: Código de cupom (opcional).
        link: URL afiliada.
        preco_anterior_historico: Preço anterior do histórico de preços.

    Returns:
        (mensagem_html, nome_do_template)
    """
    idx = random.randint(0, len(_TEMPLATES) - 1)
    template = _TEMPLATES[idx]
    alerta = random.choice(_ALERTAS[idx])
    cta = random.choice(_CTAS[idx])
    template_nome = ["A-Urgencia", "B-Oportunidade", "C-Preco-Caiu", "D-Achado"][idx]

    # Resolve preco_original: texto > histórico (só usa histórico se queda > 5%)
    preco_orig_efetivo = preco_original
    if not preco_orig_efetivo and preco_anterior_historico and preco:
        if preco_anterior_historico > preco * 1.05:
            preco_orig_efetivo = preco_anterior_historico

    # Calcula desconto se não extraído do texto mas temos os dois preços
    desconto_efetivo = desconto_pct
    if not desconto_efetivo and preco_orig_efetivo and preco:
        desconto_efetivo = _calcular_desconto_pct(preco, preco_orig_efetivo)

    bloco = _bloco_preco(preco, preco_orig_efetivo, desconto_efetivo, parcelamento, cupom)

    # Usa replace() em vez de format() para evitar KeyError quando
    # título, bloco ou link contêm { } (comum em títulos de produtos e URLs)
    mensagem = (
        template
        .replace("{alerta}", alerta)
        .replace("{titulo}", titulo)
        .replace("{bloco_preco}", bloco)
        .replace("{link}", link)
        .replace("{cta}", cta)
    )

    log.debug(
        f"[COPY] Template={template_nome} | Alerta='{alerta}' | CTA='{cta}' | "
        f"Desconto={desconto_efetivo or 0}% | Preco=R${_fmt_brl(preco) if preco else '?'}"
    )

    return mensagem, template_nome
