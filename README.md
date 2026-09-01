# Magazine Luiza Product Scraper

> English first · [Português abaixo](#português)

A Scrapy project that will collect rated (star-reviewed) products from
Magazine Luiza search results — starting with the Nivea catalog — into a CSV
file. This document records the anti-bot investigation that shaped the
project's architecture and what was changed as a result.

Status: **work in progress**. Search-result parsing, the star/brand filter,
pagination, product-detail parsing and CSV export are built and tested
end to end for the Nivea catalog.

## The problem: Akamai Bot Manager

Magazine Luiza sits behind Akamai Bot Manager. A plain HTTP request — `curl`,
and by extension Scrapy's default downloader — is rejected with `403`
immediately, before any page logic runs. Even `robots.txt` returns the same
block. This meant Scrapy could not talk to the site on its own; every request
needed to go through a real browser engine.

## What I tried and what actually mattered

| Attempt | Result |
| --- | --- |
| Scrapy's default downloader (plain HTTP) | `403` instantly — confirmed via `curl` with realistic browser headers too |
| Playwright Chromium, headless, no changes | `403` instantly |
| Playwright Chromium + classic JS stealth patches (`navigator.webdriver` override, `--disable-blink-features=AutomationControlled`) | `403` instantly — patches had no effect |
| Playwright Firefox, headless, no changes | Passes the first gate (`200`), but is denied after Akamai's JS sensor runs |
| Playwright Firefox + the same generic stealth script | Worse — the script adds `window.chrome`, which does not exist on real Firefox and is itself a tell |
| **Camoufox** (hardened Firefox fork) | Works reliably |
| TLS/JA3/JA4/HTTP2 fingerprint comparison (Firefox vanilla vs. Camoufox, via a public fingerprint-echo service) | **Identical on both** — ruled out TLS as the differentiator |
| Playwright Firefox with real `firefox_user_prefs` (not JS overrides) fixing `navigator.plugins.length` and `navigator.languages`, plus a matching `locale` | **Works reliably** (verified over multiple repeated runs, at both the search-listing and product-detail pages) |

The decisive signals were `navigator.plugins.length` (`0` on stock headless
Firefox, a bot tell) and `navigator.languages` (empty/broken without an
explicit locale) — not `navigator.webdriver`, which stayed `true` throughout
and did not by itself block access. Two further fixes were required once the
browser itself passed the check:

- Scrapy's default `User-Agent` header (`Scrapy/<version> ...`) was being
  forwarded into the real browser by scrapy-playwright, contradicting the
  browser's own fingerprint. Disabled via `PLAYWRIGHT_PROCESS_REQUEST_HEADERS
  = None`.
- The first response Akamai returns is a small JS "sensor" interstitial, not
  the real page. The spider now waits for a real page marker
  (`script#__NEXT_DATA__`, Next.js's data island) before Scrapy reads the
  response, instead of trusting the browser's `load` event alone.

## Decision

The project uses **plain Playwright (Firefox) with the tuned preferences
above** as the default browser engine — no extra binary to install or manage
beyond what `pip install scrapy-playwright` already needs.

**Camoufox is kept as a selectable fallback**, since it patches many of these
signals at the browser-engine level rather than through preferences, and is
actively maintained to track anti-bot changes. If Akamai tightens its checks
and the plain-Playwright path stops working, switching engines is a one-line
change:

```bash
scrapy crawl busca -a termo=nivea                       # default: plain Playwright
SCRAPER_BROWSER_ENGINE=camoufox scrapy crawl busca -a termo=nivea  # fallback: Camoufox
```

Using Camoufox requires `pip install camoufox` and `python -m camoufox
fetch` (downloads its browser build, ~90MB); it is commented out in
`requirements.txt` for that reason.

## Architecture

```text
busca.py (Scrapy spider) ── search-result parsing, star/brand filter, pagination
    │                       product-detail parsing (title, price, seller, factsheet)
    ▼
scrapy-playwright ── routes requests through a real browser instead of
    │                 Scrapy's default HTTP downloader
    ▼
Playwright Firefox (default) or Camoufox (optional) ── the browser Akamai
    │                                                    actually sees
    ▼
CSV (Scrapy's feed export, -o file.csv)
```

## Scrapy vs. Playwright: who does what

The two only meet at one point: a `scrapy.Request` with
`meta={"playwright": True, "playwright_page_methods": [...]}`. Everything
before that dict is built with plain Scrapy/Python; everything after the
`Response` comes back is plain Scrapy/Python again — no Playwright call
happens inside a spider callback.

| | Owns |
| --- | --- |
| Playwright | Opening the browser, navigating, waiting for the page to be ready |
| scrapy-playwright | The bridge: reads `meta["playwright"]`, hands the resulting HTML back as a normal Scrapy `Response` |
| Scrapy + plain Python | Everything else: parsing the JSON, filtering, pagination, building items, CSV export |

## Main libraries

- **Scrapy:** crawling framework — spiders, scheduling, item pipelines, CSV
  export.
- **scrapy-playwright:** replaces Scrapy's downloader with a real browser for
  requests marked `meta={"playwright": True}`.
- **Playwright:** drives the browser (navigation, waiting, page content).
- **Camoufox** *(optional)*: hardened Firefox build, selectable via
  `SCRAPER_BROWSER_ENGINE=camoufox`.

## Engine modes

| Engine | How to enable | Trade-off |
| --- | --- | --- |
| Playwright (default) | nothing — default | Fewer dependencies; tuned by hand against today's Akamai checks |
| Camoufox | `SCRAPER_BROWSER_ENGINE=camoufox` | Extra ~90MB browser download; patches fingerprint signals at the engine level, likely more resilient to future changes |

## Running it

```bash
scrapy crawl busca -a termo=nivea -a max_pages=3 -o outputs/nivea.csv
```

`outputs/` is where CSV runs are saved locally; it is not committed to this
repository (see `.gitignore`) so real scraped data never gets published here.
Example output (synthetic data, not a real scrape):

```csv
termo_busca,titulo,vendido_por,preco_normal,preco_pix,estrelas,avaliacoes,marca,referencia,linha,modelo,quantidade,url
nivea,EXAMPLE Nivea Moisturizing Cream 200ml,Sold by Example Store and delivered by Magalu,29.9,26.9,4.8,120,Nivea,0000000000000,Moisturizing,Example 200ml,1 unit,https://www.magazineluiza.com.br/example-product/p/example123/
```

---

# Português

Projeto Scrapy que vai coletar produtos com avaliação (estrelas) dos
resultados de busca do Magazine Luiza — começando pelo catálogo da Nivea —
para um arquivo CSV. Este documento registra a investigação sobre o bloqueio
anti-bot que definiu a arquitetura do projeto e o que precisou ser mudado.

Status: **em andamento**. Parsing dos resultados de busca, filtro de
estrela/marca, paginação, parsing da página de produto e exportação em CSV
estão construídos e testados de ponta a ponta pro catálogo da Nivea.

## O problema: Akamai Bot Manager

O Magazine Luiza está atrás do Akamai Bot Manager. Uma requisição HTTP pura —
`curl`, e por extensão o downloader padrão do Scrapy — é rejeitada com `403`
imediatamente, antes de qualquer lógica de página rodar. Até o `robots.txt`
recebe o mesmo bloqueio. Ou seja, o Scrapy sozinho não conseguia falar com o
site; toda requisição precisava passar por um navegador de verdade.

## O que eu tentei e o que realmente importou

| Tentativa | Resultado |
| --- | --- |
| Downloader padrão do Scrapy (HTTP puro) | `403` na hora — confirmado também via `curl` com headers realistas de navegador |
| Playwright Chromium, headless, sem alterações | `403` na hora |
| Playwright Chromium + patches clássicos de JS (`navigator.webdriver` sobrescrito, `--disable-blink-features=AutomationControlled`) | `403` na hora — os patches não tiveram efeito |
| Playwright Firefox, headless, sem alterações | Passa a primeira barreira (`200`), mas é negado depois que o sensor JS do Akamai roda |
| Playwright Firefox + o mesmo script genérico de stealth | Piorou — o script adiciona `window.chrome`, que não existe no Firefox de verdade e vira ele mesmo um sinal de automação |
| **Camoufox** (fork do Firefox enrijecido) | Funciona de forma confiável |
| Comparação de fingerprint TLS/JA3/JA4/HTTP2 (Firefox puro vs. Camoufox, via um serviço público de eco de fingerprint) | **Idêntico nos dois** — descartou o TLS como o diferencial |
| Playwright Firefox com `firefox_user_prefs` reais (não patch de JS) corrigindo `navigator.plugins.length` e `navigator.languages`, mais um `locale` correspondente | **Funciona de forma confiável** (verificado em várias execuções repetidas, tanto na página de busca quanto na de produto) |

Os sinais decisivos foram `navigator.plugins.length` (`0` no Firefox headless
padrão, um sinal de automação) e `navigator.languages` (vazio/quebrado sem um
`locale` explícito) — não o `navigator.webdriver`, que continuou `true` o
tempo todo e não bloqueou o acesso sozinho. Duas outras correções foram
necessárias depois que o navegador em si passou na checagem:

- O header padrão `User-Agent: Scrapy/<versão> ...` do Scrapy estava sendo
  repassado pro navegador real pelo scrapy-playwright, contradizendo o
  fingerprint do próprio navegador. Desligado via
  `PLAYWRIGHT_PROCESS_REQUEST_HEADERS = None`.
- A primeira resposta que o Akamai devolve é uma página-sensor pequena de JS,
  não a página real. O spider agora espera um marcador real de conteúdo
  (`script#__NEXT_DATA__`, a ilha de dados do Next.js) antes do Scrapy ler a
  resposta, em vez de confiar só no evento `load` do navegador.

## Decisão

O projeto usa **Playwright puro (Firefox) com as preferências ajustadas
acima** como engine padrão — sem binário extra pra instalar ou manter além do
que `pip install scrapy-playwright` já exige.

**O Camoufox fica como opção alternativa selecionável**, já que ele corrige
muitos desses sinais no nível do próprio motor do navegador em vez de via
preferências, e é mantido ativamente pra acompanhar mudanças de anti-bot. Se
o Akamai reforçar as checagens e o caminho com Playwright puro parar de
funcionar, trocar de engine é uma mudança de uma linha:

```bash
scrapy crawl busca -a termo=nivea                       # padrao: Playwright puro
SCRAPER_BROWSER_ENGINE=camoufox scrapy crawl busca -a termo=nivea  # alternativa: Camoufox
```

Usar o Camoufox exige `pip install camoufox` e `python -m camoufox fetch`
(baixa o build do navegador dele, ~90MB); por isso ele fica comentado no
`requirements.txt`.

## Arquitetura

```text
busca.py (spider Scrapy) ── parsing dos resultados de busca, filtro de estrela/marca, paginacao
    │                       parsing da pagina de produto (titulo, preco, vendedor, ficha tecnica)
    ▼
scrapy-playwright ── roteia as requisicoes por um navegador real em vez do
    │                 downloader HTTP padrao do Scrapy
    ▼
Playwright Firefox (padrao) ou Camoufox (opcional) ── o navegador que o
    │                                                  Akamai realmente ve
    ▼
CSV (exportacao nativa do Scrapy, -o arquivo.csv)
```

## Scrapy x Playwright: quem faz o quê

Os dois só se encontram em um ponto: um `scrapy.Request` com
`meta={"playwright": True, "playwright_page_methods": [...]}`. Tudo antes
desse dict é Scrapy/Python puro; tudo depois que o `Response` volta também é
Scrapy/Python puro de novo — nenhuma chamada de Playwright acontece dentro de
um callback do spider.

| | Responsável por |
| --- | --- |
| Playwright | Abrir o navegador, navegar, esperar a página ficar pronta |
| scrapy-playwright | A ponte: lê `meta["playwright"]`, devolve o HTML resultante como um `Response` normal do Scrapy |
| Scrapy + Python puro | Todo o resto: parsing do JSON, filtros, paginação, montagem dos itens, exportação CSV |

## Principais bibliotecas

- **Scrapy:** framework de coleta — spiders, agendamento, pipelines de item,
  exportação CSV.
- **scrapy-playwright:** substitui o downloader do Scrapy por um navegador
  real para requisições marcadas com `meta={"playwright": True}`.
- **Playwright:** controla o navegador (navegação, espera, conteúdo da
  página).
- **Camoufox** *(opcional)*: build do Firefox enrijecido, selecionável via
  `SCRAPER_BROWSER_ENGINE=camoufox`.

## Modos de engine

| Engine | Como ativar | Trade-off |
| --- | --- | --- |
| Playwright (padrão) | nada — já é o padrão | Menos dependências; ajustado manualmente contra as checagens atuais do Akamai |
| Camoufox | `SCRAPER_BROWSER_ENGINE=camoufox` | ~90MB extra de download do navegador; corrige sinais de fingerprint no nível do motor, provavelmente mais resiliente a mudanças futuras |

## Executando

```bash
scrapy crawl busca -a termo=nivea -a max_pages=3 -o outputs/nivea.csv
```

`outputs/` é onde os CSVs de cada execução ficam salvos localmente; a pasta
não é versionada nesse repositório (ver `.gitignore`), então dado real
coletado nunca é publicado aqui. Exemplo de saída (dado sintético, não é uma
coleta real):

```csv
termo_busca,titulo,vendido_por,preco_normal,preco_pix,estrelas,avaliacoes,marca,referencia,linha,modelo,quantidade,url
nivea,Creme Hidratante Nivea EXEMPLO 200ml,Vendido por Loja Exemplo e entregue por Magalu,29.9,26.9,4.8,120,Nivea,0000000000000,Hidratante,Exemplo 200ml,1 unidade,https://www.magazineluiza.com.br/produto-exemplo/p/exemplo123/
```
