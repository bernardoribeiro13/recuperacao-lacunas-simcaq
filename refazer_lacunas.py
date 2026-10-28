#!/usr/bin/env python3
"""Refaz as requisicoes das lacunas (arquivos ausentes) do dataset de microdados.

Fluxo:
  python refazer_lacunas.py planejar                          # le o dataset e grava o plano de lacunas
  python refazer_lacunas.py executar --amostra 20 --sem-dataset   # teste pequeno, nao mexe no dataset
  python refazer_lacunas.py executar                          # roda tudo; pode ser interrompido e retomado
  python refazer_lacunas.py relatorio                         # regera os CSVs a partir do log

O que faz com cada municipio ausente:
  HTTP 200 com dados   -> CAPTURADO        grava no dataset e na pasta nova
  HTTP 200 com []      -> CAPTURADO_VAZIO  grava no dataset e na pasta nova (como o dataset ja guarda os vazios)
  HTTP 4xx             -> ERRO_HTTP_4XX    nao grava; vai para o log (sem nova tentativa, exceto 408/429)
  HTTP 5xx             -> ERRO_HTTP_5XX    nao grava; vai para o log (depois de varias tentativas)
  timeout / rede       -> ERRO_REDE        nao grava; vai para o log (depois de varias tentativas)

Nunca sobrescreve um arquivo existente. Somente biblioteca padrao.
"""
import argparse
import csv
import http.client
import json
import os
import queue
import random
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_PADRAO = os.path.join(AQUI, "dados_educacionais_basicos_microdados (2)", "dados_educacionais_basicos_microdados")
MUN_PADRAO = os.path.join(AQUI, "dados_educacionais_basicos", "dados_educacionais_basicos", "_municipios_piaui.json")
NOVA_PADRAO = os.path.join(AQUI, "dados_educacionais_basicos_microdados_recuperados")
LOGS_PADRAO = os.path.join(AQUI, "logs_recuperacao")

RE_ARQ = re.compile(r"^(\d{7})_.*\.json$")
RE_ANO = re.compile(r"^\d{4}$")
RE_CITY = re.compile(r'city:"\d+"')
FALHAS = ("ERRO_HTTP_4XX", "ERRO_HTTP_5XX", "ERRO_REDE", "ERRO_RESPOSTA")
TRANSITORIAS = ("ERRO_HTTP_5XX", "ERRO_REDE", "ERRO_RESPOSTA")  # as que acionam o disjuntor


