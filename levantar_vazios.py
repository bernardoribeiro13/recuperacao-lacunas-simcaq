#!/usr/bin/env python3
"""Levanta os arquivos VAZIOS ("result": []) de um ou mais conjuntos de dados, lendo direto dos zips (ou de pastas).

So identifica; nao faz nenhuma requisicao a API. Roda localmente em segundos: ler do zip evita abrir arquivo por
arquivo no disco, que era o que tornava o levantamento lento. A reexecucao fica no GitHub Actions (refazer_vazios.yml).

Uso:
  python levantar_vazios.py <pasta_saida> conjunto1.zip conjunto2.zip ...

Cada zip (ou pasta) e um conjunto; o nome do conjunto e o nome do arquivo sem .zip. Dois layouts sao reconhecidos:
  categoria/[fase/]ano/cruzamento/<ibge>_<MUNICIPIO>.json      (ex.: dados_educacionais_superior)
  <ibge>_<MUNICIPIO>/ano/dimensao/<ano>_<id>.json               (ex.: docentes_por_escola, docentes_por_escola_superior)

Saida em <pasta_saida>:
  vazios_<conjunto>.csv          um arquivo vazio por linha
  grupos_parciais_<conjunto>.csv grupos (municipio x ano [x escola]) em que so parte dos cruzamentos esta vazia
  problemas.csv                  arquivos ilegiveis ou fora do formato (so se houver)
  plano_vazios_<conjunto>.json.gz  os vazios com a URL gravada no proprio arquivo (so os que tem URL no meta)
  resumo.md                      totais, por categoria, por ano e o padrao dos vazios

Somente biblioteca padrao.
"""
import csv
import gzip
import json
import os
import re
import sys
import time
import zipfile
from collections import Counter, defaultdict

RE_ANO = re.compile(r"^\d{4}$")
RE_MUN = re.compile(r"^(\d{7})_(.+)$")
LIMITE = 4096  # um arquivo com "result": [] tem so o meta (< 1 KB); acima disso tem dado e nem precisa ser lido


def fmt(n):
    return f"{n:,}".replace(",", ".")


def pct(a, b):
    return f"{100 * a / b:.1f}%".replace(".", ",") if b else "-"


# ---------------------------------------------------------------- leitura
def entradas(fonte):
    """Gera (caminho relativo com '/', tamanho, funcao que devolve os bytes) de cada arquivo do zip ou da pasta."""
    if zipfile.is_zipfile(fonte):
        zf = zipfile.ZipFile(fonte)
        for i in zf.infolist():
            if not i.is_dir():
                yield i.filename.replace("\\", "/"), i.file_size, (lambda i=i: zf.read(i))
    else:
        for dp, dn, fn in os.walk(fonte):
            dn[:] = [d for d in dn if d != ".git"]
            for n in fn:
                c = os.path.join(dp, n)
                yield os.path.relpath(c, fonte).replace(os.sep, "/"), os.path.getsize(c), \
                    (lambda c=c: open(c, "rb").read())


def tirar_prefixo(itens):
    """Remove pastas de cima que sao comuns a todos os arquivos (ex.: 'dados_educacionais_superior/')."""
    while True:
        primeiros = {p.split("/", 1)[0] for p, _, _ in itens}
        if len(primeiros) != 1 or any("/" not in p for p, _, _ in itens):
            return itens
        itens = [(p.split("/", 1)[1], t, f) for p, t, f in itens]


def descrever(partes):
    """-> (layout, categoria, fase, ano, cruzamento, cod, municipio, escola) ou None se fora do padrao."""
    m = RE_MUN.match(partes[0])
    if m and len(partes) == 4:  # <ibge>_<MUN>/ano/dimensao/<ano>_<id>.json
        ident = partes[3][:-5].split("_", 1)[-1]
        escola = ident if ident != m.group(1) else ""
        return "municipio", "docentes", "unica", partes[1], partes[2], m.group(1), m.group(2), escola
    if len(partes) in (4, 5):  # categoria/[fase/]ano/cruzamento/<ibge>_<MUN>.json
        fase, i = ("unica", 1) if RE_ANO.match(partes[1]) else (partes[1], 2)
        if len(partes) != i + 3 or not RE_ANO.match(partes[i]):
            return None
        a = RE_MUN.match(partes[-1][:-5])
        if not a:
            return None
        return "categoria", partes[0], fase, partes[i], partes[i + 1], a.group(1), a.group(2), ""
    return None


