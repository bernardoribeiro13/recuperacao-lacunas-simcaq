# Recuperação de lacunas — microdados educacionais do Piauí (SimCAQ)

Refaz na API do SimCAQ (`simcaq.c3sl.ufpr.br`) os municípios cujo arquivo **não existe** no dataset de microdados
(a raspagem original não gravou nada para eles). Para cada município o resultado é um destes:

| API respondeu | Status no log | O que acontece |
|---|---|---|
| 200 com dados | `CAPTURADO` | arquivo gravado |
| 200 com `[]` | `CAPTURADO_VAZIO` | arquivo gravado (o dataset já guarda vazios assim) |
| 400 / 404 | `ERRO_HTTP_4XX` | não grava; vai para o log, sem nova tentativa |
| 500 / timeout / rede | `ERRO_HTTP_5XX` / `ERRO_REDE` | 4 tentativas com espera crescente; se persistir, não grava e vai para o log |

Um 5xx no log significa "falhou depois das tentativas", não prova de que o dado não existe.

## Rodar no GitHub

**Actions → Recuperar lacunas → Run workflow.** O plano (`plano/plano_lacunas.json`) é dividido em fatias; cada fatia é um job.

| Entrada | Padrão | Para quê |
|---|---|---|
| `shards` | 24 | número de fatias (jobs) |
| `max_parallel` | 3 | jobs simultâneos. Carga na API ≈ `max_parallel` × `max_por_seg` req/s |
| `workers` / `max_por_seg` | 4 / 2 | threads e teto de req/s por job |
| `amostra` | 0 | teste: só N requisições por fatia (0 = tudo) |

Se 25 falhas 5xx/rede seguidas ocorrerem, a fatia para sozinha para não sobrecarregar a API.

## Resultado

Ao final, o artefato **`recuperados-consolidado`** (guardado 30 dias) contém:

- `recuperados.tar.gz` — os arquivos novos, na mesma organização e nomenclatura do dataset
- `capturados_com_dados.csv`, `vazios_confirmados_pela_api.csv`, `falhas_http_nao_capturados.csv` (separador `;`)
- `log_requisicoes.jsonl` — uma linha por município (status, HTTP, tentativas, URL, erro)
- `plano_proxima_rodada.json` — o que ainda falta (falhas e o que não chegou a rodar)
- `resumo.md` — contagens (também aparece na página da execução)

## Aplicar no dataset local

```
python recuperacao_lacunas\aplicar_recuperados.py caminho\recuperados.tar.gz
```

Copia cada arquivo para o dataset e para a pasta `dados_educacionais_basicos_microdados_recuperados`, sem sobrescrever nada.
Use `--dry-run` para só contar.

## Próxima rodada (falhas)

Substitua `plano/plano_lacunas.json` pelo `plano_proxima_rodada.json` do artefato, faça commit e rode o workflow de novo.
Alternativa: regenerar o plano a partir do dataset local com `python refazer_lacunas.py planejar`.

## Arquivos

- `refazer_lacunas.py` — `planejar`, `executar`, `relatorio` (só biblioteca padrão)
- `consolidar.py` — junta logs e gera pacote/relatórios dos shards
- `aplicar_recuperados.py` — aplica o pacote ao dataset local
- `dados/_municipios_piaui.json` — 224 municípios (códigos IBGE e nomes dos arquivos)
- `plano/plano_lacunas.json` — lacunas a requisitar (gerado do dataset local)
- `.github/workflows/recuperar.yml`
