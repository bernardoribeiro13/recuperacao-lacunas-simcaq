## Levantamento dos arquivos vazios

Arquivos com `"result": []`, lidos direto dos zips. Nenhuma requisição à API foi feita nesta etapa.

| Conjunto | Arquivos | Com dado | Vazios | % vazio | Problemas |
|---|---:|---:|---:|---:|---:|
| indicadores_macros_e_micros | 2.594 | 1.922 | **672** | 25,9% | 0 |

### Padrão dos vazios

Um *grupo* é o mesmo município × ano (× escola, em `docentes_por_escola`; × categoria e fase, em `dados_educacionais_superior`) ou o mesmo indicador × ano (nos conjuntos sem município) em todos os seus cruzamentos. Se o vazio pega o grupo **inteiro**, a indicação é de dado inexistente; se pega só **parte** dos cruzamentos, é mais cara de falha de coleta.

| Conjunto | Grupos com vazio | Grupo inteiro vazio | Só parte vazia | Vazios em grupos parciais |
|---|---:|---:|---:|---:|
| indicadores_macros_e_micros | 21 | 21 | 0 | 0 |

### indicadores_macros_e_micros

| Categoria | Fase | Arquivos | Vazios | % vazio |
|---|---|---:|---:|---:|
| dados_anos_estudo_2016_2024 | unica | 840 | 360 | 42,9% |
| dados_contagem_populacao | unica | 960 | 240 | 25,0% |
| dados_fora_escola_2007_2015 | unica | 189 | 21 | 11,1% |
| dados_matricula_bruta_etapa_fixa_2007_2025 | unica | 34 | 18 | 52,9% |
| dados_matricula_liquida_2007_2015 | unica | 36 | 4 | 11,1% |
| dados_nivel_instrucao_2016_2023 | unica | 48 | 0 | 0,0% |
| dados_populacao_fora_escola | unica | 42 | 14 | 33,3% |
| dados_taxa_analfabetismo | unica | 108 | 0 | 0,0% |
| dados_taxa_atendimento_2004_2015 | unica | 36 | 3 | 8,3% |
| dados_taxa_atendimento_2019_2024 | unica | 36 | 12 | 33,3% |
| dados_taxa_conclusao_basica_2019_2023 | unica | 108 | 0 | 0,0% |
| dados_taxa_conclusao_superior_2019_2023 | unica | 105 | 0 | 0,0% |
| dados_taxa_frequencia | unica | 20 | 0 | 0,0% |
| dados_taxa_matricula_2019_2024 | unica | 8 | 0 | 0,0% |
| dados_taxa_matricula_liquida_2019_2024 | unica | 24 | 0 | 0,0% |

| Ano | 2004 | 2005 | 2006 | 2007 | 2008 | 2009 | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Vazios | 0 | 0 | 0 | 0 | 0 | 0 | 30 | 0 | 0 | 0 | 0 | 0 | 122 | 122 | 122 | 2 | 133 | 133 | 2 | 2 | 2 | 2 |
| % vazio | 0,0% | 0,0% | 0,0% | 0,0% | 0,0% | 0,0% | 100,0% | 0,0% | 0,0% | 0,0% | 0,0% | 0,0% | 48,8% | 48,8% | 48,8% | 0,5% | 100,0% | 100,0% | 0,5% | 0,5% | 1,4% | 100,0% |

- Vazios com a URL da chamada gravada no `meta`: **0**; sem URL: **672**.
- Sem URL no `meta`, não há chamada registrada para refazer: esses vazios ficam só listados.
