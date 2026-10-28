# Refazer os arquivos vazios dos datasets educacionais do Piauí (SimCAQ)

Alguns arquivos dos datasets `dados_educacionais_basicos` e `dados_educacionais_basicos_microdados` estão com
`"result": []`. Este repositório **refaz a requisição de cada um** (a URL já está no `meta` do arquivo) para saber se
o vazio é real ou foi falha da raspagem. Só os arquivos que já existem vazios entram; nada é inventado.

| A API respondeu | Status no log | O que acontece |
|---|---|---|
| 200 com dados | `RECUPERADO` | salvo na pasta nova, na mesma organização e nomenclatura do dataset |
| 200 com `[]` | `CONTINUA_VAZIO` | não grava; a API confirma que não há dado |
| 400 / 404 | `ERRO_HTTP_4XX` | não grava; código no log, sem nova tentativa |
| 500 / timeout / rede | `ERRO_HTTP_5XX` / `ERRO_REDE` | 4 tentativas com espera crescente; se persistir, código no log |

O plano está em `plano/plano_vazios.json` (8.272 vazios na básica, 26.090 na microdados; `auxiliares` por último).

## Rodar

**Actions → Refazer vazios → Run workflow.** Padrão: 6 fatias, um job por vez, 8 threads, 2 req/s (~5 h no total).
Se 25 falhas 5xx/rede seguidas ocorrerem, a fatia para sozinha.

## Resultado (artefato `vazios-consolidado`)

- `recuperados_com_dados.csv` — o que tinha `[]` e agora veio com dado, com base, categoria, fase, ano e **cruzamento**
- `continua_vazio_na_api.csv` — a API respondeu 200 com `[]`: vazio real
- `erros_http.csv` — código HTTP, tentativas e trecho da resposta
- `resumo_por_cruzamento.csv` — por cruzamento: quantos foram refeitos, recuperados, continuam vazios, erros
- `log_vazios.jsonl` — um registro por arquivo; `resumo.md`; `plano_proxima_rodada.json` (erros e o que não rodou)
- `recuperados.tar.gz` — os arquivos novos

## Aplicar no dataset local

```
python refazer_vazios.py aplicar caminho\recuperados.tar.gz
```

Troca o arquivo vazio pelo recuperado. **Nunca sobrescreve um arquivo que já tem dado.** `--dry-run` só conta.
(Use `--raiz-basicos` / `--raiz-microdados` se os datasets não estiverem ao lado do script.)

## Arquivos

- `refazer_vazios.py` — `planejar`, `executar`, `relatorio`, `consolidar`, `aplicar` (só biblioteca padrão)
- `refazer_lacunas.py` — motor de requisição reaproveitado (tentativas, limite de taxa, formato do arquivo)
- `dados/_municipios_piaui.json` — 224 municípios
