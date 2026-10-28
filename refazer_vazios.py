#!/usr/bin/env python3
"""Refaz a requisicao dos arquivos que estao VAZIOS ("result": []) nos dois datasets (basicos e microdados).

Para cada arquivo vazio a URL ja esta no proprio meta; a requisicao e repetida e o resultado classificado:
  RECUPERADO       HTTP 200 com dados   -> salva na pasta nova (e, com --gravar-no-dataset, substitui o vazio)
  CONTINUA_VAZIO   HTTP 200 com []      -> nao grava; a API confirma que nao ha dado
  ERRO_HTTP_4XX / ERRO_HTTP_5XX / ERRO_REDE / ERRO_RESPOSTA  -> nao grava; o codigo vai para o log

Comandos:
  planejar    varre os datasets e lista os arquivos vazios (plano_vazios.json)
  executar    refaz as requisicoes (aceita --shard/--shards e e retomavel)
  relatorio   regera os CSVs a partir do log
  consolidar  junta os logs/pacotes dos shards (usado pelo workflow)
  aplicar     substitui, no dataset local, os vazios pelos dados recuperados (nunca sobrescreve dado)

Usa o motor de requisicao de refazer_lacunas.py. Somente biblioteca padrao.
"""
import argparse
import csv
import glob
import json
import os
import queue
import sys
import tarfile
import threading
import time
from collections import Counter, defaultdict

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import refazer_lacunas as rl  # noqa: E402

BASES = {"basicos": "dados_educacionais_basicos", "microdados": "dados_educacionais_basicos_microdados"}
SUB_RAIZ = {"basicos": os.path.join("dados_educacionais_basicos", "dados_educacionais_basicos"),
            "microdados": os.path.join("dados_educacionais_basicos_microdados (2)",
                                       "dados_educacionais_basicos_microdados")}
DONE = ("RECUPERADO", "CONTINUA_VAZIO")
MARGEM = 20


def achar(sub):
    """Os datasets ficam ao lado do script ou uma pasta acima (quando o script esta no repositorio)."""
    for base in (AQUI, os.path.dirname(AQUI)):
        if os.path.isdir(os.path.join(base, sub)):
            return os.path.join(base, sub)
    return os.path.join(AQUI, sub)


def achar_municipios():
    for p in (os.path.join(AQUI, "dados", "_municipios_piaui.json"),
              os.path.join(achar(SUB_RAIZ["basicos"]), "_municipios_piaui.json")):
        if os.path.exists(p):
            return p
    return os.path.join(AQUI, "dados", "_municipios_piaui.json")


# ---------------------------------------------------------------- planejar
def folhas(raiz):
    """Gera (pasta, [(nome, tamanho, caminho)]) de cada pasta que tem arquivos <ibge>_*.json."""
    pilha = [raiz]
    while pilha:
        d = pilha.pop()
        subs, arqs = [], []
        with os.scandir(d) as it:
            for e in it:
                if e.is_dir(follow_symlinks=False):
                    if e.name != ".git":
                        subs.append(e.path)
                elif rl.RE_ARQ.match(e.name):
                    arqs.append((e.name, e.stat().st_size, e.path))
        pilha.extend(subs)
        if arqs:
            yield d, arqs


