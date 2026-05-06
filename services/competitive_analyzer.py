"""Análise de competitividade, win rate e target price por transportadora.

Evolui a análise de competitividade existente no teste18.py adicionando:
- Win Rate cruzado por região e faixa de peso.
- Target Price Calculator com gap por transportadora.
- Price Elasticity Insights por faixa de peso.
- Perfil BID completo para qualquer transportadora (inclusive 0 vitórias).
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from config.constants import FAIXAS_PESO, LABELS_PESO, ORDEM_REGIOES, REGIOES_BR
from config.settings import TARGET_PRICE_DESCONTO
from utils.logger import get_logger
from utils.text_utils import formatar_monetario_br

logger: logging.Logger = get_logger(__name__)

# Mapa UF → Região reutilizado em todo o módulo
_MAPA_UF_REGIAO: Dict[str, str] = {
    uf: regiao for regiao, ufs in REGIOES_BR.items() for uf in ufs
}


@dataclass
class BidProfileResult:
    """Perfil BID completo de uma transportadora, independente de vitórias.

    Attributes:
        nome: Nome da transportadora analisada.
        cenario: 'participou_com_ganhos' | 'participou_sem_ganhos' | 'ausente_do_bid'.
        participou_bid: True se aparece em Transp_Nova na recotação.
        qtd_rotas_bid: Qtd de rotas cotadas pela transportadora.
        qtd_rotas_historico: Qtd de rotas onde era a transportadora atual.
        win_rate_pct: Percentual de rotas ganhas (pode ser 0.0).
        qtd_ganhos: Quantidade de rotas vencidas.
        qtd_perdidos: Quantidade de rotas perdidas.
        gap_medio_para_ganhar: Quanto precisaria reduzir em média para ganhar cada rota perdida.
        target_price_medio: Custo_Antigo * (1 - desconto) nas rotas perdidas.
        ticket_medio_transp: Custo médio por pedido desta transportadora no BID.
        delta_vs_mercado_pct: Diferença percentual do ticket vs ticket médio do mercado.
        win_rate_por_regiao: {regiao: win_rate_pct} para cada região com dados.
        gap_por_regiao: {regiao: gap_medio_R$} nas rotas perdidas por região.
        ufs_atendidas: Número de UFs distintas cobertas.
        regioes_cobertas: {regiao: qtd_rotas} distribuição de volume por região.
        custo_historico_medio: Custo médio histórico (só para ausentes do BID).
        target_competitivo: Custo_historico * (1 - desconto) — preço alvo hipotético.
        nota: Texto explicativo do cenário.
    """

    nome: str = ""
    cenario: str = ""
    participou_bid: bool = False
    qtd_rotas_bid: int = 0
    qtd_rotas_historico: int = 0
    win_rate_pct: float = 0.0
    qtd_ganhos: int = 0
    qtd_perdidos: int = 0
    gap_medio_para_ganhar: float = 0.0
    target_price_medio: float = 0.0
    ticket_medio_transp: float = 0.0
    delta_vs_mercado_pct: float = 0.0
    win_rate_por_regiao: Dict[str, float] = field(default_factory=dict)
    gap_por_regiao: Dict[str, float] = field(default_factory=dict)
    ufs_atendidas: int = 0
    regioes_cobertas: Dict[str, int] = field(default_factory=dict)
    custo_historico_medio: float = 0.0
    target_competitivo: float = 0.0
    nota: str = ""


@dataclass
class BidGapResult:
    """Análise de 'Gap para Liderar' no BID: quanto a carrier precisa reduzir para ser T1.

    Diferente de BidProfileResult (que compara vs Custo_Antigo/histórico), este
    dataclass compara a carrier alvo diretamente contra o T1 do BID atual —
    i.e., o vencedor real de preço em cada pedido no arquivo cru.

    Attributes:
        transp: Nome da transportadora analisada.
        total_pedidos: Total de pedidos onde a carrier cotou.
        pedidos_lider: Pedidos onde a carrier já é T1 (mais barata).
        pct_lider: % de pedidos onde já lidera.
        gap_medio_r: Gap médio em R$ para se tornar T1 (só pedidos não-líderes).
        gap_medio_pct: Gap médio em % para se tornar T1.
        distribuicao_posicao: {"T1": N, "T2": N, ...} quantidade por posição.
        sensibilidade: Lista de cenários de desconto e pedidos ganhos.
        competidores: Ranking de carriers que ficam à frente, com gap médio.
    """

    transp: str = ""
    total_pedidos: int = 0
    pedidos_lider: int = 0
    pct_lider: float = 0.0
    gap_medio_r: float = 0.0
    gap_medio_pct: float = 0.0
    ticket_medio_tj: float = 0.0       # custo médio da carrier foco em TODOS os pedidos cotados (T1 a T5)
    ticket_medio_t1: float = 0.0       # custo médio do vencedor T1 (nos pedidos onde a foco não é T1)
    distribuicao_posicao: Dict[str, int] = field(default_factory=dict)
    sensibilidade: List[Dict] = field(default_factory=list)
    competidores: List[Dict] = field(default_factory=list)
    df_posicao: Optional[pd.DataFrame] = field(default=None, repr=False)  # por pedido: CEP_Destino, Gap_R, Gap_Pct, TJ_Custo, T1_Custo


def analisar_gap_bid(
    caminho_crua: str,
    transp_alvo: str,
) -> Optional["BidGapResult"]:
    """Calcula o gap que a transportadora precisa fechar para liderar o BID.

    Lê o arquivo cru no formato wide (T1-T5 por linha) e, para cada pedido,
    compara o custo da carrier alvo contra o T1 (vencedor de preço).

    Args:
        caminho_crua: Caminho do arquivo de recotação crua (.xlsx ou .xls).
        transp_alvo: Nome da transportadora a analisar.

    Returns:
        BidGapResult com todas as estatísticas, ou None se a carrier não aparecer.
    """
    from loaders.raw_recotacao_loader import analisar_posicao_bid

    try:
        df = analisar_posicao_bid(caminho_crua, transp_alvo)
    except Exception as exc:
        logger.error("analisar_gap_bid: erro ao ler arquivo cru: %s", exc)
        return None

    if df.empty:
        return None

    result = BidGapResult(transp=transp_alvo)
    result.df_posicao = df
    result.total_pedidos = len(df)
    result.pedidos_lider = int((df["TJ_Posicao"] == 1).sum())
    result.pct_lider = round(result.pedidos_lider / result.total_pedidos * 100, 1)

    df_nao_lider = df[df["TJ_Posicao"] > 1].copy()
    if not df_nao_lider.empty:
        result.gap_medio_r    = round(float(df_nao_lider["Gap_R"].mean()), 2)
        result.gap_medio_pct  = round(float(df_nao_lider["Gap_Pct"].mean()), 1)
        result.ticket_medio_t1 = round(float(df_nao_lider["T1_Custo"].mean()), 2)
    else:
        result.gap_medio_r    = 0.0
        result.gap_medio_pct  = 0.0
        result.ticket_medio_t1 = round(float(df["T1_Custo"].mean()), 2) if not df.empty else 0.0

    result.ticket_medio_tj = round(float(df["TJ_Custo"].mean()), 2) if not df.empty else 0.0

    # Distribuição por posição
    for pos in range(1, 6):
        result.distribuicao_posicao[f"T{pos}"] = int((df["TJ_Posicao"] == pos).sum())

    # Sensibilidade: quantos pedidos não-líderes a carrier passaria a liderar
    # com cada nível de desconto (Gap_Pct <= desconto)
    acumulado = 0
    for desc in [5, 10, 15, 20, 25, 30]:
        ganhos = int((df_nao_lider["Gap_Pct"] <= desc).sum()) if not df_nao_lider.empty else 0
        acumulado = ganhos  # já é cumulativo (ganhos inclui todos com gap <= desc)
        result.sensibilidade.append({
            "desconto_pct":  desc,
            "pedidos_ganhos": ganhos,
            "pct_total":     round(ganhos / result.total_pedidos * 100, 1),
        })

    # Competidores: quem fica na frente de TJ com mais frequência
    if not df_nao_lider.empty:
        comp = (
            df_nao_lider.groupby("T1_Nome")
            .agg(
                vitorias_vs_tj=("Gap_R", "count"),
                gap_medio_r=("Gap_R", "mean"),
                gap_medio_pct=("Gap_Pct", "mean"),
            )
            .reset_index()
            .rename(columns={"T1_Nome": "nome"})
            .sort_values("vitorias_vs_tj", ascending=False)
        )
        comp["gap_medio_r"]   = comp["gap_medio_r"].round(2)
        comp["gap_medio_pct"] = comp["gap_medio_pct"].round(1)
        result.competidores = comp.to_dict("records")

    logger.info(
        "BidGap '%s': %d pedidos | lidera %d (%.1f%%) | gap médio R$%.2f (%.1f%%)",
        transp_alvo, result.total_pedidos, result.pedidos_lider,
        result.pct_lider, result.gap_medio_r, result.gap_medio_pct,
    )
    return result


def perfil_bid_de_gap_result(gap: BidGapResult) -> BidProfileResult:
    """Constrói um BidProfileResult correto a partir de um BidGapResult.

    Usado no modo recotação crua, onde a vitória real é TJ ser T1 no BID
    (não TJ ser mais barata que o contrato histórico).

    Args:
        gap: Resultado de analisar_gap_bid com dados do arquivo cru.

    Returns:
        BidProfileResult com cenário e métricas baseados em posição T1.
    """
    perfil = BidProfileResult(nome=gap.transp)
    perfil.participou_bid        = True
    perfil.qtd_rotas_bid         = gap.total_pedidos
    perfil.qtd_ganhos            = gap.pedidos_lider
    perfil.qtd_perdidos          = gap.total_pedidos - gap.pedidos_lider
    perfil.win_rate_pct          = gap.pct_lider
    perfil.gap_medio_para_ganhar = gap.gap_medio_r
    perfil.target_price_medio    = gap.ticket_medio_t1
    perfil.ticket_medio_transp   = gap.ticket_medio_tj
    perfil.win_rate_por_regiao   = {}  # sem dado regional no BidGapResult

    perfil.cenario = (
        "participou_com_ganhos" if gap.pedidos_lider > 0
        else "participou_sem_ganhos"
    )

    if perfil.cenario == "participou_sem_ganhos":
        perfil.nota = (
            f"{gap.transp} participou do BID ({gap.total_pedidos} pedidos) "
            f"mas não liderou nenhuma cotação (0% de win rate no BID). "
            f"Gap médio para se tornar a opção mais barata: "
            f"R$ {gap.gap_medio_r:.2f}/pedido ({gap.gap_medio_pct:.1f}%). "
            f"Ticket médio da carrier: R$ {gap.ticket_medio_tj:.2f} vs "
            f"R$ {gap.ticket_medio_t1:.2f} do líder de preço (T1)."
        )
    else:
        perfil.nota = (
            f"{gap.transp}: lidera o preço em {gap.pedidos_lider} de "
            f"{gap.total_pedidos} pedidos ({gap.pct_lider:.1f}% win rate no BID). "
            f"Nos {perfil.qtd_perdidos} pedidos restantes, gap médio de "
            f"R$ {gap.gap_medio_r:.2f} ({gap.gap_medio_pct:.1f}%) para assumir o T1."
        )

    logger.info(
        "perfil_bid_de_gap_result '%s': cenário=%s | win_rate=%.1f%% | gap_medio=R$%.2f",
        gap.transp, perfil.cenario, perfil.win_rate_pct, perfil.gap_medio_para_ganhar,
    )
    return perfil


@dataclass
class CompetitiveAnalysisResult:
    """Resultado da análise de competitividade.

    Attributes:
        win_rate_regiao: DataFrame com win rate por região.
        win_rate_peso: DataFrame com win rate por faixa de peso.
        win_rate_cruzado: DataFrame com win rate por região × faixa de peso.
        target_price: DataFrame com target price por transportadora.
        elasticity_insights: Lista de textos sobre elasticidade por faixa de peso.
        texto_diagnostico: Texto de diagnóstico consolidado Brasil.
        perfil_bid: Perfil BID detalhado da transportadora foco (se informada).
    """

    win_rate_regiao: pd.DataFrame = field(default_factory=pd.DataFrame)
    win_rate_peso: pd.DataFrame = field(default_factory=pd.DataFrame)
    win_rate_cruzado: pd.DataFrame = field(default_factory=pd.DataFrame)
    target_price: pd.DataFrame = field(default_factory=pd.DataFrame)
    elasticity_insights: List[str] = field(default_factory=list)
    texto_diagnostico: str = ""
    perfil_bid: Optional[BidProfileResult] = None


def analisar_competitividade(
    df: pd.DataFrame,
    transp_foco: Optional[List[str]] = None,
) -> CompetitiveAnalysisResult:
    """Executa análise completa de competitividade.

    Args:
        df: DataFrame processado com colunas Tem_Base, Custo_Novo, Custo_Antigo,
            UF, Peso, Transp_Nova.
        transp_foco: Lista de transportadoras de foco para diagnóstico. Se None,
            usa as top 2 por volume.

    Returns:
        CompetitiveAnalysisResult com todas as análises.
    """
    df_comp = df[df["Tem_Base"]].copy()

    if df_comp.empty:
        logger.warning("Sem dados com base histórica para análise de competitividade.")
        # Ainda gera perfil BID se houver transportadora foco
        perfil = None
        if transp_foco:
            perfil = analisar_bid_transportadora(df, transp_foco[0])
        return CompetitiveAnalysisResult(perfil_bid=perfil)

    logger.info(
        "Análise de competitividade sobre %d pedidos com base histórica", len(df_comp)
    )

    # Marca pedidos vencidos (custo novo < custo antigo)
    df_comp["Venceu"] = df_comp["Custo_Novo"] < df_comp["Custo_Antigo"]

    # Mapeia regiões
    df_comp["Regiao"] = df_comp["UF"].map(_MAPA_UF_REGIAO).fillna("Outros")

    # Faixa de peso
    df_comp["Faixa_Peso"] = pd.cut(df_comp["Peso"], bins=FAIXAS_PESO, labels=LABELS_PESO)

    win_rate_regiao = _calcular_win_rate_regiao(df_comp)
    win_rate_peso = _calcular_win_rate_peso(df_comp)
    win_rate_cruzado = _calcular_win_rate_cruzado(df_comp)
    target_price = _calcular_target_price(df_comp)
    elasticity = _gerar_insights_elasticidade(df_comp)
    diagnostico = _gerar_diagnostico_brasil(df_comp, transp_foco)

    # Perfil BID da transportadora foco (funciona mesmo com 0 vitórias)
    perfil = None
    if transp_foco:
        perfil = analisar_bid_transportadora(df, transp_foco[0])

    logger.info(
        "Win rate global: %.1f%% | %d transportadoras no target price | perfil_bid: %s",
        df_comp["Venceu"].mean() * 100,
        len(target_price),
        perfil.cenario if perfil else "N/A",
    )

    return CompetitiveAnalysisResult(
        win_rate_regiao=win_rate_regiao,
        win_rate_peso=win_rate_peso,
        win_rate_cruzado=win_rate_cruzado,
        target_price=target_price,
        elasticity_insights=elasticity,
        texto_diagnostico=diagnostico,
        perfil_bid=perfil,
    )


# ── Análise BID por transportadora (pública) ─────────────────────────────────

def analisar_bid_transportadora(df: pd.DataFrame, nome_transp: str) -> BidProfileResult:
    """Gera perfil BID completo de uma transportadora, independente de vitórias.

    Cobre três cenários:
    - participou_com_ganhos: aparece em Transp_Nova e ganhou ao menos uma rota.
    - participou_sem_ganhos: aparece em Transp_Nova mas nunca foi mais barata.
    - ausente_do_bid: não aparece em Transp_Nova (apenas no histórico como Transp_Antiga).

    Args:
        df: DataFrame processado por carregar_e_processar.
        nome_transp: Nome exato (ou parcial case-insensitive) da transportadora.

    Returns:
        BidProfileResult com todos os campos preenchidos conforme disponibilidade.
    """
    nome_upper = nome_transp.strip().upper()

    # Busca flexível: nome exato ou prefixo
    mask_bid  = df["Transp_Nova"].str.strip().str.upper() == nome_upper
    mask_hist = df["Transp_Antiga"].str.strip().str.upper() == nome_upper

    df_transp = df[mask_bid].copy()
    df_hist   = df[mask_hist].copy()

    perfil = BidProfileResult(nome=nome_transp)

    # ── Cenário C: ausente do BID ─────────────────────────────────────────────
    if df_transp.empty:
        perfil.participou_bid = False
        perfil.qtd_rotas_historico = len(df_hist)

        if df_hist.empty:
            perfil.cenario = "ausente_do_bid"
            perfil.nota = (
                f"{nome_transp} não participou desta recotação e não possui histórico "
                "como transportadora atual nas rotas analisadas."
            )
            logger.info("BID perfil: %s — ausente (sem dados)", nome_transp)
            return perfil

        perfil.cenario = "ausente_do_bid"
        custo_hist_medio = df_hist["Custo_Antigo"].mean()
        ticket_mercado   = df["Custo_Novo"].mean()
        perfil.custo_historico_medio = round(custo_hist_medio, 2)
        perfil.target_competitivo    = round(custo_hist_medio * (1 - TARGET_PRICE_DESCONTO), 2)
        perfil.delta_vs_mercado_pct  = round((custo_hist_medio / ticket_mercado - 1) * 100, 1) if ticket_mercado else 0.0

        # Cobertura histórica por região
        if "UF" in df_hist.columns:
            df_hist["_Regiao"] = df_hist["UF"].map(_MAPA_UF_REGIAO).fillna("Outros")
            perfil.ufs_atendidas   = int(df_hist["UF"].nunique())
            perfil.regioes_cobertas = df_hist["_Regiao"].value_counts().to_dict()

        perfil.nota = (
            f"{nome_transp} não participou desta recotação. "
            f"Custo histórico médio: R$ {perfil.custo_historico_medio:.2f}. "
            f"Para ser competitiva, precisaria atingir R$ {perfil.target_competitivo:.2f} "
            f"({abs(perfil.delta_vs_mercado_pct):.1f}% "
            f"{'acima' if perfil.delta_vs_mercado_pct > 0 else 'abaixo'} do mercado atual)."
        )
        logger.info("BID perfil: %s — ausente_do_bid, hist=%d rotas", nome_transp, len(df_hist))
        return perfil

    # ── Cenários A e B: participou do BID ────────────────────────────────────
    perfil.participou_bid     = True
    perfil.qtd_rotas_bid      = len(df_transp)
    perfil.qtd_rotas_historico = len(df_hist)

    # Ticket médio vs mercado
    ticket_mercado            = df["Custo_Novo"].mean()
    perfil.ticket_medio_transp = round(df_transp["Custo_Novo"].mean(), 2)
    perfil.delta_vs_mercado_pct = round(
        (perfil.ticket_medio_transp / ticket_mercado - 1) * 100, 1
    ) if ticket_mercado else 0.0

    # Cobertura geográfica
    if "UF" in df_transp.columns:
        df_transp["_Regiao"] = df_transp["UF"].map(_MAPA_UF_REGIAO).fillna("Outros")
        perfil.ufs_atendidas    = int(df_transp["UF"].nunique())
        perfil.regioes_cobertas = df_transp["_Regiao"].value_counts().to_dict()

    # Win rate (só possível onde há base histórica)
    df_com_base = df_transp[df_transp["Tem_Base"]].copy()

    if df_com_base.empty:
        # Sem base histórica: marca win_rate_por_regiao com NaN por região
        # para que o PDF mostre "N/D" na tabela (em vez de omitir a seção)
        perfil.cenario = "participou_sem_ganhos"
        if "_Regiao" in df_transp.columns:
            for reg in df_transp["_Regiao"].unique():
                perfil.win_rate_por_regiao[str(reg)] = float("nan")
        elif perfil.regioes_cobertas:
            for reg in perfil.regioes_cobertas:
                perfil.win_rate_por_regiao[str(reg)] = float("nan")
        perfil.nota = (
            f"{nome_transp} participou da recotação ({perfil.qtd_rotas_bid} rotas), "
            "mas nenhuma possui histórico de custo anterior para comparação. "
            "Win rate não calculável — são todos novos volumes."
        )
        logger.info("BID perfil: %s — sem base histórica", nome_transp)
        return perfil

    df_com_base["Venceu"] = df_com_base["Custo_Novo"] < df_com_base["Custo_Antigo"]
    df_com_base["_Regiao"] = df_com_base["UF"].map(_MAPA_UF_REGIAO).fillna("Outros")

    perfil.qtd_ganhos   = int(df_com_base["Venceu"].sum())
    perfil.qtd_perdidos = int((~df_com_base["Venceu"]).sum())
    perfil.win_rate_pct = round(df_com_base["Venceu"].mean() * 100, 1)

    # Win rate por região — sempre preenchido; regiões sem histórico ficam NaN
    todas_regioes = set(perfil.regioes_cobertas.keys()) if perfil.regioes_cobertas else set()
    wr_reg = (
        df_com_base.groupby("_Regiao")["Venceu"]
        .mean()
        .mul(100)
        .round(1)
    )
    perfil.win_rate_por_regiao = {str(k): v for k, v in wr_reg.to_dict().items()}
    # Regiões cobertas mas sem base histórica → NaN (exibido como N/D no PDF)
    for reg in todas_regioes:
        if reg not in perfil.win_rate_por_regiao:
            perfil.win_rate_por_regiao[reg] = float("nan")

    # Gap para ganhar nas rotas perdidas
    df_perdidos = df_com_base[~df_com_base["Venceu"]].copy()
    if not df_perdidos.empty:
        df_perdidos["_Gap"] = df_perdidos["Custo_Novo"] - df_perdidos["Custo_Antigo"]
        df_perdidos["_Target"] = df_perdidos["Custo_Antigo"] * (1 - TARGET_PRICE_DESCONTO)
        perfil.gap_medio_para_ganhar = round(df_perdidos["_Gap"].mean(), 2)
        perfil.target_price_medio    = round(df_perdidos["_Target"].mean(), 2)

        gap_reg = (
            df_perdidos.groupby("_Regiao")["_Gap"]
            .mean()
            .round(2)
        )
        perfil.gap_por_regiao = {str(k): v for k, v in gap_reg.to_dict().items()}

    perfil.cenario = "participou_com_ganhos" if perfil.qtd_ganhos > 0 else "participou_sem_ganhos"

    if perfil.cenario == "participou_sem_ganhos":
        perfil.nota = (
            f"{nome_transp} participou da recotação ({perfil.qtd_rotas_bid} rotas cotadas, "
            f"{perfil.qtd_perdidos} com base histórica) mas não venceu nenhuma rota. "
            f"Gap médio para vencer: R$ {abs(perfil.gap_medio_para_ganhar):.2f}/pedido. "
            f"Target price médio necessário: R$ {perfil.target_price_medio:.2f}."
        )
    else:
        perfil.nota = (
            f"{nome_transp}: {perfil.qtd_ganhos} rotas ganhas de {len(df_com_base)} "
            f"com base histórica (win rate {perfil.win_rate_pct:.1f}%). "
            f"{perfil.qtd_perdidos} rotas ainda acima do target — "
            f"gap médio R$ {abs(perfil.gap_medio_para_ganhar):.2f}/pedido."
        )

    logger.info(
        "BID perfil: %s — %s | win_rate=%.1f%% | gap_medio=R$%.2f",
        nome_transp, perfil.cenario, perfil.win_rate_pct, perfil.gap_medio_para_ganhar,
    )
    return perfil


# ── Funções auxiliares privadas ───────────────────────────────────────────────

def _calcular_win_rate_regiao(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula win rate por região.

    Args:
        df: DataFrame com colunas Venceu e Regiao.

    Returns:
        DataFrame com Win_Rate_Pct por região, ordenado.
    """
    result = (
        df.groupby("Regiao")["Venceu"]
        .agg(Win_Rate_Pct=lambda x: x.mean() * 100, Total=len)
        .reset_index()
    )
    result["Win_Rate_Pct"] = result["Win_Rate_Pct"].round(1)
    return result.sort_values("Win_Rate_Pct", ascending=False)


