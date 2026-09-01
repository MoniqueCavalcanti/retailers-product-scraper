# Guia: como o Scrapy e o Playwright se conectam neste projeto

Este documento explica em detalhe como o Scrapy e o Playwright trabalham
juntos aqui, o que cada configuração em `settings.py` faz, e a sequência real
de tentativas e erros que levou à configuração atual. É a versão longa e
didática — o [`README.md`](../README.md) tem a versão resumida, bilíngue,
pensada pra leitura rápida.

## 1. Por que o Scrapy sozinho não basta

O Scrapy, por padrão, faz requisições HTTP puras — ele monta a requisição,
manda pela rede e lê a resposta, sem executar nenhum JavaScript e sem ser um
navegador de verdade. Isso é rápido e leve, e funciona pra maioria dos sites.

O Magazine Luiza fica atrás do **Akamai Bot Manager**, um sistema anti-bot
que roda um script de "sensor" no navegador do visitante pra decidir, no
servidor deles, se quem está acessando é humano ou automação. Uma requisição
HTTP pura nunca executa esse sensor — e o Akamai trata a ausência de sensor
como sinal de bot, bloqueando com `403` antes mesmo do conteúdo da página.
Confirmamos isso com `curl` puro (bloqueado mesmo com headers realistas de
navegador) e com o downloader padrão do Scrapy (mesmo resultado).

Ou seja: pra esse site especificamente, não existe alternativa a usar um
navegador real por trás do Scrapy. A pergunta não é "Scrapy ou Playwright", é
"como fazer o Scrapy usar um navegador de verdade sem perder a estrutura de
projeto (spiders, pipelines, exportação) que o Scrapy oferece".

## 2. Como o Scrapy processa uma requisição (visão geral)

Antes de entender o Playwright encaixado, vale relembrar o fluxo padrão do
Scrapy:

```text
Spider.start()               # gera scrapy.Request(url, callback=...)
      │
      ▼
Scheduler                    # fila de requisições pendentes
      │
      ▼
Downloader Middlewares       # podem alterar a Request antes de sair
      │
      ▼
Download Handler             # de fato busca a URL (HTTP puro por padrao)
      │
      ▼
Downloader Middlewares       # podem alterar a Response antes de voltar
      │
      ▼
Spider Middlewares
      │
      ▼
Spider.parse(response)       # seu codigo: extrai dados, gera novos Requests
      │
      ▼
Item Pipelines                # limpeza, validacao, salvar em CSV/DB
```

O **Download Handler** é a peça que efetivamente "sai na rede" pra buscar a
URL. Por padrão, o Scrapy usa `HTTP11DownloadHandler` — um cliente HTTP puro
(via Twisted), sem navegador nenhum. É exatamente essa peça que trocamos.

## 3. O que o `scrapy-playwright` realmente faz

O `scrapy-playwright` fornece uma classe,
`ScrapyPlaywrightDownloadHandler`, que **herda** de `HTTP11DownloadHandler` (o
handler padrão do Scrapy) e sobrescreve o método `download_request`:

```python
async def download_request(self, request):
    if request.meta.get("playwright"):
        return await self._download_request(request)   # abre navegador
    return await super().download_request(request)      # HTTP puro, como sempre
```

Isso é o ponto mais importante de todo o guia: **o comportamento padrão do
Scrapy não muda**. Uma `scrapy.Request` comum, sem `meta={"playwright":
True}`, continua sendo uma requisição HTTP pura, do jeito mais rápido e
barato. Só as requisições marcadas explicitamente é que abrem um navegador de
verdade. Isso importa porque abrir um navegador é caro (memória, CPU,
tempo) — no nosso caso faz sentido pra toda página do Magazine Luiza (todas
precisam passar pelo Akamai), mas em outro projeto você pode querer misturar:
paginas simples via HTTP puro, só as protegidas via navegador.

Registramos essa troca em `settings.py`:

```python
DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}
TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"
```

