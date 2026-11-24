# Verificação dos arquivos vazios — dados educacionais do Piauí (SimCAQ)

> [!IMPORTANT]
> **Conclusão:** dos **34.362** arquivos vazios refeitos, **nenhum** voltou com dados novos. A API respondeu normalmente
> (HTTP 200) com lista vazia nos 34.362 casos. **O vazio é real, não foi falha de coleta**, e os arquivos que já temos
> estão corretos.

| Refeitos | Vieram com dado | Continuam vazios (HTTP 200) | Erros |
|---:|---:|---:|---:|
| **34.362** | **0** | **34.362** | **0** |

## Objetivo

Os datasets `dados_educacionais_basicos` e `dados_educacionais_basicos_microdados` foram coletados da API do SimCAQ
(`simcaq.c3sl.ufpr.br`) para municípios do Piauí, com um arquivo por consulta, organizado por categoria, fase, ano e
cruzamento. Alguns desses arquivos existem, mas estão com `"result": []`.

A pergunta era: **esse vazio é real ou a coleta falhou?**

O escopo foi mantido estreito de propósito:

- ✅ refazer a requisição **somente** dos arquivos que já existem com `[]`;
- ✅ guardar o que viesse com dado, na mesma organização e nomenclatura, e registrar o cruzamento;
- ✅ registrar o código HTTP de tudo que não viesse (404, 500, 413…);
- ❌ não testar cruzamentos novos, não fazer requisições de diagnóstico e não inventar arquivos que não existem.

## Como foi feito

```mermaid
flowchart LR
    A["34.362 arquivos<br/>com result: []"] --> B["Mesma URL<br/>(já está no meta do arquivo)"]
    B --> C{"Resposta da API"}
    C -->|"200 com dados"| D["RECUPERADO<br/>salva na pasta nova"]
    C -->|"200 com []"| E["CONTINUA_VAZIO<br/>vazio real"]
    C -->|"4xx / 5xx / rede"| F["ERRO<br/>código no log"]
```

1. **Levantamento** — listei os arquivos com `"result": []` nos dois datasets (`plano/plano_vazios.json`): 8.272 na
   básica e 26.090 na microdados. Cerca de 99% são da categoria `auxiliares`.
2. **Reexecução** — um workflow no GitHub Actions refez cada requisição, em 6 fatias, um job por vez, 8 threads e
   2 req/s, para não sobrecarregar a API.
3. **Registro** — cada arquivo gerou uma linha no log com status, HTTP, tentativas, tempo e URL.
4. **Consolidação** — o job final juntou as fatias em CSVs e num resumo.

| A API respondeu | Status no log | O que acontece |
|---|---|---|
| 200 com dados | `RECUPERADO` | salvo na pasta nova, na mesma organização do dataset |
| 200 com `[]` | `CONTINUA_VAZIO` | não grava; a API confirma que não há dado |
| 400 / 404 | `ERRO_HTTP_4XX` | não grava; código no log, sem nova tentativa |
| 500 / timeout / rede | `ERRO_HTTP_5XX` / `ERRO_REDE` | 4 tentativas com espera crescente; se persistir, código no log |

## Resultado

Execução de **28/10/2026** (run `40746741664`): todos os jobs concluídos com sucesso, cerca de 48 min por fatia,
4h47 no total. Nenhuma fatia parou antes do fim.

| Categoria | Básica | Microdados | Total | Recuperados |
|---|---:|---:|---:|---:|
| auxiliares | 8.192 | 25.862 | 34.054 | 0 |
| matriculas | 26 | 84 | 110 | 0 |
| docentes | 18 | 52 | 70 | 0 |
| turmas | 14 | 42 | 56 | 0 |
| escolas | 12 | 30 | 42 | 0 |
| funcionarios | 10 | 20 | 30 | 0 |
| **Total** | **8.272** | **26.090** | **34.362** | **0** |

Em todas as categorias e cruzamentos o resultado foi o mesmo: HTTP 200 com lista vazia.

### O que isso significa

