"""Análise de migração e churn de transportadoras.

Extrai e organiza a análise de migração do teste18.py em um módulo
coeso com geração de insights automáticos.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from config.constants import REGIOES_BR
from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)


@dataclass
class MigrationAnalysisResult:
    """Resultado da análise de migração de transportadoras.

    Attributes:
        df_migrados: DataFrame filtrado apenas para pedidos Migrados (Troca).
        resumo_por_transportadora: DataFrame com saving e volume por transportadora destino.
        insights: Dicionário com textos de insights gerados automaticamente.
        has_migration: Indica se houve migração no estudo.
    """

    df_migrados: pd.DataFrame = field(default_factory=pd.DataFrame)
    resumo_por_transportadora: pd.DataFrame = field(default_factory=pd.DataFrame)
    insights: Dict[str, str] = field(default_factory=dict)
    has_migration: bool = False


def analisar_migracao(
    df: pd.DataFrame,
    resumo_saving: dict,
    resumo_transp: pd.DataFrame,
) -> MigrationAnalysisResult:
    """Executa análise de migração de transportadoras.

    Preserva a lógica completa de insights do teste18.py e a organiza
    em um resultado estruturado.

    Args:
        df: DataFrame processado com colunas Status_Migracao, Transp_Nova,
            Transp_Antiga, Custo_Novo, Custo_Antigo, Saving_Valor, Delta_Prazo,
            UF, Peso, CEP_Faixa.
        resumo_saving: Dicionário com totais financeiros.
        resumo_transp: DataFrame com métricas por transportadora.

    Returns:
        MigrationAnalysisResult com análise completa.
    """
    df_migrados = df[df["Status_Migracao"] == "Migrado (Troca)"].copy()

    if df_migrados.empty:
        logger.info("Nenhuma migração de transportadora identificada.")
        return MigrationAnalysisResult(has_migration=False)

    # Enriquece com região
    mapa_reg = {uf: reg for reg, ufs in REGIOES_BR.items() for uf in ufs}
    df_migrados["Regiao_Temp"] = df_migrados["UF"].map(mapa_reg).fillna("Outros")

    resumo = (
        df_migrados.groupby("Transp_Nova")
        .agg(
            Volume=("Custo_Novo", "count"),
            Saving=("Saving_Valor", "sum"),
            Custo_Novo_Medio=("Custo_Novo", "mean"),
            Custo_Antigo_Medio=("Custo_Antigo", "mean"),
            Delta_Prazo_Medio=("Delta_Prazo", "mean"),
        )
        .reset_index()
        .sort_values("Volume", ascending=False)
    )

    insights = _gerar_insights_migracao(df_migrados, resumo_saving, resumo_transp)

    logger.info(
        "Migração: %d pedidos migrados | %d transportadoras destino",
        len(df_migrados), len(resumo),
    )

    return MigrationAnalysisResult(
        df_migrados=df_migrados,
        resumo_por_transportadora=resumo,
        insights=insights,
        has_migration=True,
    )


def _gerar_insights_migracao(
    df_migrados: pd.DataFrame,
    resumo_saving: dict,
    resumo_transp: pd.DataFrame,
) -> Dict[str, str]:
    """Gera dicionário de insights consultivos sobre a migração.

    Preserva a lógica completa de geração de texto do teste18.py.

    Args:
        df_migrados: DataFrame filtrado de migrados, com Regiao_Temp.
        resumo_saving: Dicionário de totais financeiros.
        resumo_transp: DataFrame de métricas por transportadora.

    Returns:
        Dicionário com chaves: titulo, txt_mix, txt_fin, txt_geo, txt_exp.
    """
    saving_mig = df_migrados["Saving_Valor"].sum()
    custo_antigo_mig = df_migrados["Custo_Antigo"].sum()
    ticket_novo = df_migrados["Custo_Novo"].mean()
    ticket_medio_geral = resumo_transp["Ticket_Medio"].mean()
    peso_medio = df_migrados["Peso"].mean()

    # Lógica de dominância
    share_migracao = df_migrados["Transp_Nova"].value_counts(normalize=True)
    if share_migracao.empty:
        titulo = "INSIGHTS ESTRATÉGICOS: MIGRAÇÃO"
        txt_mix_intro = "EFEITO DE MIX: Múltiplas transportadoras participaram da migração."
    else:
        top_nova_nome = share_migracao.idxmax()
        top_nova_share = share_migracao.max()
        is_mixed = top_nova_share < 0.70

        if is_mixed:
            top_2 = " e ".join(str(x) for x in share_migracao.head(2).index.tolist())
            titulo = "INSIGHTS ESTRATÉGICOS: MIX DE TRANSPORTADORAS"
            txt_mix_intro = f"EFEITO DE MIX (MULTIPLAYER): A estratégia vencedora combinou {top_2}."
        else:
            titulo = f"INSIGHTS ESTRATÉGICOS: POR QUE A {str(top_nova_nome).upper()} GANHOU?"
            txt_mix_intro = (
                f"EFEITO DE MIX: A {top_nova_nome} dominou a migração "
                f"({top_nova_share * 100:.0f}% do volume)."
            )

    if ticket_novo > ticket_medio_geral * 1.1:
        txt_mix = (
            f"1. {txt_mix_intro} Novo cenário absorveu rotas de ALTA COMPLEXIDADE "
            f"(Média: {peso_medio:.1f}kg)."
        )
    else:
        txt_mix = (
            f"1. {txt_mix_intro} Novo cenário venceu pela competitividade de preço "
            f"em rotas de perfil padrão (Média: {peso_medio:.1f}kg)."
        )

    pct_saving = (saving_mig / custo_antigo_mig * 100) if custo_antigo_mig > 0 else 0
    uf_saving_series = df_migrados.groupby("UF")["Saving_Valor"].sum()
    uf_maior_saving = uf_saving_series.idxmax() if not uf_saving_series.empty else "N/A"
    txt_fin = (
        f"2. FINANCEIRO: Saving líquido de R$ {saving_mig:,.2f} ({pct_saving:.1f}%), "
        f"maior impacto em {uf_maior_saving}."
    ).replace(",", ".")

    regiao_vc = df_migrados["Regiao_Temp"].value_counts()
    if not regiao_vc.empty:
        top_regiao = regiao_vc.idxmax()
        top_regiao_share = regiao_vc.max() / len(df_migrados) * 100
        geo_str = f"Foco na região {top_regiao.upper()} ({top_regiao_share:.0f}%)."
    else:
        geo_str = "Distribuição regional não identificada."
    cep_cols = df_migrados["CEP_Faixa"].value_counts().head(3).index.tolist() if "CEP_Faixa" in df_migrados.columns else []
    top_ceps = ", ".join(cep_cols) if cep_cols else "N/A"
    txt_geo = f"3. GEOGRAFIA: {geo_str} Top CEPs: {top_ceps}."

    delta_por_regiao = df_migrados.groupby("Regiao_Temp")["Delta_Prazo"].mean().dropna()
    if not delta_por_regiao.empty:
        melhor_regiao = delta_por_regiao.idxmin()
        ganho_dias = delta_por_regiao.min()
    else:
        melhor_regiao = ""
        ganho_dias = 0.0
    if ganho_dias <= -0.5 and melhor_regiao:
        txt_exp = (
            f"4. EXPERIÊNCIA: Cliente do {melhor_regiao.upper()} ganha "
            f"{abs(ganho_dias):.1f} dias de prazo."
        )
    else:
        txt_exp = "4. EXPERIÊNCIA: Prazo de entrega mantido estável (troca transparente)."

    return {
        "titulo": titulo,
        "txt_mix": txt_mix,
        "txt_fin": txt_fin,
        "txt_geo": txt_geo,
        "txt_exp": txt_exp,
    }