# ---------------------------------------------------------------- utilidades
def ler_json(caminho):
    try:
        with open(caminho, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def carregar_municipios(caminho):
    d = ler_json(caminho)
    if not d:
        sys.exit(f"nao consegui ler a lista de municipios: {caminho}")
    return {m["id"]: m["name"] for m in d["result"]}


def nome_arquivo(cod, nome):
    return f"{cod}_{nome.replace(' ', '_')}.json"


def descrever(rel):
    """'docentes/classico/2008/x_X_y' -> (categoria, fase, ano, cruzamento)."""
    p = rel.split("/")
    fase, i = "unica", 1
    if not RE_ANO.match(p[1]):
        fase, i = p[1], 2
    return p[0], fase, int(p[i]), p[i + 1]


def agora():
    return datetime.now().isoformat(timespec="seconds")


def montar_texto(meta, result):
    """Mesmo formato dos arquivos do dataset: indent=2, UTF-8 sem BOM, sem newline final (CRLF ao gravar)."""
    return json.dumps({"meta": meta, "result": result}, indent=2, ensure_ascii=False)


def gravar_exclusivo(caminho, texto):
    """Cria o arquivo de forma atomica; devolve False (sem tocar em nada) se ele ja existir."""
    if os.path.exists(caminho):
        return False
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(texto)
    if os.path.exists(caminho):
        os.remove(tmp)
        return False
    os.replace(tmp, caminho)
    return True


def url_para_requisicao(url, api_base=None):
    """A URL do meta traz aspas cruas; a requisicao precisa delas codificadas."""
    p = urllib.parse.urlsplit(url)
    esquema, rede = p.scheme, p.netloc
    if api_base:
        b = urllib.parse.urlsplit(api_base)
        esquema, rede = b.scheme, b.netloc
    return urllib.parse.urlunsplit((esquema, rede, p.path, urllib.parse.quote(p.query, safe="=&,:"), ""))


# ---------------------------------------------------------------- planejar
def cmd_planejar(args):
    M = carregar_municipios(args.municipios)
    todos = set(M)
    pastas, sem_modelo = [], []
    t0 = time.time()
    for dp, dn, fn in os.walk(args.raiz):
        dn[:] = [d for d in dn if d != ".git"]
        arqs = [n for n in fn if RE_ARQ.match(n)]
        if not arqs:
            continue
        faltam = sorted(todos - {int(n[:7]) for n in arqs})
        if not faltam:
            continue
        rel = "/".join(os.path.relpath(dp, args.raiz).split(os.sep))
        modelo = None
        for n in sorted(arqs)[:5]:
            d = ler_json(os.path.join(dp, n))
            if isinstance(d, dict) and isinstance(d.get("meta"), dict) and d["meta"].get("url"):
                modelo = d["meta"]
                break
        if modelo is None:
            sem_modelo.append(rel)
            continue
        pastas.append({"rel": rel, "meta_modelo": modelo, "faltam": faltam})
    pastas.sort(key=lambda p: p["rel"])
    os.makedirs(args.logs, exist_ok=True)
    plano = {"gerado_em": agora(), "raiz": args.raiz, "pastas": pastas}
    destino = os.path.join(args.logs, "plano_lacunas.json")
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(plano, f, ensure_ascii=False)
    por_cat = Counter()
    for p in pastas:
        cat, fase, _, _ = descrever(p["rel"])
        por_cat[(cat, fase)] += len(p["faltam"])
    print(f"plano gravado em {destino} ({time.time()-t0:.0f}s)")
    print(f"pastas com lacuna: {len(pastas)}   municipios a requisitar: {sum(por_cat.values())}")
    for (cat, fase), n in sorted(por_cat.items()):
        print(f"  {cat:13s}{fase:9s}{n:7d}")
    if sem_modelo:
        print(f"ATENCAO: {len(sem_modelo)} pastas com lacuna mas sem arquivo-modelo legivel (ignoradas):")
        for r in sem_modelo[:10]:
            print("  ", r)


# ---------------------------------------------------------------- executar
class Limitador:
    """Espaca o inicio das requisicoes (todas as threads juntas)."""

    def __init__(self, por_segundo):
        self.intervalo = 1.0 / por_segundo if por_segundo > 0 else 0.0
        self.lock = threading.Lock()
        self.proximo = 0.0

    def esperar(self, parar):
        if not self.intervalo:
            return
        with self.lock:
            agora_ = time.monotonic()
            quando = max(agora_, self.proximo)
            self.proximo = quando + self.intervalo
        parar.wait(max(0.0, quando - time.monotonic()))


def trecho(corpo, n=300):
    try:
        return corpo.decode("utf-8", "replace").strip().replace("\r", " ").replace("\n", " ")[:n]
    except Exception:
        return ""


def buscar(url, args, limitador, parar):
    """Devolve (status, http, tentativas, result, erro). Repete 5xx, rede, 408 e 429."""
    req = urllib.request.Request(url_para_requisicao(url, args.api_base),
                                 headers={"User-Agent": "dados-basicos-recuperacao/1.0", "Accept": "application/json"})
    ultimo, tentativas, retry_after = ("ERRO_REDE", None, "interrompido antes da primeira tentativa"), 0, None
    while tentativas < args.tentativas and not parar.is_set():
        tentativas += 1
        retry_after = None
        limitador.esperar(parar)
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as r:
                code, corpo = r.status, r.read()
        except urllib.error.HTTPError as e:
            code = e.code
            try:
                corpo = e.read()
            except Exception:
                corpo = b""
            ra = e.headers.get("Retry-After") if e.headers else None
            retry_after = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
            if 400 <= code < 500 and code not in (408, 429):
                return "ERRO_HTTP_4XX", code, tentativas, None, trecho(corpo)
            ultimo = ("ERRO_HTTP_4XX" if code < 500 else "ERRO_HTTP_5XX", code, trecho(corpo))
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, http.client.HTTPException,
                OSError) as e:
            ultimo = ("ERRO_REDE", None, repr(getattr(e, "reason", e))[:300])
        else:
            try:
                dados = json.loads(corpo.decode("utf-8"))
            except Exception as e:
                ultimo = ("ERRO_RESPOSTA", code, f"JSON invalido: {e}; inicio: {trecho(corpo, 120)}")
            else:
                if code == 200 and isinstance(dados, dict) and isinstance(dados.get("result"), list):
                    return ("CAPTURADO" if dados["result"] else "CAPTURADO_VAZIO"), code, tentativas, dados["result"], None
                ultimo = ("ERRO_RESPOSTA", code, f"resposta sem 'result' em lista (HTTP {code})")
        if tentativas < args.tentativas:
            espera = retry_after if retry_after is not None else \
                min(60.0, args.espera * 2 ** (tentativas - 1)) * (0.5 + random.random())
            parar.wait(espera)
    return ultimo[0], ultimo[1], tentativas, None, ultimo[2]


