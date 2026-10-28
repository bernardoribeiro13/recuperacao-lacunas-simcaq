#!/usr/bin/env python3
"""Aplica os arquivos recuperados (recuperados.tar.gz do workflow, ou uma pasta) ao dataset local.

uso: python aplicar_recuperados.py <recuperados.tar.gz | pasta> [--raiz DATASET] [--nova PASTA_NOVA] [--dry-run]

Copia cada arquivo para o dataset (--raiz) e para a pasta nova (--nova), no mesmo caminho relativo.
Nunca sobrescreve: arquivo que ja existe e ignorado. Rejeita caminhos fora do padrao
<categoria>/[fase/]<ano>/<cruzamento>/<codigo>_<NOME>.json.
"""
import argparse
import os
import re
import sys
import tarfile

AQUI = os.path.dirname(os.path.abspath(__file__))
PREFIXO = "dados_educacionais_basicos_microdados_recuperados"
SUB_RAIZ = os.path.join("dados_educacionais_basicos_microdados (2)", "dados_educacionais_basicos_microdados")
RE_NOME = re.compile(r"^\d{7}_[^/\\]+\.json$")


def achar_raiz():
    """O script pode estar ao lado do dataset ou numa subpasta (o repositorio)."""
    for base in (AQUI, os.path.dirname(AQUI)):
        if os.path.isdir(os.path.join(base, SUB_RAIZ)):
            return os.path.join(base, SUB_RAIZ)
    return os.path.join(AQUI, SUB_RAIZ)


def arquivos(origem):
    """Gera (caminho_relativo_posix, bytes) de cada arquivo do pacote."""
    if os.path.isdir(origem):
        base = os.path.join(origem, PREFIXO) if os.path.isdir(os.path.join(origem, PREFIXO)) else origem
        for dp, _, fn in os.walk(base):
            for n in fn:
                completo = os.path.join(dp, n)
                with open(completo, "rb") as f:
                    yield os.path.relpath(completo, base).replace(os.sep, "/"), f.read()
    else:
        with tarfile.open(origem, "r:*") as tf:
            for m in tf:
                if not m.isfile():
                    continue
                nome = m.name.replace("\\", "/")
                if nome.startswith(PREFIXO + "/"):
                    nome = nome[len(PREFIXO) + 1:]
                yield nome, tf.extractfile(m).read()


def valido(rel):
    partes = rel.split("/")
    if len(partes) < 4 or any(p in ("", ".", "..") for p in partes) or ":" in rel or rel.startswith("/"):
        return False
    return bool(RE_NOME.match(partes[-1]))


def gravar_exclusivo(caminho, dados):
    if os.path.exists(caminho):
        return False
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    tmp = caminho + ".tmp"
    with open(tmp, "wb") as f:
        f.write(dados)
    os.replace(tmp, caminho)
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("origem")
    ap.add_argument("--raiz", default=achar_raiz(), help="dataset de microdados")
    ap.add_argument("--nova", help="pasta nova (padrao: ao lado da pasta do dataset)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not os.path.exists(a.origem):
        sys.exit(f"origem nao encontrada: {a.origem}")
    if not os.path.isdir(a.raiz):
        sys.exit(f"dataset nao encontrado: {a.raiz} (use --raiz)")
    if not a.nova:
        a.nova = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(a.raiz))), PREFIXO)

    cont = {"dataset_criados": 0, "dataset_ja_existiam": 0, "nova_criados": 0, "nova_ja_existiam": 0, "rejeitados": 0}
    for rel, dados in arquivos(a.origem):
        if not valido(rel):
            cont["rejeitados"] += 1
            print("rejeitado:", rel)
            continue
        for chave, destino in (("dataset", a.raiz), ("nova", a.nova)):
            caminho = os.path.join(destino, *rel.split("/"))
            if a.dry_run:
                criou = not os.path.exists(caminho)
            else:
                criou = gravar_exclusivo(caminho, dados)
            cont[f"{chave}_criados" if criou else f"{chave}_ja_existiam"] += 1
    print(("(dry-run) " if a.dry_run else "") + "  ".join(f"{k}={v}" for k, v in cont.items()))


if __name__ == "__main__":
    main()
