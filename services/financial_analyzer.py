"""Análise financeira consolidada: saving, ticket médio e comparativos.

Fornece funções para calcular e formatar os principais KPIs financeiros
do estudo de viabilidade logística.
"""

import logging
from typing import Dict, Tuple

import pandas as pd

from config.constants import REGIOES_BR
from utils.logger import get_logger
from utils.text_utils import formatar_monetario_br

logger: logging.Logger = get_logger(__name__)


def calcular_kpis_financeiros(
    df: pd.DataFrame,
    resumo_saving: dict,
    regioes_br: dict = None,
) -> Dict[str, object]:
    """Calcula KPIs financeiros consolidados para uso no PDF e na capa.

    Args:
        df: DataFrame processado com todas as colunas calculadas.
        resumo_saving: Dicionário com totais financeiros do processamento.

    Returns:
        Dicionário com KPIs: saving_pct, ticket_delta_pct, is_baseline_study,
        texto_resultado e outros.
    """
    custo_antigo = float(resumo_saving.get("Custo_Antigo_Comp", 0))
    custo_novo = float(resumo_saving.get("Custo_Novo_Comp", 0))
    saving_valor = float(resumo_saving.get("Saving_Valor", 0))

    saving_pct = (saving_valor / custo_antigo * 100) if custo_antigo > 0.01 else 0.0
    is_baseline_study = custo_antigo < 100

    ticket_antigo = float(resumo_saving.get("Ticket_Antigo_Base", 0))
    ticket_novo = float(resumo_saving.get("Ticket_Novo_Base", 0))
    ticket_delta_pct = (
        ((ticket_novo / ticket_antigo) - 1) * 100 if ticket_antigo > 0 else 0.0
    )

    custo_new_biz = float(resumo_saving.get("Custo_New_Business", 0))
    qtd_new_biz = int(resumo_saving.get("Qtd_New_Business", 0))

    # ── Métricas para o Health Score ──────────────────────────────────────────
    # pct_ganho_total: % de pedidos com "GANHO TOTAL (Ouro)" entre os comparáveis
    df_comp = df[df["Tem_Base"]] if "Tem_Base" in df.columns else df
    if len(df_comp) > 0 and "Classificacao" in df_comp.columns:
        n_ganho = (df_comp["Classificacao"] == "GANHO TOTAL (Ouro)").sum()
        pct_ganho_total = float(n_ganho / len(df_comp) * 100)
    else:
        pct_ganho_total = 0.0

    # pct_regioes_saving: % das 5 regiões brasileiras com saving líquido positivo
    if "UF" in df.columns and "Saving_Valor" in df.columns and "Tem_Base" in df.columns:
        mapa_uf_regiao = {uf: reg for reg, ufs in REGIOES_BR.items() for uf in ufs}
        df_c = df[df["Tem_Base"]].copy()
        df_c["_Regiao"] = df_c["UF"].map(mapa_uf_regiao)
        saving_por_regiao = df_c.groupby("_Regiao")["Saving_Valor"].sum()
        n_regioes_pos = sum(
            1 for reg in REGIOES_BR
            if saving_por_regiao.get(reg, 0.0) > 0
        )
        pct_regioes_saving = float(n_regioes_pos / len(REGIOES_BR) * 100)
    else:
        pct_regioes_saving = 0.0

    if saving_pct > 5:
        status_fin = "GANHO DE EFICIÊNCIA ESTRUTURAL"
        descricao_fin = f"Saving de {saving_pct:.1f}% sobre a base comparável."
    elif saving_pct < -2:
        status_fin = "CENÁRIO DE INVESTIMENTO (SLA)"
        descricao_fin = f"Incremento de custo de {abs(saving_pct):.1f}%."
    else:
        status_fin = "NEUTRALIDADE FINANCEIRA"
        descricao_fin = "Estabilidade de custos."

    logger.info(
        "KPIs financeiros: saving=R$ %.2f (%.1f%%), status=%s",
        saving_valor, saving_pct, status_fin,
    )

    return {
        "custo_antigo": custo_antigo,
        "custo_novo": custo_novo,
        "saving_valor": saving_valor,
        "saving_pct": saving_pct,
        "is_baseline_study": is_baseline_study,
        "ticket_antigo": ticket_antigo,
        "ticket_novo": ticket_novo,
        "ticket_delta_pct": ticket_delta_pct,
        "custo_new_biz": custo_new_biz,
        "qtd_new_biz": qtd_new_biz,
        "status_fin": status_fin,
        "descricao_fin": descricao_fin,
        "saving_pct_formatado": formatar_monetario_br(saving_valor),
        "pct_ganho_total": pct_ganho_total,
        "pct_regioes_saving": pct_regioes_saving,
    }


def calcular_health_score(
    saving_pct: float,
    pct_ganho_total: float,
    pct_regioes_saving: float,
) -> Tuple[float, str]:
    """Calcula o Score de Saúde da Operação (0-100).

    Fórmula: 50% saving potencial + 30% qualidade do ganho + 20% amplitude geográfica.
    O saving é normalizado: saving_pct >= 20% → 100; <= 0% → 0.

    Args:
        saving_pct: Percentual de saving (pode ser negativo).
        pct_ganho_total: % de pedidos classificados como GANHO TOTAL (Ouro) (0-100).
        pct_regioes_saving: % das regiões brasileiras com saving líquido positivo (0-100).

    Returns:
        Tupla (score 0-100, classificação textual).
    """
    # Normaliza saving para escala 0-100: 0% saving → 0, 20% saving → 100
    saving_norm = max(0.0, min(100.0, saving_pct / 20 * 100))

    score = (
        0.50 * saving_norm
        + 0.30 * pct_ganho_total
        + 0.20 * pct_regioes_saving
    )
    score = round(max(0.0, min(100.0, score)), 1)

    if score >= 75:
        classificacao = "EXCELENTE"
    elif score >= 50:
        classificacao = "BOM"
    elif score >= 30:
        classificacao = "REGULAR"
    else:
        classificacao = "CRITICO"

    logger.info("Health Score: %.1f (%s)", score, classificacao)
    return score, classificacao