# ---------------------------------------------------------------- levantamento
def levantar(fonte):
    conjunto = os.path.basename(fonte.rstrip("/\\"))
    conjunto = conjunto[:-4] if conjunto.lower().endswith(".zip") else conjunto
    itens = tirar_prefixo(list(entradas(fonte)))
    cont = Counter()
    vazios, problemas = [], []
    por_cat = defaultdict(Counter)    # (categoria, fase) -> arquivos/vazios
    por_ano = defaultdict(Counter)    # ano -> arquivos/vazios
    grupos = defaultdict(Counter)     # (categoria, fase, ano, cod, escola) -> arquivos/vazios
    modelos = {}                      # pasta -> meta do primeiro arquivo legivel (para o plano)
    for rel, tam, ler in itens:
        partes = rel.split("/")
        if len(partes) == 1:
            cont["fora_do_padrao"] += 1  # ex.: _municipios_piaui.json na raiz
            continue
        d = descrever(partes) if rel.endswith(".json") else None
        if d is None:
            cont["fora_do_padrao"] += 1
            problemas.append((conjunto, rel, "fora do padrao de pastas"))
            continue
        layout, cat, fase, ano, cruz, cod, mun, esc = d
        cont["arquivos"] += 1
        por_cat[(cat, fase)]["arquivos"] += 1
        por_ano[ano]["arquivos"] += 1
        gk = (cat, fase, ano, cod, esc)
        grupos[gk]["arquivos"] += 1
        if tam > LIMITE:
            continue
        try:
            j = json.loads(ler().decode("utf-8-sig"))
        except Exception as e:
            cont["ilegivel"] += 1
            problemas.append((conjunto, rel, f"ilegivel: {e}"[:200]))
            continue
        if not (isinstance(j, dict) and isinstance(j.get("result"), list)):
            cont["sem_result"] += 1
            problemas.append((conjunto, rel, "sem 'result' em lista"))
            continue
        meta = j.get("meta") if isinstance(j.get("meta"), dict) else {}
        pasta = "/".join(partes[:-1])
        if meta.get("url") and pasta not in modelos:
            modelos[pasta] = meta
        if j["result"]:
            continue
        cont["vazios"] += 1
        por_cat[(cat, fase)]["vazios"] += 1
        por_ano[ano]["vazios"] += 1
        grupos[gk]["vazios"] += 1
        vazios.append({"conjunto": conjunto, "categoria": cat, "fase": fase, "ano": ano, "cruzamento": cruz,
                       "cod": cod, "municipio": mun, "escola": esc, "arquivo": rel, "url": meta.get("url", ""),
                       "_layout": layout, "_pasta": pasta})
    cont["com_dado"] = cont["arquivos"] - cont["vazios"] - cont["ilegivel"] - cont["sem_result"]
    return {"conjunto": conjunto, "cont": cont, "vazios": vazios, "problemas": problemas, "por_cat": por_cat,
            "por_ano": por_ano, "grupos": grupos, "modelos": modelos}


# ---------------------------------------------------------------- saida
def escrever_csv(caminho, cols, linhas):
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        w.writerows(linhas)


def gravar(r, saida):
    c = r["conjunto"]
    chave = lambda v: (v["categoria"], v["fase"], v["ano"], v["cruzamento"], v["cod"], v["escola"])
    r["vazios"].sort(key=chave)
    cols = ["conjunto", "categoria", "fase", "ano", "cruzamento", "cod", "municipio", "escola", "arquivo", "url"]
    escrever_csv(os.path.join(saida, f"vazios_{c}.csv"), cols, ([v[k] for k in cols] for v in r["vazios"]))

    parciais = [(k, n) for k, n in sorted(r["grupos"].items()) if 0 < n["vazios"] < n["arquivos"]]
    escrever_csv(os.path.join(saida, f"grupos_parciais_{c}.csv"),
                 ["conjunto", "categoria", "fase", "ano", "cod", "escola", "arquivos", "vazios"],
                 ([c, *k, n["arquivos"], n["vazios"]] for k, n in parciais))

    # plano no formato de plano/plano_vazios.json (base, rel, meta_modelo, vazios) + "urls": a URL gravada em cada
    # arquivo vazio, exatamente como esta no meta. So entram os vazios que tem URL; nenhuma URL e montada.
    pastas = defaultdict(dict)
    for v in r["vazios"]:
        if v["_layout"] == "categoria" and v["url"]:
            pastas[v["_pasta"]][int(v["cod"])] = v["url"]
    if pastas:
        plano = {"gerado_em": time.strftime("%Y-%m-%dT%H:%M:%S"),
                 "pastas": [{"base": c, "rel": p, "meta_modelo": r["modelos"][p], "vazios": sorted(urls),
                             "urls": {str(k): urls[k] for k in sorted(urls)}}
                            for p, urls in sorted(pastas.items())]}
        with gzip.open(os.path.join(saida, f"plano_vazios_{c}.json.gz"), "wt", encoding="utf-8") as f:
            json.dump(plano, f, ensure_ascii=False)
    r["n_parciais"] = len(parciais)
    r["n_plano"] = sum(len(v) for v in pastas.values())