- Os arquivos vazios que já existem nos datasets **estão corretos** e não precisam ser refeitos nem alterados.
- Não há nada para aplicar: o pacote `recuperados.tar.gz` saiu com 0 arquivos.

### O que este resultado não diz

Ele mostra que a API **não tem dado para essas consultas hoje**, mas não explica o motivo (por exemplo, se a categoria
não se aplica àquele município ou ano, ou se a API simplesmente não cobre). Investigar isso exigiria requisições de
diagnóstico, que ficaram fora do escopo.

## Onde ver os resultados

📄 **[docs/dados_nao_extraidos.md](docs/dados_nao_extraidos.md)** — o que continua sem dado, com os padrões observados
(`auxiliares`: 1.024 pares município × ano; demais categorias: só Nazária em 2007 e 2008).

📁 **[resultados/](resultados)** — cópia dos resultados no repositório:

- `continua_vazio_na_api.csv` — a lista completa dos 34.362 arquivos (a API respondeu 200 com `[]`)
- `resumo_por_cruzamento.csv` — por cruzamento: refeitos, recuperados, continuam vazios, erros
- `resumo.md` — totais por base, categoria e fase

O artefato bruto do workflow (com `log_vazios.jsonl`, uma linha por arquivo) fica em
**Actions → Refazer vazios → run `40746741664` → Artifacts → `vazios-consolidado`** e expira em 27/11/2026.

## Rodar de novo

**Actions → Refazer vazios → Run workflow.** Padrão: 6 fatias, um job por vez, 8 threads, 2 req/s (~5 h no total).
Se 25 falhas 5xx/rede seguidas ocorrerem, a fatia para sozinha.

Para aplicar um resultado no dataset local:

```
python refazer_vazios.py aplicar caminho\recuperados.tar.gz
```

Troca o arquivo vazio pelo recuperado e **nunca sobrescreve um arquivo que já tem dado**. `--dry-run` só conta.
Use `--raiz-basicos` / `--raiz-microdados` se os datasets não estiverem ao lado do script.

## Segunda etapa: dados de ensino superior

A mesma verificação, agora em **outros conjuntos, de ensino superior**, coletados da mesma API (SimCAQ) para os
municípios do Piauí. A primeira etapa (educação básica) já está concluída e **não é refeita**: aqui só roda o que
ainda não foi feito.

| Conjunto | Organização dos arquivos | Arquivos |
|---|---|---:|
| `dados_educacionais_superior` | `categoria/[fase/]ano/cruzamento/<ibge>_<MUNICIPIO>.json` | 119.840 |
| `docentes_por_escola` | `<ibge>_<MUNICIPIO>/ano/dimensao/<ano>_<escola>.json` | 48.578 |
| `docentes_por_escola_superior` | `<ibge>_<MUNICIPIO>/ano/dimensao/<ano>_<ibge>.json` | 7.168 |

### O que o levantamento encontrou (24/11/2026)

| Conjunto | Arquivos | Com dado | Vazios | % vazio | Vazios com URL no `meta` |
|---|---:|---:|---:|---:|---:|
| `dados_educacionais_superior` | 119.840 | 18.625 | **101.215** | 84,5% | 101.215 |
| `docentes_por_escola` | 48.578 | 33.618 | **14.960** | 30,8% | 0 |
| `docentes_por_escola_superior` | 7.168 | 408 | **6.760** | 94,3% | 0 |
| **Total** | **175.586** | **52.651** | **122.935** | **70,0%** | **101.215** |

Nenhum arquivo ilegível ou fora do formato.

**Os vazios aparecem sempre no grupo inteiro.** Um *grupo* é o mesmo município × ano (× escola, em
`docentes_por_escola`; × categoria e fase, em `dados_educacionais_superior`) em todos os seus cruzamentos. Quando um
grupo tem vazio, **todos** os seus cruzamentos estão vazios:

| Conjunto | Grupos com vazio | Grupo inteiro vazio | Só parte vazia |
|---|---:|---:|---:|
| `dados_educacionais_superior` | 10.122 | 10.122 | 0 |
| `docentes_por_escola` | 7.480 | 7.480 | 0 |
| `docentes_por_escola_superior` | 845 | 845 | 0 |

