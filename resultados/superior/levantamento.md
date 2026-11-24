## Levantamento dos arquivos vazios

Arquivos com `"result": []`, lidos direto dos zips. Nenhuma requisição à API foi feita nesta etapa.

| Conjunto | Arquivos | Com dado | Vazios | % vazio | Problemas |
|---|---:|---:|---:|---:|---:|
| dados_educacionais_superior | 119.840 | 18.625 | **101.215** | 84,5% | 0 |
| docentes_por_escola | 48.578 | 33.618 | **14.960** | 30,8% | 0 |
| docentes_por_escola_superior | 7.168 | 408 | **6.760** | 94,3% | 0 |

### Padrão dos vazios

Um *grupo* é o mesmo município × ano (× escola, em `docentes_por_escola`; × categoria e fase, em `dados_educacionais_superior`) em todos os seus cruzamentos. Se o vazio pega o grupo **inteiro**, a indicação é de dado inexistente; se pega só **parte** dos cruzamentos, é mais cara de falha de coleta.

| Conjunto | Grupos com vazio | Grupo inteiro vazio | Só parte vazia | Vazios em grupos parciais |
|---|---:|---:|---:|---:|
| dados_educacionais_superior | 10.122 | 10.122 | 0 | 0 |
| docentes_por_escola | 7.480 | 7.480 | 0 | 0 |
| docentes_por_escola_superior | 845 | 845 | 0 | 0 |

### dados_educacionais_superior

| Categoria | Fase | Arquivos | Vazios | % vazio |
|---|---|---:|---:|---:|
| cursos | classico | 22.176 | 17.050 | 76,9% |
| cursos | moderno | 8.064 | 7.182 | 89,1% |
| docentes | classico | 31.360 | 29.862 | 95,2% |
| docentes | moderno_ente | 3.136 | 2.947 | 94,0% |
| instituicoes | unica | 9.408 | 8.934 | 95,0% |
| matriculas | classico | 32.256 | 25.760 | 79,9% |
| matriculas | moderno | 13.440 | 9.480 | 70,5% |

| Ano | 2010 | 2011 | 2012 | 2013 | 2014 | 2015 | 2016 | 2017 | 2018 | 2019 | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Vazios | 3.638 | 8.503 | 8.459 | 8.475 | 8.540 | 8.472 | 8.399 | 8.323 | 8.169 | 8.093 | 4.902 | 4.848 | 6.274 | 6.120 |
| % vazio | 95,5% | 86,3% | 85,8% | 86,0% | 86,6% | 86,0% | 85,2% | 84,4% | 82,9% | 82,1% | 81,1% | 80,2% | 82,4% | 80,4% |

- Vazios com a URL da chamada gravada no `meta`: **101.215**; sem URL: **0**.

### docentes_por_escola

| Categoria | Fase | Arquivos | Vazios | % vazio |
|---|---|---:|---:|---:|
| docentes | unica | 48.578 | 14.960 | 30,8% |

| Ano | 2021 | 2022 | 2023 | 2024 |
|---|---:|---:|---:|---:|
| Vazios | 4.714 | 3.878 | 3.390 | 2.978 |
| % vazio | 35,5% | 31,5% | 29,0% | 26,4% |

- Vazios com a URL da chamada gravada no `meta`: **0**; sem URL: **14.960**.
- Sem URL no `meta`, não há chamada registrada para refazer: esses vazios ficam só listados.

### docentes_por_escola_superior

| Categoria | Fase | Arquivos | Vazios | % vazio |
|---|---|---:|---:|---:|
| docentes | unica | 7.168 | 6.760 | 94,3% |

| Ano | 2020 | 2021 | 2022 | 2023 |
|---|---:|---:|---:|---:|
| Vazios | 1.704 | 1.688 | 1.688 | 1.680 |
| % vazio | 95,1% | 94,2% | 94,2% | 93,8% |

- Vazios com a URL da chamada gravada no `meta`: **0**; sem URL: **6.760**.
- Sem URL no `meta`, não há chamada registrada para refazer: esses vazios ficam só listados.
