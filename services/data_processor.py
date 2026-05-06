"""Processamento central dos dados de frete: merge, padronização e cálculos base.

Preserva integralmente a lógica validada do teste18.py e a organiza em
funções coesas com type hints e logging estruturado.
"""

import logging
from datetime import datetime
from typing import Optional, Tuple

import numpy as np
import pandas as pd

from config.constants import (
    DE_PARA_UF,
    FAIXAS_PESO,
    LABELS_PESO,
    MAPA_ORIGINAL,
    MAPA_SIMULACAO,
)
from loaders.file_loader import carregar_arquivo
from loaders.data_validator import validar_dataframe
from utils.logger import get_logger
from utils.text_utils import converter_monetario, normalizar_nome_transp

logger: logging.Logger = get_logger(__name__)

_MESES_PT = {
    1: "Janeiro", 2: "Fevereiro", 3: "Marco", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}
# Versão com acentos para exibição em PDF (Latin-1 compatível via limpar_texto)
_MESES_PT_ACENTUADO = {
    1: "Janeiro", 2: "Fevereiro", 3: u"Mar\u00e7o", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def detectar_periodo(caminho_sim: str) -> str:
    """Detecta o período de referência a partir da coluna 'Data de Criação' do arquivo.

    Lê apenas a coluna de data, encontra o mês/ano mais frequente e retorna
    uma string formatada em português (ex: "Fevereiro 2026").
    Retorna string vazia se a coluna não existir ou não for legível.

    Args:
        caminho_sim: Caminho para o arquivo de simulação (xlsx ou csv).

    Returns:
        String no formato "Mês Ano" ou "" em caso de falha.
    """
    try:
        # Lê apenas os headers para localizar a coluna de data
        df_headers = pd.read_excel(caminho_sim, nrows=0) if caminho_sim.endswith((".xlsx", ".xls")) \
            else pd.read_csv(caminho_sim, nrows=0, sep=None, engine="python")
        col_data = next(
            (c for c in df_headers.columns if "cria" in str(c).lower()), None
        )
        if col_data is None:
            logger.info("Coluna de data não encontrada — período não detectado.")
            return ""

        # Lê apenas a coluna de data
        if caminho_sim.endswith((".xlsx", ".xls")):
            df_datas = pd.read_excel(caminho_sim, usecols=[col_data])
        else:
            df_datas = pd.read_csv(caminho_sim, usecols=[col_data], sep=None, engine="python")

        datas = pd.to_datetime(df_datas[col_data], errors="coerce").dropna()
        if datas.empty:
            return ""

        periodo = datas.dt.to_period("M").mode()[0]
        mes_str = _MESES_PT_ACENTUADO.get(periodo.month, str(periodo.month))
        result = f"{mes_str} {periodo.year}"
        logger.info("Período detectado automaticamente: %s", result)
        return result

    except Exception as exc:
        logger.warning("Não foi possível detectar o período: %s", exc)
        return ""


def padronizar_uf(valor: object) -> str:
    """Normaliza o valor de UF para sigla de 2 letras maiúsculas.

    Aceita tanto siglas já corretas quanto nomes completos dos estados,
    com ou sem acentuação.

    Args:
        valor: Valor bruto da coluna UF (qualquer tipo).

    Returns:
        Sigla de 2 letras em maiúsculas, ou o valor original em maiúsculas
        caso não seja reconhecido.

    Examples:
        >>> padronizar_uf("São Paulo")
        'SP'
        >>> padronizar_uf("sp")
        'SP'
        >>> padronizar_uf("MINAS GERAIS")
        'MG'
    """
    v = str(valor).strip().upper()
    if v in DE_PARA_UF.values():
        return v
    return DE_PARA_UF.get(v, v)


ProcessingResult = Tuple[
    pd.DataFrame,  # df_merged
    pd.DataFrame,  # resumo_transp
    dict,          # resumo_saving
    pd.DataFrame,  # resumo_matriz
    pd.DataFrame,  # analise_peso
    pd.Series,     # analise_uf
    pd.Series,     # analise_cep_vol
    pd.Series,     # analise_cep_saving
    pd.Series,     # analise_cep_perda
    pd.DataFrame,  # resumo_migracao
]


def carregar_e_processar(
    caminho_crua: str,
    caminho_orig: str,
) -> Optional[ProcessingResult]:
    """Carrega e processa o arquivo de recotação crua (formato BID T1-T5) com histórico.

    Pipeline:
    - Simulação: arquivo cru multi-transportadora expandido para formato longo
      (uma linha por pedido × transportadora, todas as T1-T5).
    - Histórico: merge por chave (CEP_Origem + CEP_Destino + Peso).
    - Rotas sem cotação são omitidas. A transportadora foco é selecionada
      pela interface após o carregamento.

    Args:
        caminho_crua: Arquivo de recotação crua (.xlsx).
        caminho_orig: Arquivo do cenário atual / histórico.

    Returns:
        Tupla com 10 objetos (df_merged, resumo_transp, resumo_saving,
        resumo_matriz, analise_peso, analise_uf, analise_cep_vol,
        analise_cep_saving, analise_cep_perda, resumo_migracao).
        Retorna None se ocorrer erro crítico de leitura.
    """
    from loaders.raw_recotacao_loader import expandir_recotacao_crua

    # 1. Expande todas as transportadoras do arquivo cru para formato longo
    try:
        df_sim = expandir_recotacao_crua(caminho_crua)
    except Exception as exc:
        logger.error("Erro ao processar recotação crua: %s", exc)
        return None

    if df_sim.empty:
        logger.error("Nenhuma cotação válida encontrada no arquivo cru.")
        return None

    # 2. Carrega histórico
    try:
        df_orig = carregar_arquivo(caminho_orig)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        logger.error("Erro na leitura do histórico: %s", exc)
        return None

    # 3. Renomeia histórico para nomes internos
    df_orig = df_orig.rename(columns=MAPA_ORIGINAL)

    # 4. Padroniza UF e normaliza CEPs no histórico
    if "UF" in df_orig.columns:
        df_orig["UF"] = df_orig["UF"].apply(padronizar_uf)

    # Detecta e normaliza colunas de CEP no histórico
    _cep_map = {
        "CEP ORIGEM": "CEP_Origem", "CEP Origem": "CEP_Origem",
        "CEP DESTINO": "CEP_Destino", "CEP Destino": "CEP_Destino",
        "PESO": "Peso", "Peso (KG)": "Peso",
    }
    df_orig = df_orig.rename(columns={k: v for k, v in _cep_map.items() if k in df_orig.columns})

    for col in ("CEP_Origem", "CEP_Destino"):
        if col in df_orig.columns:
            df_orig[col] = (
                df_orig[col]
                .astype(str).str.strip()
                .str.replace(r"[-.]", "", regex=True)
                .str.zfill(8)
            )

    if "Peso" in df_orig.columns:
        df_orig["Peso"] = pd.to_numeric(
            df_orig["Peso"].astype(str).str.replace(",", ".", regex=False),
            errors="coerce",
        )

    # 5. Converte custo/prazo do histórico
    for col in ["Custo_Antigo"]:
        if col in df_orig.columns:
            df_orig[col] = df_orig[col].apply(converter_monetario)
    for col in ["Prazo_Antigo"]:
        if col in df_orig.columns:
            df_orig[col] = pd.to_numeric(
                df_orig[col].astype(str)
                .str.replace(",", ".", regex=False)
                .str.replace("-", "0", regex=False),
                errors="coerce",
            ).fillna(0)

    # 6. Constrói chave de merge: CEP_Origem + CEP_Destino + Peso (arredondado)
    def _chave(df: pd.DataFrame) -> pd.Series:
        orig = df["CEP_Origem"].astype(str).str.zfill(8) if "CEP_Origem" in df.columns else "00000000"
        dest = df["CEP_Destino"].astype(str).str.zfill(8) if "CEP_Destino" in df.columns else "00000000"
        peso = pd.to_numeric(df["Peso"], errors="coerce").round(2).astype(str)
        return orig + "_" + dest + "_" + peso

    # Verifica colunas-chave no histórico antes do merge — ausência causa 0% de match
    _missing_hist = [c for c in ("CEP_Origem", "CEP_Destino", "Peso") if c not in df_orig.columns]
    if _missing_hist:
        logger.warning(
            "Histórico sem colunas de chave: %s — match será 0%%. "
            "Verifique os nomes das colunas no arquivo original.",
            ", ".join(_missing_hist),
        )

    df_sim["_chave"]  = _chave(df_sim)
    df_orig["_chave"] = _chave(df_orig)

    # 7. Seleciona colunas do histórico para o merge (sem duplicatas de chave)
    cols_hist = ["_chave", "Custo_Antigo", "Prazo_Antigo", "Transp_Antiga"]
    if "UF" in df_orig.columns:
        cols_hist.append("UF")
    df_hist_dedup = (
        df_orig[cols_hist]
        .drop_duplicates(subset=["_chave"], keep="first")
    )

    # 8. Merge por chave — left join: mantém apenas rotas cotadas pela transportadora
    df_sim = df_sim.rename(columns={
        "Transportadora": "Transp_Nova",
        "Custo":          "Custo_Novo",
        "Prazo":          "Prazo_Novo",
    })
    # Converte custo/prazo da simulação
    df_sim["Custo_Novo"] = df_sim["Custo_Novo"].apply(converter_monetario)
    df_sim["Prazo_Novo"] = pd.to_numeric(
        df_sim["Prazo_Novo"].astype(str)
        .str.replace(",", ".", regex=False)
        .str.replace("-", "0", regex=False),
        errors="coerce",
    ).fillna(0)
    df_sim["Peso"] = pd.to_numeric(df_sim["Peso"], errors="coerce").fillna(0)

    df_merged = df_sim.merge(df_hist_dedup, on="_chave", how="left")
    df_merged = df_merged.drop(columns=["_chave"])

    # 9. Garante colunas obrigatórias com defaults
    for col, default in [
        ("Custo_Antigo",  0),
        ("Prazo_Antigo",  0),
        ("Transp_Antiga", "N/A"),
        ("UF",            "??"),
    ]:
        if col not in df_merged.columns:
            df_merged[col] = default
    df_merged["Custo_Antigo"]  = df_merged["Custo_Antigo"].fillna(0)
    df_merged["Prazo_Antigo"]  = df_merged["Prazo_Antigo"].fillna(0)
    df_merged["Transp_Antiga"] = df_merged["Transp_Antiga"].fillna("N/A").astype(str)
    df_merged["UF"]            = df_merged["UF"].fillna("??")
    df_merged["Transp_Nova"]   = df_merged["Transp_Nova"].astype(str).str.strip()

    # Infere UF para pedidos sem match no histórico usando o mapeamento
    # CEP_Destino → UF do próprio arquivo histórico.
    # Isso evita a linha "??" duplicada no heatmap regional.
    mask_sem_uf = df_merged["UF"] == "??"
    if mask_sem_uf.any() and "UF" in df_orig.columns and "CEP_Destino" in df_orig.columns:
        cep_uf_map = (
            df_orig.dropna(subset=["CEP_Destino", "UF"])
            .drop_duplicates(subset=["CEP_Destino"])
            .set_index("CEP_Destino")["UF"]
        )
        df_merged.loc[mask_sem_uf, "UF"] = (
            df_merged.loc[mask_sem_uf, "CEP_Destino"].map(cep_uf_map).fillna("??")
        )
        n_inferidos = (df_merged["UF"] != "??").sum() - (~mask_sem_uf).sum()
        logger.info("UF inferida por CEP_Destino para %d pedidos sem match.", n_inferidos)

    n_transp = df_merged["Transp_Nova"].nunique()
    logger.info(
        "Merge por chave: %d cotações | %d transportadoras | match histórico: %.1f%%",
        len(df_merged),
        n_transp,
        (df_merged["Custo_Antigo"] > 0.01).mean() * 100,
    )

    return _calcular_derivados(df_merged)


# ── Derivados e agregados (compartilhado pelos dois fluxos de carga) ─────────

def calcular_derivados(df_merged: pd.DataFrame) -> ProcessingResult:
    """Versão pública de _calcular_derivados — usada externamente para re-agregar
    um subconjunto de df_merged (ex: filtrar pela transportadora foco no modo cru)."""
    return _calcular_derivados(df_merged)


def _calcular_derivados(df_merged: pd.DataFrame) -> ProcessingResult:
    """Calcula colunas derivadas e todos os agregados a partir do df mergeado.

    Usado por carregar_e_processar.

    Args:
        df_merged: DataFrame já mergeado com colunas Custo_Novo, Custo_Antigo,
            Prazo_Novo, Prazo_Antigo, Transp_Nova, Transp_Antiga, UF, Peso.

    Returns:
        Tupla ProcessingResult com 10 objetos.
    """
    # 7. Cálculos de performance
    df_merged["Tem_Base"] = df_merged["Custo_Antigo"] > 0.01

    df_merged["Saving_Valor"] = np.where(
        df_merged["Tem_Base"],
        df_merged["Custo_Antigo"] - df_merged["Custo_Novo"],
        0,
    )

    df_merged["Delta_Prazo"] = np.where(
        (df_merged["Prazo_Antigo"] > 0) & (df_merged["Prazo_Novo"] > 0),
        df_merged["Prazo_Novo"] - df_merged["Prazo_Antigo"],
        0,
    )

    # 8. Status de migração
    df_merged["Status_Migracao"] = _calcular_status_migracao(df_merged)

    # 9. Classificação quadrante
    df_merged["Classificacao"] = _classificar_pedidos(df_merged)

    # 10. CEP faixa
    if "CEP_Destino" in df_merged.columns:
        df_merged["CEP_Faixa"] = (
            df_merged["CEP_Destino"]
            .astype(str)
            .str.replace("-", "", regex=False)
            .str[:3]
            + "xx"
        )
    else:
        df_merged["CEP_Faixa"] = "N/A"

    # 11. Faixa de peso
    df_merged["Faixa_Peso"] = pd.cut(
        df_merged["Peso"], bins=FAIXAS_PESO, labels=LABELS_PESO
    )

    # 12. Agregados para gráficos
    resumo_transp = _calcular_resumo_transp(df_merged)
    resumo_saving = _calcular_resumo_saving(df_merged)
    resumo_matriz = _calcular_resumo_matriz(df_merged)
    analise_peso  = _calcular_analise_peso(df_merged)
    analise_uf    = (
        df_merged.groupby("UF")["Custo_Novo"].sum()
        .sort_values(ascending=False).head(8)
    )
    analise_cep_vol = (
        df_merged.groupby("CEP_Faixa")["Custo_Novo"]
        .count().sort_values(ascending=False).head(10)
    )
    analise_cep_saving = (
        df_merged.groupby("CEP_Faixa")["Saving_Valor"]
        .sum().sort_values(ascending=False).head(5)
    )
    analise_cep_perda = (
        df_merged[df_merged["Saving_Valor"] < 0]
        .groupby("CEP_Faixa")["Saving_Valor"]
        .sum().sort_values(ascending=True).head(5)
    )
    resumo_migracao = _calcular_resumo_migracao(df_merged)

    logger.info(
        "Processamento concluído: %d pedidos finais, saving total = R$ %.2f",
        len(df_merged),
        resumo_saving.get("Saving_Valor", 0),
    )

    return (
        df_merged,
        resumo_transp,
        resumo_saving,
        resumo_matriz,
        analise_peso,
        analise_uf,
        analise_cep_vol,
        analise_cep_saving,
        analise_cep_perda,
        resumo_migracao,
    )


# ── Funções auxiliares privadas ───────────────────────────────────────────────

def _calcular_status_migracao(df: pd.DataFrame) -> pd.Series:
    """Vetoriza o cálculo de status de migração usando np.select.

    Args:
        df: DataFrame com colunas Tem_Base, Transp_Antiga, Transp_Nova.

    Returns:
        Series com status de migração para cada linha.
    """
    t_antiga = df["Transp_Antiga"].apply(normalizar_nome_transp)
    t_nova = df["Transp_Nova"].apply(normalizar_nome_transp)

    sem_base = ~df["Tem_Base"] | t_antiga.isin(["0", "nan", "n/a"])
    mantido = (~sem_base) & (t_antiga == t_nova)
    migrado = (~sem_base) & (~mantido)

    return pd.Series(
        np.select(
            [sem_base, mantido, migrado],
            ["Novo Volume (Expansão)", "Mantido (Renegociação)", "Migrado (Troca)"],
            default="Novo Volume (Expansão)",
        ),
        index=df.index,
    )


def _classificar_pedidos(df: pd.DataFrame) -> pd.Series:
    """Classifica cada pedido em quadrante de custo × prazo.

    Args:
        df: DataFrame com colunas Tem_Base, Saving_Valor, Delta_Prazo.

    Returns:
        Series com classificação de cada pedido.
    """
    sem_base = ~df["Tem_Base"]
    saving = df["Saving_Valor"] > 0
    agilidade = df["Delta_Prazo"] <= 0

    return pd.Series(
        np.select(
            [
                sem_base,
                saving & agilidade,
                saving & ~agilidade,
                ~saving & agilidade,
            ],
            [
                "Sem Base Comparativa",
                "GANHO TOTAL (Ouro)",
                "TRADE-OFF (Economia c/ Prazo Maior)",
                "INVESTIMENTO (Mais rápido)",
            ],
            default="PERDA (Mais caro e lento)",
        ),
        index=df.index,
    )


def _calcular_resumo_transp(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega métricas por transportadora nova.

    Args:
        df: DataFrame processado.

    Returns:
        DataFrame com Custo_Total, Qtd_Pedidos, Prazo_Medio, Ticket_Medio
        por transportadora, ordenado por volume.
    """
    return (
        df.groupby("Transp_Nova")
        .agg(
            Custo_Total=("Custo_Novo", "sum"),
            Qtd_Pedidos=("Custo_Novo", "count"),
            Prazo_Medio=("Prazo_Novo", "mean"),
            Ticket_Medio=("Custo_Novo", "mean"),
        )
        .reset_index()
        .sort_values("Qtd_Pedidos", ascending=False)
    )


def _calcular_resumo_saving(df: pd.DataFrame) -> dict:
    """Calcula resumo financeiro consolidado.

    Args:
        df: DataFrame processado.

    Returns:
        Dicionário com totais financeiros para o relatório.
    """
    df_comp = df[df["Tem_Base"]]
    df_new = df[~df["Tem_Base"]]

    return {
        "Total_Geral_Novo": df["Custo_Novo"].sum(),
        "Custo_Antigo_Comp": df_comp["Custo_Antigo"].sum(),
        "Custo_Novo_Comp": df_comp["Custo_Novo"].sum(),
        "Saving_Valor": df_comp["Saving_Valor"].sum(),
        "Custo_New_Business": df_new["Custo_Novo"].sum(),
        "Qtd_New_Business": df_new["Custo_Novo"].count(),
        "Ticket_Antigo_Base": df_comp["Custo_Antigo"].mean() if not df_comp.empty else 0,
        "Ticket_Novo_Base": df_comp["Custo_Novo"].mean() if not df_comp.empty else 0,
    }


def _calcular_resumo_matriz(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega volume e valor por classificação de pedido.

    Args:
        df: DataFrame processado com coluna Classificacao.

    Returns:
        DataFrame com Qtd e Valor_Total por tipo de classificação.
    """
    return (
        df.groupby("Classificacao")
        .agg(
            Qtd=("Custo_Novo", "count"),
            Valor_Total=("Custo_Novo", "sum"),
        )
        .reset_index()
        .rename(columns={"Classificacao": "Tipo"})
    )


def _calcular_analise_peso(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula custo médio por faixa de peso e transportadora.

    Args:
        df: DataFrame processado com coluna Faixa_Peso.

    Returns:
        DataFrame pivotado: índice=Faixa_Peso, colunas=Transp_Nova, valores=média de Custo_Novo.
    """
    return (
        df.groupby(["Faixa_Peso", "Transp_Nova"], observed=False)["Custo_Novo"]
        .mean()
        .unstack()
        .fillna(0)
    )


def _calcular_resumo_migracao(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega métricas de migração por status.

    Args:
        df: DataFrame processado com colunas Status_Migracao e Tem_Base.

    Returns:
        DataFrame com Qtd, Saving, Custo_Antigo e Delta_Prazo por status.
    """
    return (
        df[df["Tem_Base"]]
        .groupby("Status_Migracao")
        .agg(
            Qtd=("Custo_Novo", "count"),
            Saving=("Saving_Valor", "sum"),
            Custo_Antigo=("Custo_Antigo", "sum"),
            Delta_Prazo=("Delta_Prazo", "mean"),
        )
        .reset_index()
    )
