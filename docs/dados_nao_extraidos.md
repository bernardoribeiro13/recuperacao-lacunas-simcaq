# Dados que não foram extraídos, mesmo após as retentativas

Este documento registra o que **continua sem dado** depois de refazer a requisição de cada arquivo vazio dos datasets
`dados_educacionais_basicos` e `dados_educacionais_basicos_microdados` (execução de 28/10/2026, run `40746741664`).
O contexto, o objetivo e o método estão no [README](../README.md).

## Resumo

| | Arquivos |
|---|---:|
| Vazios refeitos | 34.362 |
| Voltaram com dado | 0 |
| **Continuam vazios — a API responde HTTP 200 com `[]`** | **34.362** |
| Erros de requisição (4xx/5xx/rede) que persistiram após as retentativas | 0 |
| Não executados (fatia interrompida) | 0 |

As retentativas (4 tentativas com espera crescente em erros 5xx/rede) não chegaram a ser necessárias: **nenhuma
requisição falhou**. O que ficou sem dado ficou porque a **própria API não tem dado** para aquela consulta.

| Categoria | Básica | Microdados | Total |
|---|---:|---:|---:|
| auxiliares | 8.192 | 25.862 | 34.054 |
| matriculas | 26 | 84 | 110 |
| docentes | 18 | 52 | 70 |
| turmas | 14 | 42 | 56 |
| escolas | 12 | 30 | 42 |
| funcionarios | 10 | 20 | 30 |
| **Total** | **8.272** | **26.090** | **34.362** |

## O que se observa nos dados

Os vazios não estão espalhados ao acaso, o que reforça que são reais e não falha de coleta. Há dois padrões.

### 1. `auxiliares` (34.054 arquivos): 1.024 pares município × ano sem dado

- Afeta **178 municípios** e os anos de 2007 a 2020, **nas duas bases**.
- Em cada par município × ano afetado, o vazio aparece **em todos os cruzamentos de uma vez**: 8 de 8 na básica e
  22 a 28 cruzamentos na microdados. Uma falha de coleta atingiria cruzamentos isolados; aqui é o município/ano
  inteiro que não tem esse dado.
- Os 1.024 pares são os mesmos nas duas bases (1.024 × 8 = 8.192 arquivos na básica).

Pares município × ano sem dado de `auxiliares`, por ano:

| Ano | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | Total |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Municípios | 67 | 76 | 83 | 78 | 80 | 74 | 58 | 77 | 70 | 76 | 75 | 57 | 69 | 84 | **1.024** |

### 2. Demais categorias (308 arquivos): um único município, em dois anos

- Todos os 308 arquivos de `matriculas`, `docentes`, `turmas`, `escolas` e `funcionarios` são do município de
  **Nazária (código IBGE 2206720)**, e **somente dos anos de 2007 e 2008** (154 em cada ano).
- Nenhum outro município tem vazio fora de `auxiliares`.
- Hipótese, **não verificada**: Nazária ainda não existia como município nesses anos. Vale confirmar com o IBGE
  antes de afirmar.

## O que isso não diz

Os dados mostram **onde** a API não tem dado, mas não **por que**. Para `auxiliares`, por exemplo, não foi apurado se a
categoria simplesmente não se aplica a esses municípios e anos ou se a API não os cobre. Investigar exigiria
requisições de diagnóstico, que ficaram fora do escopo.

## Onde está a lista completa

Em [`resultados/`](../resultados):

- [`continua_vazio_na_api.csv`](../resultados/continua_vazio_na_api.csv) — **os 34.362 arquivos**, um por linha, com
  base, categoria, fase, ano, cruzamento, código e nome do município e a URL consultada.
- [`resumo_por_cruzamento.csv`](../resultados/resumo_por_cruzamento.csv) — por cruzamento: refeitos, recuperados,
  continuam vazios, erros.
- [`resumo.md`](../resultados/resumo.md) — totais por base, categoria e fase, como saiu do workflow.

Para rodar a mesma verificação de novo, veja a seção "Rodar de novo" do [README](../README.md).
