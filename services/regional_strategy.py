"""Estratégia de malha logística por região: recomendação e consolidação.

Implementa o Carrier Recommendation Engine, análise de impacto de
consolidação e geração da tabela de Malha Recomendada.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from config.constants import ORDEM_REGIOES, REGIOES_BR
from config.settings import (
    EMPATE_TECNICO_THRESHOLD,
    GANHO_ESCALA_MAX,
    GANHO_ESCALA_MIN,
    REGIONAL_SCORE_PESOS,
    SLA_TARGETS,
)
from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)


@dataclass
class RegionalStrategyResult:
    """Resultado da análise de estratégia regional.

    Attributes:
        malha_recomendada: DataFrame com recomendação por região.
        scores_por_regiao: DataFrame com scores de cada transportadora por região.
        impacto_consolidacao: DataFrame com análise financeira da consolidação.
        cobertura_pct: Percentual de regiões com pelo menos uma transportadora.
        texto_recomendacoes: Lista de textos consultivos por região.
    """

    malha_recomendada: pd.DataFrame = field(default_factory=pd.DataFrame)
    scores_por_regiao: pd.DataFrame = field(default_factory=pd.DataFrame)
    impacto_consolidacao: pd.DataFrame = field(default_factory=pd.DataFrame)
    cobertura_pct: float = 0.0
    texto_recomendacoes: List[str] = field(default_factory=list)


def analisar_estrategia_regional(
    df: pd.DataFrame,
    sla_compliance_por_transp: Optional[pd.DataFrame] = None,
    sla_targets: Optional[Dict[str, int]] = None,
) -> RegionalStrategyResult:
    """Executa análise completa de estratégia regional.

    Para cada região brasileira com dados suficientes:
    1. Calcula o score combinado de cada transportadora.
    2. Recomenda a principal e a backup.
    3. Projeta o impacto de consolidação.

    Args:
        df: DataFrame processado com colunas UF, Custo_Novo, Custo_Antigo,
            Prazo_Novo, Transp_Nova, Saving_Valor, Tem_Base.
        sla_compliance_por_transp: DataFrame do sla_analyzer com Pct_Compliance.
            Se None, o compliance é estimado a partir do DataFrame.
        sla_targets: Dicionário {região: target}. Se None, usa SLA_TARGETS.

    Returns:
        RegionalStrategyResult com todos os resultados.
    """
    if sla_targets is None:
        sla_targets = SLA_TARGETS

    logger.info("Iniciando análise de estratégia regional")

    # Mapa UF → Região
    mapa_uf_regiao = {
        uf: regiao for regiao, ufs in REGIOES_BR.items() for uf in ufs
    }
    df_reg = df.copy()
    df_reg["Regiao"] = df_reg["UF"].map(mapa_uf_regiao).fillna("Outros")

    scores_rows: List[dict] = []
    malha_rows: List[dict] = []
    impacto_rows: List[dict] = []
    textos: List[str] = []

    regioes_com_dados = [
        r for r in ORDEM_REGIOES
        if r in df_reg["Regiao"].values
    ]

    for regiao in regioes_com_dados:
        df_r = df_reg[df_reg["Regiao"] == regiao]
        if len(df_r) < 5:
            continue

        scores = _calcular_scores_transportadoras(
            df_r, regiao, sla_compliance_por_transp, sla_targets
        )
        if scores.empty:
            continue

        scores["Regiao"] = regiao
        scores_rows.append(scores)

        principal, backup = _selecionar_recomendacoes(scores)
        sla_target = sla_targets.get(regiao, 7)
        custo_target = _calcular_custo_target(df_r, principal)

        malha_rows.append({
            "Regiao": regiao,
            "Transp_Principal": principal,
            "Transp_Backup": backup,
            "SLA_Target_Dias": sla_target,
            "Custo_Target_R$": round(custo_target, 2),
        })

        impacto = _calcular_impacto_consolidacao(df_r, principal)
        impacto["Regiao"] = regiao
        impacto_rows.append(impacto)

        texto = _gerar_texto_recomendacao(regiao, principal, backup, scores, impacto)
        textos.append(texto)

    # Monta DataFrames finais
    malha_df = pd.DataFrame(malha_rows) if malha_rows else pd.DataFrame()
    scores_df = pd.concat(scores_rows, ignore_index=True) if scores_rows else pd.DataFrame()
    impacto_df = pd.DataFrame(impacto_rows) if impacto_rows else pd.DataFrame()

    regioes_totais = len(ORDEM_REGIOES)
    cobertura = len(regioes_com_dados) / regioes_totais * 100 if regioes_totais > 0 else 0.0

    logger.info(
        "Estratégia regional concluída: %d regiões | cobertura %.0f%%",
        len(regioes_com_dados), cobertura,
    )

    return RegionalStrategyResult(
        malha_recomendada=malha_df,
        scores_por_regiao=scores_df,
        impacto_consolidacao=impacto_df,
        cobertura_pct=round(cobertura, 1),
        texto_recomendacoes=textos,
    )


# ── Funções auxiliares privadas ───────────────────────────────────────────────

def _calcular_scores_transportadoras(
    df_regiao: pd.DataFrame,
    regiao: str,
    compliance_df: Optional[pd.DataFrame],
    sla_targets: Dict[str, int],
) -> pd.DataFrame:
    """Calcula scores combinados por transportadora em uma região.

    Score = 0.4 * saving_pct_norm + 0.4 * sla_compliance_pct + 0.2 * volume_share

    Args:
        df_regiao: DataFrame filtrado para a região.
        regiao: Nome da região para lookup de SLA target.
        compliance_df: DataFrame de compliance do sla_analyzer, ou None.
        sla_targets: Dicionário de targets por região.

    Returns:
        DataFrame com Score por transportadora, ordenado decrescente.
    """
    vol_total = len(df_regiao)
    target_dias = sla_targets.get(regiao, 7)

    agg = (
        df_regiao.groupby("Transp_Nova")
        .agg(
            Volume=("Custo_Novo", "count"),
            Custo_Medio=("Custo_Novo", "mean"),
            Prazo_Medio=("Prazo_Novo", "mean"),
            Saving_Total=("Saving_Valor", "sum"),
            Custo_Antigo_Total=("Custo_Antigo", "sum"),
        )
        .reset_index()
    )

    # Volume share (0-1)
    agg["Volume_Share"] = agg["Volume"] / vol_total

    # Saving percentual por transportadora
    agg["Saving_Pct"] = (
        agg["Saving_Total"] / agg["Custo_Antigo_Total"].replace(0, np.nan)
    ).fillna(0)

    # SLA compliance: usa dados externos se disponíveis, senão estima
    if compliance_df is not None and "Transp_Nova" in compliance_df.columns:
        comp_map = compliance_df.set_index("Transp_Nova")["Pct_Compliance"] / 100
        agg["SLA_Compliance"] = agg["Transp_Nova"].map(comp_map).fillna(0.5)
    else:
        # Estima: pedidos com prazo <= target / total
        comp_por_transp = (
            df_regiao.assign(OK=df_regiao["Prazo_Novo"] <= target_dias)
            .groupby("Transp_Nova")["OK"]
            .mean()
        )
        agg["SLA_Compliance"] = agg["Transp_Nova"].map(comp_por_transp).fillna(0)

    # Normaliza saving para 0-1 (clip entre -0.2 e 0.2)
    saving_norm = (agg["Saving_Pct"].clip(-0.2, 0.2) + 0.2) / 0.4

    agg["Score"] = (
        REGIONAL_SCORE_PESOS["saving_pct"] * saving_norm
        + REGIONAL_SCORE_PESOS["sla_compliance_pct"] * agg["SLA_Compliance"]
        + REGIONAL_SCORE_PESOS["volume_share"] * agg["Volume_Share"]
    ).round(4)

    return agg.sort_values("Score", ascending=False)


def _selecionar_recomendacoes(scores: pd.DataFrame) -> Tuple[str, str]:
    """Seleciona transportadora principal e backup com base no score.

    Se a diferença entre 1ª e 2ª for < EMPATE_TECNICO_THRESHOLD, recomenda mix.

    Args:
        scores: DataFrame com Score por transportadora, ordenado desc.

    Returns:
        Tupla (principal, backup).
    """
    if scores.empty:
        return "N/D", "N/D"

    principal_row = scores.iloc[0]
    principal = str(principal_row["Transp_Nova"])

    if len(scores) < 2:
        return principal, "N/D"

    backup_row = scores.iloc[1]
    backup = str(backup_row["Transp_Nova"])

    diff_score = (principal_row["Score"] - backup_row["Score"]) * 100
    if diff_score < EMPATE_TECNICO_THRESHOLD:
        principal = f"{principal} + {backup} (Mix)"
        backup = "Avaliar conforme volume"

    return principal, backup


def _calcular_custo_target(df_regiao: pd.DataFrame, transp_principal: str) -> float:
    """Calcula o custo target como média atual menos saving potencial estimado.

    Args:
        df_regiao: DataFrame filtrado para a região.
        transp_principal: Nome da transportadora principal recomendada.

    Returns:
        Custo target em R$.
    """
    # Remove indicador de mix para match parcial
    nome_base = transp_principal.split(" + ")[0].split(" (")[0]

    df_transp = df_regiao[df_regiao["Transp_Nova"].str.startswith(nome_base)]
    if df_transp.empty:
        df_transp = df_regiao

    custo_medio = df_transp["Custo_Novo"].mean()
    saving_medio = (GANHO_ESCALA_MIN + GANHO_ESCALA_MAX) / 2
    return custo_medio * (1 - saving_medio)


def _calcular_impacto_consolidacao(
    df_regiao: pd.DataFrame,
    transp_principal: str,
) -> dict:
    """Projeta impacto financeiro da consolidação de 100% do volume na principal.

    Args:
        df_regiao: DataFrame filtrado para a região.
        transp_principal: Nome da transportadora recomendada.

    Returns:
        Dicionário com custo_atual_fragmentado, custo_consolidado_estimado,
        economia_estimada e economia_pct.
    """
    custo_atual = df_regiao["Custo_Novo"].sum()
    nome_base = transp_principal.split(" + ")[0].split(" (")[0]

    df_transp = df_regiao[df_regiao["Transp_Nova"].str.startswith(nome_base)]
    ticket_transp = df_transp["Custo_Novo"].mean() if not df_transp.empty else df_regiao["Custo_Novo"].mean()

    volume_total = len(df_regiao)
    custo_consolidado = ticket_transp * volume_total * (1 - GANHO_ESCALA_MIN)
    economia = custo_atual - custo_consolidado
    economia_pct = (economia / custo_atual * 100) if custo_atual > 0 else 0.0

    return {
        "Custo_Atual_Fragmentado": round(custo_atual, 2),
        "Custo_Consolidado_Estimado": round(custo_consolidado, 2),
        "Economia_Estimada": round(economia, 2),
        "Economia_Pct": round(economia_pct, 1),
    }


def _gerar_texto_recomendacao(
    regiao: str,
    principal: str,
    backup: str,
    scores: pd.DataFrame,
    impacto: dict,
) -> str:
    """Gera texto consultivo para a recomendação regional.

    Args:
        regiao: Nome da região.
        principal: Transportadora principal recomendada.
        backup: Transportadora backup.
        scores: DataFrame de scores para a região.
        impacto: Dicionário com análise de consolidação.

    Returns:
        String com recomendação formatada.
    """
    economia_pct = impacto.get("Economia_Pct", 0)
    economia_val = impacto.get("Economia_Estimada", 0)

    score_top = scores.iloc[0]["Score"] * 100 if not scores.empty else 0

    return (
        f"{regiao.upper()}: Recomendado {principal} (score: {score_top:.0f}/100). "
        f"Backup: {backup}. "
        f"Consolidação estimada: economia de R$ {economia_val:,.0f} ({economia_pct:.1f}%).".replace(",", ".")
    )
