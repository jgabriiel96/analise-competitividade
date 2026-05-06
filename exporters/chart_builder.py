"""Geração de todos os gráficos matplotlib para o relatório PDF.

Preserva integralmente a lógica visual do teste18.py e adiciona novos
gráficos para SLA, malha regional e competitividade evoluída.
"""

import logging
import math
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.cm as cm
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config.constants import (
    COLOR_MAP_CLASSIFICACAO,
    HEX_AMARELO,
    HEX_AZUL,
    HEX_AZUL_ESCURO,
    HEX_CINZA,
    HEX_VERDE,
    HEX_VERMELHO,
    ORDEM_REGIOES,
    REGIOES_BR,
)
from config.settings import (
    CHART_DPI,
    PDF_MAX_TRANSPORTADORAS_HEATMAP,
    PDF_MAX_TRANSPORTADORAS_PESO,
    PDF_MAX_TRANSPORTADORAS_PIE,
)
from exporters.temp_manager import get_temp_path
from services.sla_analyzer import SLAComplianceResult, ALTO_RISCO, BAIXO_RISCO, RISCO_MODERADO
from services.regional_strategy import RegionalStrategyResult
from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)

plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial"]


def criar_graficos(
    df: pd.DataFrame,
    resumo_transp: pd.DataFrame,
    resumo_saving: dict,
    resumo_matriz: pd.DataFrame,
    analise_peso: pd.DataFrame,
    analise_uf: pd.Series,
    analise_cep_vol: pd.Series,
    analise_cep_saving: pd.Series,
    analise_cep_perda: pd.Series,
    resumo_migracao: pd.DataFrame,
    sla_result: Optional[SLAComplianceResult] = None,
    regional_result: Optional[RegionalStrategyResult] = None,
    transp_foco: Optional[List[str]] = None,
    temp_dir: str = ".",
    df_mercado: Optional[pd.DataFrame] = None,
) -> Dict[str, str]:
    """Gera todos os gráficos do relatório e retorna dicionário de caminhos.

    Args:
        df: DataFrame completo processado.
        resumo_transp: Resumo por transportadora.
        resumo_saving: Dicionário com KPIs financeiros.
        resumo_matriz: Resumo da matriz de decisão.
        analise_peso: Custo médio por faixa de peso × transportadora.
        analise_uf: Custo total por UF (top 8).
        analise_cep_vol: Volume por faixa de CEP (top 10).
        analise_cep_saving: Saving por faixa de CEP (top 5).
        analise_cep_perda: Perda por faixa de CEP (top 5).
        resumo_migracao: Resumo de migração por status.
        sla_result: Resultado da análise de SLA (opcional).
        regional_result: Resultado da estratégia regional (opcional).
        temp_dir: Diretório para arquivos temporários.

    Returns:
        Dicionário {chave: caminho_arquivo_png}.
    """
    imagens: Dict[str, str] = {}

    _grafico_share(df, resumo_transp, imagens, temp_dir)
    _grafico_saving(resumo_saving, imagens, temp_dir)
    _grafico_matriz(resumo_matriz, imagens, temp_dir)
    _grafico_ticket(df, imagens, temp_dir)
    _grafico_heatmap(df, resumo_transp, imagens, temp_dir)
    _grafico_dashboard_migracao(df, imagens, temp_dir)
    _grafico_uf(analise_uf, imagens, temp_dir)
    _grafico_peso(analise_peso, resumo_transp, imagens, temp_dir)
    _grafico_cep_combinado(analise_cep_vol, analise_cep_saving, imagens, temp_dir)
    # Gráfico de pricing usa df_mercado (todas as carriers T1-T5) para ter
    # o benchmark completo. Quando ausente, cai para o df T1.
    _grafico_pricing(df_mercado if df_mercado is not None else df, imagens, temp_dir, transp_foco)

    if sla_result is not None:
        _grafico_sla_semaforo(sla_result, imagens, temp_dir)
        _grafico_sla_compliance(sla_result, imagens, temp_dir)

    if regional_result is not None and not regional_result.malha_recomendada.empty:
        _grafico_malha_scores(regional_result, imagens, temp_dir)

    logger.info("Gráficos gerados: %d arquivos", len(imagens))
    return imagens


# ── Gráficos existentes (preservados do teste18.py) ───────────────────────────

_SHARE_LIMIT = 7  # deve ser igual ao LIMIT da tabela em _pagina_visao_geral