A segunda linha é obrigatória: o Playwright é assíncrono via `asyncio`, e o
Scrapy roda por padrão sobre outro sistema de eventos (Twisted "puro"). Essa
configuração troca o reator do Twisted por um que roda em cima do `asyncio`,
permitindo que os dois convivam no mesmo processo.

## 4. O ciclo de vida completo de uma requisição com Playwright

Quando uma `Request` tem `meta={"playwright": True}`, isso acontece por
dentro:

1. O handler pega (ou abre, se ainda não existe) um **Browser** — um processo
   do navegador rodando em segundo plano. Isso é feito uma vez por execução
   do spider, não uma vez por página.
2. Dentro do Browser, abre um **BrowserContext** — equivalente a uma janela
   anônima/isolada (cookies, storage e config próprios). Configuramos o
   context padrão em `PLAYWRIGHT_CONTEXTS` (locale, viewport).
3. Dentro do Context, abre uma **Page** — uma aba.
4. Chama `page.goto(request.url)`. Aqui que a navegação de verdade acontece:
   o navegador manda a requisição HTTP real (por isso o TLS/fingerprint é do
   navegador, não do Scrapy).
5. Executa, em ordem, cada `PageMethod` que você colocou em
   `meta["playwright_page_methods"]` (ex.: esperar um seletor aparecer,
   clicar em algo, rolar a página, tirar screenshot).
6. Captura o HTML final (`page.content()`), o status HTTP da navegação
   principal e os headers da resposta.
7. Fecha a Page (por padrão) e devolve tudo isso como uma `Response` normal
   do Scrapy — dali pra frente, é Scrapy 100% padrão de novo: sua função
   `parse(response)` recebe um objeto `Response` comum, com `.status`,
   `.text`, `.css()`, `.xpath()` etc. O `parse()` não sabe nem precisa saber
   que por trás teve um navegador.

No nosso spider ([`busca.py`](../magazineluiza/spiders/busca.py)):

```python
yield scrapy.Request(
    url,
    meta={
        "playwright": True,
        "playwright_page_methods": [
            PageMethod("wait_for_selector", "script#__NEXT_DATA__",
                       state="attached", timeout=20000),
        ],
    },
    callback=self.parse,
)
```

O `PageMethod` é literalmente uma chamada adiada: `PageMethod("wait_for_selector", "script#__NEXT_DATA__", state="attached", timeout=20000)`
equivale a rodar `await page.wait_for_selector("script#__NEXT_DATA__", state="attached", timeout=20000)`
na aba, no passo 5 acima, antes do Scrapy ler a resposta.

## 5. Cada configuração explicada

| Configuração | O que faz | Por que está assim |
| --- | --- | --- |
| `DOWNLOAD_HANDLERS` | Troca o handler de `http`/`https` pelo do scrapy-playwright | Sem isso, `meta={"playwright": True}` não tem efeito nenhum |
| `TWISTED_REACTOR` | Faz o Scrapy rodar sobre o loop de eventos do `asyncio` | Playwright exige `asyncio`; sem essa linha o processo trava/erra |
| `PLAYWRIGHT_BROWSER_TYPE = "firefox"` | Qual motor de navegador abrir | Testamos Chromium e Firefox contra o Akamai; só o Firefox passa (ver seção 7) |
| `PLAYWRIGHT_LAUNCH_OPTIONS` | Argumentos passados pra `playwright.firefox.launch(...)` | Aqui entram as `firefox_user_prefs` que corrigem os sinais de automação (seção 7) |
| `PLAYWRIGHT_CONTEXTS` | Configuração do(s) `BrowserContext` (locale, viewport, etc.) | Sem `locale`, `navigator.languages` fica quebrado — um dos sinais que o Akamai pega |
| `PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT` | Tempo máximo pra `page.goto` completar | 30s dá folga pro Akamai processar o sensor antes de desistir |
| `PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None` | Desliga o repasse automático dos headers do Scrapy pro navegador | Sem isso, o header `User-Agent: Scrapy/...` vaza pro navegador real e quebra a consistência do fingerprint (seção 7) |
| `ROBOTSTXT_OBEY = False` | Não consulta/obedece `robots.txt` | O `robots.txt` do site também retorna `403` do Akamai — não é uma regra de disallow de verdade, é o mesmo bloqueio anti-bot |
| `CONCURRENT_REQUESTS_PER_DOMAIN = 1` / `DOWNLOAD_DELAY = 2` | Limita a 1 requisição por vez, com 2s de intervalo | Cada requisição já abre uma aba de navegador (caro); e é boa prática não sobrecarregar o site |
| `SCRAPER_BROWSER_ENGINE` (variável de ambiente) | Escolhe entre `playwright` (padrão) e `camoufox` | Ver seção 8 |

