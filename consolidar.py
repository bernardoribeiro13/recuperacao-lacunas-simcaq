#!/usr/bin/env python3
"""Consolida o resultado de todos os shards do workflow.

uso: python consolidar.py <artefatos> <plano.json> <saida>

<artefatos> contem nova/<arvore do dataset>/... e logs/shard-N/log_requisicoes.jsonl (de todos os shards).
Gera em <saida>:
  log_requisicoes.jsonl            log unico
  capturados_com_dados.csv, vazios_confirmados_pela_api.csv, falhas_http_nao_capturados.csv
  plano_proxima_rodada.json        o que ainda falta (nao feito ou com falha), no formato do plano
  resumo.md                        contagens
  recuperados.tar.gz               arvore nova, pronta para aplicar_recuperados.py
"""
import argparse
import glob
import json
import os
import sys
import tarfile
from collections import Counter, defaultdict
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import refazer_lacunas as rl  # noqa: E402

PREFIXO = "dados_educacionais_basicos_microdados_recuperados"
SUCESSOS = ("CAPTURADO", "CAPTURADO_VAZIO")


def unir_logs(artefatos, destino):
    n = 0
    with open(destino, "w", encoding="utf-8") as out:
        for p in sorted(glob.glob(os.path.join(artefatos, "logs", "shard-*", "log_requisicoes.jsonl"))):
            with open(p, encoding="utf-8") as f:
                for linha in f:
                    linha = linha.strip()
                    if not linha:
                        continue
                    try:
                        json.loads(linha)
                    except ValueError:
                        continue  # linha truncada
                    out.write(linha + "\n")
                    n += 1
    return n


def empacotar(nova, destino):
    n = 0
    with tarfile.open(destino, "w:gz", compresslevel=6) as tf:
        for dp, _, fn in os.walk(nova):
            for nome in sorted(fn):
                completo = os.path.join(dp, nome)
                arc = PREFIXO + "/" + os.path.relpath(completo, nova).replace(os.sep, "/")
                tf.add(completo, arcname=arc, recursive=False)
                n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("artefatos")
    ap.add_argument("plano")
    ap.add_argument("saida")
    a = ap.parse_args()
    os.makedirs(a.saida, exist_ok=True)

    log_unico = os.path.join(a.saida, "log_requisicoes.jsonl")
    n_log = unir_logs(a.artefatos, log_unico)
    print(f"{n_log} registros de log unidos")
    if n_log:
        rl.cmd_relatorio(SimpleNamespace(logs=a.saida))

    ultimo = rl.carregar_log(log_unico)
    plano = json.load(open(a.plano, encoding="utf-8"))
    feitas = {k for k, r in ultimo.items() if r["status"] in SUCESSOS}
    proxima, total_plano, sem_registro = [], 0, 0
    for p in plano["pastas"]:
        total_plano += len(p["faltam"])
        restam = [c for c in p["faltam"] if (p["rel"], c) not in feitas]
        sem_registro += sum(1 for c in restam if (p["rel"], c) not in ultimo)
        if restam:
            proxima.append({**p, "faltam": restam})
    with open(os.path.join(a.saida, "plano_proxima_rodada.json"), "w", encoding="utf-8") as f:
        json.dump({"gerado_em": rl.agora(), "raiz": plano.get("raiz"), "pastas": proxima}, f, ensure_ascii=False)

    nova = os.path.join(a.artefatos, "nova")
    n_arq = empacotar(nova, os.path.join(a.saida, "recuperados.tar.gz")) if os.path.isdir(nova) else 0

    cont = Counter(r["status"] for r in ultimo.values())
    falhas = sum(cont[s] for s in rl.FALHAS)
    por_cat = defaultdict(Counter)
    for r in ultimo.values():
        por_cat[(r["categoria"], r["fase"])][r["status"]] += 1
    md = ["## Recuperacao de lacunas", "",
          f"- Lacunas no plano: **{total_plano}**",
          f"- Capturadas com dados: **{cont['CAPTURADO']}**",
          f"- Confirmadas vazias pela API (HTTP 200 com `[]`): **{cont['CAPTURADO_VAZIO']}**",
          f"- Falhas (400/404/5xx/rede, depois das tentativas): **{falhas}**",
          f"- Sem registro (shard parou antes): **{sem_registro}**",
          f"- Arquivos no pacote `recuperados.tar.gz`: **{n_arq}**", "",
          "| Categoria | Fase | Com dados | Vazios | Falhas |", "|---|---|---:|---:|---:|"]
    for (cat, fase), c in sorted(por_cat.items()):
        md.append(f"| {cat} | {fase} | {c['CAPTURADO']} | {c['CAPTURADO_VAZIO']} | {sum(c[s] for s in rl.FALHAS)} |")
    texto = "\n".join(md) + "\n"
    with open(os.path.join(a.saida, "resumo.md"), "w", encoding="utf-8") as f:
        f.write(texto)
    print("\n" + texto)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(texto)


if __name__ == "__main__":
    main()