def cmd_planejar(args):
    excluir = set()
    if args.excluir_log:
        with open(args.excluir_log, encoding="utf-8") as f:
            for linha in f:
                try:
                    r = json.loads(linha)
                except ValueError:
                    continue
                if r.get("status") == "CAPTURADO_VAZIO" and r.get("arquivo_dataset"):
                    excluir.add(("microdados", r["pasta"], r["cod"]))
    pastas, ilegiveis, t0 = [], [], time.time()
    for base, raiz in (("basicos", args.raiz_basicos), ("microdados", args.raiz_microdados)):
        for d, arqs in folhas(raiz):
            modelo = E = None
            for _, _, caminho in arqs[:5]:
                j = rl.ler_json(caminho)
                if isinstance(j, dict) and isinstance(j.get("meta"), dict) and j["meta"].get("url"):
                    modelo = j["meta"]
                    E = len(rl.montar_texto(modelo, []).replace("\n", "\r\n").encode("utf-8"))
                    break
            if modelo is None:
                ilegiveis.append(d)
                continue
            rel = "/".join(os.path.relpath(d, raiz).split(os.sep))
            vazios = []
            for nome, tam, caminho in arqs:
                if tam > E + MARGEM:
                    continue  # grande demais para ser um result []
                j = rl.ler_json(caminho)
                if isinstance(j, dict) and isinstance(j.get("result"), list) and not j["result"]:
                    cod = int(nome[:7])
                    if (base, rel, cod) not in excluir:
                        vazios.append(cod)
            if vazios:
                pastas.append({"base": base, "rel": rel, "meta_modelo": modelo, "vazios": sorted(vazios)})
        print(f"{base}: varrido ({time.time()-t0:.0f}s)", flush=True)
    # auxiliares por ultimo: sao 99% dos vazios e quase todos municipios sem dado; o resto sai primeiro
    pastas.sort(key=lambda p: (rl.descrever(p["rel"])[0] == "auxiliares", p["base"], p["rel"]))
    os.makedirs(args.logs, exist_ok=True)
    destino = args.plano or os.path.join(args.logs, "plano_vazios.json")
    os.makedirs(os.path.dirname(os.path.abspath(destino)), exist_ok=True)
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({"gerado_em": rl.agora(), "pastas": pastas}, f, ensure_ascii=False)
    por = Counter()
    for p in pastas:
        por[(p["base"], rl.descrever(p["rel"])[0], rl.descrever(p["rel"])[1])] += len(p["vazios"])
    print(f"plano gravado em {destino}")
    print(f"pastas com vazio: {len(pastas)}   arquivos vazios: {sum(por.values())}")
    for (b, cat, fase), n in sorted(por.items()):
        print(f"  {b:11s}{cat:13s}{fase:9s}{n:7d}")
    if excluir:
        print(f"(ignorados {len(excluir)} vazios criados por mim na execucao local anterior: {args.excluir_log})")
    if ilegiveis:
        print(f"ATENCAO: {len(ilegiveis)} pastas sem arquivo-modelo legivel (ignoradas)")


# ---------------------------------------------------------------- log
def carregar_log(caminho):
    ultimo = {}
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        r = json.loads(linha)
                    except ValueError:
                        continue
                    ultimo[(r["base"], r["pasta"], r["cod"])] = r
    return ultimo


# ---------------------------------------------------------------- executar
def substituir_vazio(caminho, texto):
    """Troca o arquivo vazio pelo com dado. Nunca sobrescreve um arquivo que ja tem dado."""
    if os.path.exists(caminho):
        d = rl.ler_json(caminho)
        if isinstance(d, dict) and d.get("result"):
            return "ja_tinha_dado"
        acao = "substituido"
    else:
        acao = "criado"
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(texto)
    os.replace(tmp, caminho)
    return acao