## 6. A jornada de debug (o que quebrou e por quê)

Construir isso não funcionou de primeira. Três problemas reais apareceram,
nessa ordem:

**6.1 — O spider não rodava nada.** O Scrapy 2.13+ trocou o ponto de entrada
do spider: `start_requests()` (um gerador síncrono) foi substituído por
`async def start()` (um gerador assíncrono). Definir só `start_requests` faz
o Scrapy simplesmente não chamar nada — zero requisições, zero erro visível.
A correção foi usar `async def start(self): yield scrapy.Request(...)`.

**6.2 — `403` mesmo com um navegador de verdade.** O Scrapy injeta por padrão
o header `User-Agent: Scrapy/2.18 (+https://scrapy.org)` em toda requisição.
O scrapy-playwright, por padrão, sincroniza os headers da `Request` do Scrapy
com a navegação real do navegador — ou seja, esse header ia junto,
sobrescrevendo o User-Agent que o próprio navegador mandaria. Pro Akamai,
isso é uma inconsistência: o `navigator.userAgent` que o JavaScript da página
lê é diferente do header HTTP que efetivamente chegou no servidor. Corrigido
com `PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None`.

**6.3 — Resposta de ~2KB sem dado nenhum.** Mesmo depois do `403` resolvido,
a resposta vinha pequena (2 a 2,5KB) e sem o JSON de dados da página. Olhando
o corpo, era uma página-sensor do Akamai: um HTML mínimo com um `<script>`
que roda testes no navegador, grava cookies (`_abck`, `bm_sz`, `bm_so`) e só
então decide se libera o conteúdo real — às vezes recarregando a página,
às vezes trocando o conteúdo via JS. O evento `load` do Playwright dispara
assim que essa página-sensor termina de carregar, não quando o conteúdo real
aparece. A correção foi esperar explicitamente por algo que só existe na
página real:

```python
PageMethod("wait_for_selector", "script#__NEXT_DATA__", state="attached", timeout=20000)
```

Detalhe importante: o padrão do `wait_for_selector` é esperar o elemento
ficar **visível**. Uma tag `<script>` nunca é visível (não é renderizada),
então o padrão trava até o timeout. `state="attached"` espera só o elemento
existir no DOM, que é o que precisamos aqui.

## 7. Por que Chromium falha, Firefox falha "pela metade", e o que resolveu de vez

Depois desses três ajustes, o Chromium do Playwright continuava recebendo
`403` na hora — com ou sem os patches clássicos de stealth
(`navigator.webdriver` sobrescrito via `Object.defineProperty`,
`--disable-blink-features=AutomationControlled`). O Firefox "cru" passava a
primeira barreira (chegava na página-sensor, HTTP 200) mas era negado depois
do sensor rodar.

Testamos duas hipóteses:

**Hipótese A — é o fingerprint TLS/rede.** Usamos um serviço público de
"eco" de fingerprint (`tls.peet.ws/api/all`), que devolve o JA3, JA4 e o
fingerprint HTTP/2 (estilo Akamai) que o servidor efetivamente vê na conexão.
Comparamos Firefox puro do Playwright contra o Camoufox: **os dois hashes
eram idênticos**, byte a byte. Isso descarta o TLS como o diferencial — faz
sentido, os dois usam a mesma stack de rede real do Firefox (NSS); só o
Chromium tem fingerprint diferente (motor diferente).