def resumo(rs, saida):
    md = ["## Levantamento dos arquivos vazios", "",
          "Arquivos com `\"result\": []`, lidos direto dos zips. Nenhuma requisição à API foi feita nesta etapa.", "",
          "| Conjunto | Arquivos | Com dado | Vazios | % vazio | Problemas |", "|---|---:|---:|---:|---:|---:|"]
    for r in rs:
        k = r["cont"]
        md.append(f"| {r['conjunto']} | {fmt(k['arquivos'])} | {fmt(k['com_dado'])} | **{fmt(k['vazios'])}** | "
                  f"{pct(k['vazios'], k['arquivos'])} | {fmt(k['ilegivel'] + k['sem_result'])} |")

    md += ["", "### Padrão dos vazios", "",
           "Um *grupo* é o mesmo município × ano (× escola, em `docentes_por_escola`; × categoria e fase, em "
           "`dados_educacionais_superior`) em todos os seus cruzamentos. Se o vazio pega o grupo **inteiro**, "
           "a indicação é de dado inexistente; se pega só **parte** dos cruzamentos, é mais cara de falha de coleta.",
           "", "| Conjunto | Grupos com vazio | Grupo inteiro vazio | Só parte vazia | Vazios em grupos parciais |",
           "|---|---:|---:|---:|---:|"]
    for r in rs:
        com = [n for n in r["grupos"].values() if n["vazios"]]
        inteiros = sum(1 for n in com if n["vazios"] == n["arquivos"])
        parc = [n for n in com if n["vazios"] < n["arquivos"]]
        md.append(f"| {r['conjunto']} | {fmt(len(com))} | {fmt(inteiros)} | {fmt(len(parc))} | "
                  f"{fmt(sum(n['vazios'] for n in parc))} |")

    for r in rs:
        md += ["", f"### {r['conjunto']}", "", "| Categoria | Fase | Arquivos | Vazios | % vazio |",
               "|---|---|---:|---:|---:|"]
        for (cat, fase), n in sorted(r["por_cat"].items()):
            md.append(f"| {cat} | {fase} | {fmt(n['arquivos'])} | {fmt(n['vazios'])} | {pct(n['vazios'], n['arquivos'])} |")
        anos = sorted(r["por_ano"])
        md += ["", "| Ano | " + " | ".join(anos) + " |", "|---|" + "---:|" * len(anos),
               "| Vazios | " + " | ".join(fmt(r["por_ano"][a]["vazios"]) for a in anos) + " |",
               "| % vazio | " + " | ".join(pct(r["por_ano"][a]["vazios"], r["por_ano"][a]["arquivos"]) for a in anos) + " |"]
        sem_url = sum(1 for v in r["vazios"] if not v["url"])
        if r["vazios"]:
            md += ["", f"- Vazios com a URL da chamada gravada no `meta`: **{fmt(len(r['vazios']) - sem_url)}**"
                       f"; sem URL: **{fmt(sem_url)}**."]
        if sem_url:
            md.append("- Sem URL no `meta`, não há chamada registrada para refazer: esses vazios ficam só listados.")
    texto = "\n".join(md) + "\n"
    with open(os.path.join(saida, "resumo.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    return texto


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    saida, fontes = sys.argv[1], sys.argv[2:]
    os.makedirs(saida, exist_ok=True)
    rs, problemas = [], []
    for fonte in fontes:
        t0 = time.time()
        r = levantar(fonte)
        gravar(r, saida)
        rs.append(r)
        problemas += r["problemas"]
        k = r["cont"]
        print(f"{r['conjunto']}: {fmt(k['arquivos'])} arquivos, {fmt(k['vazios'])} vazios, "
              f"{fmt(len(r['problemas']))} problemas ({time.time() - t0:.0f}s)", flush=True)
    if problemas:
        escrever_csv(os.path.join(saida, "problemas.csv"), ["conjunto", "arquivo", "problema"], problemas)
    texto = resumo(rs, saida)
    print("\n" + texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texto)


if __name__ == "__main__":
    main()