def cmd_executar(args):
    M = rl.carregar_municipios(args.municipios)
    arq_plano = args.plano or os.path.join(args.logs, "plano_vazios.json")
    if not os.path.exists(arq_plano):
        sys.exit(f"plano nao encontrado ({arq_plano}); rode: python refazer_vazios.py planejar")
    plano = json.load(open(arq_plano, encoding="utf-8"))
    arq_log = os.path.join(args.logs, "log_vazios.jsonl")
    ja = carregar_log(arq_log)
    itens, no_log = [], 0
    for p in plano["pastas"]:
        for cod in p["vazios"]:
            ant = ja.get((p["base"], p["rel"], cod))
            if ant and not (args.repetir_erros and ant["status"] in rl.FALHAS):
                no_log += 1
                continue
            itens.append({"base": p["base"], "rel": p["rel"], "cod": cod, "municipio": M[cod],
                          "arquivo": rl.nome_arquivo(cod, M[cod]), "modelo": p["meta_modelo"]})
    print(f"vazios a refazer: {len(itens)}   (ja registrados no log: {no_log})")
    if args.shards > 1:
        itens = itens[args.shard::args.shards]
        print(f"shard {args.shard + 1}/{args.shards}: {len(itens)} requisicoes")
    if args.limite:
        itens = itens[:args.limite]
    if not itens:
        print("nada a fazer.")
        return cmd_relatorio(args)

    os.makedirs(args.logs, exist_ok=True)
    fila = queue.Queue()
    for it in itens:
        fila.put(it)
    total, parar = len(itens), threading.Event()
    limitador, trava = rl.Limitador(args.max_por_seg), threading.Lock()
    contagem, seguidas, feitos = Counter(), [0], [0]
    t0 = time.monotonic()
    flog = open(arq_log, "a", encoding="utf-8")
    raizes = {"basicos": args.raiz_basicos, "microdados": args.raiz_microdados}

    def registrar(it, status, http_, tent, result, erro, dur, url, dest_nv, dest_ds, obs):
        cat, fase, ano, cruz = rl.descrever(it["rel"])
        reg = {"ts": rl.agora(), "base": it["base"], "pasta": it["rel"], "categoria": cat, "fase": fase, "ano": ano,
               "cruzamento": cruz, "cod": it["cod"], "municipio": it["municipio"], "status": status, "http": http_,
               "tentativas": tent, "linhas": None if result is None else len(result), "duracao_s": round(dur, 1),
               "url": url, "arquivo_novo": dest_nv, "arquivo_dataset": dest_ds, "erro": erro, "obs": obs}
        with trava:
            flog.write(json.dumps(reg, ensure_ascii=False) + "\n")
            flog.flush()
            contagem[status] += 1
            feitos[0] += 1
            seguidas[0] = seguidas[0] + 1 if status in rl.TRANSITORIAS else 0
            if seguidas[0] >= args.max_falhas_seguidas and not parar.is_set():
                parar.set()
                print(f"\n!! {seguidas[0]} falhas 5xx/rede seguidas: parando para nao sobrecarregar a API. "
                      f"Rode de novo mais tarde; o que ja foi feito nao se repete.")
            if feitos[0] % 50 == 0 or feitos[0] == total:
                dec = time.monotonic() - t0
                taxa = feitos[0] / dec if dec else 0
                eta = (total - feitos[0]) / taxa / 60 if taxa else 0
                print(f"  {feitos[0]}/{total}  {taxa:.2f} req/s  ~{eta:.0f} min restantes  " +
                      " ".join(f"{k}={v}" for k, v in sorted(contagem.items())), flush=True)

    def trabalhador():
        while not parar.is_set():
            try:
                it = fila.get_nowait()
            except queue.Empty:
                return
            meta = dict(it["modelo"])
            meta["city_id"] = it["cod"]
            meta["url"] = rl.RE_CITY.sub(f'city:"{it["cod"]}"', it["modelo"]["url"])
            t1 = time.monotonic()
            status, http_, tent, result, erro = rl.buscar(meta["url"], args, limitador, parar)
            if status == "ERRO_REDE" and parar.is_set() and tent == 0:
                return  # interrompido antes de tentar: fica pendente
            status = {"CAPTURADO": "RECUPERADO", "CAPTURADO_VAZIO": "CONTINUA_VAZIO"}.get(status, status)
            dest_nv = dest_ds = obs = None
            if status == "RECUPERADO":
                meta["extracted_at"] = rl.agora()
                texto = rl.montar_texto(meta, result)
                rel = it["rel"].split("/")
                if rl.gravar_exclusivo(os.path.join(args.nova, BASES[it["base"]], *rel, it["arquivo"]), texto):
                    dest_nv = "/".join([BASES[it["base"]]] + rel + [it["arquivo"]])
                if args.gravar_no_dataset:
                    acao = substituir_vazio(os.path.join(raizes[it["base"]], *rel, it["arquivo"]), texto)
                    dest_ds = acao
            registrar(it, status, http_, tent, result, erro, time.monotonic() - t1, meta["url"], dest_nv, dest_ds, obs)

    fios = [threading.Thread(target=trabalhador, daemon=True) for _ in range(args.workers)]
    for f in fios:
        f.start()
    try:
        while any(f.is_alive() for f in fios):
            time.sleep(0.5)
            if args.max_minutos and not parar.is_set() and (time.monotonic() - t0) / 60 >= args.max_minutos:
                print(f"\nlimite de {args.max_minutos} min atingido: parando; o restante fica para a proxima rodada.")
                parar.set()
    except KeyboardInterrupt:
        print("\ninterrompendo (terminando as requisicoes em andamento)...")
        parar.set()
        for f in fios:
            f.join(timeout=args.timeout + 5)
    flog.close()
    print(f"\nconcluido: {feitos[0]} de {total} nesta execucao em {(time.monotonic()-t0)/60:.1f} min")
    cmd_relatorio(args)