def _grafico_share(
    df: pd.DataFrame,
    resumo_transp: pd.DataFrame,
    imagens: dict,
    temp_dir: str,
) -> None:
    """Gráfico de barras horizontais: share de pedidos por transportadora.

    Usa o mesmo corte (LIMIT=7) da tabela da Seção 4, garantindo que
    o grupo 'OUTRAS' tenha o mesmo total nos dois lugares.
    """
    try:
        df_bar = resumo_transp.copy()

        # Separa "OUTRAS" antes do sort — deve ficar fixo na última posição (barra inferior)
        tem_outras = False
        row_outras_data = None
        if len(df_bar) > _SHARE_LIMIT:
            top = df_bar.iloc[:_SHARE_LIMIT].copy()
            restante = df_bar.iloc[_SHARE_LIMIT:]
            outros_val = restante["Qtd_Pedidos"].sum()
            n_outras = len(restante)
            if outros_val > 0:
                tem_outras = True
                row_outras_data = {"Transp_Nova": f"OUTRAS ({n_outras} transp.)", "Qtd_Pedidos": outros_val}
            df_bar = top

        # Ordena as transportadoras individuais menor→maior (maior fica no topo do barh)
        df_bar = df_bar.sort_values("Qtd_Pedidos", ascending=True).reset_index(drop=True)

        # Reinsere "OUTRAS" no início do DataFrame → aparece na barra inferior do gráfico
        if tem_outras:
            df_bar = pd.concat(
                [pd.DataFrame([row_outras_data]), df_bar], ignore_index=True
            )

        total_ped = resumo_transp["Qtd_Pedidos"].sum()
        pcts = df_bar["Qtd_Pedidos"] / total_ped * 100
        nomes = [str(n)[:26] for n in df_bar["Transp_Nova"]]
        n = len(df_bar)

        # Paleta: última barra (topo) = maior volume → verde; "OUTRAS" (base) = cinza escuro
        palette = [HEX_CINZA] * n
        palette[-1] = HEX_VERDE          # maior transportadora individual no topo
        if tem_outras:
            palette[0] = "#888888"       # "OUTRAS" na base em cinza diferenciado

        fig, ax = plt.subplots(figsize=(10, max(2.5, 0.48 * n)))
        fig.patch.set_facecolor("white")

        bars = ax.barh(
            nomes, pcts, color=palette,
            edgecolor="white", linewidth=0.6, height=0.62,
        )

        # Rótulos dentro/fora das barras
        for bar, pct, qtd in zip(bars, pcts, df_bar["Qtd_Pedidos"]):
            w = bar.get_width()
            label = f"{pct:.1f}%  ({int(qtd):,})".replace(",", ".")
            if w >= 8:
                ax.text(
                    w - 0.5, bar.get_y() + bar.get_height() / 2,
                    label, va="center", ha="right",
                    fontsize=8.5, color="white", fontweight="bold",
                )
            else:
                ax.text(
                    w + 0.5, bar.get_y() + bar.get_height() / 2,
                    label, va="center", ha="left",
                    fontsize=8.5, color="#444444",
                )

        ax.set_xlim(0, max(pcts) * 1.22)
        ax.set_xlabel("% do total de pedidos", fontsize=9, color="#666666")
        ax.set_title("Share de Pedidos — Cenário Simulado", loc="left",
                     fontsize=11, fontweight="bold", color="#1E3A5F", pad=6)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", labelsize=9, colors="#444444")
        ax.tick_params(axis="x", labelsize=8, colors="#888888")
        ax.xaxis.grid(True, linestyle="--", alpha=0.4, color="#cccccc")
        ax.set_axisbelow(True)

        plt.tight_layout(pad=0.6)
        path = get_temp_path("share", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["share"] = path
    except Exception as exc:
        logger.error("Erro no gráfico share: %s", exc)
        plt.close("all")


def _grafico_saving(resumo_saving: dict, imagens: dict, temp_dir: str) -> None:
    """Gráfico horizontal: comparativo custo histórico vs novo + KPI saving."""
    if not resumo_saving:
        return
    try:
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4), gridspec_kw={"width_ratios": [2, 1]})
        vals = [float(resumo_saving["Custo_Antigo_Comp"]), float(resumo_saving["Custo_Novo_Comp"])]
        cats = ["Custo Histórico", "Custo Novo"]

        bars = ax1.barh([1, 0], vals, color=[HEX_CINZA, HEX_VERDE], height=0.5)
        ax1.axis("off")
        ax1.set_title("Comparativo (Base Validada)", loc="left", fontsize=12,
                      fontweight="bold", color="#444444", pad=10)
        max_val = max(vals) if max(vals) > 0 else 1
        ax1.set_xlim(0, max_val * 1.25)

        for i, bar in enumerate(bars):
            w = bar.get_width()
            ax1.text(-max_val * 0.05, 1 - i, cats[i], va="center", ha="right",
                     fontsize=10, fontweight="bold", color="#444444")
            ax1.text(w + max_val * 0.02, bar.get_y() + bar.get_height() / 2,
                     f"R$ {w:,.0f}".replace(",", "."), va="center",
                     fontweight="bold", fontsize=10, color="#333333")

        ax2.axis("off")
        saving_val = float(resumo_saving["Saving_Valor"])
        saving_pct = (saving_val / vals[0] * 100) if vals[0] > 0 else 0
        cor = HEX_VERDE if saving_val > 0 else HEX_VERMELHO
        sinal = "-" if saving_val > 0 else "+"

        ax2.text(0.5, 0.7, "RESULTADO", ha="center", va="center", fontsize=10, color="#666666")
        val_fmt = f"R$ {abs(saving_val):,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
        ax2.text(0.5, 0.5, val_fmt, ha="center", va="center",
                 fontsize=16, fontweight="bold", color=cor)
        bbox_props = dict(boxstyle="round,pad=0.4", fc=cor, ec="none")
        ax2.text(0.5, 0.3, f"{sinal}{abs(saving_pct):.1f}%", ha="center", va="center",
                 fontsize=12, fontweight="bold", color="white", bbox=bbox_props)

        plt.tight_layout()
        path = get_temp_path("saving", temp_dir)
        plt.savefig(path, dpi=CHART_DPI)
        plt.close()
        imagens["saving"] = path
    except Exception as exc:
        logger.error("Erro no gráfico saving: %s", exc)
        plt.close("all")