**Hipótese B — é algo que o JavaScript da página consegue ler.** Comparamos
alguns valores que o próprio `navigator`/`window` expõem:

| Sinal | Firefox puro (antes) | Camoufox |
| --- | --- | --- |
| `navigator.webdriver` | `true` | `false` |
| `navigator.plugins.length` | `0` | `5` |
| `navigator.languages` | `['undefined']` (quebrado) | `['en-US', 'en']` |

A primeira tentativa de corrigir isso foi um patch de JavaScript clássico
(`Object.defineProperty(navigator, 'webdriver', {get: () => undefined})` e
similares, o tipo de script usado em bibliotecas de stealth pra Chromium).
Resultado: piorou. Um desses patches adiciona `window.chrome = {runtime:
{}}` — que faz sentido pra fingir ser Chrome, mas **não existe no Firefox
de verdade**, e essa inconsistência virou, ela mesma, um sinal de bot.

O que efetivamente resolveu foi usar **preferências reais do Firefox**
(`firefox_user_prefs`), não overrides de JavaScript por cima:

```python
PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,
    "firefox_user_prefs": {
        "dom.webdriver.enabled": False,
        "marionette.enabled": False,
        "pdfjs.disabled": False,              # corrige plugins.length (0 -> 5)
        "intl.accept_languages": "pt-BR, pt, en-US, en",  # corrige navigator.languages
    },
}
PLAYWRIGHT_CONTEXTS = {
    "default": {"locale": "pt-BR", "viewport": {"width": 1280, "height": 720}},
}
```

Resultado testado 3 vezes seguidas, e depois confirmado também numa página
de produto: `200`, HTML completo (~1MB), com todos os dados. Curiosamente,
`navigator.webdriver` continuou `true` mesmo depois disso — ou seja, pra esse
site, esse sinal específico pesa menos do que normalmente se assume; o que
importou foi `plugins` e `languages` fazerem sentido.

**Diferença entre "preferência real" e "patch de JavaScript":** uma
preferência (`firefox_user_prefs`) muda o comportamento do navegador desde
antes da página carregar — é assim que o Firefox "de verdade" se comportaria
com aquela configuração. Um patch de JavaScript roda depois, por cima de um
navegador que já reportava o valor errado, e cria inconsistências sutis
(timing, `toString()` de funções sobrescritas, objetos que não deveriam
existir) que sistemas anti-bot sofisticados conseguem detectar.

## 8. Playwright puro vs. Camoufox

| | Playwright puro (padrão neste projeto) | Camoufox |
| --- | --- | --- |
| O que é | Firefox oficial, baixado pelo próprio Playwright, com preferências ajustadas manualmente por nós | Fork do Firefox recompilado especificamente pra reduzir sinais de automação |
| Dependência extra | Nenhuma além de `scrapy-playwright` | `pip install camoufox` + `python -m camoufox fetch` (~90MB) |
| Como foi validado aqui | Ajuste manual, testado contra o Akamai hoje | Já vinha funcionando antes mesmo de qualquer ajuste manual |
| Resiliência a mudanças futuras | Depende de mantermos os ajustes atualizados se o Akamai mudar as checagens | Mantido ativamente por terceiros pra acompanhar esse tipo de mudança |
| Quando trocar pra ele | — | Se o caminho padrão voltar a ser bloqueado |

Trocar de engine é uma variável de ambiente, sem editar código:

```bash
scrapy crawl busca -a termo=nivea                                   # padrao
SCRAPER_BROWSER_ENGINE=camoufox scrapy crawl busca -a termo=nivea   # alternativa
```