# ---------------------------------------------------------------- relatorio
def escrever_csv(caminho, cols, regs):
    with open(caminho, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for r in regs:
            w.writerow([r.get(c) if r.get(c) is not None else "" for c in cols])


def cmd_relatorio(args):
    ultimo = carregar_log(os.path.join(args.logs, "log_vazios.jsonl"))
    if not ultimo:
        print("log vazio; nada a relatar.")
        return
    chave = lambda r: (r["base"], r["categoria"], r["fase"], r["ano"], r["cruzamento"], r["cod"])
    grupos = {"RECUPERADO": [], "CONTINUA_VAZIO": [], "ERRO": []}
    for r in sorted(ultimo.values(), key=chave):
        grupos["ERRO" if r["status"] in rl.FALHAS else r["status"]].append(r)
    ident = ["base", "categoria", "fase", "ano", "cruzamento", "cod", "municipio"]
    escrever_csv(os.path.join(args.logs, "recuperados_com_dados.csv"),
                 ident + ["linhas", "arquivo_novo", "arquivo_dataset", "url", "ts"], grupos["RECUPERADO"])
    escrever_csv(os.path.join(args.logs, "continua_vazio_na_api.csv"), ident + ["url", "ts"], grupos["CONTINUA_VAZIO"])
    escrever_csv(os.path.join(args.logs, "erros_http.csv"),
                 ident + ["status", "http", "tentativas", "erro", "url", "ts"], grupos["ERRO"])
    por = defaultdict(Counter)
    for r in ultimo.values():
        por[(r["base"], r["categoria"], r["fase"], r["cruzamento"])][r["status"]] += 1
    linhas = []
    for k, c in sorted(por.items()):
        linhas.append({"base": k[0], "categoria": k[1], "fase": k[2], "cruzamento": k[3],
                       "vazios_refeitos": sum(c.values()), "recuperados_com_dados": c["RECUPERADO"],
                       "continua_vazio": c["CONTINUA_VAZIO"], "erros": sum(c[s] for s in rl.FALHAS)})
    escrever_csv(os.path.join(args.logs, "resumo_por_cruzamento.csv"),
                 ["base", "categoria", "fase", "cruzamento", "vazios_refeitos", "recuperados_com_dados",
                  "continua_vazio", "erros"], linhas)
    cont = Counter(r["status"] for r in ultimo.values())
    print("\n== RELATORIO (ultimo resultado de cada arquivo vazio)")
    print(f"  tinha [] e agora veio dado ...... {cont['RECUPERADO']:7d}  -> recuperados_com_dados.csv")
    print(f"  continua [] na API (200) ........ {cont['CONTINUA_VAZIO']:7d}  -> continua_vazio_na_api.csv")
    print(f"  erro (nao capturado) ............ {len(grupos['ERRO']):7d}  -> erros_http.csv")
    for s in rl.FALHAS:
        if cont[s]:
            cod = Counter(r["http"] for r in grupos["ERRO"] if r["status"] == s)
            print(f"      {s}: {cont[s]} {dict(cod) if s != 'ERRO_REDE' else ''}")
    print(f"  por cruzamento: resumo_por_cruzamento.csv   (pasta: {args.logs})")


# ---------------------------------------------------------------- consolidar (workflow)
def cmd_consolidar(args):
    os.makedirs(args.saida, exist_ok=True)
    log_unico = os.path.join(args.saida, "log_vazios.jsonl")
    n = 0
    with open(log_unico, "w", encoding="utf-8") as out:
        for p in sorted(glob.glob(os.path.join(args.artefatos, "logs", "shard-*", "log_vazios.jsonl"))):
            with open(p, encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    try:
                        json.loads(linha)
                    except ValueError:
                        continue
                    out.write(linha + "\n")
                    n += 1
    print(f"{n} registros de log unidos")
    if n:
        cmd_relatorio(argparse.Namespace(logs=args.saida))
    ultimo = carregar_log(log_unico)
    plano = json.load(open(args.plano, encoding="utf-8"))
    pendentes, total = [], 0
    for p in plano["pastas"]:
        total += len(p["vazios"])
        resta = [c for c in p["vazios"] if (ultimo.get((p["base"], p["rel"], c)) or {}).get("status") not in DONE]
        if resta:
            pendentes.append({**p, "vazios": resta})
    with open(os.path.join(args.saida, "plano_proxima_rodada.json"), "w", encoding="utf-8") as f:
        json.dump({"gerado_em": rl.agora(), "pastas": pendentes}, f, ensure_ascii=False)
    nova = os.path.join(args.artefatos, "nova")
    n_arq = 0
    if os.path.isdir(nova):
        with tarfile.open(os.path.join(args.saida, "recuperados.tar.gz"), "w:gz", compresslevel=6) as tf:
            for dp, _, fn in os.walk(nova):
                for nome in sorted(fn):
                    completo = os.path.join(dp, nome)
                    tf.add(completo, arcname="recuperados_vazios/" + os.path.relpath(completo, nova).replace(os.sep, "/"),
                           recursive=False)
                    n_arq += 1
    cont = Counter(r["status"] for r in ultimo.values())
    erros = sum(cont[s] for s in rl.FALHAS)
    por = defaultdict(Counter)
    for r in ultimo.values():
        por[(r["base"], r["categoria"], r["fase"])][r["status"]] += 1
    md = ["## Vazios refeitos", "", f"- Arquivos vazios no plano: **{total}**",
          f"- Tinham `[]` e agora vieram com dado: **{cont['RECUPERADO']}**",
          f"- Continuam `[]` na API (HTTP 200): **{cont['CONTINUA_VAZIO']}**",
          f"- Erro (4xx/5xx/rede): **{erros}**",
          f"- Ainda sem registro (shard parou antes): **{sum(len(p['vazios']) for p in pendentes) - erros}**",
          f"- Arquivos no pacote `recuperados.tar.gz`: **{n_arq}**", "",
          "| Base | Categoria | Fase | Recuperados | Continua vazio | Erros |", "|---|---|---|---:|---:|---:|"]
    for (b, cat, fase), c in sorted(por.items()):
        md.append(f"| {b} | {cat} | {fase} | {c['RECUPERADO']} | {c['CONTINUA_VAZIO']} | {sum(c[s] for s in rl.FALHAS)} |")
    texto = "\n".join(md) + "\n"
    with open(os.path.join(args.saida, "resumo.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    print("\n" + texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texto)


# ---------------------------------------------------------------- aplicar (local)
def cmd_aplicar(args):
    raizes = {BASES["basicos"]: args.raiz_basicos, BASES["microdados"]: args.raiz_microdados}

    def arquivos():
        if os.path.isdir(args.pacote):
            base = args.pacote
            if os.path.isdir(os.path.join(base, "recuperados_vazios")):
                base = os.path.join(base, "recuperados_vazios")
            for dp, _, fn in os.walk(base):
                for n in fn:
                    c = os.path.join(dp, n)
                    with open(c, "rb") as f:
                        yield os.path.relpath(c, base).replace(os.sep, "/"), f.read()
        else:
            with tarfile.open(args.pacote, "r:*") as tf:
                for m in tf:
                    if m.isfile():
                        nome = m.name.replace("\\", "/")
                        if nome.startswith("recuperados_vazios/"):
                            nome = nome[len("recuperados_vazios/"):]
                        yield nome, tf.extractfile(m).read()

    cont = Counter()
    for rel, dados in arquivos():
        partes = rel.split("/")
        if (len(partes) < 5 or any(p in ("", ".", "..") for p in partes) or ":" in rel or partes[0] not in raizes
                or not rl.RE_ARQ.match(partes[-1])):
            cont["rejeitados"] += 1
            print("rejeitado:", rel)
            continue
        alvo = os.path.join(raizes[partes[0]], *partes[1:])
        existente = rl.ler_json(alvo) if os.path.exists(alvo) else None
        if isinstance(existente, dict) and existente.get("result"):
            cont["ja_tinha_dado"] += 1
            continue
        cont["criados" if not os.path.exists(alvo) else "vazios_substituidos"] += 1
        if args.dry_run:
            continue
        os.makedirs(os.path.dirname(alvo), exist_ok=True)
        tmp = alvo + ".tmp"
        with open(tmp, "wb") as f:
            f.write(dados)
        os.replace(tmp, alvo)
    print(("(dry-run) " if args.dry_run else "") + "  ".join(f"{k}={v}" for k, v in sorted(cont.items())))


# ---------------------------------------------------------------- main
def main():
    pai = argparse.ArgumentParser(add_help=False)
    pai.add_argument("--raiz-basicos", default=achar(SUB_RAIZ["basicos"]))
    pai.add_argument("--raiz-microdados", default=achar(SUB_RAIZ["microdados"]))
    pai.add_argument("--municipios", default=achar_municipios())
    pai.add_argument("--nova", default=os.path.join(AQUI, "recuperados_vazios"),
                     help="pasta nova: <nova>/<nome do dataset>/<mesma organizacao do dataset>")
    pai.add_argument("--logs", default=os.path.join(AQUI, "logs_vazios"))
    pai.add_argument("--plano", help="padrao: <logs>/plano_vazios.json")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pl = sub.add_parser("planejar", parents=[pai])
    pl.add_argument("--excluir-log", help="log jsonl da execucao local anterior: ignora os [] que ela mesma criou")
    ex = sub.add_parser("executar", parents=[pai])
    ex.add_argument("--workers", type=int, default=4)
    ex.add_argument("--max-por-seg", type=float, default=2.0)
    ex.add_argument("--tentativas", type=int, default=4)
    ex.add_argument("--espera", type=float, default=2.0)
    ex.add_argument("--timeout", type=float, default=60.0)
    ex.add_argument("--max-falhas-seguidas", type=int, default=25)
    ex.add_argument("--shard", type=int, default=0)
    ex.add_argument("--shards", type=int, default=1)
    ex.add_argument("--max-minutos", type=float)
    ex.add_argument("--limite", type=int, help="so as N primeiras requisicoes")
    ex.add_argument("--repetir-erros", action="store_true")
    ex.add_argument("--gravar-no-dataset", action="store_true",
                    help="substitui o arquivo vazio pelo recuperado direto nos datasets (uso local)")
    ex.add_argument("--api-base", help="troca esquema+host (testes)")
    sub.add_parser("relatorio", parents=[pai])
    co = sub.add_parser("consolidar", parents=[pai])
    co.add_argument("artefatos")
    co.add_argument("saida")
    ap_ = sub.add_parser("aplicar", parents=[pai])
    ap_.add_argument("pacote", help="recuperados.tar.gz ou pasta")
    ap_.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    {"planejar": cmd_planejar, "executar": cmd_executar, "relatorio": cmd_relatorio,
     "consolidar": cmd_consolidar, "aplicar": cmd_aplicar}[args.cmd](args)


if __name__ == "__main__":
    main()
