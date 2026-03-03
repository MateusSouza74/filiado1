"""
parser.py - Extração e análise inteligente de mensagens.

Responsabilidades:
  - Extrair URLs de texto bruto
  - Identificar domínio/marketplace
  - Extrair preço, parcelamento e cupom
  - Extrair título do produto
  - Formatar mensagem final para repostagem
"""

import re
from dataclasses import dataclass, field
from typing import Optional

from logger import get_logger

log = get_logger(__name__)

# Regex para capturar URLs (inclusive encurtadas como amzn.to, bit.ly)
URL_PATTERN = re.compile(r"https?://[^\s\)\]\">]+")

# Regex para preços em Real COM centavos (com ou sem R$): R$ 1.299,99 ou 1.299,99
PRECO_PATTERN = re.compile(r"(?:R\$)?\s?(\d{1,3}(?:\.\d{3})*,\d{2})")

# Regex para preços inteiros COM R$ explícito: R$ 759 (sem vírgula/centavos)
# Lookahead negativo evita capturar o inteiro de "R$ 1.299,99" → só pega se NÃO vier vírgula ou dígito a seguir
PRECO_INTEIRO_PATTERN = re.compile(r"R\$\s*(\d{1,3}(?:\.\d{3})*)(?!\d|,)")

# Regex para parcelamento: "12x de R$ 199,99 sem juros"
PARCELAMENTO_PATTERN = re.compile(
    r"(\d{1,2})[xX]\s*(?:de)?\s*R?\$?\s?(\d{1,3}(?:\.\d{3})*,\d{2})(.*?)(?:\n|$)",
    re.IGNORECASE,
)

# Regex para parcelamento no formato inverso: "R$ 119,00 em até 3x [sem juros]"
PARCELAMENTO_ALT_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{3})*,\d{2})\s+em\s+até\s+(\d{1,2})[xX]"
    r"(?:\s+(sem\s+juros|s/\s*juros))?",
    re.IGNORECASE,
)

# Regex para cupons de desconto.
# A palavra-chave é case-insensitive ("cupom", "Cupom", "CUPOM"),
# mas o código capturado DEVE estar em maiúsculas no texto original
# (cupons reais são sempre "TECH20" ou "3DO3CPU", nunca "especial").
# (?-i:...) desativa o IGNORECASE apenas para o grupo de captura.
# Primeiro caractere pode ser letra OU dígito (ex: "3DO3CPU").
CUPOM_PATTERN = re.compile(
    r"(?:cupom|cod(?:igo)?|c[oó]digo|use|promo)\s?[:\-]?\s?(?-i:([A-Z0-9][A-Z0-9]{3,19}))",
    re.IGNORECASE,
)

# Palavras que não são cupons válidos
PALAVRAS_INVALIDAS = {"CUPOM", "CODIGO", "CODE", "USE", "PROMO", "DESCONTO", "EXTRA"}

# Regex para preço ORIGINAL ("De: R$ 500,00" / "Era R$ 500" / "Antes: R$ 500")
PRECO_ORIGINAL_PATTERN = re.compile(
    r"(?:de|era|antes|original|cheio)[:\s]+R?\$?\s?(\d{1,3}(?:\.\d{3})*,\d{2})",
    re.IGNORECASE,
)

# Regex para % de desconto explícito no texto ("50% OFF", "30% de desconto")
DESCONTO_PCT_PATTERN = re.compile(
    r"(\d{1,3})\s*%\s*(?:off|de\s*desconto|desconto)"
    r"|(?:desconto|economize)\s+(?:de\s+)?(\d{1,3})\s*%",
    re.IGNORECASE,
)


# ==============================================================================
# 📦 DATACLASS DE RESULTADO
# ==============================================================================

@dataclass
class MensagemParsed:
    """Resultado completo da análise de uma mensagem."""
    texto_original: str = ""
    urls_encontradas: list[str] = field(default_factory=list)
    url_principal: str = ""
    dominio: str = ""
    titulo: str = ""
    preco: Optional[float] = None
    preco_original: Optional[float] = None   # Preço "De:" extraído do texto
    desconto_pct: Optional[int] = None        # % desconto extraído do texto
    parcelamento: Optional[str] = None
    cupom: Optional[str] = None
    tem_midia: bool = False

    @property
    def valida(self) -> bool:
        """Uma mensagem é válida se tiver pelo menos uma URL."""
        return bool(self.url_principal)