def _calcular_win_rate_peso(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula win rate por faixa de peso.

    Args:
        df: DataFrame com colunas Venceu e Faixa_Peso.

    Returns:
        DataFrame com Win_Rate_Pct por faixa de peso.
    """
    result = (
        df.groupby("Faixa_Peso", observed=False)["Venceu"]
        .agg(Win_Rate_Pct=lambda x: x.mean() * 100, Total=len)
        .reset_index()
    )
    result["Win_Rate_Pct"] = result["Win_Rate_Pct"].round(1)
    return result


def _calcular_win_rate_cruzado(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula win rate cruzado por região e faixa de peso.

    Args:
        df: DataFrame com colunas Venceu, Regiao e Faixa_Peso.

    Returns:
        DataFrame pivotado com Regiao no índice e Faixa_Peso nas colunas.
    """
    cruzado = (
        df.groupby(["Regiao", "Faixa_Peso"], observed=False)["Venceu"]
        .mean()
        .mul(100)
        .round(1)
        .reset_index()
        .rename(columns={"Venceu": "Win_Rate_Pct"})
    )
    return cruzado.pivot(index="Regiao", columns="Faixa_Peso", values="Win_Rate_Pct").fillna(0)


def _calcular_target_price(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula target price para pedidos perdidos por transportadora.

    Para cada transportadora e rota onde Custo_Novo > Custo_Antigo:
    - Target = Custo_Antigo * (1 - TARGET_PRICE_DESCONTO)
    - Gap = Custo_Novo - Target

    Args:
        df: DataFrame com colunas Venceu, Custo_Novo, Custo_Antigo, Transp_Nova.

    Returns:
        DataFrame com Target_Price_Medio, Gap_Medio, Qtd_Perdidos por transportadora.
    """
    df_perdido = df[~df["Venceu"]].copy()
    if df_perdido.empty:
        return pd.DataFrame()

    df_perdido["Target_Price"] = df_perdido["Custo_Antigo"] * (1 - TARGET_PRICE_DESCONTO)
    df_perdido["Gap"] = df_perdido["Custo_Novo"] - df_perdido["Target_Price"]

    result = (
        df_perdido.groupby("Transp_Nova")
        .agg(
            Qtd_Perdidos=("Custo_Novo", "count"),
            Custo_Novo_Medio=("Custo_Novo", "mean"),
            Target_Price_Medio=("Target_Price", "mean"),
            Gap_Medio=("Gap", "mean"),
        )
        .reset_index()
    )
    result = result.round(2).sort_values("Qtd_Perdidos", ascending=False)
    return result


def _gerar_insights_elasticidade(df: pd.DataFrame) -> List[str]:
    """Identifica faixas de peso com maior/menor competitividade.

    Args:
        df: DataFrame com colunas Venceu e Faixa_Peso.

    Returns:
        Lista de strings com insights sobre elasticidade de preço.
    """
    insights: List[str] = []

    win_peso = (
        df.groupby("Faixa_Peso", observed=False)["Venceu"]
        .mean()
        .mul(100)
        .round(1)
        .dropna()
    )

    if win_peso.empty:
        return insights

    melhor_faixa = str(win_peso.idxmax())
    pior_faixa = str(win_peso.idxmin())
    melhor_pct = win_peso.max()
    pior_pct = win_peso.min()

    insights.append(
        f"COMPETITIVIDADE CONCENTRADA: Melhor win rate na faixa {melhor_faixa} "
        f"({melhor_pct:.0f}% dos pedidos vencidos)."
    )

    if pior_pct < 40:
        insights.append(
            f"PONTO DE ATENÇÃO: Na faixa {pior_faixa}, a tabela perde competitividade "
            f"(apenas {pior_pct:.0f}% win rate). Revisão de pricing recomendada."
        )

    # Identifica faixas consecutivas com win rate alto (> 60%)
    faixas_fortes = [str(f) for f, v in win_peso.items() if v > 60]
    if faixas_fortes:
        insights.append(
            f"ZONA DE FORÇA: Faixas {', '.join(faixas_fortes)} com win rate superior a 60%."
        )

    return insights


def _gerar_diagnostico_brasil(
    df: pd.DataFrame,
    transp_foco: Optional[List[str]],
) -> str:
    """Gera texto de diagnóstico estratégico consolidado Brasil.

    Preserva a lógica do teste18.py (comparativo top 2 grupos) e a enriquece
    com informações de win rate global.

    Args:
        df: DataFrame com colunas Transp_Nova, Custo_Novo, UF, Venceu.
        transp_foco: Lista de transportadoras de foco. Pode ser None.

    Returns:
        String com diagnóstico formatado.
    """
    fmt = lambda x: formatar_monetario_br(x)

    df_br = df.copy()
    df_br["Grupo"] = (
        df_br["Transp_Nova"].str.split(" ").str[0].str.split("-").str[0].str.strip().str.upper()
    )

    grupos_foco: List[str] = []
    if transp_foco:
        grupos_foco = list(
            set(
                str(t).split(" ")[0].split("-")[0].strip().upper()
                for t in transp_foco
            )
        )

    win_global = df["Venceu"].mean() * 100

    if grupos_foco:
        lider = grupos_foco[0]
        df_lider = df_br[df_br["Grupo"] == lider]
        df_mercado = df_br[df_br["Grupo"] != lider]

        if not df_lider.empty and not df_mercado.empty:
            v_lider = df_lider["Custo_Novo"].mean()
            v_mercado = df_mercado["Custo_Novo"].mean()
            gap_pct = ((v_lider / v_mercado) - 1) * 100
            dominancia = df_lider["UF"].value_counts().idxmax()
            status = "abaixo" if gap_pct < 0 else "acima"

            return (
                f"VISÃO BRASIL | Win Rate global: {win_global:.1f}%. "
                f"O grupo {lider} opera com custo medio de {fmt(v_lider)}, "
                f"valor {abs(gap_pct):.1f}% {status} do benchmark ({fmt(v_mercado)}). "
                f"Maior volume concentrado em {dominancia}."
            )

    if len(df_br["Grupo"].unique()) >= 2:
        ranking = df_br["Grupo"].value_counts()
        g1, g2 = ranking.index[0], ranking.index[1]
        v1 = df_br[df_br["Grupo"] == g1]["Custo_Novo"].mean()
        v2 = df_br[df_br["Grupo"] == g2]["Custo_Novo"].mean()
        lider = g1 if v1 < v2 else g2
        desaf = g2 if lider == g1 else g1
        v_lider, v_desaf = min(v1, v2), max(v1, v2)
        gap_reais = v_desaf - v_lider

        return (
            f"VISÃO BRASIL | Win Rate global: {win_global:.1f}%. "
            f"{lider} lidera com custo medio {fmt(v_lider)} vs "
            f"{fmt(v_desaf)} do {desaf}. "
            f"Meta de redução para {desaf}: {fmt(gap_reais)}/pedido."
        )

    return (
        f"VISÃO BRASIL | Win Rate global: {win_global:.1f}%. "
        f"Apenas um grupo econômico identificado — sem benchmark direto disponível."
    )