def _grafico_matriz(resumo_matriz: pd.DataFrame, imagens: dict, temp_dir: str) -> None:
    """Gráfico horizontal: classificação dos pedidos por quadrante — design limpo."""
    try:
        _NOMES_CURTOS = {
            "GANHO TOTAL (Ouro)": "GANHO TOTAL",
            "TRADE-OFF (Economia c/ Prazo Maior)": "TRADE-OFF",
            "INVESTIMENTO (Mais r\xe1pido)": "INVESTIMENTO",
            "PERDA (Mais caro e lento)": "PERDA",
            "Sem Base Comparativa": "SEM BASE",
        }

        rm = resumo_matriz.copy()
        rm["Nome_Curto"] = rm["Tipo"].map(_NOMES_CURTOS).fillna(
            rm["Tipo"].str[:18]
        )
        rm = rm.sort_values("Qtd", ascending=True)
        colors = [COLOR_MAP_CLASSIFICACAO.get(x, HEX_CINZA) for x in rm["Tipo"]]
        total = rm["Qtd"].sum()

        fig, ax = plt.subplots(figsize=(12, 4))
        bars = ax.barh(rm["Nome_Curto"], rm["Qtd"], color=colors,
                       height=0.52, edgecolor="white", linewidth=0.5)

        for bar, (_, row) in zip(bars, rm.iterrows()):
            w = bar.get_width()
            pct = (w / total * 100) if total > 0 else 0
            valor_str = f"R$ {row['Valor_Total']:,.0f}".replace(",", ".")
            label = f"  {int(w)} ped. ({pct:.1f}%)   {valor_str}"
            ax.text(w + total * 0.008, bar.get_y() + bar.get_height() / 2,
                    label, va="center", fontsize=9.5, color="#333333", fontweight="bold")

        ax.set_xlim(0, rm["Qtd"].max() * 1.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_visible(False)
        ax.tick_params(axis="y", length=0)
        ax.tick_params(axis="x", labelsize=8.5)
        ax.xaxis.grid(True, linestyle="--", alpha=0.25, color="#BBBBBB")
        ax.set_axisbelow(True)
        ax.set_xlabel("Quantidade de Pedidos", fontsize=9, color="#555555")
        plt.yticks(fontsize=11, fontweight="bold")
        plt.tight_layout()

        path = get_temp_path("matrix", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["matrix"] = path
    except Exception as exc:
        logger.error("Erro no gráfico matriz: %s", exc)
        plt.close("all")


def _grafico_ticket(df: pd.DataFrame, imagens: dict, temp_dir: str) -> None:
    """Gráfico horizontal: comparativo de ticket médio atual vs simulado."""
    try:
        cm_novo = df["Custo_Novo"].mean()
        df_base = df[df["Custo_Antigo"] > 0]
        cm_antigo = df_base["Custo_Antigo"].mean() if not df_base.empty else cm_novo

        fig, ax = plt.subplots(figsize=(8, 3))
        vals = [cm_antigo, cm_novo]
        cats = ["Ticket Médio Atual (Histórico)", "Ticket Médio Simulado (Novo)"]
        bars = ax.barh(cats[::-1], vals[::-1], color=[HEX_VERDE, HEX_CINZA], height=0.6)
        ax.set_title("Comparativo de Ticket Médio (R$/Pedido)", loc="left",
                     fontsize=12, fontweight="bold", color="#444444")
        ax.axis("off")
        max_t = max(vals) if max(vals) > 0 else 1
        ax.set_xlim(0, max_t * 1.3)

        for bar in bars:
            ax.text(bar.get_width() * 1.02, bar.get_y() + bar.get_height() / 2,
                    f"R$ {bar.get_width():,.2f}".replace(",", "."),
                    va="center", fontweight="bold", fontsize=11, color="#333333")

        plt.tight_layout()
        path = get_temp_path("ticket_comp", temp_dir)
        plt.savefig(path, dpi=CHART_DPI)
        plt.close()
        imagens["ticket_comp"] = path
    except Exception as exc:
        logger.error("Erro no gráfico ticket: %s", exc)
        plt.close("all")


def _grafico_heatmap(
    df: pd.DataFrame,
    resumo_transp: pd.DataFrame,
    imagens: dict,
    temp_dir: str,
) -> None:
    """Heatmap regional de share de volume por UF × transportadora."""
    try:
        df_heat = df.copy()
        df_heat["Transp_Nova"] = df_heat["Transp_Nova"].astype(str)

        heatmap_full = df_heat.pivot_table(
            index="UF", columns="Transp_Nova", values="Custo_Novo",
            aggfunc="count", fill_value=0,
        )
        if "nan" in heatmap_full.columns:
            heatmap_full = heatmap_full.drop(columns=["nan"])

        top_names = resumo_transp.head(PDF_MAX_TRANSPORTADORAS_HEATMAP)["Transp_Nova"].tolist()
        heatmap_data = heatmap_full[[c for c in top_names if c in heatmap_full.columns]].copy()
        heatmap_data.columns = [
            str(c)[:15] + ".." if len(str(c)) > 15 else str(c)
            for c in heatmap_data.columns
        ]

        ordered_ufs: List[str] = []
        for regiao in ORDEM_REGIOES:
            ufs_presentes = [uf for uf in REGIOES_BR[regiao] if uf in heatmap_data.index]
            ordered_ufs.extend(sorted(ufs_presentes))
        ordered_ufs.extend([uf for uf in heatmap_data.index if uf not in ordered_ufs])
        heatmap_data = heatmap_data.reindex(ordered_ufs)

        heatmap_pct = heatmap_data.div(heatmap_data.sum(axis=1), axis=0).fillna(0) * 100

        fig, ax = plt.subplots(figsize=(12, 14))
        plt.subplots_adjust(left=0.16, right=0.91, bottom=0.16, top=0.92)

        im = ax.imshow(heatmap_pct, cmap="Greens", aspect="auto", vmin=0, vmax=100)
        cbar = ax.figure.colorbar(im, ax=ax, fraction=0.03, pad=0.04)
        cbar.ax.set_ylabel("Share de Volume (%)", rotation=-90, va="bottom", fontsize=10)

        ax.set_xticks(np.arange(len(heatmap_pct.columns)))
        ax.set_yticks(np.arange(len(heatmap_pct.index)))
        ax.set_xticklabels(heatmap_pct.columns, rotation=90, ha="center", fontsize=9)
        ax.set_yticklabels(heatmap_pct.index, fontsize=10, fontweight="bold")

        current_y = 0
        for regiao in ORDEM_REGIOES:
            ufs = [uf for uf in REGIOES_BR[regiao] if uf in heatmap_data.index]
            if not ufs:
                continue
            count = len(ufs)
            y_top, y_bottom = current_y - 0.5, current_y + count - 0.5
            y_center = current_y + count / 2 - 0.5
            if current_y + count < len(heatmap_data):
                ax.axhline(y=y_bottom, color="white", linewidth=2)
            ax.plot([-0.7, -0.7], [y_top + 0.1, y_bottom - 0.1],
                    color="#444444", linewidth=1.5, clip_on=False)
            ax.text(-0.85, y_center, regiao.upper(), ha="center", va="center",
                    rotation=90, fontsize=8, fontweight="bold", color="#555555")
            current_y += count

        for i in range(len(heatmap_pct.index)):
            for j in range(len(heatmap_pct.columns)):
                val = heatmap_pct.iloc[i, j]
                if val > 5:
                    text_color = "white" if val > 50 else "black"
                    ax.text(j, i, f"{val:.0f}", ha="center", va="center",
                            color=text_color, fontsize=8)

        ax.set_title("Competitividade Regional (Top 8 Players)", fontsize=14,
                     fontweight="bold", pad=30, color="#333333")
        ax.text(0.5, 1.02, "Share de volume por estado",
                transform=ax.transAxes, ha="center", fontsize=9, color="#666666")

        path = get_temp_path("heatmap", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["heatmap"] = path
    except Exception as exc:
        logger.error("Erro no heatmap: %s", exc)
        plt.close("all")


def _grafico_dashboard_migracao(df: pd.DataFrame, imagens: dict, temp_dir: str) -> None:
    """Dashboard de evidências da migração (4 sub-gráficos)."""
    try:
        from config.constants import REGIOES_BR

        df_migrados = df[df["Status_Migracao"] == "Migrado (Troca)"].copy()
        df_validos = df[df["Tem_Base"]]

        if df_migrados.empty:
            return

        mapa_reg = {uf: reg for reg, ufs in REGIOES_BR.items() for uf in ufs}
        df_migrados["Reg_Visual"] = df_migrados["UF"].map(mapa_reg).fillna("Outros")

        fig, axes = plt.subplots(2, 2, figsize=(12, 6.5))
        plt.subplots_adjust(wspace=0.3, hspace=0.45, top=0.9, bottom=0.1, left=0.08, right=0.95)

        # Peso médio
        ax1 = axes[0, 0]
        peso_mig = df_migrados["Peso"].mean()
        peso_mantido = df_validos[df_validos["Status_Migracao"] != "Migrado (Troca)"]["Peso"].mean()
        bars1 = ax1.bar(["Mantidos", "Migrados"], [peso_mantido, peso_mig],
                        color=[HEX_CINZA, HEX_VERDE], width=0.6)
        ax1.set_title("1. Perfil de Carga (Peso Médio)", fontsize=11, fontweight="bold", color="#444444")
        ax1.set_ylabel("kg", fontsize=9)
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        for p in bars1:
            h = p.get_height()
            ax1.annotate(f"{h:.1f}kg", (p.get_x() + p.get_width() / 2, h),
                         ha="center", va="bottom", fontsize=10, fontweight="bold")

        # Ticket médio
        ax2 = axes[0, 1]
        tick_a = df_migrados["Custo_Antigo"].mean()
        tick_n = df_migrados["Custo_Novo"].mean()
        bars2 = ax2.bar(["Antes", "Depois"], [tick_a, tick_n],
                        color=[HEX_CINZA, HEX_VERDE], width=0.6)
        ax2.set_title("2. Ticket Médio (Trechos Migrados)", fontsize=11, fontweight="bold", color="#444444")
        ax2.set_ylabel("R$", fontsize=9)
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)
        for p in bars2:
            h = p.get_height()
            ax2.annotate(f"R$ {h:.0f}", (p.get_x() + p.get_width() / 2, h),
                         ha="center", va="bottom", fontsize=10, fontweight="bold")

        # Foco geográfico
        ax3 = axes[1, 0]
        s_reg = df_migrados["Reg_Visual"].value_counts().head(4).sort_values(ascending=True)
        ax3.barh(s_reg.index, s_reg.values, color=HEX_AZUL, height=0.6)
        ax3.set_title("3. Onde ocorreu a troca? (Vol)", fontsize=11, fontweight="bold", color="#444444")
        ax3.spines["top"].set_visible(False)
        ax3.spines["right"].set_visible(False)
        for i, v in enumerate(s_reg.values):
            ax3.text(v + s_reg.max() * 0.02, i, f"{v}", va="center", fontsize=9, fontweight="bold")

        # Redução de prazo
        ax4 = axes[1, 1]
        delta_reg = df_migrados.groupby("Reg_Visual")["Delta_Prazo"].mean()
        delta_reg = delta_reg[delta_reg != 0].sort_values(ascending=False).head(4)

        if not delta_reg.empty:
            colors_sla = [HEX_VERDE if x < 0 else HEX_VERMELHO for x in delta_reg.values]
            ax4.barh(delta_reg.index, delta_reg.values, color=colors_sla, height=0.6)
            ax4.set_title("4. Redução de Prazo (Dias)", fontsize=11, fontweight="bold", color="#444444")
            ax4.axvline(0, color="black", linewidth=0.5, linestyle="--")
            ax4.spines["top"].set_visible(False)
            ax4.spines["right"].set_visible(False)
            for i, v in enumerate(delta_reg.values):
                offset = 0.2 if v < 0 else -0.2
                align = "left" if v > 0 else "right"
                ax4.text(v + offset, i, f"{v:.1f}d", va="center", ha=align,
                         fontsize=9, fontweight="bold")
        else:
            ax4.text(0.5, 0.5, "Sem alteração de prazo", ha="center", va="center",
                     transform=ax4.transAxes)

        path = get_temp_path("insights_visual", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["insights_visual"] = path
    except Exception as exc:
        logger.error("Erro no dashboard de migração: %s", exc)
        plt.close("all")


def _grafico_uf(analise_uf: pd.Series, imagens: dict, temp_dir: str) -> None:
    """Gráfico horizontal: concentração de custo por UF."""
    try:
        fig, ax = plt.subplots(figsize=(10, 5))
        analise_uf_sorted = analise_uf.sort_values(ascending=True)
        ax.barh(analise_uf_sorted.index, analise_uf_sorted.values, color=HEX_VERDE)
        ax.set_title("Concentração Regional", loc="left", fontsize=12,
                     fontweight="bold", color="#444444")
        ax.axis("off")
        for i, v in enumerate(analise_uf_sorted.values):
            ax.text(0, i, analise_uf_sorted.index[i], ha="right", va="center",
                    fontsize=10, transform=ax.get_yaxis_transform())
            ax.text(v, i, f" R$ {v:,.0f}".replace(",", "."), va="center", fontsize=9)
        plt.tight_layout()
        path = get_temp_path("uf", temp_dir)
        plt.savefig(path, dpi=CHART_DPI)
        plt.close()
        imagens["uf"] = path
    except Exception as exc:
        logger.error("Erro no gráfico UF: %s", exc)
        plt.close("all")


def _grafico_peso(
    analise_peso: pd.DataFrame,
    resumo_transp: pd.DataFrame,
    imagens: dict,
    temp_dir: str,
) -> None:
    """Gráfico de barras agrupadas: custo médio por faixa de peso (top 5)."""
    if analise_peso.empty:
        return
    try:
        top_5 = resumo_transp.head(PDF_MAX_TRANSPORTADORAS_PESO)["Transp_Nova"].tolist()
        cols = [c for c in top_5 if c in analise_peso.columns]
        ap_filtered = analise_peso[cols].copy()

        # Paleta alinhada ao relatório
        _CORES_PESO = [HEX_VERDE, HEX_AZUL, HEX_AMARELO, HEX_VERMELHO,
                       "#17A589", "#8E44AD", "#E67E22"]

        fig, ax = plt.subplots(figsize=(11, 8))
        cores = _CORES_PESO[:len(cols)]
        ap_filtered.plot(kind="bar", ax=ax, width=0.80, color=cores,
                         edgecolor="white", linewidth=0.5)
        ax.set_title("Custo Médio por Faixa de Peso (Top 5 Players)", loc="left",
                     fontsize=13, fontweight="bold", color="#333333", pad=14)
        max_val = ap_filtered.max().max() if not ap_filtered.empty else 100
        ax.set_ylim(0, max_val * 1.35)
        ax.set_xlabel("")
        ax.set_ylabel("Custo Médio (R$)", fontsize=9, color="#555555")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.grid(True, linestyle="--", alpha=0.25, color="#AAAAAA")
        ax.set_axisbelow(True)
        plt.xticks(rotation=0, fontsize=9.5, fontweight="bold")
        plt.yticks(fontsize=8.5)

        for container in ax.containers:
            labels_v = [f"R${b.get_height():,.0f}" if b.get_height() > 0 else ""
                        for b in container]
            ax.bar_label(container, labels=labels_v, fontsize=7,
                         rotation=90, padding=3, label_type="edge")

        ax.legend(title="Transportadoras", frameon=False, fontsize=8.5,
                  title_fontsize=8.5, loc="upper center",
                  bbox_to_anchor=(0.5, -0.08), ncol=min(len(cols), 5))
        plt.subplots_adjust(bottom=0.18)
        path = get_temp_path("peso", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["peso"] = path
    except Exception as exc:
        logger.error("Erro no gráfico peso: %s", exc)
        plt.close("all")


def _grafico_cep_combinado(
    analise_cep_vol: pd.Series,
    analise_cep_saving: pd.Series,
    imagens: dict,
    temp_dir: str,
) -> None:
    """Gráfico combinado: volume e saving por faixa de CEP em 2 subplots lado a lado."""
    try:
        vol  = analise_cep_vol.sort_values(ascending=True)
        sav  = analise_cep_saving.sort_values(ascending=True)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, max(5, len(vol) * 0.52)))
        plt.subplots_adjust(wspace=0.45)

        # ── Subplot 1: Volume de Pedidos ─────────────────────────────────────
        bars1 = ax1.barh(vol.index.astype(str), vol.values,
                         color=HEX_AZUL, height=0.6, alpha=0.88, zorder=3)
        for bar in bars1:
            w = bar.get_width()
            ax1.text(w * 0.5, bar.get_y() + bar.get_height() / 2,
                     f"{int(w)}", va="center", ha="center",
                     fontsize=8, color="white", fontweight="bold")
        ax1.set_xlabel("Pedidos", fontsize=8.5, color="#555555")
        ax1.spines["top"].set_visible(False)
        ax1.spines["right"].set_visible(False)
        ax1.xaxis.grid(True, linestyle="--", alpha=0.25, color="#BBBBBB")
        ax1.set_axisbelow(True)
        ax1.tick_params(axis="y", labelsize=9)
        ax1.tick_params(axis="x", labelsize=8)
        ax1.set_title("Volume de Pedidos por Faixa CEP",
                      fontsize=10, fontweight="bold", color="#333333", pad=8)

        # ── Subplot 2: Saving (R$) ────────────────────────────────────────────
        bars2 = ax2.barh(sav.index.astype(str), sav.values,
                         color=HEX_VERDE, height=0.6, alpha=0.88, zorder=3)
        for bar in bars2:
            w = bar.get_width()
            if w > 0:
                ax2.text(w * 0.5, bar.get_y() + bar.get_height() / 2,
                         f"R${w:,.0f}".replace(",", "."),
                         va="center", ha="center",
                         fontsize=8, color="white", fontweight="bold")
        ax2.set_xlabel("Saving Total (R$)", fontsize=8.5, color="#555555")
        ax2.xaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"R${v/1000:.0f}k" if v >= 1000 else f"R${v:.0f}")
        )
        ax2.spines["top"].set_visible(False)
        ax2.spines["right"].set_visible(False)
        ax2.xaxis.grid(True, linestyle="--", alpha=0.25, color="#BBBBBB")
        ax2.set_axisbelow(True)
        ax2.tick_params(axis="y", labelsize=9)
        ax2.tick_params(axis="x", labelsize=8)
        ax2.set_title("Saving por Faixa CEP  (Top 5)",
                      fontsize=10, fontweight="bold", color="#333333", pad=8)

        plt.tight_layout()
        path = get_temp_path("cep_vol", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["cep_vol"] = path
    except Exception as exc:
        logger.error("Erro no grafico CEP combinado: %s", exc)
        plt.close("all")


def _grafico_pricing(
    df: pd.DataFrame,
    imagens: dict,
    temp_dir: str,
    transp_foco: Optional[List[str]] = None,
) -> None:
    """Gráfico de competitividade: custo foco vs benchmark por região + linha de Target Price."""
    try:
        mapa_reg = {uf: reg for reg, ufs in REGIOES_BR.items() for uf in ufs}
        df2 = df.copy()
        df2["Regiao"] = df2["UF"].map(mapa_reg).fillna("Outros")
        df2["Grupo_Upper"] = df2["Transp_Nova"].str.strip().str.upper()

        foco_upper = [str(t).strip().upper() for t in (transp_foco or [])]
        df_foco  = df2[df2["Grupo_Upper"].isin(foco_upper)]  if foco_upper else pd.DataFrame()
        df_bench = df2[~df2["Grupo_Upper"].isin(foco_upper)] if foco_upper else df2

        regioes = [r for r in ORDEM_REGIOES if r in df2["Regiao"].values]
        if not regioes:
            return

        custo_foco = [
            df_foco[df_foco["Regiao"] == r]["Custo_Novo"].mean()
            if not df_foco.empty else float("nan")
            for r in regioes
        ]
        custo_bench = [
            df_bench[df_bench["Regiao"] == r]["Custo_Novo"].mean()
            if not df_bench.empty else float("nan")
            for r in regioes
        ]
        target = [b * 0.95 if not pd.isna(b) else float("nan") for b in custo_bench]

        x = np.arange(len(regioes))
        width = 0.35
        fig, ax = plt.subplots(figsize=(12, 5))

        foco_label = transp_foco[0].title() if transp_foco else "Transp. Foco"

        # Título dinâmico com o nome real da transportadora foco
        ax.set_title(
            f"{foco_label}  vs  Benchmark de Mercado  |  Custo Médio por Região",
            loc="left", fontsize=11, fontweight="bold", color="#1E3A5F",
        )

        # Barras
        b1 = ax.bar(x - width / 2, custo_foco,  width,
                    label=foco_label, color=HEX_VERDE,            alpha=0.88, zorder=3)
        b2 = ax.bar(x + width / 2, custo_bench, width,
                    label="Benchmark Mercado", color=HEX_AZUL_ESCURO, alpha=0.72, zorder=3)

        # Linha Target Price
        ax.plot(x, target, "o--", color=HEX_VERMELHO, linewidth=2.0,
                markersize=7, label="Target Price (-5% bench)", zorder=4)

        # Labels dentro das barras (foco) — texto branco para não colidir com a linha target
        for bar in b1:
            h = bar.get_height()
            if pd.notna(h) and h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h * 0.5,
                        f"R${h:.2f}", ha="center", va="center",
                        fontsize=7.5, color="white", fontweight="bold")
        # Labels dentro das barras (benchmark)
        for bar in b2:
            h = bar.get_height()
            if pd.notna(h) and h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h * 0.5,
                        f"R${h:.2f}", ha="center", va="center",
                        fontsize=7.5, color="white", fontweight="bold")

        # Labels do target price — acima de cada marcador, com fundo branco para legibilidade
        y_max = max((v for v in custo_bench if pd.notna(v)), default=1)
        for i, t_val in enumerate(target):
            if pd.notna(t_val):
                ax.annotate(
                    f"R${t_val:.2f}",
                    xy=(x[i], t_val),
                    xytext=(0, 10),
                    textcoords="offset points",
                    ha="center", va="bottom",
                    fontsize=7.5, color=HEX_VERMELHO, fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec=HEX_VERMELHO,
                              alpha=0.85, linewidth=0.6),
                )

        ax.set_xticks(x)
        ax.set_xticklabels(regioes, fontsize=10.5, fontweight="bold")
        ax.set_ylabel("Custo Médio por Pedido (R$)", fontsize=9, color="#555555")
        ax.yaxis.set_major_formatter(
            plt.FuncFormatter(lambda v, _: f"R${v:,.2f}".replace(",", "."))
        )
        # Expande eixo Y para acomodar labels acima das barras e da linha
        ax.set_ylim(0, y_max * 1.28)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.yaxis.grid(True, linestyle="--", alpha=0.3, color="#BBBBBB")
        ax.set_axisbelow(True)
        # Legenda fora do gráfico — abaixo do eixo X
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.12),
            ncol=3,
            fontsize=9,
            framealpha=0.9,
            edgecolor="#CCCCCC",
        )

        plt.tight_layout()
        path = get_temp_path("pricing", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["pricing"] = path
    except Exception as exc:
        logger.error("Erro no grafico pricing: %s", exc)
        plt.close("all")


# ── Novos gráficos (SLA e Malha Regional) ────────────────────────────────────

def _grafico_sla_semaforo(
    sla_result: SLAComplianceResult,
    imagens: dict,
    temp_dir: str,
) -> None:
    """Gráfico de semáforo de risco por transportadora."""
    try:
        risco_df = sla_result.risco_por_transp.head(10)
        if risco_df.empty:
            return

        fig, ax = plt.subplots(figsize=(10, max(4, len(risco_df) * 0.6)))
        color_map_risco = {
            ALTO_RISCO: HEX_VERMELHO,
            RISCO_MODERADO: HEX_AMARELO,
            BAIXO_RISCO: HEX_VERDE,
        }
        cores = [color_map_risco.get(r, HEX_CINZA) for r in risco_df["Classificacao_Risco"]]

        bars = ax.barh(risco_df["Transp_Nova"], risco_df["Indice_Risco"],
                       color=cores, height=0.6)
        ax.set_title("Índice de Risco de Atraso por Transportadora", loc="left",
                     fontsize=12, fontweight="bold", color="#444444")
        ax.set_xlabel("Índice de Risco (0 = baixo, 1 = alto)", fontsize=9)
        ax.set_xlim(0, 1.1)
        ax.axvline(0.35, color=HEX_AMARELO, linewidth=1.5, linestyle="--", alpha=0.7, label="Moderado")
        ax.axvline(0.60, color=HEX_VERMELHO, linewidth=1.5, linestyle="--", alpha=0.7, label="Alto")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.legend(fontsize=8)

        for bar, (_, row) in zip(bars, risco_df.iterrows()):
            ax.text(row["Indice_Risco"] + 0.02, bar.get_y() + bar.get_height() / 2,
                    f"{row['Classificacao_Risco']} | {row['Pct_Compliance']:.0f}% SLA",
                    va="center", fontsize=8, color="#333333")

        plt.tight_layout()
        path = get_temp_path("sla_semaforo", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["sla_semaforo"] = path
    except Exception as exc:
        logger.error("Erro no gráfico SLA semáforo: %s", exc)
        plt.close("all")


def _grafico_sla_compliance(
    sla_result: SLAComplianceResult,
    imagens: dict,
    temp_dir: str,
) -> None:
    """Ranking de compliance SLA — 2 segmentos, ordenado do melhor ao pior."""
    try:
        comp_df = sla_result.compliance_por_transp.copy()
        comp_df = comp_df[comp_df["Total_Pedidos"] >= 5]
        if comp_df.empty:
            return

        # Ascending sort: pior no índice 0 (base do gráfico), melhor no topo
        comp_df = comp_df.sort_values("Pct_Compliance", ascending=True)

        n = len(comp_df)
        fig, ax = plt.subplots(figsize=(12, max(6, n * 0.58)))

        y = np.arange(n)
        pct_dentro = comp_df["Pct_Compliance"].values
        pct_fora   = (comp_df["Pct_Alerta"] + comp_df["Pct_Fora"]).values

        ax.barh(y, pct_dentro, color=HEX_VERDE,    height=0.6, label="Dentro do SLA", zorder=3)
        ax.barh(y, pct_fora,   left=pct_dentro,
                color=HEX_VERMELHO, height=0.6, alpha=0.82, label="Fora do SLA", zorder=3)

        # Label de % compliance na extremidade direita
        for i, pct in enumerate(pct_dentro):
            cor_txt = "#1a5c1a" if pct >= 50 else "#aa0000"
            ax.text(101, i, f"{pct:.0f}%", va="center", ha="left",
                    fontsize=8.5, fontweight="bold", color=cor_txt)

        # Label dentro da barra verde (so se grande o suficiente)
        for i, pct in enumerate(pct_dentro):
            if pct >= 10:
                ax.text(pct / 2, i, f"{pct:.0f}%", va="center", ha="center",
                        fontsize=7.5, color="white", fontweight="bold")

        ax.set_yticks(list(y))
        ax.set_yticklabels(comp_df["Transp_Nova"].tolist(), fontsize=9)
        ax.set_xlim(0, 118)
        ax.set_xlabel("% de Pedidos", fontsize=9, color="#555555")
        ax.axvline(80, color="#888888", linewidth=1.2, linestyle="--", alpha=0.55, label="Meta 80%")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.xaxis.grid(True, linestyle="--", alpha=0.2, color="#BBBBBB")
        ax.set_axisbelow(True)
        ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.07),
                  ncol=3, fontsize=9, framealpha=0.9, edgecolor="#CCCCCC")

        plt.tight_layout()
        path = get_temp_path("sla_compliance", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["sla_compliance"] = path
    except Exception as exc:
        logger.error("Erro no gráfico SLA compliance: %s", exc)
        plt.close("all")


def _grafico_malha_scores(
    regional_result: RegionalStrategyResult,
    imagens: dict,
    temp_dir: str,
) -> None:
    """Gráfico de barras: score das transportadoras por região."""
    try:
        scores_df = regional_result.scores_por_regiao
        if scores_df.empty:
            return

        regioes = scores_df["Regiao"].unique()
        n_regioes = len(regioes)

        fig, axes = plt.subplots(1, n_regioes, figsize=(3 * n_regioes, 8), sharey=False)
        if n_regioes == 1:
            axes = [axes]

        for ax, regiao in zip(axes, regioes):
            df_r = scores_df[scores_df["Regiao"] == regiao].head(5)
            bars = ax.bar(
                range(len(df_r)),
                df_r["Score"] * 100,
                color=[HEX_VERDE if i == 0 else HEX_CINZA for i in range(len(df_r))],
                width=0.6,
            )
            ax.set_title(regiao, fontsize=10, fontweight="bold", color="#444444")
            ax.set_xticks(range(len(df_r)))
            ax.set_xticklabels(
                [str(t)[:10] for t in df_r["Transp_Nova"]],
                rotation=45, ha="right", fontsize=7,
            )
            ax.set_ylim(0, 110)
            ax.set_ylabel("Score (0-100)", fontsize=8)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            for bar in bars:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                        f"{bar.get_height():.0f}", ha="center", va="bottom", fontsize=8)

        fig.suptitle("Score por Transportadora por Região", fontsize=13, fontweight="bold",
                     color="#333333", y=1.02)
        plt.tight_layout()
        path = get_temp_path("malha_scores", temp_dir)
        plt.savefig(path, dpi=CHART_DPI, bbox_inches="tight")
        plt.close()
        imagens["malha_scores"] = path
    except Exception as exc:
        logger.error("Erro no gráfico malha scores: %s", exc)
        plt.close("all")