# ==============================================================================
# 🔍 FUNÇÕES DE EXTRAÇÃO
# ==============================================================================

def extrair_urls(texto: str) -> list[str]:
    """Extrai todas as URLs presentes no texto."""
    return URL_PATTERN.findall(texto)


def identificar_dominio(url: str) -> str:
    """
    Extrai o domínio base de uma URL.

    Ex: 'https://www.amazon.com.br/dp/B08...' -> 'amazon.com.br'
    """
    try:
        # Remove protocolo
        sem_protocolo = re.sub(r"^https?://", "", url)
        # Pega só o host (antes da primeira barra)
        host = sem_protocolo.split("/")[0].lower()
        # Remove 'www.'
        host = re.sub(r"^www\.", "", host)
        return host
    except Exception:
        return ""


def _converter_preco(valor_str: str) -> float:
    """Converte string de preço brasileiro para float."""
    try:
        return float(valor_str.replace(".", "").replace(",", "."))
    except ValueError:
        return 0.0


def extrair_preco(texto: str) -> Optional[float]:
    """
    Extrai o preço mais relevante do texto.

    Estratégia:
    - Combina preços com centavos (1.299,99) e inteiros com R$ (R$ 759)
    - Filtra valores muito baixos (< R$ 10)
    - Descarta valores outliers muito acima da mediana
    - Retorna o menor valor candidato plausível (preço promocional)
    """
    # Une preços com vírgula (R$ 1.299,99 ou 1.299,99) e inteiros com R$ (R$ 759)
    todos = PRECO_PATTERN.findall(texto) + PRECO_INTEIRO_PATTERN.findall(texto)
    numeros = [_converter_preco(v) for v in todos if _converter_preco(v) > 10]

    if not numeros:
        return None

    numeros.sort()
    max_val = max(numeros)

    # Candidatos: valores acima de 20% do maior valor (evita centavos de parcelamento)
    candidatos = [n for n in numeros if n > (max_val * 0.20)]
    if not candidatos:
        candidatos = [max_val]

    return min(candidatos)  # Preço promocional geralmente é o menor plausível


def extrair_parcelamento(texto: str) -> Optional[str]:
    """
    Extrai informação de parcelamento.

    Suporta dois formatos:
      - "12x de R$ 199,99 sem juros"  (parcelas antes do preço)
      - "R$ 119,00 em até 3x"         (preço antes das parcelas)
    """
    match = PARCELAMENTO_PATTERN.search(texto)
    if match:
        parcelas = match.group(1)
        valor = match.group(2)
        resto = match.group(3).lower()
        if "sem" in resto or "s/" in resto:
            return f"{parcelas}x de R$ {valor} sem juros"
        return f"{parcelas}x de R$ {valor}"

    alt = PARCELAMENTO_ALT_PATTERN.search(texto)
    if alt:
        valor = alt.group(1)
        parcelas = alt.group(2)
        resto = (alt.group(3) or "").lower()
        if "sem" in resto or "s/" in resto:
            return f"{parcelas}x de R$ {valor} sem juros"
        return f"{parcelas}x de R$ {valor}"

    return None


def extrair_cupom(texto: str) -> Optional[str]:
    """Extrai código de cupom de desconto do texto."""
    match = CUPOM_PATTERN.search(texto)
    if not match:
        return None

    candidato = match.group(1).strip().upper()

    if candidato in PALAVRAS_INVALIDAS or len(candidato) < 4:
        return None

    return candidato


