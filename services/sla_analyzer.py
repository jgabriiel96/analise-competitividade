"""Análise de SLA, projeção de risco de atraso e trade-off custo × prazo.

Módulo central da evolução do projeto MAX. Implementa:
- SLA Compliance Analysis por transportadora e região.
- Delay Risk Projection com Índice de Risco ponderado.
- SLA vs Cost Trade-off Matrix (custo por dia de prazo).
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.constants import REGIOES_BR
from config.settings import (
    RISCO_ALTO_THRESHOLD,
    RISCO_MODERADO_THRESHOLD,
    SLA_ALERTA_MARGEM,
    SLA_TARGETS,
)
from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)

# Classificações de SLA
DENTRO_SLA = "DENTRO_SLA"
ALERTA_SLA = "ALERTA"
FORA_SLA = "FORA_SLA"

# Classificações de Risco
BAIXO_RISCO = "BAIXO_RISCO"
RISCO_MODERADO = "RISCO_MODERADO"
ALTO_RISCO = "ALTO_RISCO"


@dataclass
class SLAComplianceResult:
    """Resultado completo da análise de SLA compliance.

    Attributes:
        df_com_sla: DataFrame original enriquecido com colunas de SLA.
        compliance_por_transp: DataFrame com métricas de SLA por transportadora.
        compliance_por_regiao: DataFrame com métricas de SLA por região.
        risco_por_transp: DataFrame com índice de risco por transportadora.
        trade_off_matrix: DataFrame com custo por dia de SLA por transportadora.
        compliance_global_pct: Percentual global de pedidos dentro do SLA.
        texto_acoes_preventivas: Lista de textos consultivos gerados automaticamente.
    """

    df_com_sla: pd.DataFrame = field(default_factory=pd.DataFrame)
    compliance_por_transp: pd.DataFrame = field(default_factory=pd.DataFrame)
    compliance_por_regiao: pd.DataFrame = field(default_factory=pd.DataFrame)
    risco_por_transp: pd.DataFrame = field(default_factory=pd.DataFrame)
    trade_off_matrix: pd.DataFrame = field(default_factory=pd.DataFrame)
    compliance_global_pct: float = 0.0
    texto_acoes_preventivas: List[str] = field(default_factory=list)


def analisar_sla(
    df: pd.DataFrame,
    sla_targets: Optional[Dict[str, int]] = None,
) -> SLAComplianceResult:
    """Executa análise completa de SLA sobre o DataFrame processado.

    Args:
        df: DataFrame com colunas Prazo_Novo, UF, Transp_Nova, Custo_Novo, Peso.
        sla_targets: Dicionário {região: dias_target}. Se None, usa SLA_TARGETS
            do settings.py.

    Returns:
        SLAComplianceResult com todas as análises de SLA.
    """
    if sla_targets is None:
        sla_targets = SLA_TARGETS

    logger.info("Iniciando análise de SLA com targets: %s", sla_targets)

    df_sla = df.copy()

    # Mapeia cada UF para sua região
    mapa_uf_regiao = {
        uf: regiao for regiao, ufs in REGIOES_BR.items() for uf in ufs
    }
    df_sla["Regiao_SLA"] = df_sla["UF"].map(mapa_uf_regiao).fillna("Outros")

    # Atribui target de SLA por região
    df_sla["SLA_Target"] = df_sla["Regiao_SLA"].map(sla_targets).fillna(
        max(sla_targets.values()) if sla_targets else 7
    )

    # Classifica cada pedido
    df_sla["SLA_Status"] = _classificar_sla(
        df_sla["Prazo_Novo"], df_sla["SLA_Target"]
    )

    compliance_global = (
        (df_sla["SLA_Status"] == DENTRO_SLA).sum() / len(df_sla) * 100
        if len(df_sla) > 0
        else 0.0
    )

    compliance_por_transp = _calcular_compliance_por_transp(df_sla)
    compliance_por_regiao = _calcular_compliance_por_regiao(df_sla)
    risco_por_transp = _calcular_indice_risco(df_sla, compliance_por_transp)
    trade_off_matrix = _calcular_trade_off_matrix(df_sla)
    acoes = _gerar_acoes_preventivas(risco_por_transp, compliance_por_transp)

    logger.info(
        "SLA global: %.1f%% compliance | %d transportadoras analisadas",
        compliance_global,
        len(compliance_por_transp),
    )

    return SLAComplianceResult(
        df_com_sla=df_sla,
        compliance_por_transp=compliance_por_transp,
        compliance_por_regiao=compliance_por_regiao,
        risco_por_transp=risco_por_transp,
        trade_off_matrix=trade_off_matrix,
        compliance_global_pct=round(compliance_global, 2),
        texto_acoes_preventivas=acoes,
    )


def _classificar_sla(
    prazo: pd.Series,
    target: pd.Series,
) -> pd.Series:
    """Classifica cada pedido em DENTRO_SLA, ALERTA ou FORA_SLA.

    Args:
        prazo: Series com prazo realizado (dias).
        target: Series com target de SLA por pedido.

    Returns:
        Series com classificação de SLA.
    """
    return pd.Series(
        np.select(
            [
                prazo <= target,
                prazo <= (target + SLA_ALERTA_MARGEM),
            ],
            [DENTRO_SLA, ALERTA_SLA],
            default=FORA_SLA,
        ),
        index=prazo.index,
    )


def _calcular_compliance_por_transp(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula métricas de SLA compliance por transportadora.

    Args:
        df: DataFrame com colunas SLA_Status e Transp_Nova.

    Returns:
        DataFrame com % dentro_sla, % alerta, % fora_sla por transportadora.
    """
    total_por_transp = df.groupby("Transp_Nova")["SLA_Status"].count()

    dentro = df[df["SLA_Status"] == DENTRO_SLA].groupby("Transp_Nova")["SLA_Status"].count()
    alerta = df[df["SLA_Status"] == ALERTA_SLA].groupby("Transp_Nova")["SLA_Status"].count()
    fora = df[df["SLA_Status"] == FORA_SLA].groupby("Transp_Nova")["SLA_Status"].count()

    result = pd.DataFrame({
        "Total_Pedidos": total_por_transp,
        "Dentro_SLA": dentro,
        "Alerta_SLA": alerta,
        "Fora_SLA": fora,
    }).fillna(0).reset_index()

    result["Pct_Compliance"] = (result["Dentro_SLA"] / result["Total_Pedidos"] * 100).round(1)
    result["Pct_Alerta"] = (result["Alerta_SLA"] / result["Total_Pedidos"] * 100).round(1)
    result["Pct_Fora"] = (result["Fora_SLA"] / result["Total_Pedidos"] * 100).round(1)

    return result.sort_values("Pct_Compliance", ascending=False)


