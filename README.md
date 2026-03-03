# Affiliate Bot v2.0

Bot profissional para monitoramento e repostagem de ofertas no Telegram com injeção automática de links de afiliado.

## Funcionalidades

- Monitora múltiplos canais Telegram configuráveis
- Detecta e extrai URLs automaticamente
- Injeta código de afiliado por marketplace:
  - **Amazon** — tag via URL parameter
  - **Mercado Livre** — via painel de afiliados (Selenium)
  - **Lomadee** — Kabum, Casas Bahia, Extra, Ponto, Nike, Netshoes e outros
  - **Shopee** — via parâmetro de afiliado
- Extrai preço, parcelamento e cupom do texto
- Evita repostagem duplicada (histórico com TTL configurável)
- Rastreamento de variação de preço
- Logs estruturados em console e arquivo rotativo
- Testes unitários completos

---

## Instalação

```bash
# 1. Clone ou copie o projeto
cd affiliate-bot

# 2. Crie um ambiente virtual (recomendado)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac

# 3. Instale as dependências
pip install -r requirements.txt

# 4. Configure o .env
cp .env.example .env
# Edite o .env com seus dados
```

---

## Configuração

Edite o arquivo `.env` com suas credenciais:

| Variável | Descrição | Onde obter |
|---|---|---|
| `TELEGRAM_API_ID` | ID da API Telegram | [my.telegram.org](https://my.telegram.org) |
| `TELEGRAM_API_HASH` | Hash da API Telegram | [my.telegram.org](https://my.telegram.org) |
| `BOT_TOKEN` | Token do seu bot | [@BotFather](https://t.me/BotFather) |
| `CANAL_DESTINO` | ID ou @username do canal destino | ID numérico do seu canal |
| `CANAIS_ORIGEM` | Canais para monitorar (separados por vírgula) | @canal1,@canal2 |
| `AMAZON_TAG` | Sua tag Amazon Associates | Painel Amazon Associates |
| `LOMADEE_SOURCE_ID` | Source ID Lomadee | Painel Lomadee → Ferramentas |
| `SHOPEE_AFFILIATE_ID` | ID Shopee Affiliates | Painel Shopee Affiliates |

---

## Como Rodar

### Primeira execução (com Mercado Livre)
```bash
# Abre Chrome visível para você fazer login no ML
python main.py
```

### Execuções seguintes (login já salvo)
```bash
# Pula verificação de login (mais rápido)
python main.py --no-ml-check
```

### Testar se o bot está configurado
```bash
python main.py --test-bot
```

### Modo Debug (logs detalhados)
```bash
# No .env: DEBUG=true
python main.py --no-ml-check
```

---

## Rodando os Testes

```bash
# Todos os testes
python -m pytest tests/ -v

# Apenas parser
python -m pytest tests/test_parser.py -v

# Apenas conversor de links
python -m pytest tests/test_link_converter.py -v

# Com cobertura de código
pip install pytest-cov
python -m pytest tests/ --cov=. --cov-report=term-missing
```

---

## Estrutura do Projeto

```
affiliate-bot/
├── main.py               # Ponto de entrada
├── config.py             # Configurações via .env
├── logger.py             # Sistema de logs
├── utils.py              # Deduplicação e helpers
├── parser.py             # Extração de URL, preço, cupom
├── link_converter.py     # Injeção de afiliado por marketplace
├── price_monitor.py      # Rastreamento de preços
├── telegram_listener.py  # Monitoramento de canais (Telethon)
├── telegram_poster.py    # Envio de mensagens (Bot API)
├── tests/
│   ├── test_parser.py
│   ├── test_link_converter.py
│   ├── test_utils.py
│   └── test_telegram_poster.py
├── data/                 # Gerado automaticamente
│   ├── historico_duplicatas.json
│   └── historico_precos.json
├── logs/                 # Gerado automaticamente
│   └── affiliate_bot.log
├── requirements.txt
├── .env.example
└── .gitignore
```

---

## Adicionando um Novo Marketplace

Edite `link_converter.py`:

```python
class MeuMarketplaceConverter(MarketplaceConverter):

    DOMINIOS = ["meusite.com.br"]

    def suporta(self, dominio: str) -> bool:
        return any(d in dominio for d in self.DOMINIOS)

    def converter(self, url: str) -> str:
        # Sua lógica de injeção aqui
        return f"{url}?afiliado={Config.MEU_CODIGO}"

# Registre no final do arquivo:
_CONVERSORES.append(MeuMarketplaceConverter())
```

---

## Logs

Os logs ficam em `logs/affiliate_bot.log` (rotativo, máx 5 arquivos de 5MB):

```
2024-01-15 14:30:22 [INFO] telegram_listener | [LISTENER] Nova mensagem de 'LaPromotion'
2024-01-15 14:30:22 [INFO] parser | [PARSER] Parseado: domínio=amazon.com.br | preço=R$299.99
2024-01-15 14:30:23 [INFO] link_converter | [CONVERSOR] Usando AmazonConverter para 'amazon.com.br'
2024-01-15 14:30:23 [INFO] telegram_poster | [POSTER] Texto enviado. message_id=1234
```