As tabelas por categoria e por ano estão em [`resultados/superior/levantamento.md`](resultados/superior/levantamento.md).

### Por que a reexecução foi para o CI

Na primeira etapa, o levantamento foi local e só a reexecução rodou no GitHub Actions. Aqui o volume é bem maior:
**cerca de 175 mil arquivos** e **122.935 vazios**, mais de três vezes os 34.362 da primeira etapa. Foram muitos para
rodar como o outro rodou, então **julguei melhor levar o processo para o CI** e automatizá-lo, sem depender do
computador local por horas:

- **Levantamento: local.** Ler os 175 mil arquivos um a um no disco travou o computador. Lendo direto dos zips
  (`levantar_vazios.py`), o mesmo levantamento leva segundos.
- **Reexecução: no Actions.** São 101.215 chamadas. A 2 req/s, como na primeira etapa, isso dá cerca de 14 horas. O
  workflow divide em fatias, retoma o que ficar pendente e para sozinho se a API começar a falhar.

### Reexecução

O objetivo é confirmar que **as chamadas que foram feitas** realmente devolvem vazio. Por isso, cada arquivo é refeito
com **exatamente a URL gravada no `meta` do próprio arquivo**. Nenhuma URL é montada (as 101.215 do plano foram
conferidas, uma a uma, contra os arquivos). Status, limites e pacote de saída são os mesmos da primeira etapa.

| Conjunto | Vazios | Situação |
|---|---:|---|
| `dados_educacionais_superior` | 101.215 | no plano `plano/plano_vazios_superior.json.gz` |
| `docentes_por_escola` | 14.960 | sem URL no `meta`: não há chamada registrada para refazer; ficam listados em `plano/vazios_docentes_por_escola.csv` |
| `docentes_por_escola_superior` | 6.760 | sem URL no `meta`: idem, em `plano/vazios_docentes_por_escola_superior.csv` |

**Para rodar:** Actions → **Refazer vazios (ensino superior)** → Run workflow. Padrão: 6 fatias, um job por vez,
8 threads, 2 req/s. O resultado sai no artefato `superior-consolidado`. Para um teste curto antes, use `limite` = 20.

> [!WARNING]
> Em 24/11/2026, a API respondeu `HTTP 500` ("database error") a todas as requisições, inclusive a URLs que
> funcionaram na coleta. Rode o teste curto antes da execução completa. Se a API continuar falhando, cada fatia para
> sozinha depois de 25 falhas seguidas, e o que ficou pendente vai para `plano_proxima_rodada.json.gz`.

Para aplicar os recuperados no dataset local: `python refazer_vazios.py aplicar caminho\recuperados.tar.gz`
(use `--raiz-superior` se o dataset não estiver ao lado do script).

Para refazer o levantamento:

```
python levantar_vazios.py levantamento dados_educacionais_superior.zip docentes_por_escola.zip docentes_por_escola_superior.zip
```

## Arquivos

- `refazer_vazios.py` — `planejar`, `executar`, `relatorio`, `consolidar`, `aplicar` (só biblioteca padrão)
- `refazer_lacunas.py` — motor de requisição reaproveitado (tentativas, limite de taxa, formato do arquivo)
- `plano/plano_vazios.json` — a lista dos 34.362 arquivos vazios
- `dados/_municipios_piaui.json` — os 224 municípios
- `.github/workflows/refazer_vazios.yml` — o workflow
- `levantar_vazios.py` — segunda etapa: levantamento dos vazios lendo direto dos zips
- `plano/plano_vazios_superior.json.gz` — segunda etapa: os 101.215 vazios, com a URL gravada em cada arquivo
- `plano/vazios_docentes_por_escola*.csv` — segunda etapa: os vazios dos conjuntos de docentes (sem URL no `meta`)
- `resultados/superior/levantamento.md` — segunda etapa: o levantamento completo, por categoria e por ano
- `.github/workflows/refazer_vazios_superior.yml` — segunda etapa: o workflow da reexecução
