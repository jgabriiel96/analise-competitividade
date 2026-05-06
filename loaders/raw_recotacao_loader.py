"""Loader para recotação no formato crú (multi-transportadora por linha).

Estrutura do arquivo:
  Linha 0: vazia
  Linha 1: rótulos de grupo — "Transportadora 1", "Transportadora 2", ...
  Linha 2: nomes de colunas — CEP Origem, CEP Destino, Peso (KG), ..., Transportadora, Prazo, Custo, ...
  Linha 3+: dados

Cada linha pode ter até 5 cotações simultâneas (T1 = mais barata, T5 = mais cara).
"""

import logging
from typing import List

import pandas as pd

from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)

_N_CARRIERS = 5

_COLS_BASE = [
    "CEP_Origem", "CEP_Destino", "Peso", "Tipo", "NF",
    "Largura", "Altura", "Comprimento", "Qtde_Volumes",
]
_COLS_FULL = _COLS_BASE + [
    col
    for i in range(1, _N_CARRIERS + 1)
    for col in [f"T{i}_Nome", f"T{i}_Prazo", f"T{i}_Custo"]
]


def _ler_bruto(caminho: str) -> pd.DataFrame:
    """Lê o arquivo cru e normaliza colunas e tipos básicos."""
    # header=2 usa a linha de rótulos de grupo como cabeçalho;
    # skiprows=[3] remove a linha de sub-cabeçalho (CEP Origem, Peso, ...)
    df = pd.read_excel(caminho, header=2, skiprows=[3])

    # Garante que temos no máximo as colunas esperadas
    n_cols = min(len(df.columns), len(_COLS_FULL))
    df = df.iloc[:, :n_cols].copy()
    df.columns = _COLS_FULL[:n_cols]

    # Remove linhas completamente vazias
    df = df.dropna(how="all").reset_index(drop=True)

    # Normaliza CEPs: remove hífens, pontos, preenche com zeros à esquerda
    for col in ("CEP_Origem", "CEP_Destino"):
        if col in df.columns:
            df[col] = (
                df[col]
                .astype(str)
                .str.strip()
                .str.replace(r"[-.]", "", regex=True)
                .str.zfill(8)
            )

    # Normaliza Peso para float
    if "Peso" in df.columns:
        df["Peso"] = pd.to_numeric(
            df["Peso"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )

    logger.info("Recotação crua lida: %d linhas", len(df))
    return df


def listar_transportadoras_crua(caminho: str) -> List[str]:
    """Retorna lista ordenada de transportadoras únicas no arquivo cru.

    Varre as colunas T1-T5 Nome e agrega todos os nomes válidos.

    Args:
        caminho: Caminho do arquivo de recotação crua (.xlsx ou .xls).

    Returns:
        Lista de strings ordenada alfabeticamente.
    """
    df = _ler_bruto(caminho)
    nomes: set = set()
    _invalidos = {"NAN", "", "NONE", "0", "N/A", "NULL"}

    for i in range(1, _N_CARRIERS + 1):
        col = f"T{i}_Nome"
        if col not in df.columns:
            continue
        vals = (
            df[col]
            .dropna()
            .astype(str)
            .str.strip()
        )
        vals = vals[~vals.str.upper().isin(_invalidos)]
        nomes.update(vals.tolist())

    result = sorted(nomes)
    logger.info(
        "Transportadoras encontradas no arquivo cru: %d", len(result)
    )
    return result


def analisar_posicao_bid(caminho: str, transp_alvo: str) -> pd.DataFrame:
    """Retorna um DataFrame com a posição e o gap de cada pedido em relação ao T1.

    Para cada pedido no arquivo cru, localiza a transportadora alvo (em qualquer
    posição T1-T5), identifica o T1 (mais barata) e calcula quanto a alvo precisaria
    reduzir para se tornar a líder de preço.

    Args:
        caminho: Arquivo de recotação crua (.xlsx ou .xls).
        transp_alvo: Nome exato da transportadora a analisar (case-insensitive).

    Returns:
        DataFrame com colunas:
            CEP_Origem, CEP_Destino, Peso,
            TJ_Posicao (1-5), TJ_Custo,
            T1_Nome, T1_Custo,
            Gap_R  (TJ_Custo - T1_Custo — 0 quando TJ já é T1),
            Gap_Pct (Gap_R / TJ_Custo * 100).
        Pedidos onde a transportadora não aparece são omitidos.
    """
    df = _ler_bruto(caminho)
    _invalidos = {"NAN", "", "NONE", "0", "N/A", "NULL"}
    alvo_upper = transp_alvo.strip().upper()

    rows = []
    for _, row in df.iterrows():
        tj_pos = tj_custo = None

        # Localiza a posição da transportadora alvo
        for i in range(1, _N_CARRIERS + 1):
            nome_col = f"T{i}_Nome"
            if nome_col not in df.columns:
                continue
            nome = str(row.get(nome_col, "")).strip().upper()
            if nome in _invalidos:
                continue
            if nome == alvo_upper:
                tj_pos = i
                tj_custo = pd.to_numeric(row.get(f"T{i}_Custo"), errors="coerce")
                break

        if tj_pos is None or pd.isna(tj_custo):
            continue  # transportadora não cotou este pedido

        # Obtém T1 (a mais barata — já está na posição 1 do arquivo)
        t1_nome  = str(row.get("T1_Nome", "")).strip()
        t1_custo = pd.to_numeric(row.get("T1_Custo"), errors="coerce")

        if pd.isna(t1_custo) or t1_nome.upper() in _invalidos:
            continue

        gap_r   = round(float(tj_custo) - float(t1_custo), 2)
        gap_pct = round(gap_r / float(tj_custo) * 100, 2) if tj_custo > 0 else 0.0

        rows.append({
            "CEP_Origem": str(row["CEP_Origem"]),
            "CEP_Destino": str(row["CEP_Destino"]),
            "Peso":        row["Peso"],
            "TJ_Posicao":  tj_pos,
            "TJ_Custo":    float(tj_custo),
            "T1_Nome":     t1_nome,
            "T1_Custo":    float(t1_custo),
            "Gap_R":       gap_r,
            "Gap_Pct":     gap_pct,
        })

    if not rows:
        logger.warning("analisar_posicao_bid: '%s' não encontrada no arquivo.", transp_alvo)
        return pd.DataFrame(columns=[
            "CEP_Origem", "CEP_Destino", "Peso",
            "TJ_Posicao", "TJ_Custo", "T1_Nome", "T1_Custo",
            "Gap_R", "Gap_Pct",
        ])

    result = pd.DataFrame(rows)
    logger.info(
        "analisar_posicao_bid: '%s' — %d pedidos | já lidera: %d | gap médio: R$%.2f",
        transp_alvo,
        len(result),
        (result["TJ_Posicao"] == 1).sum(),
        result[result["TJ_Posicao"] > 1]["Gap_R"].mean() if (result["TJ_Posicao"] > 1).any() else 0,
    )
    return result


def expandir_recotacao_crua(caminho: str) -> pd.DataFrame:
    """Expande o arquivo cru para formato longo: uma linha por (pedido × transportadora).

    Cada linha do arquivo cru pode ter até 5 cotações (T1-T5). Esta função
    "derrete" essas colunas em linhas, preservando todas as transportadoras.
    Isso permite que a análise compare todas as carriers contra o histórico,
    com a transportadora foco sendo escolhida normalmente na seção 4 da UI.

    Args:
        caminho: Caminho do arquivo de recotação crua (.xlsx ou .xls).

    Returns:
        DataFrame com colunas: CEP_Origem, CEP_Destino, Peso,
        Transportadora, Prazo, Custo.
        Cotações com transportadora vazia/NaN são omitidas.
    """
    df = _ler_bruto(caminho)
    _invalidos = {"NAN", "", "NONE", "0", "N/A", "NULL"}

    rows = []
    for _, row in df.iterrows():
        for i in range(1, _N_CARRIERS + 1):
            nome_col = f"T{i}_Nome"
            if nome_col not in df.columns:
                continue
            nome = str(row.get(nome_col, "")).strip()
            if nome.upper() in _invalidos:
                continue
            rows.append({
                "CEP_Origem":     str(row["CEP_Origem"]),
                "CEP_Destino":    str(row["CEP_Destino"]),
                "Peso":           row["Peso"],
                "Transportadora": nome,
                "Prazo":          row.get(f"T{i}_Prazo"),
                "Custo":          row.get(f"T{i}_Custo"),
            })

    if not rows:
        logger.warning("Nenhuma cotação válida encontrada no arquivo cru.")
        return pd.DataFrame(
            columns=["CEP_Origem", "CEP_Destino", "Peso",
                     "Transportadora", "Prazo", "Custo"]
        )

    result = pd.DataFrame(rows)
    n_transp = result["Transportadora"].nunique()
    logger.info(
        "Expansão concluída: %d cotações | %d transportadoras | %d pedidos originais",
        len(result), n_transp, len(df),
    )
    return result