def _calcular_compliance_por_regiao(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula SLA compliance por região geográfica.

    Args:
        df: DataFrame com colunas SLA_Status e Regiao_SLA.

    Returns:
        DataFrame com % compliance por região.
    """
    total = df.groupby("Regiao_SLA")["SLA_Status"].count()
    dentro = df[df["SLA_Status"] == DENTRO_SLA].groupby("Regiao_SLA")["SLA_Status"].count()

    result = pd.DataFrame({"Total": total, "Dentro_SLA": dentro}).fillna(0).reset_index()
    result["Pct_Compliance"] = (result["Dentro_SLA"] / result["Total"] * 100).round(1)

    return result.rename(columns={"Regiao_SLA": "Regiao"}).sort_values(
        "Pct_Compliance", ascending=False
    )


def _calcular_indice_risco(
    df: pd.DataFrame,
    compliance_df: pd.DataFrame,
) -> pd.DataFrame:
    """Calcula Índice de Risco de Atraso por transportadora.

    O índice é composto por três fatores ponderados:
    - % de pedidos fora do SLA (40%)
    - Desvio padrão normalizado do prazo (40%)
    - Peso médio normalizado da carga (20%)

    Args:
        df: DataFrame com colunas Prazo_Novo, Peso, SLA_Status, Transp_Nova.
        compliance_df: DataFrame já calculado de compliance por transportadora.

    Returns:
        DataFrame com Indice_Risco e Classificacao_Risco por transportadora.
    """
    stats = (
        df.groupby("Transp_Nova")
        .agg(
            Prazo_Std=("Prazo_Novo", "std"),
            Peso_Medio=("Peso", "mean"),
            Prazo_Medio=("Prazo_Novo", "mean"),
        )
        .fillna(0)
        .reset_index()
    )

    result = compliance_df.merge(stats, on="Transp_Nova", how="left")

    # Normalização min-max para cada fator (0 a 1)
    pct_fora = result["Pct_Fora"] / 100  # já é 0-1

    prazo_std_max = result["Prazo_Std"].max()
    prazo_std_norm = (
        result["Prazo_Std"] / prazo_std_max if prazo_std_max > 0 else 0.0
    )

    peso_max = result["Peso_Medio"].max()
    peso_norm = result["Peso_Medio"] / peso_max if peso_max > 0 else 0.0

    result["Indice_Risco"] = (
        0.40 * pct_fora + 0.40 * prazo_std_norm + 0.20 * peso_norm
    ).round(3)

    result["Classificacao_Risco"] = pd.Series(
        np.select(
            [
                result["Indice_Risco"] >= RISCO_ALTO_THRESHOLD,
                result["Indice_Risco"] >= RISCO_MODERADO_THRESHOLD,
            ],
            [ALTO_RISCO, RISCO_MODERADO],
            default=BAIXO_RISCO,
        )
    )

    return result.sort_values("Indice_Risco", ascending=False)


def _calcular_trade_off_matrix(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula o custo por dia de SLA (trade-off custo × prazo) por transportadora.

    Args:
        df: DataFrame com colunas Custo_Novo, Prazo_Novo, Transp_Nova, Regiao_SLA.

    Returns:
        DataFrame com Custo_por_Dia e Sweet_Spot por transportadora e região.
    """
    agg = (
        df.groupby(["Transp_Nova", "Regiao_SLA"])
        .agg(
            Custo_Medio=("Custo_Novo", "mean"),
            Prazo_Medio=("Prazo_Novo", "mean"),
            Volume=("Custo_Novo", "count"),
        )
        .reset_index()
    )

    # Evita divisão por zero
    agg["Custo_por_Dia"] = (
        agg["Custo_Medio"] / agg["Prazo_Medio"].replace(0, np.nan)
    ).fillna(0).round(2)

    # Sweet Spot: menor custo por dia em cada região
    idx_min = agg.groupby("Regiao_SLA")["Custo_por_Dia"].idxmin()
    agg["Sweet_Spot"] = False
    agg.loc[idx_min[idx_min.notna()].values, "Sweet_Spot"] = True

    return agg.sort_values(["Regiao_SLA", "Custo_por_Dia"])


def _gerar_acoes_preventivas(
    risco_df: pd.DataFrame,
    compliance_df: pd.DataFrame,
) -> List[str]:
    """Gera lista de ações preventivas com base nos índices de risco.

    Args:
        risco_df: DataFrame com Indice_Risco e Classificacao_Risco.
        compliance_df: DataFrame com Pct_Compliance por transportadora.

    Returns:
        Lista de strings com recomendações consultivas ordenadas por prioridade.
    """
    acoes: List[str] = []

    alto_risco = risco_df[risco_df["Classificacao_Risco"] == ALTO_RISCO]
    moderado_risco = risco_df[risco_df["Classificacao_Risco"] == RISCO_MODERADO]

    for _, row in alto_risco.iterrows():
        transp = row["Transp_Nova"]
        pct_fora = row.get("Pct_Fora", 0)
        acoes.append(
            f"CRÍTICO | {transp}: {pct_fora:.0f}% dos pedidos fora do SLA. "
            f"Ação imediata: acionar reunião operacional e revisar tabela de prazo."
        )

    for _, row in moderado_risco.iterrows():
        transp = row["Transp_Nova"]
        std = row.get("Prazo_Std", 0)
        acoes.append(
            f"ATENÇÃO | {transp}: variabilidade de prazo elevada (desvio={std:.1f}d). "
            f"Monitorar por 30 dias e exigir plano de melhoria."
        )

    if not acoes:
        acoes.append(
            "POSITIVO: Todas as transportadoras apresentam perfil de risco controlado. "
            "Manter monitoramento mensal de SLA."
        )

    return acoes