def extrair_preco_original(texto: str) -> Optional[float]:
    """
    Extrai o preço 'De:' (original, antes do desconto) do texto.
    Ex: 'De: R$ 599,00' → 599.0 | 'Era R$ 1.299,99' → 1299.99
    """
    match = PRECO_ORIGINAL_PATTERN.search(texto)
    if not match:
        return None
    try:
        return float(match.group(1).replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


def extrair_desconto_pct(texto: str) -> Optional[int]:
    """
    Extrai % de desconto explícito do texto.
    Ex: '50% OFF' → 50 | 'desconto de 30%' → 30
    """
    match = DESCONTO_PCT_PATTERN.search(texto)
    if not match:
        return None
    # O padrão tem dois grupos alternativos — pega o que capturou
    valor = match.group(1) or match.group(2)
    try:
        pct = int(valor)
        return pct if 1 <= pct <= 99 else None
    except (ValueError, TypeError):
        return None


def extrair_titulo(texto: str, url_principal: str = "") -> str:
    """
    Extrai o título do produto do texto.

    Estratégia: Procura a primeira linha com conteúdo relevante
    (sem URL, sem preço, tamanho mínimo).
    """
    linhas = texto.split("\n")

    for linha in linhas:
        linha = linha.strip()
        # Ignora linhas curtas, com URL ou com preço
        if (
            len(linha) > 8
            and "http" not in linha
            and "R$" not in linha
            and not PRECO_PATTERN.search(linha)
            and not CUPOM_PATTERN.search(linha)
        ):
            # Remove emojis comuns de início de linha para ficar mais limpo
            titulo_limpo = re.sub(r"^[\U0001F300-\U0001FFFF\s⚡🔥💥✅❗]+", "", linha).strip()
            if len(titulo_limpo) > 5:
                return titulo_limpo

    return "Oferta Imperdível"


# ==============================================================================
# 🧠 PARSER PRINCIPAL
# ==============================================================================

def parsear_mensagem(texto: str, tem_midia: bool = False) -> MensagemParsed:
    """
    Analisa uma mensagem completa e retorna um objeto estruturado.

    Args:
        texto: Texto bruto da mensagem do Telegram.
        tem_midia: Se a mensagem contém imagem/mídia.

    Returns:
        MensagemParsed com todos os dados extraídos.
    """
    resultado = MensagemParsed(texto_original=texto, tem_midia=tem_midia)

    if not texto:
        log.debug("[PARSER] Mensagem vazia, ignorando.")
        return resultado

    # Extração de URLs
    resultado.urls_encontradas = extrair_urls(texto)
    if not resultado.urls_encontradas:
        log.debug("[PARSER] Nenhuma URL encontrada na mensagem.")
        return resultado

    resultado.url_principal = resultado.urls_encontradas[0]
    resultado.dominio = identificar_dominio(resultado.url_principal)

    # Extração de dados do texto
    resultado.preco = extrair_preco(texto)
    resultado.preco_original = extrair_preco_original(texto)
    resultado.desconto_pct = extrair_desconto_pct(texto)
    resultado.parcelamento = extrair_parcelamento(texto)
    resultado.cupom = extrair_cupom(texto)
    resultado.titulo = extrair_titulo(texto, resultado.url_principal)

    log.debug(
        f"[PARSER] Parseado: domínio={resultado.dominio} | "
        f"preço=R${resultado.preco} | original=R${resultado.preco_original} | "
        f"desconto={resultado.desconto_pct}% | cupom={resultado.cupom} | "
        f"título='{resultado.titulo[:40]}...'"
    )

    return resultado


# ==============================================================================
# ✉️ FORMATADOR DE MENSAGEM
# ==============================================================================

def formatar_mensagem(
    parsed: MensagemParsed,
    link_afiliado: str,
    variacao_info: Optional[dict] = None,
) -> str:
    """
    Gera a mensagem formatada usando o copy_engine com template rotativo.

    Args:
        parsed: Dados extraídos da mensagem original.
        link_afiliado: Link já convertido com código de afiliado.
        variacao_info: Dict do price_monitor com preco_anterior (opcional).

    Returns:
        String HTML pronta para envio via Telegram Bot API.
    """
    from copy_engine import gerar_mensagem

    preco_anterior = variacao_info.get("preco_anterior") if variacao_info else None

    mensagem, _ = gerar_mensagem(
        titulo=parsed.titulo,
        preco=parsed.preco,
        preco_original=parsed.preco_original,
        desconto_pct=parsed.desconto_pct,
        parcelamento=parsed.parcelamento,
        cupom=parsed.cupom,
        link=link_afiliado,
        preco_anterior_historico=preco_anterior,
    )
    return mensagem