Em `settings.py`, isso é um `if`/`else` simples que monta
`PLAYWRIGHT_LAUNCH_OPTIONS` de um jeito ou de outro — no caminho do Camoufox,
usamos `camoufox.utils.launch_options(...)`, uma função do próprio pacote
Camoufox que devolve o dicionário de opções de lançamento (executável,
argumentos, preferências) sem precisar abrir o navegador manualmente; é o
mesmo dicionário que o `scrapy-playwright` espera em
`PLAYWRIGHT_LAUNCH_OPTIONS`, então basta substituir.

## 9. Quem é Scrapy e quem é Playwright dentro do `busca.py`

A seção 4 mostrou o ciclo de vida em geral; aqui é a mesma ideia mapeada
função por função em cima do spider real
([`magazineluiza/spiders/busca.py`](../magazineluiza/spiders/busca.py)).

| Trecho | De quem é | Por quê |
| --- | --- | --- |
| `WAIT_NEXT_DATA = PageMethod("wait_for_selector", ...)` | **Playwright puro** | É literalmente a chamada `page.wait_for_selector(...)` que vai rodar dentro da aba |
| `extrair_next_data`: `response.css(...)` | Scrapy | `response.css` é o seletor do Scrapy sobre o HTML já capturado — não existe mais navegador nesse ponto |
| `extrair_next_data`: `json.loads(...)` | Python puro | — |
| `montar_request_busca`: `scrapy.Request(url, callback=..., cb_kwargs=...)` | Scrapy | Monta a requisição, mas ainda não decide como ela será buscada |
| `montar_request_busca`: `meta={"playwright": True, "playwright_page_methods": [...]}` | **A fronteira** | Esse dict é o que o `scrapy-playwright` lê pra decidir "abrir navegador nessa aqui" — é o único ponto de contato entre os dois |
| `e_da_marca`, `texto_vendedor`, `ficha_tecnica` | Python puro | Nenhuma chamada de Scrapy nem de Playwright — só leitura de dict |
| `BuscaSpider.parse_busca` / `parse_produto` | Scrapy (+ Python puro por dentro) | Recebem um `Response` normal; tudo que fazem com ele é Scrapy/Python |
| `yield ProdutoItem(...)` | Scrapy | É assim que um resultado pronto (viraria linha do CSV) se diferencia de `yield scrapy.Request(...)` (mais uma página pra visitar) |

**A ideia central:** o Playwright só entra em ação dentro do dict `meta` de um
`scrapy.Request` — e isso acontece de forma invisível, dentro do
`ScrapyPlaywrightDownloadHandler` configurado no `settings.py`. A partir do
momento que `parse_busca` ou `parse_produto` começam a rodar, o navegador já
fechou a aba e devolveu um `Response` comum; nenhuma linha de `parse_busca`,
`parse_produto` ou das funções auxiliares (`e_da_marca`, `texto_vendedor`,
`ficha_tecnica`) chama Playwright. Se um dia for preciso interagir com a
página antes de ler o resultado (clicar em algo, rolar pra carregar mais
itens), a mudança entra na lista `playwright_page_methods`, não no meio da
lógica de parsing.

Resumindo em uma frase: **Playwright decide *como* buscar uma página (duas
linhas de configuração por `Request`); Scrapy + Python decidem *o que fazer*
com ela depois que chegou.**

## 10. Resumo de uma frase por peça

- **Scrapy**: organiza o projeto (spiders, fila de requisições, pipelines,
  exportação) e decide *quando* buscar cada URL.
- **scrapy-playwright**: substitui *como* o Scrapy busca uma URL — de HTTP
  puro pra um navegador de verdade — só quando pedido via `meta`.
- **Playwright**: a biblioteca que efetivamente controla o navegador (abrir
  aba, navegar, esperar elementos, ler o HTML final).
- **Firefox (motor)**: o navegador que o Akamai realmente vê na outra ponta;
  precisa se comportar como um Firefox real o suficiente pra passar no
  sensor deles.
- **Camoufox**: uma variante mais "blindada" do mesmo Firefox, disponível
  como opção caso a configuração manual pare de ser suficiente.