def carregar_log(caminho):
    """Ultimo registro de cada (pasta, cod)."""
    ultimo = {}
    if os.path.exists(caminho):
        with open(caminho, encoding="utf-8") as f:
            for linha in f:
                linha = linha.strip()
                if linha:
                    try:
                        r = json.loads(linha)
                    except ValueError:
                        continue  # linha truncada por interrupcao
                    ultimo[(r["pasta"], r["cod"])] = r
    return ultimo


def cmd_executar(args):
    M = carregar_municipios(args.municipios)
    arq_plano = args.plano or os.path.join(args.logs, "plano_lacunas.json")
    if not os.path.exists(arq_plano):
        sys.exit(f"plano nao encontrado ({arq_plano}); rode primeiro: python refazer_lacunas.py planejar")
    plano = json.load(open(arq_plano, encoding="utf-8"))
    arq_log = os.path.join(args.logs, "log_requisicoes.jsonl")
    ja_logado = carregar_log(arq_log)

    itens, ja_existia, ja_no_log = [], 0, 0
    for p in plano["pastas"]:
        for cod in p["faltam"]:
            nome = nome_arquivo(cod, M[cod])
            if os.path.exists(os.path.join(args.raiz, *p["rel"].split("/"), nome)):
                ja_existia += 1
                continue
            anterior = ja_logado.get((p["rel"], cod))
            if anterior and not (args.repetir_erros and anterior["status"] in FALHAS):
                ja_no_log += 1
                continue
            itens.append({"rel": p["rel"], "cod": cod, "municipio": M[cod], "arquivo": nome, "modelo": p["meta_modelo"]})
    print(f"pendentes: {len(itens)}   (ja existiam no dataset: {ja_existia}; ja registrados no log: {ja_no_log})")
    if args.shards > 1:
        # fatias intercaladas: cada shard pega todas as categorias, com carga parecida
        itens = itens[args.shard::args.shards]
        print(f"shard {args.shard + 1}/{args.shards}: {len(itens)} requisicoes")
    if args.amostra:
        itens = random.Random(1).sample(itens, min(args.amostra, len(itens)))
    if args.limite:
        itens = itens[:args.limite]
    if not itens:
        print("nada a fazer.")
        return cmd_relatorio(args)

    if args.dry_run:
        for it in itens[:10]:
            meta_url = RE_CITY.sub(f'city:"{it["cod"]}"', it["modelo"]["url"])
            print("  ", url_para_requisicao(meta_url, args.api_base))
            print("      ->", os.path.join(args.nova, *it["rel"].split("/"), it["arquivo"]))
        print(f"(dry-run: {len(itens)} requisicoes seriam feitas)")
        return

    os.makedirs(args.logs, exist_ok=True)
    fila = queue.Queue()
    for it in itens:
        fila.put(it)
    total = len(itens)
    parar = threading.Event()
    limitador = Limitador(args.max_por_seg)
    trava = threading.Lock()
    contagem, seguidas, feitos = Counter(), [0], [0]
    t0 = time.monotonic()
    flog = open(arq_log, "a", encoding="utf-8")

    def registrar(it, status, http_, tentativas, result, erro, dur, dest_ds, dest_nv, obs):
        cat, fase, ano, cruz = descrever(it["rel"])
        reg = {"ts": agora(), "pasta": it["rel"], "categoria": cat, "fase": fase, "ano": ano, "cruzamento": cruz,
               "cod": it["cod"], "municipio": it["municipio"], "status": status, "http": http_,
               "tentativas": tentativas, "linhas": None if result is None else len(result),
               "duracao_s": round(dur, 1), "url": it["url"], "arquivo_dataset": dest_ds, "arquivo_novo": dest_nv,
               "erro": erro, "obs": obs}
        with trava:
            flog.write(json.dumps(reg, ensure_ascii=False) + "\n")
            flog.flush()
            contagem[status] += 1
            feitos[0] += 1
            seguidas[0] = seguidas[0] + 1 if status in TRANSITORIAS else 0
            if seguidas[0] >= args.max_falhas_seguidas and not parar.is_set():
                parar.set()
                print(f"\n!! {seguidas[0]} falhas transitorias seguidas (5xx/rede): parando para nao sobrecarregar a API. "
                      f"Rode 'executar' de novo mais tarde; o que ja foi feito nao se repete.")
            if feitos[0] % 20 == 0 or feitos[0] == total:
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
            meta["url"] = RE_CITY.sub(f'city:"{it["cod"]}"', it["modelo"]["url"])
            it["url"] = meta["url"]
            t1 = time.monotonic()
            status, http_, tentativas, result, erro = buscar(meta["url"], args, limitador, parar)
            if status == "ERRO_REDE" and parar.is_set() and tentativas == 0:
                return  # interrompido antes de tentar: nao registra, fica pendente
            dest_ds = dest_nv = obs = None
            if result is not None and not (status == "CAPTURADO_VAZIO" and args.nao_gravar_vazios):
                meta["extracted_at"] = agora()
                texto = montar_texto(meta, result)
                rel = it["rel"].split("/")
                if not args.sem_dataset:
                    if gravar_exclusivo(os.path.join(args.raiz, *rel, it["arquivo"]), texto):
                        dest_ds = "/".join(rel + [it["arquivo"]])
                    else:
                        obs = "dataset ja tinha o arquivo; nao sobrescrito"
                if gravar_exclusivo(os.path.join(args.nova, *rel, it["arquivo"]), texto):
                    dest_nv = "/".join(rel + [it["arquivo"]])
            registrar(it, status, http_, tentativas, result, erro, time.monotonic() - t1, dest_ds, dest_nv, obs)

    fios = [threading.Thread(target=trabalhador, daemon=True) for _ in range(args.workers)]
    for f in fios:
        f.start()
    try:
        while any(f.is_alive() for f in fios):
            time.sleep(0.5)
            if args.max_minutos and not parar.is_set() and (time.monotonic() - t0) / 60 >= args.max_minutos:
                print(f"\nlimite de {args.max_minutos} min atingido: parando; o restante fica pendente para a proxima rodada.")
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
def cmd_relatorio(args):
    ultimo = carregar_log(os.path.join(args.logs, "log_requisicoes.jsonl"))
    if not ultimo:
        print("log vazio; nada a relatar.")
        return
    grupos = {"CAPTURADO": [], "CAPTURADO_VAZIO": [], "FALHA": []}
    for r in ultimo.values():
        grupos["FALHA" if r["status"] in FALHAS else r["status"]].append(r)
    cols_ok = ["categoria", "fase", "ano", "cruzamento", "cod", "municipio", "status", "linhas", "arquivo_novo",
               "arquivo_dataset", "obs", "url", "ts"]
    cols_err = ["categoria", "fase", "ano", "cruzamento", "cod", "municipio", "status", "http", "tentativas", "erro",
                "url", "ts"]
    saidas = [("capturados_com_dados.csv", grupos["CAPTURADO"], cols_ok),
              ("vazios_confirmados_pela_api.csv", grupos["CAPTURADO_VAZIO"], cols_ok),
              ("falhas_http_nao_capturados.csv", grupos["FALHA"], cols_err)]
    for nome, regs, cols in saidas:
        regs.sort(key=lambda r: (r["categoria"], r["fase"], r["ano"], r["cruzamento"], r["cod"]))
        with open(os.path.join(args.logs, nome), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(cols)
            for r in regs:
                w.writerow([r.get(c) if r.get(c) is not None else "" for c in cols])
    por_status = Counter(r["status"] for r in ultimo.values())
    print("\n== RELATORIO (ultimo resultado de cada municipio/pasta no log)")
    print(f"  capturados com dados ............ {por_status['CAPTURADO']:7d}  -> capturados_com_dados.csv")
    print(f"  vazios confirmados pela API ..... {por_status['CAPTURADO_VAZIO']:7d}  -> vazios_confirmados_pela_api.csv")
    print(f"  falhas (nao capturados) ......... {len(grupos['FALHA']):7d}  -> falhas_http_nao_capturados.csv")
    for s in FALHAS:
        if por_status[s]:
            codigos = Counter(r["http"] for r in grupos["FALHA"] if r["status"] == s)
            print(f"      {s}: {por_status[s]}  {dict(codigos) if s != 'ERRO_REDE' else ''}")
    print(f"  arquivos em: {args.logs}")


# ---------------------------------------------------------------- main
def main():
    pai = argparse.ArgumentParser(add_help=False)
    pai.add_argument("--raiz", default=RAIZ_PADRAO, help="dataset de microdados a completar")
    pai.add_argument("--municipios", default=MUN_PADRAO)
    pai.add_argument("--nova", default=NOVA_PADRAO, help="pasta nova com a mesma organizacao do dataset")
    pai.add_argument("--logs", default=LOGS_PADRAO)
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("planejar", parents=[pai], help="lista as lacunas do dataset")
    ex = sub.add_parser("executar", parents=[pai], help="faz as requisicoes e grava")
    ex.add_argument("--workers", type=int, default=4)
    ex.add_argument("--max-por-seg", type=float, default=2.0, help="teto global de requisicoes iniciadas por segundo")
    ex.add_argument("--tentativas", type=int, default=4, help="tentativas por municipio em 5xx/rede")
    ex.add_argument("--espera", type=float, default=2.0, help="espera base (s) do recuo exponencial")
    ex.add_argument("--timeout", type=float, default=60.0)
    ex.add_argument("--max-falhas-seguidas", type=int, default=25, help="para tudo apos N falhas 5xx/rede seguidas")
    ex.add_argument("--plano", help="caminho do plano (padrao: <logs>/plano_lacunas.json)")
    ex.add_argument("--shard", type=int, default=0, help="indice (0-based) da fatia a processar")
    ex.add_argument("--shards", type=int, default=1, help="em quantas fatias o plano e dividido")
    ex.add_argument("--max-minutos", type=float, help="para sozinho apos N minutos (o que falta fica pendente)")
    ex.add_argument("--amostra", type=int, help="processa N lacunas sorteadas (teste)")
    ex.add_argument("--limite", type=int, help="processa so as N primeiras")
    ex.add_argument("--sem-dataset", action="store_true", help="grava somente na pasta nova")
    ex.add_argument("--nao-gravar-vazios", action="store_true", help="resposta 200 com [] so vai para o log")
    ex.add_argument("--repetir-erros", action="store_true", help="tenta de novo o que o log marcou como erro")
    ex.add_argument("--dry-run", action="store_true")
    ex.add_argument("--api-base", help="troca esquema+host das URLs (ex.: http://127.0.0.1:8000, para testes)")
    sub.add_parser("relatorio", parents=[pai], help="regera os CSVs a partir do log")
    args = ap.parse_args()
    {"planejar": cmd_planejar, "executar": cmd_executar, "relatorio": cmd_relatorio}[args.cmd](args)


if __name__ == "__main__":
    main()
