"""Montagem do relatório PDF executivo  -  MAX Logistics Intelligence Platform.

Redesign completo:
- Sistema 3 cores: #006400 (verde), #1E3A5F (azul escuro), #4A4A4A (texto).
- Capa com sidebar lateral 40mm verde e Health Score em badge circular.
- Resumo Executivo (pág 2) com 5 cards de KPI.
- Tabelas com cabeçalho em azul escuro (texto branco) e listras zebra.
- Boxes com borda lateral esquerda colorida (estilo moderno).
- Seções numeradas de 1 a 11 sem lacunas.
- Layout controlado por get_y()  -  sem set_y() fixo para evitar páginas órfãs.
"""

import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from fpdf import FPDF

from config.constants import (
    COR_ALERTA_RGB,
    COR_AZUL_CLARO,
    COR_AZUL_ESCURO_RGB,
    COR_PRIMARIA_RGB,
    COR_TEXTO_RGB,
    COR_VERDE_CLARO,
    COR_VERMELHO_RGB,
    COR_ZEBRA_RGB,
    HEX_AMARELO,
    HEX_AZUL,
    HEX_VERDE,
    HEX_VERMELHO,
    ORDEM_REGIOES,
    REGIOES_BR,
)
from services.sla_analyzer import (
    SLAComplianceResult,
    ALTO_RISCO,
    RISCO_MODERADO,
    BAIXO_RISCO,
)
from services.regional_strategy import RegionalStrategyResult
from services.migration_analyzer import MigrationAnalysisResult
from services.competitive_analyzer import CompetitiveAnalysisResult, BidGapResult
from utils.logger import get_logger
from utils.text_utils import limpar_texto, formatar_monetario_br

import pandas as pd

logger: logging.Logger = get_logger(__name__)

# ── Atalhos de cor ────────────────────────────────────────────────────────────
_V = COR_PRIMARIA_RGB          # verde
_A = COR_AZUL_ESCURO_RGB       # azul escuro
_C = COR_TEXTO_RGB             # cinza texto
_BR = (255, 255, 255)          # branco
_LN = (210, 215, 220)          # linha separadora


# ══════════════════════════════════════════════════════════════════════════════
# PDFReport  -  classe base com helpers visuais reutilizáveis
# ══════════════════════════════════════════════════════════════════════════════

class PDFReport(FPDF):
    """Classe base do relatório MAX com helpers visuais padronizados."""

    def header(self) -> None:
        """Cabeçalho discreto a partir da página 2."""
        if self.page_no() > 1:
            self.set_y(6)
            # Tag de bloco — lado esquerdo; cor e texto variam conforme o bloco atual
            header_label = getattr(self, "transp_foco_label", "")
            if header_label:
                label_color = getattr(self, "header_label_color", _V)
                self.set_font("Arial", "B", 7)
                self.set_text_color(*label_color)
                self.cell(80, 6, limpar_texto(header_label), 0, 0, "L")
            else:
                self.cell(80, 6, "", 0, 0, "L")
            # Lado direito — confidencial
            self.set_font("Arial", "I", 7.5)
            self.set_text_color(160, 165, 170)
            self.cell(0, 6, "ESTUDO DE VIABILIDADE LOGÍSTICA | CONFIDENCIAL", 0, 0, "R")
            self.ln(8)
            self.set_draw_color(*_LN)
            self.line(10, 15, 200, 15)

    def footer(self) -> None:
        """Rodapé com número de página e branding (apenas a partir da página 2)."""
        if self.page_no() == 1:
            return
        self.set_y(-13)
        self.set_draw_color(*_LN)
        self.line(10, self.get_y() - 1, 200, self.get_y() - 1)
        self.set_font("Arial", "", 7.5)
        self.set_text_color(150, 155, 160)
        self.cell(95, 8, "Intelipost Analytics  | MAX", 0, 0, "L")
        self.cell(95, 8, f"Página {self.page_no()}", 0, 0, "R")

    # ── Títulos de seção ──────────────────────────────────────────────────────

    def titulo_secao(self, numero: str, texto: str) -> None:
        """Título de seção com underline verde."""
        self.ln(4)
        self.set_font("Arial", "B", 13)
        self.set_text_color(*_A)
        self.cell(0, 9, limpar_texto(f"{numero}. {texto}"), 0, 1, "L")
        # linha verde grossa
        y = self.get_y()
        self.set_draw_color(*_V)
        self.set_line_width(0.8)
        self.line(10, y, 80, y)
        self.set_line_width(0.2)
        self.set_draw_color(*_LN)
        self.line(80, y, 200, y)
        self.ln(6)

    def subtitulo(self, texto: str) -> None:
        """Subtítulo de seção."""
        self.set_font("Arial", "B", 10)
        self.set_text_color(*_A)
        self.cell(0, 7, limpar_texto(texto), 0, 1, "L")
        self.ln(1)

    # ── Boxes ─────────────────────────────────────────────────────────────────

    def box_borda(
        self,
        titulo: str,
        linhas: List[str],
        cor: tuple = None,
        cor_fundo: tuple = None,
        compact: bool = False,
    ) -> None:
        """Box com borda lateral esquerda colorida (estilo moderno).

        Args:
            titulo: Título em negrito no topo.
            linhas: Lista de strings do corpo.
            cor: Cor RGB da borda (default verde).
            cor_fundo: Cor RGB do fundo (default cinza claro).
            compact: Reduz padding interno para caber em espaços menores.
        """
        if cor is None:
            cor = _V
        if cor_fundo is None:
            cor_fundo = (248, 248, 248)

        lh       = 4.5 if compact else 5
        gap_line = 1   if compact else 2
        pad_top  = 3   if compact else 4
        pad_bot  = 5   if compact else 10
        h_titulo = 6   if compact else 8

        h_linhas = sum(max(1, math.ceil(len(l) / 88)) * lh for l in linhas) + len(linhas) * gap_line
        h_total = h_titulo + h_linhas + pad_bot

        y = self.get_y()
        # borda colorida 4px
        self.set_fill_color(*cor)
        self.rect(10, y, 4, h_total, "F")
        # fundo
        self.set_fill_color(*cor_fundo)
        self.rect(14, y, 186, h_total, "F")

        self.set_xy(19, y + pad_top)
        self.set_font("Arial", "B", 9.5)
        self.set_text_color(*cor)
        self.cell(0, 5, limpar_texto(titulo), 0, 1)

        self.set_font("Arial", "", 8.5)
        self.set_text_color(55, 55, 55)
        for linha in linhas:
            self.set_x(19)
            self.multi_cell(177, lh, limpar_texto(linha), 0, "L")
            self.ln(gap_line - 1 if gap_line > 1 else 0)

        self.set_y(y + h_total + 3)

    def box_alerta(self, titulo: str, linhas: List[str]) -> None:
        """Box de alerta com fundo amarelo."""
        self.box_borda(titulo, linhas, cor=(180, 120, 0), cor_fundo=COR_ALERTA_RGB)

    def box_sucesso(self, titulo: str, linhas: List[str], compact: bool = False) -> None:
        """Box de destaque positivo com fundo verde claro."""
        self.box_borda(titulo, linhas, cor=_V, cor_fundo=COR_VERDE_CLARO, compact=compact)

    def box_info(self, titulo: str, linhas: List[str], compact: bool = False) -> None:
        """Box informativo com fundo azul claro."""
        self.box_borda(titulo, linhas, cor=_A, cor_fundo=COR_AZUL_CLARO, compact=compact)

    # ── Tabelas ───────────────────────────────────────────────────────────────

    def tabela_header(
        self,
        col_widths: List[float],
        headers: List[str],
        aligns: Optional[List[str]] = None,
    ) -> None:
        """Cabeçalho de tabela em azul escuro com texto branco."""
        if aligns is None:
            aligns = ["C"] * len(headers)
        self.set_fill_color(*_A)
        self.set_text_color(*_BR)
        self.set_font("Arial", "B", 8.5)
        for w, h, a in zip(col_widths, headers, aligns):
            self.cell(w, 9, limpar_texto(h), 0, 0, a, fill=True)
        self.ln()

    def tabela_linha(
        self,
        col_widths: List[float],
        valores: List[str],
        aligns: List[str],
        zebra: bool = False,
        bold: bool = False,
    ) -> None:
        """Linha de tabela com zebra striping opcional."""
        self.set_fill_color(*(COR_ZEBRA_RGB if zebra else _BR))
        self.set_text_color(*_C)
        self.set_font("Arial", "B" if bold else "", 8.5)
        for w, v, a in zip(col_widths, valores, aligns):
            self.cell(w, 8, limpar_texto(str(v)), 0, 0, a, fill=True)
        self.ln()

    def linha_separadora(self) -> None:
        """Linha horizontal de separação."""
        self.ln(2)
        self.set_draw_color(*_LN)
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    # ── KPI Card ──────────────────────────────────────────────────────────────

    def kpi_card(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        label: str,
        valor: str,
        sub: str = "",
        cor: tuple = None,
    ) -> None:
        """Desenha um card de KPI com label, valor em destaque e subtítulo."""
        if cor is None:
            cor = _A
        # sombra leve
        self.set_fill_color(230, 233, 237)
        self.rect(x + 1, y + 1, w, h, "F")
        # card principal
        self.set_fill_color(*_BR)
        self.rect(x, y, w, h, "F")
        # barra superior colorida
        self.set_fill_color(*cor)
        self.rect(x, y, w, 4, "F")

        self.set_xy(x + 3, y + 7)
        self.set_font("Arial", "B", 7.5)
        self.set_text_color(120, 125, 130)
        self.cell(w - 6, 5, limpar_texto(label.upper()), 0, 1, "C")

        self.set_x(x + 3)
        self.set_font("Arial", "B", 16)
        self.set_text_color(*cor)
        self.cell(w - 6, 10, limpar_texto(valor), 0, 1, "C")

        if sub:
            self.set_x(x + 3)
            self.set_font("Arial", "", 7.5)
            self.set_text_color(120, 125, 130)
            self.cell(w - 6, 5, limpar_texto(sub), 0, 1, "C")


# ══════════════════════════════════════════════════════════════════════════════
# Função pública principal
# ══════════════════════════════════════════════════════════════════════════════

def gerar_relatorio_final(
    df: pd.DataFrame,
    r_transp: pd.DataFrame,
    resumo_saving: dict,
    resumo_matriz: pd.DataFrame,
    imagens: Dict[str, str],
    save_path: str,
    transp_foco: Optional[List[str]] = None,
    nome_cliente: str = "Cliente MAX",
    periodo_referencia: str = "",
    health_score: float = 0.0,
    health_classificacao: str = "N/D",
    sla_result: Optional[SLAComplianceResult] = None,
    regional_result: Optional[RegionalStrategyResult] = None,
    migration_result: Optional[MigrationAnalysisResult] = None,
    kpis: Optional[dict] = None,
    competitive_result: Optional[CompetitiveAnalysisResult] = None,
    gap_bid_result: Optional[BidGapResult] = None,
    df_foco: Optional[pd.DataFrame] = None,
) -> None:
    """Gera o relatório PDF executivo completo.

    Args:
        df: DataFrame completo processado (T1 por pedido em modo cru).
        r_transp: Resumo por transportadora.
        resumo_saving: Dicionário com KPIs financeiros.
        resumo_matriz: Resumo da matriz de decisão.
        imagens: Dicionário com caminhos dos arquivos PNG.
        save_path: Caminho de destino do PDF.
        transp_foco: Transportadoras de foco para análise competitiva.
        nome_cliente: Nome do cliente a exibir na capa.
        periodo_referencia: Período de referência (ex: "Março 2025").
        health_score: Score de saúde da operação (0-100).
        health_classificacao: Classificação textual do health score.
        sla_result: Resultado da análise de SLA (opcional).
        regional_result: Resultado da estratégia regional (opcional).
        migration_result: Resultado da análise de migração (opcional).
        competitive_result: Perfil BID e análise de competitividade (opcional).
        df_foco: Linhas da transportadora foco vindas do df completo (todas as
            carriers). Usado em modo cru quando a foco não aparece como T1.
    """
    Path(save_path).parent.mkdir(parents=True, exist_ok=True)

    pdf = PDFReport()
    pdf.set_auto_page_break(auto=True, margin=18)

    foco_nome = transp_foco[0].upper() if transp_foco else ""

    # ── CAPA ──────────────────────────────────────────────────────────────────
    pdf.transp_foco_label = ""
    _pagina_capa(pdf, nome_cliente, periodo_referencia, health_score, health_classificacao,
                 resumo_saving, sla_result)

    # ── RESUMO EXECUTIVO (pág. 2) — sem label de bloco no topo ───────────────
    _pagina_resumo_executivo(
        pdf, df, r_transp, resumo_saving,
        health_score, health_classificacao,
        sla_result, regional_result, transp_foco,
        kpis=kpis,
        df_foco=df_foco,
        gap_bid_result=gap_bid_result,
    )

    # ── ÍNDICE DO RELATÓRIO (pág. 3) — sem label de bloco no topo ────────────
    _pagina_indice(pdf)

    # ── Painel da Transportadora Foco (pág. 4) — sem label; já tem faixa interna
    if transp_foco:
        _pagina_painel_foco(pdf, df, r_transp, resumo_saving, transp_foco, regional_result,
                            df_foco=df_foco,
                            gap_bid_result=gap_bid_result)

    # ── BLOCO 1: Transportadora Foco (header verde — ativa a partir da seção 1)
    pdf.transp_foco_label = f"EM ANÁLISE: {foco_nome}" if foco_nome else ""
    pdf.header_label_color = _V

    # ── 1. Competitividade & Pricing ──────────────────────────────────────────
    _pagina_competitividade(pdf, df, imagens, transp_foco, competitive_result, gap_bid_result,
                            df_foco_raw=df_foco)

    # ── 2. Malha Regional ─────────────────────────────────────────────────────
    if regional_result is not None and not regional_result.malha_recomendada.empty:
        _pagina_malha_regional(pdf, df, regional_result, imagens, transp_foco,
                               gap_bid_result=gap_bid_result)

    # ── 3. Presença Geográfica da Foco ────────────────────────────────────────
    _pagina_geografia(pdf, df, resumo_saving, imagens, transp_foco,
                      gap_bid_result=gap_bid_result)

    # ── BLOCO 2: Panorama da Operação (header azul escuro) ────────────────────
    pdf.transp_foco_label = "PANORAMA DA OPERAÇÃO"
    pdf.header_label_color = _A

    # ── 4. Visão Geral ────────────────────────────────────────────────────────
    _pagina_visao_geral(pdf, df, r_transp, resumo_saving, imagens, transp_foco)

    # ── 5. Migração ───────────────────────────────────────────────────────────
    _pagina_migracao(pdf, df, r_transp, resumo_saving, imagens, migration_result, transp_foco)

    # ── 6. Financeiro ─────────────────────────────────────────────────────────
    _pagina_financeiro(pdf, resumo_saving, imagens)

    # ── 7. Matriz de Decisão ──────────────────────────────────────────────────
    _pagina_matriz(pdf, df, resumo_matriz, imagens)

    # ── 8. Heatmap Regional ───────────────────────────────────────────────────
    _pagina_heatmap(pdf, imagens)

    # ── 9. Perfil de Carga ────────────────────────────────────────────────────
    _pagina_perfil_carga(pdf, df, r_transp, imagens, transp_foco)

    # ── BLOCO 3: Fechamento (header azul escuro) ──────────────────────────────
    pdf.transp_foco_label = "CONCLUSÃO DO ESTUDO"
    pdf.header_label_color = _A

    # ── 10. Conclusão e Próximos Passos ───────────────────────────────────────
    _pagina_diagnostico(
        pdf, df, r_transp, resumo_saving,
        migration_result, regional_result, sla_result, transp_foco,
        gap_bid_result=gap_bid_result,
    )

    # Seção 11 (Painel SLA) removida: targets não refletem contratos reais do cliente

    try:
        pdf.output(save_path)
        logger.info("PDF gerado: %s", save_path)
    except Exception as exc:
        logger.error("Falha ao salvar PDF: %s", exc)
        raise


# ══════════════════════════════════════════════════════════════════════════════
# Páginas privadas
# ══════════════════════════════════════════════════════════════════════════════

def _pagina_capa(
    pdf: PDFReport,
    nome_cliente: str,
    periodo: str,
    health_score: float,
    health_class: str,
    resumo_saving: dict,
    sla_result: Optional[SLAComplianceResult],
) -> None:
    """Capa editorial: sidebar verde com identidade MAX + área de conteúdo hierárquica."""
    _SB = 58  # largura da sidebar (mm)
    _CX = _SB + 8  # x inicial da área de conteúdo
    _CW = 200 - _CX  # largura útil da área de conteúdo

    # Desativa auto_page_break durante a capa para evitar página em branco
    _apb    = pdf.auto_page_break
    _bmargin = pdf.b_margin
    pdf.set_auto_page_break(False)

    pdf.add_page()

    # ── SIDEBAR — painel verde completo ──────────────────────────────────────
    pdf.set_fill_color(*_V)
    pdf.rect(0, 0, _SB, 297, "F")

    # "Intelipost | MAX" — identidade consolidada no topo
    pdf.set_xy(0, 16)
    pdf.set_font("Arial", "B", 10)
    pdf.set_text_color(*_BR)
    pdf.cell(_SB, 7, "Intelipost | MAX", 0, 0, "C")

    # Tagline abaixo da marca
    pdf.set_xy(0, 25)
    pdf.set_font("Arial", "I", 6)
    pdf.set_text_color(190, 225, 190)
    pdf.cell(_SB, 5, limpar_texto("Automação & Inteligência de Dados"), 0, 0, "C")

    # Linha fina decorativa abaixo da tagline
    pdf.set_draw_color(255, 255, 255)
    pdf.set_line_width(0.3)
    pdf.line(10, 33, _SB - 10, 33)
    pdf.set_line_width(0.2)

    # "MAX" watermark — grande, verde mais claro, centro da sidebar
    pdf.set_xy(0, 118)
    pdf.set_font("Arial", "B", 48)
    pdf.set_text_color(0, 145, 0)   # verde claro sobre verde escuro — efeito watermark
    pdf.cell(_SB, 24, "MAX", 0, 0, "C")

    # Linha tracejada (simulada) antes do rodapé da sidebar
    pdf.set_draw_color(190, 225, 190)
    pdf.set_line_width(0.25)
    _dx = 8
    for xi in range(_dx, _SB - _dx, 5):
        pdf.line(xi, 248, xi + 3, 248)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(*_LN)

    # Data no rodapé da sidebar
    pdf.set_xy(0, 255)
    pdf.set_font("Arial", "", 6.5)
    pdf.set_text_color(190, 225, 190)
    pdf.cell(_SB, 5, datetime.now().strftime("%d/%m/%Y"), 0, 0, "C")

    # "Confidencial — Uso Interno"
    pdf.set_xy(0, 262)
    pdf.set_font("Arial", "I", 6)
    pdf.set_text_color(190, 225, 190)
    pdf.cell(_SB, 5, limpar_texto("Confidencial — Uso Interno"), 0, 0, "C")

    # ── ÁREA DE CONTEÚDO ─────────────────────────────────────────────────────

    # Label pequeno: nome do cliente em verde caps
    pdf.set_xy(_CX, 38)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(*_V)
    pdf.cell(_CW, 5, limpar_texto(nome_cliente.upper()), 0, 1, "L")

    # Linha verde fina como separador visual
    pdf.set_draw_color(*_V)
    pdf.set_line_width(0.5)
    pdf.line(_CX, 45, _CX + 70, 45)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(*_LN)

    # Título principal — 2 linhas em bold 26pt azul escuro
    pdf.set_xy(_CX, 50)
    pdf.set_font("Arial", "B", 26)
    pdf.set_text_color(*_A)
    pdf.cell(_CW, 14, "ESTUDO DE", 0, 1, "L")
    pdf.set_x(_CX)
    pdf.cell(_CW, 14, limpar_texto("VIABILIDADE LOGÍSTICA"), 0, 1, "L")

    # Barra verde accent sob o título
    y_acc = pdf.get_y() + 2
    pdf.set_fill_color(*_V)
    pdf.rect(_CX, y_acc, 72, 4, "F")

    # Subtítulo
    pdf.set_xy(_CX, y_acc + 11)
    pdf.set_font("Arial", "", 10)
    pdf.set_text_color(110, 115, 120)
    pdf.cell(_CW, 7, limpar_texto("Análise Competitiva de Transportadoras"), 0, 1, "L")

    # Período de referência
    if periodo:
        pdf.set_x(_CX)
        pdf.set_font("Arial", "I", 9)
        pdf.set_text_color(140, 145, 150)
        pdf.cell(_CW, 6, limpar_texto(f"Período de Referência: {periodo}"), 0, 1, "L")

    # Linha verde separadora antes da lista de seções
    y_sep = pdf.get_y() + 6
    pdf.set_draw_color(*_V)
    pdf.set_line_width(0.5)
    pdf.line(_CX, y_sep, 200, y_sep)
    pdf.set_line_width(0.2)
    pdf.set_draw_color(*_LN)

    # ── Lista numerada de seções (inspiração no modelo editorial) ─────────────
    _secoes_capa = [
        ("01", "Competitividade & Pricing"),
        ("02", limpar_texto("Malha Logística Recomendada")),
        ("03", limpar_texto("Presença Geográfica — Foco")),
        ("04", "Panorama da Operação"),
        ("05", limpar_texto("Conclusão e Próximos Passos")),
    ]
    y_lista = y_sep + 5
    _item_h = 11
    for idx, (num, titulo) in enumerate(_secoes_capa):
        bg = (246, 249, 253) if idx % 2 == 0 else (255, 255, 255)
        # Fundo zebra
        pdf.set_fill_color(*bg)
        pdf.rect(_CX, y_lista, _CW, _item_h, "F")
        # Acento verde esquerdo
        pdf.set_fill_color(*_V)
        pdf.rect(_CX, y_lista, 3, _item_h, "F")
        # Número
        pdf.set_xy(_CX + 5, y_lista + 2)
        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(*_V)
        pdf.cell(10, 6, num, 0, 0, "L")
        # Título da seção
        pdf.set_font("Arial", "", 8)
        pdf.set_text_color(*_C)
        pdf.cell(_CW - 15, 6, titulo, 0, 0, "L")
        y_lista += _item_h

    # ── Disclaimers compactos ─────────────────────────────────────────────────
    y_d = y_lista + 12

    # Disclaimer 1 — tabelas de frete
    pdf.set_xy(_CX, y_d)
    pdf.set_fill_color(245, 247, 250)
    pdf.rect(_CX, y_d, _CW, 16, "F")
    pdf.set_draw_color(210, 215, 220)
    pdf.set_line_width(0.3)
    pdf.rect(_CX, y_d, _CW, 16, "D")
    pdf.set_line_width(0.2)
    pdf.set_draw_color(*_LN)
    pdf.set_xy(_CX + 3, y_d + 2)
    pdf.set_font("Arial", "B", 6.5)
    pdf.set_text_color(140, 100, 0)
    pdf.cell(0, 3.5, "IMPORTANTE: COMPARAÇÃO ENTRE TABELAS DE FRETE", 0, 1)
    pdf.set_x(_CX + 3)
    pdf.set_font("Arial", "", 6)
    pdf.set_text_color(80, 85, 90)
    pdf.multi_cell(
        _CW - 6, 3.2,
        limpar_texto(
            "Este estudo compara tabelas de frete da simulação com o cenário atual. "
            "Não considera regras de cotação da conta de produção (regras de negócio, "
            "pedidos mínimos, restrições por CEP ou modalidade, acordos comerciais vigentes)."
        ),
        0, "L",
    )

    # Disclaimer 2 — resultados futuros
    y_d2 = y_d + 19
    pdf.set_xy(_CX, y_d2)
    pdf.set_fill_color(255, 245, 230)
    pdf.rect(_CX, y_d2, _CW, 14, "F")
    pdf.set_draw_color(200, 140, 60)
    pdf.set_line_width(0.3)
    pdf.rect(_CX, y_d2, _CW, 14, "D")
    pdf.set_line_width(0.2)
    pdf.set_draw_color(*_LN)
    pdf.set_xy(_CX + 3, y_d2 + 2)
    pdf.set_font("Arial", "B", 6.5)
    pdf.set_text_color(160, 80, 0)
    pdf.cell(0, 3.5, limpar_texto("AVISO: ESTE ESTUDO NÃO GARANTE RESULTADOS FUTUROS"), 0, 1)
    pdf.set_x(_CX + 3)
    pdf.set_font("Arial", "", 6)
    pdf.set_text_color(80, 85, 90)
    pdf.multi_cell(
        _CW - 6, 3.2,
        limpar_texto(
            "A base analisada reflete pedidos já realizados. Pedidos futuros podem não seguir "
            "as mesmas tendências, características, origens e regiões aqui identificadas."
        ),
        0, "L",
    )

    # ── Rodapé da área de conteúdo ────────────────────────────────────────────
    pdf.set_draw_color(*_LN)
    pdf.set_line_width(0.3)
    pdf.line(_CX, 272, 200, 272)
    pdf.set_line_width(0.2)

    pdf.set_xy(_CX, 275)
    pdf.set_font("Arial", "B", 8)
    pdf.set_text_color(*_A)
    pdf.cell(_CW, 5, "Intelipost Analytics  |  MAX", 0, 0, "L")

    # Restaura auto_page_break para o restante do relatório
    pdf.set_auto_page_break(_apb, _bmargin)


def _pagina_resumo_executivo(
    pdf: PDFReport,
    df: pd.DataFrame,
    r_transp: pd.DataFrame,
    resumo_saving: dict,
    health_score: float,
    health_class: str,
    sla_result: Optional[SLAComplianceResult],
    regional_result: Optional[RegionalStrategyResult],
    transp_foco: Optional[List[str]],
    kpis: Optional[dict] = None,
    df_foco: Optional[pd.DataFrame] = None,
    gap_bid_result: Optional[BidGapResult] = None,
) -> None:
    """Resumo Executivo (página 2) com cards de KPI e alertas automáticos."""
    pdf.add_page()

    # Título da página
    pdf.set_xy(10, 18)
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(*_A)
    pdf.cell(0, 8, "RESUMO EXECUTIVO", 0, 1, "L")
    pdf.set_y(26)
    pdf.set_draw_color(*_V)
    pdf.set_line_width(1.0)
    pdf.line(10, 26, 200, 26)
    pdf.set_line_width(0.2)
    pdf.ln(6)

    # ── KPI Cards ─────────────────────────────────────────────────────────────
    saving_val    = float(resumo_saving.get("Saving_Valor", 0))
    custo_base    = float(resumo_saving.get("Custo_Antigo_Comp", 0))
    saving_pct    = (saving_val / custo_base * 100) if custo_base > 0.01 else 0
    is_sem_base   = custo_base < 100  # sem histórico: HS não é significativo
    cobertura_pct = regional_result.cobertura_pct if regional_result else 0.0
    n_pedidos     = len(df)
    n_comp        = int(df["Tem_Base"].sum()) if "Tem_Base" in df.columns else n_pedidos
    n_new_biz     = n_pedidos - n_comp

    # Delta prazo: apenas pedidos com prazo histórico real (exclui new business e zeros)
    if "Prazo_Antigo" in df.columns and "Delta_Prazo" in df.columns:
        df_com_prazo = df[(df["Prazo_Antigo"] > 0) & (df["Prazo_Novo"] > 0)]
        delta_prazo  = df_com_prazo["Delta_Prazo"].mean() if not df_com_prazo.empty else 0.0
        n_prazo      = len(df_com_prazo)
    else:
        delta_prazo = 0.0
        n_prazo     = 0

    cor_saving = _V if saving_val >= 0 else (192, 0, 0)
    cor_hs = (
        _V if health_score >= 75
        else ((190, 120, 0) if health_score >= 50 else (192, 0, 0))
    )

    saving_str  = limpar_texto(f"R$ {abs(saving_val):,.0f}".replace(",", "."))
    pedidos_str = f"{n_pedidos:,}".replace(",", ".")
    if is_sem_base:
        pedidos_sub = limpar_texto("sem custo histórico")
        saving_sub  = limpar_texto("sem base histórica")
    else:
        pedidos_sub = limpar_texto(f"base: {n_comp:,} pedidos".replace(",", "."))
        saving_sub  = limpar_texto(f"{saving_pct:+.1f}% vs histórico")
    delta_str   = limpar_texto(f"{delta_prazo:+.1f}d")   # sinal indica direção; cor reforça

    if delta_prazo <= -0.5:
        delta_sub = limpar_texto(f"mais rápido vs hist.")
        cor_delta = _V
    elif delta_prazo >= 0.5:
        delta_sub = limpar_texto(f"mais lento vs hist.")
        cor_delta = (192, 100, 0)
    else:
        delta_sub = limpar_texto(f"prazo mantido vs hist.")
        cor_delta = _A

    card_w, card_h = 37, 40
    gap = 2
    y_cards = pdf.get_y()
    x_start = 10

    cards = [
        ("Pedidos Analisados", pedidos_str,               pedidos_sub,                _A),
        ("Saving Total",       saving_str,                saving_sub,                 cor_saving),
        ("Cobertura Reg.",     f"{cobertura_pct:.0f}%",   "malha recomendada",        _A),
        ("Delta Lead Time",    delta_str,                  delta_sub,                  cor_delta),
    ]
    if not is_sem_base:
        cards.insert(3, ("Health Score", f"{health_score:.0f}/100", limpar_texto(health_class), cor_hs))
    for i, (label, valor, sub, cor) in enumerate(cards):
        pdf.kpi_card(x_start + i * (card_w + gap), y_cards, card_w, card_h,
                     label, valor, sub, cor)

    pdf.set_y(y_cards + card_h + 6)

    # ── Síntese narrativa ─────────────────────────────────────────────────────
    if saving_pct > 5:
        cenario_str = f"ganho de eficiência estrutural com saving de {saving_pct:.1f}%"
    elif saving_pct < -2:
        cenario_str = f"cenário de investimento (+{abs(saving_pct):.1f}% de custo)"
    else:
        cenario_str = "resultado financeiro neutro"

    delta_narrativa = (
        limpar_texto(f"redução de {abs(delta_prazo):.1f}d no lead time vs histórico ({n_prazo} ped.)")
        if delta_prazo <= -0.5
        else limpar_texto(f"acréscimo de {delta_prazo:.1f}d no lead time vs histórico ({n_prazo} ped.) — monitorar")
        if delta_prazo >= 0.5
        else limpar_texto(f"prazo médio mantido vs histórico ({n_prazo} ped.)")
    )
    _hs_sufixo = (
        ""
        if is_sem_base
        else f" Health Score: {health_score:.0f}/100 ({health_class})."
    )
    if is_sem_base:
        _n_ped_fmt = f"{n_pedidos:,}".replace(",", ".")
        sintese = limpar_texto(
            f"O cenário simulado cobre {_n_ped_fmt} pedidos sem base histórica de custo de envio. "
            f"Cobertura regional de {cobertura_pct:.0f}% da malha recomendada e {delta_narrativa}."
        )
    else:
        sintese = limpar_texto(
            f"O cenário simulado apresenta {cenario_str} ({saving_str}) sobre {n_comp} pedidos comparáveis "
            f"({n_new_biz} sem histórico), cobertura regional de {cobertura_pct:.0f}% da malha recomendada "
            f"e {delta_narrativa}.{_hs_sufixo}"
        )
    pdf.set_font("Arial", "I", 8.5)
    pdf.set_text_color(80, 85, 95)
    pdf.multi_cell(0, 5, sintese, 0, "L")
    pdf.ln(2)

    # Disclaimer regras de cotação
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(140, 100, 0)
    pdf.set_x(10)
    pdf.multi_cell(
        190, 4,
        limpar_texto(
            "Atenção: este estudo é uma comparação entre tabelas de frete. "
            "Não considera regras de cotação da conta de produção (regras de negócio, pedidos mínimos, "
            "restrições por CEP/modalidade ou acordos comerciais vigentes)."
        ),
        0, "L",
    )
    pdf.ln(4)

    # ── Legenda T1-T5 ──────────────────────────────────────────────────────────
    _leg_y = pdf.get_y()
    pdf.set_fill_color(240, 244, 250)
    pdf.rect(10, _leg_y, 190, 10, "F")
    pdf.set_fill_color(*_A)
    pdf.rect(10, _leg_y, 4, 10, "F")
    pdf.set_xy(17, _leg_y + 1.5)
    pdf.set_font("Arial", "B", 7)
    pdf.set_text_color(*_A)
    pdf.cell(22, 3.5, limpar_texto("GLOSSÁRIO BID:"), 0, 0)
    pdf.set_font("Arial", "", 7)
    pdf.set_text_color(*_C)
    _legenda_itens = [
        ("T1", "opção mais barata"),
        ("T2", "2a mais barata"),
        ("T3", "3a"),
        ("T4", "4a"),
        ("T5", "mais cara"),
        ("Vencer o BID", "ser T1"),
    ]
    for _tk, _tv in _legenda_itens:
        pdf.set_font("Arial", "B", 7)
        pdf.set_text_color(*_A)
        pdf.cell(pdf.get_string_width(_tk) + 1, 3.5, _tk, 0, 0)
        pdf.set_font("Arial", "", 7)
        pdf.set_text_color(*_C)
        pdf.cell(pdf.get_string_width(f"= {_tv}  ") + 1, 3.5, limpar_texto(f"= {_tv}  "), 0, 0)
    pdf.set_y(_leg_y + 12)

    # ── Alerta de concentração de transportadora ───────────────────────────────
    if not r_transp.empty:
        qtd_total = r_transp["Qtd_Pedidos"].sum()
        top_share = r_transp.iloc[0]["Qtd_Pedidos"] / qtd_total * 100 if qtd_total > 0 else 0
        top_nome = str(r_transp.iloc[0]["Transp_Nova"])
        if top_share >= 40:
            pdf.box_alerta(
                f"ALERTA DE CONCENTRAÇÃO: {top_nome} representa {top_share:.0f}% do volume",
                [
                    f"Alta dependência de transportadora única aumenta risco operacional e reduz poder de negociação.",
                    f"Recomendação: Homologar ao menos 2 transportadoras alternativas para as principais UFs de {top_nome}.",
                ],
            )

    # ── Card da transportadora foco ───────────────────────────────────────────
    if transp_foco:
        foco_nomes = [str(t).strip().upper() for t in transp_foco if str(t).strip()]
        nome_exibicao = transp_foco[0].title() if transp_foco else "Foco"
        # Usa df_foco (linhas da carrier no df completo) quando disponível —
        # necessário em modo cru onde a foco pode não aparecer nas linhas T1.
        _df_foco_exec = df_foco if (df_foco is not None and not df_foco.empty) \
            else df[df["Transp_Nova"].str.strip().str.upper().isin(foco_nomes)]

        if not _df_foco_exec.empty:
            n_ped       = len(_df_foco_exec)
            # Custo/prazo refletem vitórias T1 (consistente com card da pág 4).
            # Se a foco não venceu nenhuma rota, cai para cotações cruas.
            _df_foco_t1_exec = df[df["Transp_Nova"].str.strip().str.upper().isin(foco_nomes)]
            _usar_t1 = not _df_foco_t1_exec.empty
            _src = _df_foco_t1_exec if _usar_t1 else _df_foco_exec
            custo_foco  = _src["Custo_Novo"].mean() if "Custo_Novo" in _src.columns else 0.0
            prazo_foco  = _src["Prazo_Novo"].mean() if "Prazo_Novo" in _src.columns else 0.0
            saving_foco = _df_foco_t1_exec["Saving_Valor"].sum() if "Saving_Valor" in _df_foco_t1_exec.columns else 0.0
            top_ufs = (
                ", ".join(_df_foco_exec["UF"].value_counts().head(3).index.tolist())
                if "UF" in _df_foco_exec.columns else "N/A"
            )

            # Card visual compacto (mesma estrutura do card na secao 8)
            cx, cy = 10, pdf.get_y()
            cw, ch = 190, 30
            pdf.set_fill_color(*COR_VERDE_CLARO)
            pdf.rect(cx, cy, cw, ch, "F")
            pdf.set_fill_color(*_V)
            pdf.rect(cx, cy, 5, ch, "F")
            pdf.set_draw_color(*_V)
            pdf.set_line_width(0.5)
            pdf.rect(cx, cy, cw, ch, "D")
            pdf.set_line_width(0.2)
            pdf.set_draw_color(*_LN)

            # Título
            pdf.set_xy(cx + 8, cy + 2)
            pdf.set_font("Arial", "B", 9.5)
            pdf.set_text_color(*_V)
            pdf.cell(0, 5, limpar_texto(f"TRANSPORTADORA FOCO  -  {nome_exibicao.upper()}"), 0, 1)

            # 4 KPIs inline — terminologia reflete participação no BID
            _vit = gap_bid_result.pedidos_lider
            _lbl_ped_exec = "Pedidos no BID"
            _val_ped_exec = (
                f"{n_ped}  (0 vitórias T1)"
                if _vit == 0
                else f"{n_ped}  ({_vit} vitórias T1)"
            )
            _lbl_sav_exec = "Saving Capturado"
            if _vit and _vit > 0:
                _val_sav_exec = limpar_texto(
                    f"{formatar_monetario_br(saving_foco)}  (vitórias T1)"
                )
            else:
                _val_sav_exec = limpar_texto("R$ 0,00  (sem vitórias T1)")

            _lbl_custo_exec = "Custo Médio Vit. T1" if _usar_t1 else "Custo Médio/Ped."
            _fkpis = [
                (_lbl_ped_exec,       _val_ped_exec),
                (_lbl_custo_exec,     formatar_monetario_br(custo_foco)),
                ("Prazo Médio",       f"{prazo_foco:.1f} dias"),
                (_lbl_sav_exec,       _val_sav_exec),
            ]
            kw = (cw - 10) / len(_fkpis)
            for ki, (kl, kv) in enumerate(_fkpis):
                kx = cx + 8 + ki * kw
                pdf.set_xy(kx, cy + 10)
                pdf.set_font("Arial", "", 6)
                pdf.set_text_color(100, 105, 110)
                pdf.cell(kw, 3.5, limpar_texto(kl.upper()), 0, 1)
                pdf.set_xy(kx, cy + 13.5)
                pdf.set_font("Arial", "B", 8)
                pdf.set_text_color(*_V)
                pdf.cell(kw, 5, limpar_texto(kv), 0, 0)

            # Regioes
            pdf.set_xy(cx + 8, cy + 23)
            pdf.set_font("Arial", "I", 6.5)
            pdf.set_text_color(80, 90, 80)
            pdf.cell(0, 3.5, limpar_texto(f"Principais UFs: {top_ufs}"), 0, 1)

            pdf.set_y(cy + ch + 5)
            pdf.set_text_color(*_C)

    # ── Health Score: Metodologia ─────────────────────────────────────────────
    if kpis and not is_sem_base:
        saving_p   = kpis.get("saving_pct", 0.0)
        pct_ganho  = kpis.get("pct_ganho_total", 0.0)
        pct_reg    = kpis.get("pct_regioes_saving", 0.0)
        pdf.box_info(
            "HEALTH SCORE: COMO ELE É CALCULADO",
            [
                limpar_texto(f"50% Saving Potencial: saving de {saving_p:.1f}% sobre a base comparável"),
                limpar_texto(f"30% Qualidade do Ganho: {pct_ganho:.0f}% dos pedidos classificados como GANHO TOTAL"),
                limpar_texto(f"20% Amplitude Geográfica: {pct_reg:.0f}% das regiões brasileiras com saving líquido positivo"),
            ],
        )


def _pagina_indice(pdf: PDFReport) -> None:
    """Página 3 — Índice completo do relatório."""
    pdf.add_page()

    pdf.set_xy(10, 18)
    pdf.set_font("Arial", "B", 14)
    pdf.set_text_color(*_A)
    pdf.cell(0, 8, limpar_texto("ÍNDICE DO RELATÓRIO"), 0, 1, "L")
    pdf.set_y(26)
    pdf.set_draw_color(*_V)
    pdf.set_line_width(1.0)
    pdf.line(10, 26, 200, 26)
    pdf.set_line_width(0.2)
    pdf.ln(8)

    secoes = [
        ("1",  "Competitividade & Pricing",      "Foco vs benchmark por região, tabela de Target Price (Gap % = distância ao target, não ao benchmark) e diagnóstico"),
        ("2",  "Malha Logística Recomendada",    "Score por região, transportadora principal e backup recomendado"),
        ("3",  "Presença Geográfica  -  Foco",   "Distribuição por faixa de CEP: saving (foco com vitórias) ou oportunidade de entrada (foco sem vitórias no BID)"),
        ("4",  "Visão Geral da Simulação",       "Share de pedidos e tabela resumo por transportadora"),
        ("5",  "Dinâmica de Migração",           "Pedidos migrados, mantidos e novos - tabela De/Para"),
        ("6",  "Análise Financeira",             "KPIs de saving, custo base e variação de ticket médio"),
        ("7",  "Matriz de Decisão",              "Classificação GANHO / TRADE-OFF / INVESTIMENTO / PERDA"),
        ("8",  "Heatmap de Competitividade",     "Competitividade de custo por UF e transportadora"),
        ("9",  "Perfil de Carga",                "Custo médio por faixa de peso - líder de custo por segmento"),
        ("10", "Conclusão e Próximos Passos",    "Síntese do estudo e sugestão de próximos passos baseada nos dados"),
    ]

    blocos = [
        ("BLOCO 1 — EM ANÁLISE", _V, [0, 1, 2]),
        ("BLOCO 2 — PANORAMA DA OPERAÇÃO", _A, [3, 4, 5, 6, 7, 8]),
        ("BLOCO 3 — CONCLUSÃO", _A, [9]),
    ]

    col_num   = 8
    col_titulo = 70
    col_desc  = 112

    for bloco_titulo, bloco_cor, indices in blocos:
        # Cabeçalho do bloco
        pdf.set_fill_color(*bloco_cor)
        pdf.set_text_color(*_BR)
        pdf.set_font("Arial", "B", 8.5)
        pdf.cell(col_num + col_titulo + col_desc, 7,
                 limpar_texto(bloco_titulo), 0, 1, "L", fill=True)

        # Header de colunas
        pdf.set_fill_color(*(230, 235, 240))
        pdf.set_text_color(*_A)
        pdf.set_font("Arial", "B", 8)
        pdf.cell(col_num,   6, "N.",    0, 0, "C", fill=True)
        pdf.cell(col_titulo, 6, limpar_texto("Seção"), 0, 0, "L", fill=True)
        pdf.cell(col_desc,  6, limpar_texto("Conteúdo"), 0, 1, "L", fill=True)

        _LINE_H = 4.5  # altura de cada linha de texto na coluna descrição
        for j, i in enumerate(indices):
            num, titulo, desc = secoes[i]
            bg_color = COR_ZEBRA_RGB if j % 2 == 0 else (255, 255, 255)

            pdf.set_font("Arial", "", 8.5)
            desc_clean = limpar_texto(desc)
            # Estima quantas linhas o texto vai ocupar em col_desc
            n_lines = max(1, int(pdf.get_string_width(desc_clean) / col_desc) + 1)
            row_h = max(8.0, n_lines * _LINE_H + 3.0)

            y_top = pdf.get_y()

            # Fundo zebra cobrindo toda a linha
            pdf.set_fill_color(*bg_color)
            pdf.rect(10, y_top, col_num + col_titulo + col_desc, row_h, "F")

            # Nº — verticalmente centralizado
            pdf.set_xy(10, y_top + (row_h - 5) / 2)
            pdf.set_text_color(*_C)
            pdf.cell(col_num, 5, num, 0, 0, "C")

            # Seção — verticalmente centralizada
            pdf.set_xy(10 + col_num, y_top + (row_h - 5) / 2)
            pdf.cell(col_titulo, 5, limpar_texto(titulo), 0, 0, "L")

            # Descrição — multi_cell com quebra natural de linha
            pdf.set_xy(10 + col_num + col_titulo, y_top + 2)
            pdf.multi_cell(col_desc, _LINE_H, desc_clean, 0, "L")

            # Avança cursor para a próxima linha
            pdf.set_xy(10, y_top + row_h)

        pdf.ln(5)


def _pagina_painel_foco(
    pdf: PDFReport,
    df: pd.DataFrame,
    r_transp: pd.DataFrame,
    resumo_saving: dict,
    transp_foco: List[str],
    regional_result: Optional[RegionalStrategyResult],
    df_foco: Optional[pd.DataFrame] = None,
    gap_bid_result: Optional[BidGapResult] = None,
) -> None:
    """Painel dedicado à transportadora foco — protagonista do estudo."""
    pdf.add_page()

    foco_upper = {str(t).strip().upper() for t in transp_foco}
    nome_foco  = transp_foco[0].title()

    # Usa df_foco (carrier foco do df completo) quando disponível —
    # necessário em modo cru onde a foco pode não aparecer nas linhas T1.
    _df_foco = (df_foco if (df_foco is not None and not df_foco.empty)
                else df[df["Transp_Nova"].str.strip().str.upper().isin(foco_upper)])
    df_bench = df[~df["Transp_Nova"].str.strip().str.upper().isin(foco_upper)]

    # ── Hero header ───────────────────────────────────────────────────────────
    pdf.set_fill_color(*_V)
    pdf.rect(0, 18, 210, 22, "F")
    pdf.set_xy(10, 21)
    pdf.set_font("Arial", "B", 18)
    pdf.set_text_color(*_BR)
    pdf.cell(0, 8, limpar_texto(nome_foco.upper()), 0, 1, "L")
    pdf.set_x(10)
    pdf.set_font("Arial", "", 9)
    pdf.set_text_color(200, 230, 200)
    pdf.cell(0, 5, "Transportadora em Análise  |  Impacto sobre a Operação", 0, 1, "L")
    pdf.set_y(44)

    # ── Zona 1: 6 KPI cards (2 linhas × 3) ───────────────────────────────────
    n_ped        = len(_df_foco)
    total_ped    = len(df)
    pct_vol      = n_ped / total_ped * 100 if total_ped > 0 else 0.0
    # Em modo BID cru: saving capturado = somente pedidos onde a foco foi T1
    # (linhas da foco no df principal, que já está filtrado para T1 por pedido).
    # Os demais pedidos cotados mas não ganhos pertencem a outra transportadora.
    # Custo/prazo refletem vitórias T1 (rotas ganhas). Sem vitórias, cai para
    # cotações cruas só para não exibir zero — a leitura do card já trata o caso.
    _df_foco_t1 = df[df["Transp_Nova"].str.strip().str.upper().isin(foco_upper)]
    saving_foco = float(_df_foco_t1["Saving_Valor"].sum()) if "Saving_Valor" in _df_foco_t1.columns else 0.0
    custo_foco_cmp = (
        float(_df_foco_t1["Custo_Novo"].mean())
        if not _df_foco_t1.empty
        else float(_df_foco["Custo_Novo"].mean()) if not _df_foco.empty else 0.0
    )
    prazo_foco_cmp = (
        float(_df_foco_t1["Prazo_Novo"].mean())
        if "Prazo_Novo" in _df_foco_t1.columns and not _df_foco_t1.empty
        else float(_df_foco["Prazo_Novo"].mean())
        if "Prazo_Novo" in _df_foco.columns and not _df_foco.empty
        else 0.0
    )
    saving_total = float(resumo_saving.get("Saving_Valor", 0))
    pct_saving   = saving_foco / saving_total * 100 if saving_total != 0 else 0.0
    custo_foco   = custo_foco_cmp
    custo_bench  = float(df_bench["Custo_Novo"].mean()) if not df_bench.empty else 0.0
    gap_custo    = (custo_foco_cmp / custo_bench - 1) * 100 if custo_bench > 0 else 0.0
    prazo_foco   = prazo_foco_cmp
    prazo_bench  = float(df_bench["Prazo_Novo"].mean()) if "Prazo_Novo" in df_bench.columns and not df_bench.empty else 0.0
    delta_prazo  = prazo_foco_cmp - prazo_bench

    mapa_reg = {uf: reg for reg, ufs in REGIOES_BR.items() for uf in ufs}
    regioes_foco = sorted(set(_df_foco["UF"].map(mapa_reg).dropna())) if "UF" in _df_foco.columns else []
    n_regioes    = len(regioes_foco)

    cor_gap   = _V if gap_custo <= 0 else (180, 0, 0)
    cor_prazo = _V if delta_prazo <= 0 else (180, 80, 0)
    cor_sav   = _V if saving_foco >= 0 else (180, 0, 0)

    _vitorias = gap_bid_result.pedidos_lider
    _venceu_t1 = bool(_vitorias and _vitorias > 0)

    _lbl_ped = "Pedidos no BID"
    _sub_ped = (
        f"0 vitórias T1 / {n_ped} cotados"
        if _vitorias == 0
        else f"{_vitorias} vitórias T1 / {n_ped} cotados"
    )
    if _venceu_t1:
        _val_sav  = formatar_monetario_br(saving_foco)
        _sub_sav  = limpar_texto(f"{pct_saving:.1f}% do saving total (vitórias T1)")
        _cor_sav2 = cor_sav
    else:
        _val_sav  = formatar_monetario_br(0.0)
        _sub_sav  = limpar_texto("Sem vitórias T1 no BID")
        _cor_sav2 = _A

    card_w, card_h, gap = 60, 32, 5
    _custo_lbl = "Custo Médio Vitórias T1" if _venceu_t1 else "Custo Médio/Pedido"
    _custo_sub = (
        f"{gap_custo:+.1f}% vs mercado (T1 vs T1)"
        if _venceu_t1
        else f"{gap_custo:+.1f}% vs mercado"
    )
    _linha1 = [
        (_lbl_ped,             f"{n_ped:,}".replace(",", "."),   limpar_texto(_sub_ped),   _A),
        ("Saving Capturado",   _val_sav,                          limpar_texto(_sub_sav),   _cor_sav2),
        (_custo_lbl,           formatar_monetario_br(custo_foco), limpar_texto(_custo_sub), cor_gap),
    ]
    _prazo_sub = (
        limpar_texto("prazo cotado (sem vitórias T1)")
        if _vitorias == 0
        else f"{delta_prazo:+.1f}d vs mercado"
    )
    _pos_sub = (
        "do benchmark de custo (T1 vs T1)"
        if _venceu_t1
        else "do benchmark de custo"
    )
    _linha2 = [
        ("Prazo Médio",         f"{prazo_foco:.1f} dias",                _prazo_sub,                           cor_prazo),
        ("Regiões Cobertas",    str(n_regioes),                          limpar_texto(", ".join(regioes_foco[:3]) + ("..." if n_regioes > 3 else "")), _A),
        ("Posicionamento",      "ABAIXO" if gap_custo < -2 else ("ACIMA" if gap_custo > 2 else "NEUTRO"),
                                limpar_texto(_pos_sub),                   _V if gap_custo < -2 else ((180, 0, 0) if gap_custo > 2 else _A)),
    ]

    y_l1 = pdf.get_y()
    for i, (lbl, val, sub, cor) in enumerate(_linha1):
        pdf.kpi_card(10 + i * (card_w + gap), y_l1, card_w, card_h, lbl, val, sub, cor)

    y_l2 = y_l1 + card_h + 4
    for i, (lbl, val, sub, cor) in enumerate(_linha2):
        pdf.kpi_card(10 + i * (card_w + gap), y_l2, card_w, card_h, lbl, val, sub, cor)

    pdf.set_y(y_l2 + card_h + 6)

    # ── Zona 2: Top rotas (UFs) e malha ──────────────────────────────────────
    pdf.subtitulo(limpar_texto(
        f"Principais Rotas  -  {nome_foco}  (presença de cotação  |  saving = vitórias T1)"
    ))

    if "UF" in _df_foco.columns and not _df_foco.empty:
        agg_uf = (
            _df_foco.groupby("UF")
            .agg(Pedidos=("Custo_Novo", "count"), Custo_Med=("Custo_Novo", "mean"))
            .reset_index()
        )
        # Vitórias T1 e saving por UF (linhas da foco no df principal — T1)
        if "UF" in df.columns:
            df_foco_t1 = df[df["Transp_Nova"].str.strip().str.upper().isin(foco_upper)]
            vit_t1 = df_foco_t1.groupby("UF").size().rename("Vit_T1")
            sav_t1 = df_foco_t1.groupby("UF")["Saving_Valor"].sum().rename("Saving")
            agg_uf = agg_uf.merge(vit_t1, on="UF", how="left").merge(sav_t1, on="UF", how="left")
        else:
            agg_uf["Vit_T1"] = 0
            agg_uf["Saving"] = 0.0
        agg_uf["Vit_T1"] = agg_uf["Vit_T1"].fillna(0).astype(int)
        agg_uf["Saving"] = agg_uf["Saving"].fillna(0.0)

        agg_uf = agg_uf.sort_values("Pedidos", ascending=False)
        top_ufs = agg_uf.head(8)
        outras  = agg_uf.iloc[8:]

        col_w_r = [22, 20, 22, 42, 36, 22, 20]
        pdf.tabela_header(
            col_w_r,
            ["UF", "Pedidos", "Vit. T1", "Região", "Saving (R$)", "Custo Méd.", "% Op."],
            ["C", "C", "C", "L", "R", "R", "C"],
        )
        for i, (_, row) in enumerate(top_ufs.iterrows()):
            regiao_uf = limpar_texto(mapa_reg.get(str(row["UF"]), "Outros"))
            pct_uf    = row["Pedidos"] / total_ped * 100 if total_ped > 0 else 0
            cor_sav_r = _V if row["Saving"] >= 0 else (192, 0, 0)
            pdf.set_fill_color(*(COR_VERDE_CLARO if i % 2 == 0 else _BR))
            pdf.set_text_color(*_A)
            pdf.set_font("Arial", "B", 8.5)
            pdf.cell(col_w_r[0], 7, str(row["UF"]), 0, 0, "C", fill=True)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "", 8.5)
            pdf.cell(col_w_r[1], 7, str(int(row["Pedidos"])), 0, 0, "C", fill=True)
            pdf.cell(col_w_r[2], 7, str(int(row["Vit_T1"])), 0, 0, "C", fill=True)
            pdf.cell(col_w_r[3], 7, regiao_uf, 0, 0, "L", fill=True)
            pdf.set_text_color(*cor_sav_r)
            pdf.cell(col_w_r[4], 7, formatar_monetario_br(row["Saving"]).replace(",00", ""), 0, 0, "R", fill=True)
            pdf.set_text_color(*_C)
            pdf.cell(col_w_r[5], 7, formatar_monetario_br(row["Custo_Med"]).replace(",00", ""), 0, 0, "R", fill=True)
            pdf.cell(col_w_r[6], 7, f"{pct_uf:.1f}%", 0, 1, "C", fill=True)

        # Linha "Outras" — fecha a conta de saving total
        if not outras.empty:
            n_outras_ufs = len(outras)
            ped_outras   = int(outras["Pedidos"].sum())
            vit_outras   = int(outras["Vit_T1"].sum())
            sav_outras   = float(outras["Saving"].sum())
            # Custo médio ponderado pela qtd de cotações
            custo_outras = float((outras["Custo_Med"] * outras["Pedidos"]).sum() / ped_outras) if ped_outras > 0 else 0.0
            pct_outras   = ped_outras / total_ped * 100 if total_ped > 0 else 0
            cor_sav_o    = _V if sav_outras >= 0 else (192, 0, 0)

            i_outras = len(top_ufs)
            pdf.set_fill_color(*(COR_VERDE_CLARO if i_outras % 2 == 0 else _BR))
            pdf.set_text_color(*_A)
            pdf.set_font("Arial", "BI", 8.5)
            pdf.cell(col_w_r[0], 7, "Outras", 0, 0, "C", fill=True)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "I", 8.5)
            pdf.cell(col_w_r[1], 7, str(ped_outras), 0, 0, "C", fill=True)
            pdf.cell(col_w_r[2], 7, str(vit_outras), 0, 0, "C", fill=True)
            pdf.cell(col_w_r[3], 7, limpar_texto(f"{n_outras_ufs} UFs"), 0, 0, "L", fill=True)
            pdf.set_text_color(*cor_sav_o)
            pdf.cell(col_w_r[4], 7, formatar_monetario_br(sav_outras).replace(",00", ""), 0, 0, "R", fill=True)
            pdf.set_text_color(*_C)
            pdf.cell(col_w_r[5], 7, formatar_monetario_br(custo_outras).replace(",00", ""), 0, 0, "R", fill=True)
            pdf.cell(col_w_r[6], 7, f"{pct_outras:.1f}%", 0, 1, "C", fill=True)

        pdf.ln(4)

    # ── Zona 3: Box de impacto e recomendação ─────────────────────────────────
    _qual_t1_nar = " (em vitórias T1)" if _venceu_t1 else ""
    pos_texto = (
        f"O estudo aponta que {nome_foco} apresenta custo médio {abs(gap_custo):.1f}% abaixo "
        f"das demais transportadoras da simulação{_qual_t1_nar} — um dado relevante para a análise de viabilidade."
        if gap_custo < -2 else
        f"O estudo aponta que {nome_foco} apresenta custo médio {abs(gap_custo):.1f}% acima "
        f"das demais transportadoras{_qual_t1_nar} — o cliente pode avaliar se outros fatores justificam esse diferencial."
        if gap_custo > 2 else
        f"O estudo aponta que {nome_foco} apresenta custo médio equivalente ao das demais transportadoras{_qual_t1_nar} — "
        "a decisão pode considerar fatores como cobertura regional e histórico operacional."
    )
    prazo_texto = (
        f"Em prazo, a simulação indica {abs(delta_prazo):.1f}d a menos que a média das demais transportadoras — "
        "um possível benefício para a experiência do consumidor final."
        if delta_prazo < -0.3 else
        f"Em prazo, a simulação indica {abs(delta_prazo):.1f}d a mais que a média das demais transportadoras — "
        "um ponto de atenção que o cliente pode considerar na sua avaliação."
        if delta_prazo > 0.3 else
        "Em prazo, a simulação indica equivalência com a média das demais transportadoras."
    )

    malha_texto = ""
    if regional_result is not None and not regional_result.malha_recomendada.empty:
        malha = regional_result.malha_recomendada
        regs_principal = malha[
            malha["Transp_Principal"].str.upper().str.contains(list(foco_upper)[0] if foco_upper else "", na=False)
        ]["Regiao"].tolist() if foco_upper else []
        if regs_principal:
            malha_texto = limpar_texto(
                f"Malha recomendada: transportadora principal em {', '.join(regs_principal)} — "
                "papel estratégico confirmado na cobertura regional."
            )

    linhas_box = [limpar_texto(pos_texto), limpar_texto(prazo_texto)]
    if malha_texto:
        linhas_box.append(malha_texto)

    pdf.box_borda(
        limpar_texto(f"O QUE OS DADOS INDICAM SOBRE {nome_foco.upper()}"),
        linhas_box,
        cor=_V,
        cor_fundo=COR_VERDE_CLARO,
    )


def _pagina_visao_geral(
    pdf: PDFReport,
    df: pd.DataFrame,
    r_transp: pd.DataFrame,
    resumo_saving: dict,
    imagens: dict,
    transp_foco: Optional[List[str]] = None,
) -> None:
    """Seção 1: Visão Geral — KPI cards + gráfico + tabela + insight."""
    pdf.add_page()
    pdf.titulo_secao("4", "Visão Geral da Simulação")

    # ── ZONA 1: 4 KPI cards ───────────────────────────────────────────────────
    qtd_total   = r_transp["Qtd_Pedidos"].sum() if not r_transp.empty else 0
    n_transp    = len(r_transp)
    custo_total = r_transp["Custo_Total"].sum() if not r_transp.empty else 0.0
    custo_medio = custo_total / qtd_total if qtd_total > 0 else 0.0
    prazo_medio = (
        (r_transp["Prazo_Medio"] * r_transp["Qtd_Pedidos"]).sum() / qtd_total
        if qtd_total > 0 else 0.0
    )
    saving_pct  = float(resumo_saving.get("Saving_Pct", 0))
    cor_saving  = _V if saving_pct >= 0 else (180, 0, 0)

    _cards = [
        ("Total de Pedidos",      f"{int(qtd_total):,}".replace(",", "."),  "no cenário simulado",   _A),
        ("Transportadoras",       str(n_transp),                             "ativas na simulação",   _A),
        ("Prazo Médio",           f"{prazo_medio:.1f} dias",                 "média ponderada",       _A),
        ("Custo Médio/Pedido",    formatar_monetario_br(custo_medio),        f"saving {saving_pct:.1f}%", cor_saving),
    ]

    card_w, card_h, gap = 45, 30, 4
    y_c = pdf.get_y()
    for i, (label, valor, sub, cor) in enumerate(_cards):
        pdf.kpi_card(8 + i * (card_w + gap), y_c, card_w, card_h, label, valor, sub, cor)
    pdf.set_y(y_c + card_h + 3)

    # ── Nota compacta ─────────────────────────────────────────────────────────
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(120, 125, 130)
    pdf.set_x(10)
    pdf.multi_cell(
        190, 4,
        limpar_texto(
            "Escopo: 100% da volumetria enviada foi simulada. O share de pedidos indica como a carga "
            "seria distribuída no novo cenário para maximizar eficiência de custo e prazo."
        ),
        0, "L",
    )
    pdf.ln(3)

    # ── ZONA 2: Gráfico de share ──────────────────────────────────────────────
    if "share" in imagens:
        y_img = pdf.get_y()
        n_barras = min(len(r_transp), 7) + (1 if len(r_transp) > 7 else 0)
        h_img = max(38, min(n_barras * 10, 80))
        pdf.image(imagens["share"], x=10, y=y_img, w=190, h=h_img)
        pdf.set_y(y_img + h_img + 4)
    else:
        pdf.ln(5)

    # ── ZONA 3: Tabela de transportadoras ────────────────────────────────────
    pdf.subtitulo("Resumo por Transportadora")
    col_w  = [62, 22, 38, 22, 22, 24]
    hdrs   = ["Transportadora", "Pedidos", "Custo Total", "Prazo Méd.", "% Vol", "Custo Méd."]
    aligns = ["L", "C", "R", "C", "C", "R"]
    pdf.tabela_header(col_w, hdrs, aligns)

    LIMIT = 7
    foco_upper = {str(t).strip().upper() for t in (transp_foco or [])}
    for i, (_, row) in enumerate(r_transp.head(LIMIT).iterrows()):
        pct_vol = row["Qtd_Pedidos"] / qtd_total * 100 if qtd_total > 0 else 0
        is_foco = str(row["Transp_Nova"]).strip().upper() in foco_upper
        valores = [
            limpar_texto(str(row["Transp_Nova"])[:30]),
            str(row["Qtd_Pedidos"]),
            f"R$ {row['Custo_Total']:,.0f}",
            f"{row['Prazo_Medio']:.1f} d",
            f"{pct_vol:.1f}%",
            formatar_monetario_br(row["Ticket_Medio"]).replace(",00", ""),
        ]
        if is_foco:
            pdf.set_fill_color(*COR_VERDE_CLARO)
            pdf.set_text_color(*_V)
            pdf.set_font("Arial", "B", 8.5)
            for w, v, a in zip(col_w, valores, aligns):
                pdf.cell(w, 8, limpar_texto(str(v)), 0, 0, a, fill=True)
            pdf.ln()
        else:
            pdf.tabela_linha(col_w, valores, aligns, zebra=(i % 2 == 0))

    if len(r_transp) > LIMIT:
        restante = r_transp.iloc[LIMIT:]
        pct_outros = restante["Qtd_Pedidos"].sum() / qtd_total * 100 if qtd_total > 0 else 0
        pdf.tabela_linha(
            col_w,
            [
                limpar_texto(f"OUTRAS ({len(restante)} transp.)"),
                str(restante["Qtd_Pedidos"].sum()),
                f"R$ {restante['Custo_Total'].sum():,.0f}",
                f"{restante['Prazo_Medio'].mean():.1f} d",
                f"{pct_outros:.1f}%",
                formatar_monetario_br(restante["Ticket_Medio"].mean()).replace(",00", ""),
            ],
            aligns,
            zebra=(LIMIT % 2 == 0),
        )

    pdf.ln(3)

    # ── ZONA 4: Insight estratégico ───────────────────────────────────────────
    if not r_transp.empty:
        lider_vol   = limpar_texto(str(r_transp.iloc[0]["Transp_Nova"]))
        lider_vol_pct = r_transp.iloc[0]["Qtd_Pedidos"] / qtd_total * 100 if qtd_total > 0 else 0
        top3_pct    = r_transp.head(3)["Qtd_Pedidos"].sum() / qtd_total * 100 if qtd_total > 0 else 0
        lider_custo = limpar_texto(str(r_transp.nsmallest(1, "Ticket_Medio").iloc[0]["Transp_Nova"]))
        custo_min   = r_transp["Ticket_Medio"].min()

        alerta_conc = "concentração elevada - avaliar risco operacional." if top3_pct > 70 else "distribuição equilibrada."
        linha1 = limpar_texto(
            f"Líder em volume: {lider_vol} ({lider_vol_pct:.0f}% dos pedidos). "
            f"Top 3 transportadoras somam {top3_pct:.0f}% - {alerta_conc}"
        )
        linha2 = limpar_texto(
            f"Menor custo médio: {lider_custo} com {formatar_monetario_br(custo_min)} por pedido - "
            "referência de benchmark para negociações."
        )
        pdf.box_borda("DIAGNÓSTICO DA SIMULAÇÃO", [linha1, linha2], compact=True)


def _pagina_migracao(
    pdf: PDFReport,
    df: pd.DataFrame,
    r_transp: pd.DataFrame,
    resumo_saving: dict,
    imagens: dict,
    migration_result: Optional[MigrationAnalysisResult],
    transp_foco: Optional[List[str]] = None,
) -> None:
    """Secao 2: Dinamica de Troca de Transportadoras — redesign com KPI cards."""
    pdf.add_page()
    pdf.titulo_secao("5", "Dinâmica de Troca de Transportadoras")

    # ── ZONA 1: 4 KPI cards ───────────────────────────────────────────────────
    has_mig = migration_result is not None and migration_result.has_migration
    df_mig = migration_result.df_migrados if has_mig else pd.DataFrame()

    n_migrados = len(df_mig) if not df_mig.empty else 0
    saving_mig = float(df_mig["Saving_Valor"].sum()) if not df_mig.empty and "Saving_Valor" in df_mig.columns else 0.0
    ticket_antes = float(df_mig["Custo_Antigo"].mean()) if not df_mig.empty and "Custo_Antigo" in df_mig.columns else 0.0
    ticket_depois = float(df_mig["Custo_Novo"].mean()) if not df_mig.empty and "Custo_Novo" in df_mig.columns else 0.0

    # Principal destino: transportadora que recebeu mais pedidos migrados
    if not df_mig.empty and "Transp_Nova" in df_mig.columns:
        principal_destino = str(df_mig["Transp_Nova"].value_counts().idxmax())
        n_principal = int(df_mig["Transp_Nova"].value_counts().max())
    else:
        principal_destino = "N/A"
        n_principal = 0

    saving_str_mig = formatar_monetario_br(saving_mig).replace(",00", "")
    ticket_str = f"R${ticket_depois:,.0f}".replace(",", ".")
    ticket_sub = f"era R${ticket_antes:,.0f}".replace(",", ".")
    destino_str = limpar_texto(principal_destino[:16])

    _cards = [
        ("Pedidos Migrados",    str(n_migrados),    "",           _A),
        ("Saving da Migração",  saving_str_mig,     "frete médio migrado", _V),
        ("Frete Médio Migrado", ticket_str,         ticket_sub,   (0, 120, 0) if ticket_depois < ticket_antes else (160, 80, 0)),
        ("Principal Destino",   destino_str,        f"{n_principal} pedidos", _A),
    ]

    card_w, card_h, gap = 45, 30, 4
    y_c = pdf.get_y()
    for i, (label, valor, sub, cor) in enumerate(_cards):
        cx = 8 + i * (card_w + gap)
        pdf.kpi_card(cx, y_c, card_w, card_h, label, valor, sub, cor)

    pdf.set_y(y_c + card_h + 4)

    # ── Nota metodologica compacta ────────────────────────────────────────────
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(120, 125, 130)
    pdf.set_x(10)
    pdf.multi_cell(
        190, 4,
        limpar_texto(
            "Metodologia: diferenciamos TROCA de transportadora (Migração) de REDUÇÃO DE CUSTO "
            "na mesma transportadora (Renegociação). O gráfico abaixo detalha cada fluxo por dimensão."
        ),
        0, "L",
    )
    pdf.ln(3)

    # ── ZONA 2: grafico insights_visual ──────────────────────────────────────
    if "insights_visual" in imagens:
        y_img = pdf.get_y()
        pdf.image(imagens["insights_visual"], x=10, y=y_img, w=190)
        pdf.set_y(y_img + 100)
    else:
        pdf.ln(4)
        pdf.set_font("Arial", "I", 8.5)
        pdf.set_text_color(120, 125, 130)
        pdf.set_x(10)
        pdf.multi_cell(
            190, 5,
            limpar_texto(
                "Análise de fluxo de migração não disponível: ausência de base histórica "
                "comparável para este período."
            ),
            0, "L",
        )
        pdf.ln(4)

    # ── ZONA 3: nova pagina  -  Tabela De/Para + Insights ────────────────────
    if has_mig:
        pdf.add_page()
        pdf.subtitulo("5. Dinâmica de Troca  -  continuação")

    if has_mig and not df_mig.empty and "Transp_Antiga" in df_mig.columns:
        pdf.subtitulo("Fluxo de Migração  -  De / Para")
        depara = (
            df_mig.groupby(["Transp_Antiga", "Transp_Nova"])
            .agg(
                Pedidos=("Custo_Novo", "count"),
                Saving=("Saving_Valor", "sum"),
                Custo_Antigo=("Custo_Antigo", "sum"),
            )
            .reset_index()
            .sort_values("Pedidos", ascending=False)
            .head(8)
        )
        depara["Pct_Saving"] = depara.apply(
            lambda r: (r["Saving"] / r["Custo_Antigo"] * 100) if r["Custo_Antigo"] > 0 else 0.0,
            axis=1,
        )

        col_w_dp = [57, 57, 24, 33, 22]
        pdf.tabela_header(
            col_w_dp,
            ["DE (Transportadora Antiga)", "PARA (Transportadora Nova)", "Pedidos", "Saving (R$)", "% Saving"],
            ["L", "L", "C", "R", "C"],
        )
        foco_upper_mig = {str(t).strip().upper() for t in (transp_foco or [])}
        for i, (_, row) in enumerate(depara.iterrows()):
            is_foco = str(row["Transp_Nova"]).strip().upper() in foco_upper_mig
            cor_saving = _V if row["Saving"] >= 0 else (192, 0, 0)
            if is_foco:
                pdf.set_fill_color(*COR_VERDE_CLARO)
                pdf.set_text_color(*_V)
                pdf.set_font("Arial", "B", 8.5)
            else:
                pdf.set_fill_color(*(COR_ZEBRA_RGB if i % 2 == 0 else _BR))
                pdf.set_text_color(*_C)
                pdf.set_font("Arial", "", 8.5)
            pdf.cell(col_w_dp[0], 8, limpar_texto(str(row["Transp_Antiga"])[:28]), 0, 0, "L", fill=True)
            pdf.cell(col_w_dp[1], 8, limpar_texto(str(row["Transp_Nova"])[:28]), 0, 0, "L", fill=True)
            pdf.cell(col_w_dp[2], 8, str(row["Pedidos"]), 0, 0, "C", fill=True)
            pdf.set_text_color(*(cor_saving if not is_foco else _V))
            pdf.cell(col_w_dp[3], 8, formatar_monetario_br(row["Saving"]).replace(",00", "").replace(",", "."), 0, 0, "R", fill=True)
            pct_txt = f"{row['Pct_Saving']:.1f}%"
            pdf.cell(col_w_dp[4], 8, limpar_texto(pct_txt), 0, 1, "C", fill=True)
        pdf.ln(4)

    # ── ZONA 4: Insights estrategicos em box_borda ────────────────────────────
    if has_mig:
        ins = migration_result.insights
        txt_mix = ins.get("txt_mix", "")
        txt_fin = ins.get("txt_fin", "")
        txt_geo = ins.get("txt_geo", "")
        txt_exp = ins.get("txt_exp", "")

        linhas_insight = [l for l in [txt_mix, txt_fin, txt_geo, txt_exp] if l]

        custo_new_biz = float(resumo_saving.get("Custo_New_Business", 0))
        qtd_new_biz = int(resumo_saving.get("Qtd_New_Business", 0))
        custo_base_comp = float(resumo_saving.get("Custo_Antigo_Comp", 0))
        if custo_base_comp >= 100 and custo_new_biz > 0:
            linhas_insight.append(
                f"EXPANSÃO DE COBERTURA: R$ {custo_new_biz:,.2f} em {qtd_new_biz} pedidos "
                f"sem tabela histórica - ganho geográfico líquido."
            )

        if linhas_insight:
            titulo_ins = limpar_texto(ins.get("titulo", "INSIGHTS ESTRATÉGICOS DA MIGRAÇÃO"))
            pdf.box_borda(titulo_ins, linhas_insight)


def _pagina_financeiro(pdf: PDFReport, resumo_saving: dict, imagens: dict) -> None:
    """Seção 3: Análise Financeira (Saving ou Projeção)."""
    pdf.add_page()
    custo_base = float(resumo_saving.get("Custo_Antigo_Comp", 0))
    custo_new_biz = float(resumo_saving.get("Custo_New_Business", 0))
    qtd_new_biz = int(resumo_saving.get("Qtd_New_Business", 0))
    is_baseline = custo_base < 100

    if is_baseline:
        pdf.titulo_secao("6", "Análise Financeira  -  Projeção Orçamentária")
        pdf.box_alerta(
            "BASE HISTÓRICA INSUFICIENTE:",
            [
                f"Não há dados financeiros suficientes para comparação direta. "
                f"Este estudo apresenta a PROJEÇÃO ORÇAMENTÁRIA do novo cenário.",
                f"Total projetado: R$ {custo_new_biz:,.2f} para cobertura de 100% da volumetria.",
            ],
        )
    else:
        saving = float(resumo_saving.get("Saving_Valor", 0))
        saving_pct = (saving / custo_base * 100) if custo_base > 0 else 0
        pdf.titulo_secao("6", "Análise Financeira  -  Saving Operacional")
        cor_box = "sucesso" if saving >= 0 else "alerta"
        linhas = [
            f"BASE ATUAL: R$ {custo_base:,.2f} (pedidos com custo histórico validado). "
            f"Saving: R$ {saving:,.2f} ({saving_pct:.1f}%).",
            f"EXPANSÃO: R$ {custo_new_biz:,.2f} ({qtd_new_biz} pedidos sem tabela ativa)  -  ganho de cobertura.",
        ]
        if saving >= 0:
            pdf.box_sucesso("RESULTADO FINANCEIRO:", linhas)
        else:
            pdf.box_alerta("RESULTADO FINANCEIRO  -  INVESTIMENTO:", linhas)

    if not is_baseline:
        saving = float(resumo_saving.get("Saving_Valor", 0))
        ticket_ant = float(resumo_saving.get("Ticket_Antigo_Base", 0))
        ticket_nov = float(resumo_saving.get("Ticket_Novo_Base", 0))
        delta_ticket = ticket_nov - ticket_ant
        delta_pct = (delta_ticket / ticket_ant * 100) if ticket_ant > 0 else 0
        saving_pct2 = (saving / custo_base * 100) if custo_base > 0 else 0

        # KPI cards modernos
        pdf.ln(2)
        y_cards = pdf.get_y()
        cor_sav = _V if saving >= 0 else (192, 0, 0)
        cor_tkt = _V if delta_ticket <= 0 else (190, 120, 0)
        card_w, card_h = 59, 38
        gap = 2
        cards_fin = [
            ("Custo Base Histórico", formatar_monetario_br(custo_base), "base validada", _A),
            ("Saving Capturado", formatar_monetario_br(abs(saving)), f"{saving_pct2:+.1f}% redução", cor_sav),
            ("Variação Ticket Médio", f"{delta_pct:+.1f}%", f"R$ {ticket_ant:.0f} -> R$ {ticket_nov:.0f}", cor_tkt),
        ]
        for idx, (lbl, val, sub, cor) in enumerate(cards_fin):
            pdf.kpi_card(10 + idx * (card_w + gap), y_cards, card_w, card_h, lbl, val, sub, cor)
        pdf.set_y(y_cards + card_h + 5)

    if is_baseline:
        pdf.ln(10)

    if not is_baseline:
        saving = float(resumo_saving.get("Saving_Valor", 0))
        saving_pct_fin = (saving / custo_base * 100) if custo_base > 0 else 0
        pdf.ln(2)
        pdf.box_info(
            limpar_texto("POR QUE NEM TODOS OS PEDIDOS ENTRAM NO CÁLCULO DE SAVING?"),
            [
                limpar_texto(
                    f"{qtd_new_biz} pedidos da simulação não possuem custo histórico correspondente."
                ),
                limpar_texto(
                    "Motivo: o custo de envio não foi informado no momento da criação do pedido,"
                ),
                limpar_texto(
                    "impossibilitando a comparação financeira com o cenário simulado."
                ),
                limpar_texto(
                    f"Custo simulado deste grupo: R$ {custo_new_biz:,.2f} - informativo, sem base de comparação."
                ),
                limpar_texto(
                    f"O saving de {saving_pct_fin:.1f}% é calculado apenas sobre os pedidos com histórico validado."
                ),
            ],
        )


def _pagina_matriz(
    pdf: PDFReport,
    df: pd.DataFrame,
    resumo_matriz: pd.DataFrame,
    imagens: dict,
) -> None:
    """Seção 4: Matriz de Decisão — gráfico + cards + tabela analítica."""
    pdf.add_page()
    pdf.titulo_secao("7", "Matriz de Decisão")

    # ── ZONA 1: Gráfico (~105mm) ──────────────────────────────────────────────
    if "matrix" in imagens:
        y_m = pdf.get_y()
        pdf.image(imagens["matrix"], x=5, y=y_m, w=200, h=67)
        pdf.set_y(y_m + 71)

    # ── ZONA 2: Mini-cards por quadrante ─────────────────────────────────────
    _COR_QUAD = {
        "GANHO TOTAL":  (0, 100, 0),
        "TRADE-OFF":    (190, 120, 0),
        "INVESTIMENTO": (30, 58, 95),
        "PERDA":        (192, 0, 0),
    }
    _TIPO_MAP = {
        "GANHO TOTAL":  "GANHO TOTAL (Ouro)",
        "TRADE-OFF":    "TRADE-OFF (Economia c/ Prazo Maior)",
        "INVESTIMENTO": "INVESTIMENTO (Mais r\xe1pido)",
        "PERDA":        "PERDA (Mais caro e lento)",
    }

    total_qtd = resumo_matriz["Qtd"].sum() if not resumo_matriz.empty else 1
    card_w, card_h, gap = 44, 32, 4
    y_cards = pdf.get_y()

    for i, (label, cor) in enumerate(_COR_QUAD.items()):
        tipo_full = _TIPO_MAP[label]
        row = resumo_matriz[resumo_matriz["Tipo"] == tipo_full]
        qtd   = int(row["Qtd"].values[0])   if not row.empty else 0
        valor = float(row["Valor_Total"].values[0]) if not row.empty else 0.0
        pct   = qtd / total_qtd * 100        if total_qtd > 0  else 0.0

        cx, cy = 10 + i * (card_w + gap), y_cards
        # sombra
        pdf.set_fill_color(210, 215, 220)
        pdf.rect(cx + 1.5, cy + 1.5, card_w, card_h, "F")
        # fundo
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(cx, cy, card_w, card_h, "F")
        # barra superior colorida
        pdf.set_fill_color(*cor)
        pdf.rect(cx, cy, card_w, 7, "F")
        # label do quadrante
        pdf.set_xy(cx, cy + 1)
        pdf.set_font("Arial", "B", 6)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(card_w, 5, label, 0, 0, "C")
        # quantidade em destaque
        pdf.set_xy(cx, cy + 10)
        pdf.set_font("Arial", "B", 14)
        pdf.set_text_color(*cor)
        pdf.cell(card_w, 8, f"{qtd}", 0, 1, "C")
        # % e valor
        pdf.set_xy(cx, cy + 20)
        pdf.set_font("Arial", "", 6.5)
        pdf.set_text_color(110, 115, 120)
        valor_k = f"R$ {valor/1000:.0f}k" if valor >= 10000 else formatar_monetario_br(valor)
        pdf.cell(card_w, 5, limpar_texto(f"{pct:.1f}%  |  {valor_k}"), 0, 0, "C")
        # borda
        pdf.set_draw_color(*cor)
        pdf.set_line_width(0.4)
        pdf.rect(cx, cy, card_w, card_h, "D")
        pdf.set_line_width(0.2)
        pdf.set_draw_color(*_LN)

    pdf.set_y(y_cards + card_h + 5)

    # ── ZONA 3: Tabela analítica ──────────────────────────────────────────────
    pdf.subtitulo("Breakdown Analítico por Quadrante")
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(110, 115, 120)
    pdf.cell(0, 4,
        limpar_texto("Saving médio, R$/dia e Delta Prazo calculados apenas sobre pedidos com base histórica validada (prazo antigo e novo informados)."),
        0, 1, "L")
    pdf.ln(1)

    # Ordem de exibição: GANHO TOTAL → TRADE-OFF → INVESTIMENTO → PERDA → SEM BASE
    _ORDEM_TIPOS = [
        "GANHO TOTAL (Ouro)",
        "TRADE-OFF (Economia c/ Prazo Maior)",
        "INVESTIMENTO (Mais r\xe1pido)",
        "PERDA (Mais caro e lento)",
        "Sem Base Comparativa",
    ]
    _NOMES_CURTOS = {
        "GANHO TOTAL (Ouro)":                  "GANHO TOTAL",
        "TRADE-OFF (Economia c/ Prazo Maior)": "TRADE-OFF",
        "INVESTIMENTO (Mais r\xe1pido)":        "INVESTIMENTO",
        "PERDA (Mais caro e lento)":           "PERDA",
        "Sem Base Comparativa":                "SEM BASE",
    }

    col_w = [34, 18, 14, 34, 30, 30, 30]
    pdf.tabela_header(
        col_w,
        [limpar_texto(h) for h in ["Quadrante", "Qtd", "% Vol", "Valor Total", "Saving Médio", "R$/dia", "Delta Prazo"]],
        ["L", "C", "C", "R", "R", "R", "C"],
    )

    resumo_ordenado = pd.Categorical(
        resumo_matriz["Tipo"], categories=_ORDEM_TIPOS, ordered=True
    )
    resumo_matriz = resumo_matriz.assign(_ordem=resumo_ordenado).sort_values("_ordem").drop(columns=["_ordem"])

    perda_valor = 0.0  # acumula para box de oportunidade perdida
    qtd_favoravel = 0  # GANHO TOTAL + TRADE-OFF

    for i, (_, row_rm) in enumerate(resumo_matriz.iterrows()):
        tipo = str(row_rm["Tipo"])
        nome_curto = _NOMES_CURTOS.get(tipo, tipo[:16])
        qtd_v   = int(row_rm["Qtd"])
        valor_v = float(row_rm["Valor_Total"])
        pct_v   = qtd_v / total_qtd * 100 if total_qtd > 0 else 0

        df_tipo = df[df["Classificacao"] == tipo]

        # Saving médio — exclui SEM BASE
        if "Saving_Valor" in df_tipo.columns and not df_tipo.empty and tipo != "Sem Base Comparativa":
            sav_med = df_tipo["Saving_Valor"].mean()
            sav_str = limpar_texto(formatar_monetario_br(sav_med))
            if tipo == "PERDA (Mais caro e lento)":
                perda_valor = float(df_tipo["Saving_Valor"].sum())
        else:
            sav_str = "-"

        # Delta Prazo — filtra apenas pedidos com histórico real de prazo
        if "Delta_Prazo" in df_tipo.columns and not df_tipo.empty and tipo != "Sem Base Comparativa":
            if "Prazo_Antigo" in df_tipo.columns and "Prazo_Novo" in df_tipo.columns:
                df_tipo_prazo = df_tipo[(df_tipo["Prazo_Antigo"] > 0) & (df_tipo["Prazo_Novo"] > 0)]
            else:
                df_tipo_prazo = df_tipo
            if not df_tipo_prazo.empty:
                dp_med = df_tipo_prazo["Delta_Prazo"].mean()
                dp_str = limpar_texto(f"{dp_med:+.1f} dias")
            else:
                dp_str = "-"
        else:
            dp_str = "-"

        # R$/dia — apenas para TRADE-OFF e INVESTIMENTO (onde prazo é a variável de decisão)
        rdia_str = "-"
        if tipo in ("TRADE-OFF (Economia c/ Prazo Maior)", "INVESTIMENTO (Mais r\xe1pido)"):
            if "Prazo_Antigo" in df_tipo.columns and "Prazo_Novo" in df_tipo.columns and "Saving_Valor" in df_tipo.columns:
                df_rdia = df_tipo[
                    (df_tipo["Prazo_Antigo"] > 0) & (df_tipo["Prazo_Novo"] > 0)
                ]
                if not df_rdia.empty:
                    dp_abs = df_rdia["Delta_Prazo"].abs().mean()
                    sav_rdia = df_rdia["Saving_Valor"].mean()
                    if dp_abs > 0:
                        rdia_str = limpar_texto(f"R${sav_rdia / dp_abs:.2f}")

        # Acumula favoráveis
        if tipo in ("GANHO TOTAL (Ouro)", "TRADE-OFF (Economia c/ Prazo Maior)"):
            qtd_favoravel += qtd_v

        pdf.tabela_linha(
            col_w,
            [
                nome_curto,
                str(qtd_v),
                f"{pct_v:.1f}%",
                formatar_monetario_br(valor_v),
                sav_str,
                rdia_str,
                dp_str,
            ],
            ["L", "C", "C", "R", "R", "R", "C"],
            zebra=(i % 2 == 0),
        )

    pdf.ln(2)
    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(110, 115, 120)
    pdf.cell(0, 4, limpar_texto("R$/dia = saving médio por dia de variação de prazo (apenas TRADE-OFF e INVESTIMENTO)."), 0, 1, "L")
    pdf.ln(3)

    # ── Box síntese + Custo de Oportunidade ──────────────────────────────────
    pct_fav = qtd_favoravel / total_qtd * 100 if total_qtd > 0 else 0.0
    linhas_sintese = [
        limpar_texto(f"{qtd_favoravel} pedidos ({pct_fav:.0f}% do volume) estão em situação favorável"
                     f" (GANHO TOTAL + TRADE-OFF) - base sólida para negociação contratual."),
    ]
    if perda_valor < 0:
        oport_str = formatar_monetario_br(abs(perda_valor))
        linhas_sintese.append(
            limpar_texto(f"Custo de oportunidade (PERDA): {oport_str} em saving negativo —"
                         " pedidos mais caros e mais lentos que o cenario atual.")
        )
    pdf.box_info(limpar_texto("SÍNTESE DA MATRIZ DE DECISÃO"), linhas_sintese)


def _pagina_geografia(
    pdf: PDFReport,
    df: pd.DataFrame,
    resumo_saving: dict,
    imagens: dict,
    transp_foco: Optional[List[str]] = None,
    gap_bid_result: Optional[BidGapResult] = None,
) -> None:
    """Secao 3: Presenca Geografica da transportadora foco por faixa de CEP.

    Modo 1 (carrier com vitórias): tabela de Saving por Faixa de CEP.
    Modo 2 (carrier sem vitórias + gap_bid_result disponível): tabela de
    Oportunidade por Faixa de CEP — ordenada pelo menor gap, mostrando
    onde a carrier mais se aproxima de liderar o BID.
    """
    pdf.add_page()

    foco_nome = transp_foco[0] if transp_foco else ""
    foco_label = limpar_texto(foco_nome.upper()) if foco_nome else "FOCO"
    pdf.titulo_secao("3", limpar_texto(f"Presença Geográfica  -  {foco_label}"))

    # Filtra df pela transportadora foco — match exato (isin) para evitar match parcial
    # entre carriers com nomes similares (ex.: "DOMINALOG SP" vs "DOMINALOG SP II")
    foco_upper_set = {str(t).strip().upper() for t in (transp_foco or [])}
    df_foco = df[df["Transp_Nova"].str.strip().str.upper().isin(foco_upper_set)] if foco_upper_set else df

    sem_vitoria = len(df_foco) == 0
    tem_gap_data = (
        gap_bid_result is not None
        and gap_bid_result.df_posicao is not None
        and not gap_bid_result.df_posicao.empty
    )

    # ── MODO 2: sem vitórias no BID — mostra oportunidade geográfica ─────────
    if sem_vitoria and tem_gap_data:
        pdf.set_font("Arial", "I", 8)
        pdf.set_text_color(120, 125, 130)
        pdf.multi_cell(
            0, 4,
            limpar_texto(
                f"Faixas de CEP com maior potencial de competitividade para {foco_nome}. "
                "Ordenadas pelo menor gap de preço — onde a transportadora mais se aproxima "
                "de liderar o BID."
            ),
            0, "L",
        )
        pdf.ln(3)

        if "cep_vol" in imagens:
            y_img = pdf.get_y()
            pdf.image(imagens["cep_vol"], x=8, y=y_img, w=194, h=80)
            pdf.set_y(y_img + 84)

        pdf.subtitulo(limpar_texto(f"Oportunidade por Faixa de CEP  -  {foco_label}"))
        pdf.set_font("Arial", "I", 7.5)
        pdf.set_text_color(120, 125, 130)
        pdf.cell(0, 4,
                 limpar_texto(
                     f"Pedidos ordenados por proximidade de ganhar o BID. "
                     "Menor gap = maior prioridade de negociação."
                 ),
                 0, 1, "L")
        pdf.ln(2)

        # Agrega por faixa de CEP destino
        df_gap = gap_bid_result.df_posicao.copy()
        df_gap["CEP_Faixa"] = df_gap["CEP_Destino"].str[:3] + "xx"
        tabela_op = (
            df_gap.groupby("CEP_Faixa")
            .agg(
                Volume=("Gap_R", "count"),
                Gap_Medio_R=("Gap_R", "mean"),
                Gap_Medio_Pct=("Gap_Pct", "mean"),
                Custo_TJ=("TJ_Custo", "mean"),
                Custo_Lider=("T1_Custo", "mean"),
            )
            .sort_values("Gap_Medio_Pct", ascending=True)
            .head(10)
        )
        tabela_op["Vol_Pct"] = (tabela_op["Volume"] / tabela_op["Volume"].sum() * 100).round(1)
        tabela_op["Gap_Medio_R"]   = tabela_op["Gap_Medio_R"].round(2)
        tabela_op["Gap_Medio_Pct"] = tabela_op["Gap_Medio_Pct"].round(1)

        # Legenda de prioridade
        _leg_op = [
            ("OPORTUNIDADE", (0, 120, 0),     "Gap <= 15%"),
            ("POTENCIAL",    (160, 100, 0),   "Gap 15-30%"),
            ("AVALIAR",      (100, 100, 120), "Gap > 30%"),
        ]
        for i, (lbl, cor_l, dsc) in enumerate(_leg_op):
            pdf.set_font("Arial", "B", 6.5)
            pdf.set_text_color(*cor_l)
            lbl_w = pdf.get_string_width(limpar_texto(lbl)) + 2  # largura exata + 2mm padding
            pdf.cell(lbl_w, 4, limpar_texto(lbl), 0, 0, "L")
            pdf.set_font("Arial", "", 6.5)
            pdf.set_text_color(110, 115, 120)
            dsc_txt = limpar_texto(f"= {dsc}")
            dsc_w = pdf.get_string_width(dsc_txt) + 2
            ln = 1 if i == len(_leg_op) - 1 else 0
            pdf.cell(dsc_w, 4, dsc_txt, 0, ln, "L")
            if ln == 0:
                pdf.cell(6, 4, "", 0, 0)  # espaçador entre itens na mesma linha
        pdf.set_text_color(*_C)
        pdf.ln(2)

        col_w_op = [32, 20, 22, 38, 30, 38]
        hdrs_op  = ["Faixa CEP", "Pedidos", "% Volume", "Gap Medio (R$)", "Gap (%)", "Prioridade"]
        alns_op  = ["L", "C", "C", "R", "C", "C"]
        pdf.tabela_header(col_w_op, hdrs_op, alns_op)

        for idx, (cep, row) in enumerate(tabela_op.iterrows()):
            gap_pct = row["Gap_Medio_Pct"]
            if gap_pct <= 15.0:
                prior_op, cor_op = "OPORTUNIDADE", (0, 120, 0)
            elif gap_pct <= 30.0:
                prior_op, cor_op = "POTENCIAL",    (160, 100, 0)
            else:
                prior_op, cor_op = "AVALIAR",      (100, 100, 120)

            zebra = (246, 249, 253) if idx % 2 == 0 else (255, 255, 255)
            pdf.set_fill_color(*zebra)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "B" if idx < 3 else "", 8.5)
            pdf.cell(col_w_op[0], 6, limpar_texto(f"CEP {cep}"), 0, 0, "L", True)
            pdf.set_font("Arial", "", 8.5)
            pdf.cell(col_w_op[1], 6, str(int(row["Volume"])), 0, 0, "C", True)
            pdf.cell(col_w_op[2], 6, f"{row['Vol_Pct']:.1f}%", 0, 0, "C", True)
            gap_r_str = limpar_texto(f"R$ {row['Gap_Medio_R']:,.2f}".replace(",", "."))
            pdf.cell(col_w_op[3], 6, gap_r_str, 0, 0, "R", True)
            pdf.cell(col_w_op[4], 6, f"{gap_pct:.1f}%", 0, 0, "C", True)
            xp, yp = pdf.get_x(), pdf.get_y()
            pdf.set_fill_color(*zebra)
            pdf.cell(col_w_op[5], 6, "", 0, 0, "C", True)
            pdf.set_xy(xp, yp)
            pdf.set_font("Arial", "B", 7.5)
            pdf.set_text_color(*cor_op)
            pdf.cell(col_w_op[5], 6, limpar_texto(prior_op), 0, 1, "C", False)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "", 8.5)

        # Insight box Modo 2
        pdf.ln(3)
        top3_op = tabela_op.head(3)
        top3_op_ceps = ", ".join(f"CEP {c}" for c in top3_op.index)
        top3_op_gap_r_min = top3_op["Gap_Medio_R"].min()
        top3_op_gap_r_max = top3_op["Gap_Medio_R"].max()
        top3_op_gap_pct   = top3_op["Gap_Medio_Pct"].mean()

        insight_op = limpar_texto(
            f"Top 3 faixas ({top3_op_ceps}): gap medio de {top3_op_gap_pct:.1f}% — "
            f"onde {foco_nome} mais se aproxima de liderar o BID. "
            f"Para competir nessas faixas, precisa reduzir entre "
            f"R$ {top3_op_gap_r_min:.2f} e R$ {top3_op_gap_r_max:.2f} por pedido."
        )
        pdf.box_borda(
            limpar_texto(f"O QUE OS DADOS INDICAM  -  {foco_label} POR CEP"),
            [insight_op],
            cor=_V,
            cor_fundo=COR_VERDE_CLARO,
        )
        return

    # ── MODO 1: carrier com vitórias ─────────────────────────────────────────
    saving_total_raw = float(df_foco["Saving_Valor"].sum()) if "Saving_Valor" in df_foco.columns and len(df_foco) > 0 else 0.0
    # Detecta modo BID cru sem histórico: vitórias T1 mas saving = 0 (sem Tem_Base)
    _modo_sem_historico = (saving_total_raw == 0.0) and (gap_bid_result is not None)
    saving_total = saving_total_raw if saving_total_raw != 0.0 else 1.0

    tem_cep = "CEP_Faixa" in df_foco.columns
    tem_sav = "Saving_Valor" in df_foco.columns

    # Agregação COMPLETA por faixa de CEP (todas as faixas com vitórias da foco).
    # Antes era separado em vol_serie e sav_serie ambos limitados a head(10) — o
    # JOIN deixava saving = NaN para faixas top-volume que não estavam no top-saving,
    # mascarando o saving real e classificando tudo como MONITORAR.
    if tem_cep:
        if tem_sav:
            agg_cep = df_foco.groupby("CEP_Faixa").agg(
                Volume=("Custo_Novo", "count"),
                Saving=("Saving_Valor", "sum"),
            )
        else:
            agg_cep = df_foco.groupby("CEP_Faixa").agg(Volume=("Custo_Novo", "count"))
            agg_cep["Saving"] = 0.0
        agg_cep["Saving"] = agg_cep["Saving"].fillna(0.0)
    else:
        agg_cep = pd.DataFrame(columns=["Volume", "Saving"])

    perda_serie = (
        df_foco[df_foco["Saving_Valor"] < 0].groupby("CEP_Faixa")["Saving_Valor"].sum()
        .sort_values(ascending=True).head(5)
        if tem_cep and tem_sav else pd.Series(dtype=float)
    )

    # Nota explicativa adaptada ao modo
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(120, 125, 130)
    if _modo_sem_historico:
        pdf.multi_cell(
            0, 4,
            limpar_texto(
                f"Distribuição geográfica das vitórias T1 de {foco_nome} na simulação BID. "
                "Sem contrato histórico comparável — saving não calculável. "
                "Volume por faixa de CEP indica presença e concentração de mercado."
            ),
            0, "L",
        )
    else:
        pdf.multi_cell(
            0, 4,
            limpar_texto(
                f"Distribuição geográfica dos pedidos atribuídos a {foco_nome} na simulação. "
                "Mostra onde a transportadora tem maior concentração de volume e saving potencial por faixa de CEP."
            ),
            0, "L",
        )
    pdf.ln(3)

    # ── ZONA 1: Grafico combinado (reutiliza imagem geral se não houver foco-específica) ─────
    if "cep_vol" in imagens:
        y_img = pdf.get_y()
        pdf.image(imagens["cep_vol"], x=8, y=y_img, w=194, h=80)
        pdf.set_y(y_img + 84)

    # ── ZONA 2: Tabela filtrada pela foco ────────────────────────────────────
    _subtit_geo = (
        limpar_texto(f"Volume por Faixa de CEP  -  {foco_label}  (vitórias T1 no BID)")
        if _modo_sem_historico
        else limpar_texto(f"Saving por Faixa de CEP  -  {foco_label}")
    )
    pdf.subtitulo(_subtit_geo)
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(120, 125, 130)
    _nota_geo = (
        limpar_texto(f"Pedidos T1 de {foco_nome} por faixa de CEP. Prioridade indica concentração de volume (sem histórico para saving).")
        if _modo_sem_historico
        else limpar_texto(f"Pedidos da {foco_nome} ordenados por saving. Prioridade indica retorno potencial por faixa.")
    )
    pdf.cell(0, 4, _nota_geo, 0, 1, "L")
    pdf.ln(2)

    # Ordena por saving (intenção do título). Sem histórico, cai para volume.
    if not agg_cep.empty and agg_cep["Saving"].sum() != 0:
        agg_cep = agg_cep.sort_values("Saving", ascending=False)
    else:
        agg_cep = agg_cep.sort_values("Volume", ascending=False)

    total_vol_foco = int(agg_cep["Volume"].sum()) if not agg_cep.empty else 0
    tabela = agg_cep.head(10).copy()
    outras = agg_cep.iloc[10:].copy()
    tabela["Saving_Pct"] = (tabela["Saving"] / saving_total * 100).round(1)
    tabela["Vol_Pct"]    = (
        (tabela["Volume"] / total_vol_foco * 100).round(1)
        if total_vol_foco > 0 else 0.0
    )

    # Legenda inline em 2 linhas de 2 itens — acima do header, sem set_xy flutuante
    _leg = [
        ("ALTA",      (0, 120, 0),     "Top 3 por saving"),
        ("MÉDIA",     (160, 100, 0),   "Posições 4-6"),
        ("MONITORAR", (100, 100, 120), "Saving positivo menor"),
        ("ATENÇÃO",   (180, 0, 0),     "Custo simulado > atual"),
    ]
    for i, (lbl, cor_l, dsc) in enumerate(_leg):
        pdf.set_font("Arial", "B", 6.5)
        pdf.set_text_color(*cor_l)
        pdf.cell(20, 4, limpar_texto(lbl), 0, 0, "L")
        pdf.set_font("Arial", "", 6.5)
        pdf.set_text_color(110, 115, 120)
        pdf.cell(55, 4, limpar_texto(f"= {dsc}"), 0, 1 if i % 2 == 1 else 0, "L")
    pdf.set_text_color(*_C)
    pdf.ln(2)

    col_w = [38, 24, 24, 38, 24, 32]
    hdrs  = ["Faixa CEP", "Pedidos", "% Volume", "Saving (R$)", "% Saving", "Prioridade"]
    alns  = ["L", "C", "C", "R", "C", "C"]
    pdf.tabela_header(col_w, hdrs, alns)

    for idx, (cep, row) in enumerate(tabela.iterrows()):
        rank = idx + 1
        if _modo_sem_historico:
            # Sem histórico: prioridade por volume (rank), nunca "ATENÇÃO" por saving zero
            if rank <= 3:
                prior, cor_p = "ALTO VOL",  (0, 120, 0)
            elif rank <= 6:
                prior, cor_p = "MED. VOL",  (160, 100, 0)
            else:
                prior, cor_p = "MENOR VOL", (100, 100, 120)
        elif rank <= 3 and row["Saving"] > 0:
            prior, cor_p = "ALTA",      (0, 120, 0)
        elif rank <= 6 and row["Saving"] > 0:
            prior, cor_p = "MÉDIA",     (160, 100, 0)
        elif row["Saving"] < 0:
            prior, cor_p = "ATENÇÃO",   (180, 0, 0)
        else:
            prior, cor_p = "MONITORAR", (100, 100, 120)

        zebra = (246, 249, 253) if idx % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*zebra)
        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "B" if rank <= 3 else "", 8.5)
        pdf.cell(col_w[0], 6, limpar_texto(f"CEP {cep}"), 0, 0, "L", True)
        pdf.set_font("Arial", "", 8.5)
        pdf.cell(col_w[1], 6, str(int(row["Volume"])), 0, 0, "C", True)
        pdf.cell(col_w[2], 6, f"{row['Vol_Pct']:.1f}%", 0, 0, "C", True)
        # Melhoria 2: valor negativo em vermelho
        sav_str = limpar_texto(f"R$ {row['Saving']:,.0f}".replace(",", ".")) if row["Saving"] != 0 else "-"
        pdf.set_text_color((180, 0, 0) if row["Saving"] < 0 else _C)
        pdf.cell(col_w[3], 6, sav_str, 0, 0, "R", True)
        pdf.set_text_color(_C if row["Saving"] >= 0 else (180, 0, 0))
        pdf.cell(col_w[4], 6, f"{row['Saving_Pct']:.1f}%", 0, 0, "C", True)
        pdf.set_text_color(*_C)
        # Célula prioridade colorida
        xp, yp = pdf.get_x(), pdf.get_y()
        pdf.set_fill_color(*zebra)
        pdf.cell(col_w[5], 6, "", 0, 0, "C", True)
        pdf.set_xy(xp, yp)
        pdf.set_font("Arial", "B", 7.5)
        pdf.set_text_color(*cor_p)
        pdf.cell(col_w[5], 6, limpar_texto(prior), 0, 1, "C", False)
        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "", 8.5)

    # Linha "Outras" — fecha a conta de saving + volume das faixas fora do top 10
    if not outras.empty:
        n_outras   = len(outras)
        vol_outras = int(outras["Volume"].sum())
        sav_outras = float(outras["Saving"].sum())
        sav_pct_o  = (sav_outras / saving_total * 100) if saving_total != 0 else 0.0
        vol_pct_o  = (vol_outras / total_vol_foco * 100) if total_vol_foco > 0 else 0.0

        i_out = len(tabela)
        zebra = (246, 249, 253) if i_out % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*zebra)
        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "BI", 8.5)
        pdf.cell(col_w[0], 6, limpar_texto(f"Outras ({n_outras} faixas)"), 0, 0, "L", True)
        pdf.set_font("Arial", "I", 8.5)
        pdf.cell(col_w[1], 6, str(vol_outras), 0, 0, "C", True)
        pdf.cell(col_w[2], 6, f"{vol_pct_o:.1f}%", 0, 0, "C", True)
        sav_o_str = limpar_texto(f"R$ {sav_outras:,.0f}".replace(",", ".")) if sav_outras != 0 else "-"
        pdf.set_text_color((180, 0, 0) if sav_outras < 0 else _C)
        pdf.cell(col_w[3], 6, sav_o_str, 0, 0, "R", True)
        pdf.set_text_color(*_C)
        pdf.cell(col_w[4], 6, f"{sav_pct_o:.1f}%", 0, 0, "C", True)
        pdf.cell(col_w[5], 6, "-", 0, 1, "C", True)
        pdf.set_font("Arial", "", 8.5)

    # ── ZONA 3: O que os dados indicam ───────────────────────────────────────
    pdf.ln(3)
    top3 = tabela[tabela["Saving"] > 0].head(3)

    if _modo_sem_historico or top3.empty:
        # Sem histórico ou sem saving positivo: insight baseado em volume e gap (se disponível)
        top3_vol = tabela.head(3)
        top3_ceps_vol = ", ".join(f"CEP {c}" for c in top3_vol.index)
        top3_vol_pct_val = top3_vol["Vol_Pct"].sum()
        n_vitorias = len(df_foco)
        if tem_gap_data and gap_bid_result is not None:
            gap_medio = gap_bid_result.gap_medio_r
            insight = limpar_texto(
                f"Top 3 faixas por volume ({top3_ceps_vol}): {top3_vol_pct_val:.0f}% das {n_vitorias} vitórias T1. "
                f"Sem contrato histórico comparável — saving não calculável nesta simulação. "
                f"Gap médio para ampliar liderança: R$ {gap_medio:.2f}/pedido."
            )
        else:
            insight = limpar_texto(
                f"Top 3 faixas por volume ({top3_ceps_vol}): {top3_vol_pct_val:.0f}% das {n_vitorias} vitórias T1. "
                "Sem contrato histórico comparável — saving não calculável nesta simulação. "
                "Para análise de saving, é necessário contrato de frete histórico do cliente."
            )
        linhas_insight = [insight]
    else:
        top3_ceps    = ", ".join(f"CEP {c}" for c in top3.index[:3])
        top3_vol_pct = top3["Vol_Pct"].sum()
        top3_sav_pct = top3["Saving_Pct"].sum()
        top3_sav_val = top3["Saving"].sum()

        perda_ceps = [str(c) for c in perda_serie.index[:2]] if not perda_serie.empty else []
        txt_perda  = (
            limpar_texto(f"CEP {' e CEP '.join(perda_ceps)}: custo simulado > atual — menor competitividade nessas faixas.")
            if perda_ceps else ""
        )

        insight = limpar_texto(
            f"Top 3 faixas ({top3_ceps}): {top3_vol_pct:.0f}% do volume e "
            f"{top3_sav_pct:.0f}% do saving ({formatar_monetario_br(top3_sav_val)}). "
            f"Maior retorno potencial caso a tabela seja implementada."
        )
        linhas_insight = [insight]
        if txt_perda:
            linhas_insight.append(txt_perda)

    pdf.box_borda(
        limpar_texto(f"O QUE OS DADOS INDICAM  -  {foco_label} POR CEP"),
        linhas_insight,
        cor=_V,
        cor_fundo=COR_VERDE_CLARO,
    )


def _pagina_heatmap(pdf: PDFReport, imagens: dict) -> None:
    """Seção 6: Heatmap de Competitividade Regional."""
    pdf.add_page()
    pdf.titulo_secao("8", "Heatmap de Competitividade Regional")
    if "heatmap" in imagens:
        y_h = pdf.get_y()
        # Preenche todo o espaço disponível até a margem inferior (297 - 18mm)
        h_disp = 279 - y_h
        pdf.image(imagens["heatmap"], x=8, y=y_h, w=194, h=h_disp)
    else:
        pdf.ln(10)
        pdf.set_font("Arial", "I", 9)
        pdf.set_text_color(130, 130, 130)
        pdf.cell(0, 8, "Dados insuficientes para gerar Heatmap Regional.", 0, 1, "C")


def _pagina_perfil_carga(
    pdf: PDFReport,
    df: pd.DataFrame,
    r_transp: pd.DataFrame,
    imagens: dict,
    transp_foco: Optional[List[str]] = None,
) -> None:
    """Seção 9: Perfil de Carga — gráfico + tabela 'Lider de Custo por Faixa'."""
    pdf.add_page()
    pdf.titulo_secao("9", "Perfil de Carga  -  Custo por Faixa de Peso")

    # ── Gráfico ocupa topo da página ──────────────────────────────────────────
    if "peso" in imagens:
        y_h = pdf.get_y()
        # Reserva ~140mm para o gráfico, deixando espaço para a tabela abaixo
        pdf.image(imagens["peso"], x=8, y=y_h, w=194, h=138)
        pdf.set_y(y_h + 142)

    # ── Tabela analítica: Lider de Custo por Faixa ────────────────────────────
    if "Faixa_Peso" in df.columns and "Custo_Novo" in df.columns and not r_transp.empty:
        top5 = r_transp.head(5)["Transp_Nova"].tolist()
        df_base = df[df["Transp_Nova"].isin(top5)].copy()

        foco_lower = transp_foco[0].lower() if transp_foco else ""

        pdf.subtitulo("Líder de Custo por Faixa de Peso")
        pdf.set_font("Arial", "I", 8)
        pdf.set_text_color(110, 115, 120)
        pdf.cell(0, 5,
            limpar_texto(
                "Transportadora com menor custo médio em cada faixa. "
                + (f"Linhas em verde = {transp_foco[0]} lidera a faixa." if foco_lower else "")
            ),
            0, 1, "L")
        pdf.ln(1)

        col_w = [32, 68, 28, 30, 32]
        pdf.tabela_header(
            col_w,
            ["Faixa", "Transportadora Líder", "Custo Líder", "Média Geral", "Saving vs Max"],
            ["L", "L", "R", "R", "C"],
        )

        faixas_ordenadas = ["0-5kg", "5-10kg", "10-20kg", "20-30kg",
                            "30-50kg", "50-100kg", "100kg+"]
        for i, faixa in enumerate(faixas_ordenadas):
            df_f = df_base[df_base["Faixa_Peso"].astype(str) == faixa]
            if df_f.empty:
                continue
            custos = df_f.groupby("Transp_Nova")["Custo_Novo"].mean()
            custos = custos[custos > 0]
            if custos.empty:
                continue
            lider_nome = custos.idxmin()
            custo_lider = custos.min()
            custo_max = custos.max()
            custo_medio = custos.mean()
            saving_pct = ((custo_max - custo_lider) / custo_max * 100) if custo_max > 0 else 0
            is_foco = bool(foco_lower and foco_lower in str(lider_nome).lower())
            valores = [
                faixa,
                limpar_texto(str(lider_nome)[:32]),
                formatar_monetario_br(custo_lider),
                formatar_monetario_br(custo_medio),
                f"{saving_pct:.1f}%",
            ]
            aligns = ["L", "L", "R", "R", "C"]
            if is_foco:
                pdf.set_fill_color(*COR_VERDE_CLARO)
                pdf.set_text_color(*_V)
                pdf.set_font("Arial", "B", 8.5)
                for w, v, a in zip(col_w, valores, aligns):
                    pdf.cell(w, 8, v, 0, 0, a, fill=True)
                pdf.ln()
                pdf.set_text_color(*_C)
            else:
                pdf.tabela_linha(col_w, valores, aligns, zebra=(i % 2 == 0))


def _pagina_diagnostico(
    pdf: PDFReport,
    df: pd.DataFrame,
    r_transp: pd.DataFrame,
    resumo_saving: dict,
    migration_result: Optional[MigrationAnalysisResult],
    regional_result: Optional[RegionalStrategyResult],
    sla_result: Optional[SLAComplianceResult],
    transp_foco: Optional[List[str]] = None,
    gap_bid_result: Optional[BidGapResult] = None,
) -> None:
    """Secao 8: Conclusão e Próximos Passos — sugestões baseadas nos dados."""
    pdf.add_page()
    pdf.titulo_secao("10", "Conclusão e Próximos Passos")

    saving_total = float(resumo_saving.get("Saving_Valor", 0))
    custo_antigo = float(resumo_saving.get("Custo_Antigo_Comp", 0))
    saving_pct   = (saving_total / custo_antigo * 100) if custo_antigo > 0.01 else 0
    nome_foco    = transp_foco[0].title() if transp_foco else None
    is_bid_cru   = gap_bid_result is not None and gap_bid_result.pedidos_lider and gap_bid_result.pedidos_lider > 0

    df_migrados = (
        migration_result.df_migrados
        if migration_result is not None and migration_result.has_migration
        else pd.DataFrame()
    )

    # Calcula desempenho da foco vs benchmark diretamente do df (r_transp agrega "OUTRAS")
    foco_acima_bench = False
    foco_abaixo_bench = False
    pct_acima_foco   = 0.0
    if nome_foco and not df.empty and "Custo_Novo" in df.columns and "Transp_Nova" in df.columns:
        foco_upper   = nome_foco.strip().upper()
        df_foco_loc  = df[df["Transp_Nova"].str.strip().str.upper() == foco_upper]
        df_bench_loc = df[df["Transp_Nova"].str.strip().str.upper() != foco_upper]
        if not df_foco_loc.empty and not df_bench_loc.empty:
            custo_foco_val  = float(df_foco_loc["Custo_Novo"].mean())
            custo_bench_val = float(df_bench_loc["Custo_Novo"].mean())
            if custo_bench_val > 0:
                pct_acima_foco    = (custo_foco_val - custo_bench_val) / custo_bench_val * 100
                foco_acima_bench  = pct_acima_foco > 10
                foco_abaixo_bench = pct_acima_foco < -10

    # Nota de contexto
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(120, 125, 130)
    pdf.multi_cell(
        190, 4,
        limpar_texto(
            "As sugestões abaixo são baseadas exclusivamente nos dados desta simulação. "
            "A decisão de implementação e o caminho a seguir são de responsabilidade do cliente, "
            "considerando fatores operacionais, comerciais e estratégicos não contemplados neste estudo."
        ),
        0, "L",
    )
    pdf.ln(5)

    # ── Sugestão de próximos passos (roadmap) ────────────────────────────────
    _renderizar_roadmap(
        pdf, saving_pct, regional_result, sla_result,
        nome_foco=nome_foco, foco_acima_bench=foco_acima_bench,
        foco_abaixo_bench=foco_abaixo_bench, pct_acima=pct_acima_foco,
        is_bid_cru=is_bid_cru,
    )

    # ── Síntese do estudo ─────────────────────────────────────────────────────
    _renderizar_sintese(
        pdf, df_migrados, saving_total, saving_pct,
        nome_foco=nome_foco, foco_acima_bench=foco_acima_bench,
        foco_abaixo_bench=foco_abaixo_bench,
        is_bid_cru=is_bid_cru,
    )


def _renderizar_roadmap(
    pdf: PDFReport,
    saving_pct: float,
    regional_result: Optional[RegionalStrategyResult],
    sla_result: Optional[SLAComplianceResult],
    nome_foco: Optional[str] = None,
    foco_acima_bench: bool = False,
    foco_abaixo_bench: bool = False,
    pct_acima: float = 0.0,
    is_bid_cru: bool = False,
) -> None:
    """Roadmap visual de implementacao em 3 colunas."""
    n_regioes = len(regional_result.texto_recomendacoes) if regional_result and regional_result.texto_recomendacoes else 0
    sla_meta  = f"{sla_result.compliance_global_pct:.0f}%" if sla_result else "N/A"
    _qual_t1  = " (em vitórias T1)" if is_bid_cru else ""

    if saving_pct > 0:
        if foco_acima_bench and nome_foco:
            fase1_acao = (
                f"Saving de {abs(saving_pct):.0f}% identificado no mix geral. "
                f"{nome_foco} está {pct_acima:.0f}% acima do benchmark{_qual_t1} — "
                "revisar tabela antes de homologar (ver seção 1)."
            )
        elif foco_abaixo_bench and nome_foco:
            pct_abaixo = abs(pct_acima)
            _alerta_cru = (
                " Atenção: essa comparação considera apenas rotas T1 vencidas; "
                "ver Tabela de Target Price (seção 1) para o cenário de cotações totais."
                if is_bid_cru else ""
            )
            fase1_acao = (
                f"Saving de {abs(saving_pct):.0f}% identificado. "
                f"{nome_foco} está {pct_abaixo:.0f}% abaixo do benchmark{_qual_t1} — "
                f"perfil competitivo favorável à homologação no TMS.{_alerta_cru}"
            )
        else:
            fase1_acao = (
                f"O estudo aponta potencial de saving de {abs(saving_pct):.0f}% nos pedidos validados. "
                "Uma possibilidade seria avaliar a homologação das novas transportadoras no TMS."
            )
    else:
        fase1_acao = (
            "O estudo indica que os pedidos analisados não geraram ganho financeiro. "
            "Pode ser relevante revisar as tabelas com as transportadoras atuais."
        )
    fase2_acao = (
        f"Com base na malha sugerida para {n_regioes} regiões, uma opção seria considerar "
        "acordos de volume com os parceiros identificados como mais competitivos."
        if n_regioes > 0
        else "O heatmap regional pode ser um ponto de partida para avaliar "
             "a consolidação de parceiros por região."
    )
    fase3_acao = (
        "Independentemente da decisão, pode ser útil estruturar um acompanhamento "
        "de prazo de entrega por transportadora para embasar futuras negociações de tabela."
    )

    fases = [
        ("PASSO 1",  "Validação Interna",     "Curto prazo",   fase1_acao,  _V),
        ("PASSO 2",  "Análise Regional",       "Médio prazo",   fase2_acao,  _A),
        ("PASSO 3",  "Monitoramento",          "Contínuo",      fase3_acao,  (74, 74, 74)),
    ]

    pdf.subtitulo("Sugestão de Próximos Passos")
    col_w   = 62
    gap     = 2
    total_w = len(fases) * col_w + (len(fases) - 1) * gap
    start_x = 8
    y_road  = pdf.get_y()
    row_h   = 8   # altura do cabecalho de cada coluna
    body_h  = 28  # altura do corpo de texto

    for ci, (fase, subtitulo_f, prazo, acao, cor) in enumerate(fases):
        cx = start_x + ci * (col_w + gap)

        # Fundo do corpo
        pdf.set_fill_color(250, 250, 252)
        pdf.rect(cx, y_road, col_w, row_h + body_h, "F")

        # Cabecalho colorido
        pdf.set_fill_color(*cor)
        pdf.rect(cx, y_road, col_w, row_h, "F")

        # Fase + prazo no cabecalho
        pdf.set_xy(cx, y_road + 0.5)
        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(col_w, 4, limpar_texto(fase), 0, 1, "C")
        pdf.set_xy(cx, y_road + 4.5)
        pdf.set_font("Arial", "", 6.5)
        pdf.cell(col_w, 3, limpar_texto(f"{subtitulo_f}  |  {prazo}"), 0, 0, "C")

        # Corpo com texto da acao
        pdf.set_xy(cx + 2, y_road + row_h + 2)
        pdf.set_font("Arial", "", 7.5)
        pdf.set_text_color(60, 65, 70)
        pdf.multi_cell(col_w - 4, 4.5, limpar_texto(acao), 0, "L")

        # Borda da coluna
        pdf.set_draw_color(*cor)
        pdf.set_line_width(0.4)
        pdf.rect(cx, y_road, col_w, row_h + body_h, "D")
        pdf.set_line_width(0.2)
        pdf.set_draw_color(*_LN)

    pdf.set_y(y_road + row_h + body_h + 5)
    pdf.set_text_color(*_C)


def _renderizar_sintese(
    pdf: PDFReport,
    df_migrados: pd.DataFrame,
    saving_total: float,
    saving_pct: float,
    nome_foco: Optional[str] = None,
    foco_acima_bench: bool = False,
    foco_abaixo_bench: bool = False,
    is_bid_cru: bool = False,
) -> None:
    """Síntese do estudo — apresenta o que os dados mostram, sem prescrever decisão."""
    if df_migrados.empty:
        return

    share_mig  = df_migrados["Transp_Nova"].value_counts(normalize=True)
    top_nova   = str(share_mig.idxmax())
    peso_medio = df_migrados["Peso"].mean() if "Peso" in df_migrados.columns else 0
    perfil     = "cargas pesadas (acima de 5kg)" if peso_medio > 5 else "cargas leves (até 5kg)"

    # O destaque ("com destaque para X") sempre aponta o real motor do saving (top_nova),
    # exceto quando a própria foco é o top migrador.
    # A performance da foco (acima/abaixo do benchmark) aparece apenas como nota adicional.
    foco_is_top = nome_foco and top_nova.strip().upper() == nome_foco.strip().upper()
    ref_foco    = nome_foco if foco_is_top else top_nova

    if saving_pct > 0:
        if share_mig.max() < 0.7:
            estrategia = limpar_texto(f"mix de transportadoras com destaque para {ref_foco}")
        else:
            estrategia = limpar_texto(ref_foco)

        nota_foco = ""
        _qual_t1 = " (em vitórias T1)" if is_bid_cru else ""
        if nome_foco and not foco_is_top and foco_acima_bench:
            nota_foco = limpar_texto(
                f" A transportadora {nome_foco}, objeto deste estudo, apresenta custo acima do benchmark{_qual_t1}"
                " e contribui de forma limitada para o saving total — ver análise detalhada nas seções 1 e 2."
            )
        elif nome_foco and not foco_is_top and foco_abaixo_bench:
            _alerta_cru = (
                " Observação: comparação restrita às rotas T1 vencidas; nas demais cotações o "
                "posicionamento é diferente — ver Tabela de Target Price na seção 1."
                if is_bid_cru else ""
            )
            nota_foco = limpar_texto(
                f" A transportadora {nome_foco}, objeto deste estudo, apresenta custo abaixo do benchmark{_qual_t1}"
                f" — perfil competitivo relevante para a decisão de homologação.{_alerta_cru}"
            )

        sintese = limpar_texto(
            f"O estudo indica que o cenário simulado, baseado em {estrategia}, "
            f"apresenta aderência ao perfil de {perfil} da operação "
            f"e aponta potencial de saving de {formatar_monetario_br(saving_total)} "
            f"({saving_pct:.1f}% de redução em relação ao cenário atual)."
            f"{nota_foco} "
            "Esses dados podem ser usados como base para a tomada de decisão."
        )
        pdf.box_sucesso("SÍNTESE DO ESTUDO:", [sintese])
    else:
        sintese = limpar_texto(
            f"O estudo aponta que o cenário simulado apresenta custo {abs(saving_pct):.1f}% superior ao atual. "
            "Esse resultado pode ser relevante caso o cliente identifique ganhos operacionais ou de cobertura "
            "que justifiquem o diferencial financeiro — a avaliação desse trade-off é do cliente."
        )
        pdf.box_alerta("SÍNTESE DO ESTUDO:", [sintese])


def _pagina_competitividade(
    pdf: PDFReport,
    df: pd.DataFrame,
    imagens: dict,
    transp_foco: Optional[List[str]],
    competitive_result: Optional[CompetitiveAnalysisResult] = None,
    gap_bid_result: Optional[BidGapResult] = None,
    df_foco_raw: Optional[pd.DataFrame] = None,
) -> None:
    """Secao 9: Analise de Competitividade & Pricing — 3 zonas + Perfil BID + Gap BID."""
    pdf.add_page()
    pdf.titulo_secao("1", "Competitividade & Pricing  -  Target Price")

    # Pre-calcula dados de pricing por regiao
    mapa_reg = {uf: reg for reg, ufs in REGIOES_BR.items() for uf in ufs}
    df2 = df.copy()
    df2["Regiao"] = df2["UF"].map(mapa_reg).fillna("Outros")
    df2["Grupo_Upper"] = df2["Transp_Nova"].str.strip().str.upper()
    foco_upper = [str(t).strip().upper() for t in (transp_foco or [])]

    # df_foco_raw traz todas as cotações da foco (ganhas + perdidas) — base correta
    # da tabela de Target Price (a foco pode não aparecer no df T1 por região).
    df_foco = df_foco_raw.copy()
    if "UF" in df_foco.columns:
        df_foco["Regiao"] = df_foco["UF"].map(mapa_reg).fillna("Outros")
    else:
        df_foco["Regiao"] = "Outros"
    if "Transp_Nova" in df_foco.columns:
        df_foco["Grupo_Upper"] = df_foco["Transp_Nova"].str.strip().str.upper()
    else:
        df_foco["Grupo_Upper"] = ""

    df_bench = df2[~df2["Grupo_Upper"].isin(foco_upper)] if foco_upper else df2
    nome_foco = transp_foco[0].title() if transp_foco else "Transportadora Foco"

    # Nota metodologica
    pdf.set_font("Arial", "I", 8.5)
    pdf.set_text_color(100, 105, 110)
    _metod = (
        f"Posicionamento de {nome_foco} vs benchmark de mercado por região. "
        "Target Price = benchmark - 5%: preço-alvo de negociação para manter competitividade "
        "estrutural sem ceder margem desnecessária."
        f" * Nesta tabela, 'Custo Cotado' é a média de TODAS as cotações de {nome_foco} "
        "(ganhas + perdidas) — diferente do card 'Custo Médio Vitórias T1' do panorama, "
        "que considera apenas rotas vencidas."
    )
    pdf.multi_cell(0, 5, limpar_texto(_metod), 0, "L")
    pdf.ln(2)

    # ── ZONA 1: Grafico ───────────────────────────────────────────────────────
    if "pricing" in imagens:
        y_img = pdf.get_y()
        pdf.image(imagens["pricing"], x=8, y=y_img, w=194, h=82)
        pdf.set_y(y_img + 86)

    # ── ZONA 2: Tabela Target Price por regiao ────────────────────────────────
    pdf.subtitulo("Tabela de Target Price por Região")
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(110, 115, 120)
    pdf.cell(
        0, 4,
        limpar_texto("Target Price = Benchmark de mercado - 5%  |  Situação calculada sobre custo médio por pedido."),
        0, 1, "L",
    )
    pdf.ln(1)

    col_w = [34, 30, 30, 30, 24, 22, 26]
    hdrs  = ["Região", "Custo Cotado", "Benchmark", "Target (-5%)", "Gap R$", "Gap %", "Situação"]
    alns  = ["L", "R", "R", "R", "R", "C", "C"]
    pdf.tabela_header(col_w, hdrs, alns)

    regioes_ord = [r for r in ORDEM_REGIOES if r in df2["Regiao"].values]
    for idx, reg in enumerate(regioes_ord):
        c_foco  = df_foco[df_foco["Regiao"] == reg]["Custo_Novo"].mean()  if not df_foco.empty  else float("nan")
        c_bench = df_bench[df_bench["Regiao"] == reg]["Custo_Novo"].mean() if not df_bench.empty else float("nan")
        c_tgt   = c_bench * 0.95 if pd.notna(c_bench) else float("nan")

        if pd.notna(c_foco) and pd.notna(c_tgt):
            gap_r = c_foco - c_tgt
            gap_p = (c_foco / c_tgt - 1) * 100 if c_tgt > 0 else float("nan")
            if c_foco <= c_tgt:
                sit, cor_sit = "COMPETITIVO", (0, 120, 0)
            elif c_foco <= c_bench:
                sit, cor_sit = "DENTRO", (160, 100, 0)
            else:
                sit, cor_sit = "ACIMA BENCH", (180, 0, 0)
        else:
            gap_r, gap_p = float("nan"), float("nan")
            sit, cor_sit = "S/DADOS", (130, 130, 130)

        zebra = (246, 249, 253) if idx % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*zebra)
        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "B", 8.5)
        pdf.cell(col_w[0], 7, limpar_texto(reg), 0, 0, "L", True)
        pdf.set_font("Arial", "", 8.5)
        pdf.cell(col_w[1], 7, limpar_texto(f"R$ {c_foco:.2f}")  if pd.notna(c_foco)  else "-", 0, 0, "R", True)
        pdf.cell(col_w[2], 7, limpar_texto(f"R$ {c_bench:.2f}") if pd.notna(c_bench) else "-", 0, 0, "R", True)
        pdf.cell(col_w[3], 7, limpar_texto(f"R$ {c_tgt:.2f}")   if pd.notna(c_tgt)   else "-", 0, 0, "R", True)
        gap_r_str = (f"+ R$ {gap_r:.2f}" if gap_r >= 0 else f"- R$ {abs(gap_r):.2f}") if pd.notna(gap_r) else "-"
        gap_p_str = (f"+{gap_p:.1f}%" if gap_p >= 0 else f"{gap_p:.1f}%") if pd.notna(gap_p) else "-"
        pdf.cell(col_w[4], 7, limpar_texto(gap_r_str), 0, 0, "R", True)
        pdf.cell(col_w[5], 7, limpar_texto(gap_p_str), 0, 0, "C", True)
        # Celula situacao colorida
        x_sit = pdf.get_x()
        y_sit = pdf.get_y()
        pdf.set_fill_color(*zebra)
        pdf.cell(col_w[6], 7, "", 0, 0, "C", True)
        pdf.set_xy(x_sit, y_sit)
        pdf.set_font("Arial", "B", 7)
        pdf.set_text_color(*cor_sit)
        pdf.cell(col_w[6], 7, limpar_texto(sit), 0, 1, "C", False)
        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "", 8.5)

    pdf.ln(1)
    # Nota explicativa: Gap % da tabela usa Target como base, não o benchmark
    pdf.set_font("Arial", "I", 7)
    pdf.set_text_color(130, 135, 140)
    pdf.multi_cell(
        0, 4,
        limpar_texto(
            "* Gap % = distância do custo atual até o Target Price (benchmark - 5%). "
            "Difere do gap vs benchmark exibido nas demais seções: "
            "ex. 21,8% acima do Target ≠ 15,7% acima do benchmark — "
            "o Target é 5% mais baixo, portanto o gap a partir dele é sempre maior."
        ),
        0, "L",
    )
    pdf.set_text_color(*_C)
    pdf.ln(3)

    # ── ZONA 3: Diagnostico estrategico ──────────────────────────────────────
    try:
        df_all = df2.copy()

        # Diagnóstico usa somente as vitórias T1 da foco (comparação justa T1 vs T1).
        # A tabela de Target Price acima mantém as cotações completas (mostra gap de precificação).
        df_foco_diag = df2[df2["Grupo_Upper"].isin(foco_upper)]

        regs_validas = [r for r in regioes_ord if not df_foco_diag.empty and
                        not df_foco_diag[df_foco_diag["Regiao"] == r].empty and
                        not df_bench[df_bench["Regiao"] == r].empty]

        linhas_diag: List[str] = []

        # Posicionamento geral
        if not df_foco_diag.empty and not df_bench.empty:
            geral_foco  = df_foco_diag["Custo_Novo"].mean()
            geral_bench = df_bench["Custo_Novo"].mean()
            gap_geral   = (geral_foco / geral_bench - 1) * 100
            prazo_foco  = df_foco_diag["Prazo_Novo"].mean() if "Prazo_Novo" in df_foco_diag.columns else float("nan")
            prazo_bench = df_bench["Prazo_Novo"].mean() if "Prazo_Novo" in df_bench.columns else float("nan")
            txt_prazo = ""
            if pd.notna(prazo_foco) and pd.notna(prazo_bench):
                delta_p = prazo_foco - prazo_bench
                txt_prazo = limpar_texto(
                    f" Lead time: {abs(delta_p):.1f}d {'mais rápido' if delta_p < 0 else 'mais lento'} que o mercado."
                )
            status_geral = "ABAIXO do benchmark" if gap_geral < 0 else "ACIMA do benchmark"
            _suf_t1 = " (em vitórias T1)"
            linhas_diag.append(limpar_texto(
                f"CUSTO GERAL{_suf_t1}: {nome_foco} apresenta custo médio {abs(gap_geral):.1f}% {status_geral} "
                f"(R$ {geral_foco:.2f} vs R$ {geral_bench:.2f} do mercado).{txt_prazo}"
            ))

        # Melhor e pior regiao para a foco (T1 wins only em BID cru — comparação justa T1 vs T1)
        scores = {}
        for reg in regs_validas:
            cf = df_foco_diag[df_foco_diag["Regiao"] == reg]["Custo_Novo"].mean()
            cb = df_bench[df_bench["Regiao"] == reg]["Custo_Novo"].mean()
            if pd.notna(cf) and pd.notna(cb) and cb > 0:
                scores[reg] = (cf / cb - 1) * 100

        if len(scores) >= 2:
            melhor = min(scores, key=scores.get)
            pior   = max(scores, key=scores.get)
            # Quando todos os scores são negativos (foco abaixo em todas as regiões),
            # o "pior" é apenas "menos abaixo" — não há pressão de custo real.
            todas_abaixo = all(v < 0 for v in scores.values())
            if todas_abaixo:
                _txt_pior = (
                    f"MENOR FOLGA: {pior} é a região com menor margem vs benchmark "
                    f"({scores[pior]:+.1f}%) — ainda abaixo, mas mais próxima do mercado."
                )
            else:
                _txt_pior = (
                    f"PONTO DE ATENÇÃO: maior pressão de custo no {pior} ({scores[pior]:+.1f}% vs benchmark)."
                )
            linhas_diag.append(limpar_texto(
                f"DESTAQUE POSITIVO{_suf_t1}: melhor posicionamento identificado no {melhor} "
                f"({scores[melhor]:+.1f}% vs benchmark). {_txt_pior}"
            ))
            # Regioes criticas acima do benchmark (só faz sentido com 2+ regiões)
            criticas = [r for r, v in scores.items() if v > 0]
            if criticas:
                linhas_diag.append(limpar_texto(
                    f"REFERÊNCIA DE PREÇO: em {len(criticas)} região(ões) ({', '.join(criticas)}) o custo "
                    "está acima do benchmark — dado que pode ser útil em futuras negociações de tabela."
                ))
            else:
                linhas_diag.append(limpar_texto(
                    "REFERÊNCIA DE PREÇO: nas vitórias T1, o custo da foco fica abaixo do benchmark em todas as "
                    "regiões — porém a Tabela de Target Price acima (todas cotações) mostra o oposto. "
                    "A foco vence apenas rotas onde já é competitiva; as cotações perdidas estão acima do mercado."
                ))
        elif len(scores) == 1:
            reg_unica = list(scores.keys())[0]
            val_unica = list(scores.values())[0]
            status_unica = "acima" if val_unica > 0 else "abaixo"
            linhas_diag.append(limpar_texto(
                f"COBERTURA REGIONAL: {nome_foco} opera exclusivamente no {reg_unica} "
                f"({val_unica:+.1f}% vs benchmark) — análise comparativa regional não aplicável "
                "para carrier com presença em uma única região."
            ))

        if linhas_diag:
            pdf.box_borda(
                limpar_texto(f"O QUE OS DADOS INDICAM  -  {nome_foco.upper()} vs MERCADO"),
                linhas_diag,
                cor=_A,
                cor_fundo=COR_AZUL_CLARO,
            )
    except Exception as exc:
        logger.error("Erro ao gerar diagnostico competitividade: %s", exc)
        pdf.set_font("Arial", "I", 9)
        pdf.cell(0, 8, limpar_texto(f"Diagnóstico indisponível: {exc}"), 0, 1)

    # ── ZONA 4: Gap para Liderar no BID ───────────────────────────────────────
    _bloco_gap_bid(pdf, gap_bid_result)


def _cards_kpi_bid(pdf: PDFReport, kpis: list) -> None:
    """Renderiza linha de cards KPI pequenos para o bloco de Perfil BID."""
    if not kpis:
        return
    n       = len(kpis)
    total_w = 194
    card_w  = total_w / n
    x0      = pdf.get_x()
    y0      = pdf.get_y()

    for i, (label, valor) in enumerate(kpis):
        x = x0 + i * card_w
        # Fundo do card
        pdf.set_fill_color(240, 244, 250)
        pdf.rect(x + 1, y0, card_w - 2, 14, "F")
        # Label
        pdf.set_xy(x + 1, y0 + 1)
        pdf.set_font("Arial", "", 6.5)
        pdf.set_text_color(100, 105, 115)
        pdf.cell(card_w - 2, 4, limpar_texto(label), 0, 0, "C")
        # Valor
        pdf.set_xy(x + 1, y0 + 5.5)
        pdf.set_font("Arial", "B", 9)
        pdf.set_text_color(*_A)
        pdf.cell(card_w - 2, 6, limpar_texto(valor), 0, 0, "C")

    pdf.set_xy(x0, y0 + 16)
    pdf.set_text_color(*_C)


def _bloco_gap_bid(pdf: PDFReport, gap: BidGapResult) -> None:
    """Renderiza o bloco 'Gap para Liderar no BID' na página de competitividade.

    Mostra quanto a carrier precisa reduzir para se tornar T1 em cada pedido,
    com análise de sensibilidade por nível de desconto e ranking de competidores.
    """
    _MIN_SPACE = 80
    if (297 - 18 - pdf.get_y()) < _MIN_SPACE:
        pdf.add_page()
    pdf.ln(5)
    pdf.subtitulo(limpar_texto(f"Gap para Liderar no BID  —  {gap.transp}"))

    # Nota explicativa
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(100, 105, 110)
    pdf.multi_cell(
        0, 4.5,
        limpar_texto(
            f"Análise de quanto {gap.transp} precisaria reduzir o preço por pedido para se "
            "tornar a opção mais barata (T1) no BID. Baseado no arquivo de recotação crua, "
            "comparando diretamente com o vencedor de preço real de cada cotação."
        ),
        0, "L",
    )
    pdf.ln(3)

    # ── KPI row ───────────────────────────────────────────────────────────────
    kpis_gap = [
        ("Pedidos Cotados",   str(gap.total_pedidos)),
        ("Já Lidera (T1)",    f"{gap.pedidos_lider}  ({gap.pct_lider:.1f}%)"),
        ("Gap Médio",         f"R$ {gap.gap_medio_r:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")),
        ("Desconto Necessário", f"{gap.gap_medio_pct:.1f}%"),
    ]
    _cards_kpi_bid(pdf, kpis_gap)
    pdf.ln(4)

    # ── Distribuição de posição ───────────────────────────────────────────────
    if gap.distribuicao_posicao:
        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(*_A)
        pdf.cell(0, 5, limpar_texto("Distribuição de Posição no BID"), 0, 1)
        pdf.set_font("Arial", "", 8)
        pdf.set_text_color(*_C)
        pos_parts = []
        for pos in ["T1", "T2", "T3", "T4", "T5"]:
            n = gap.distribuicao_posicao.get(pos, 0)
            if n > 0:
                pct = round(n / gap.total_pedidos * 100, 1)
                pos_parts.append(f"{pos}: {n} pedidos ({pct}%)")
        pdf.cell(0, 5, limpar_texto("  |  ".join(pos_parts)), 0, 1)
        pdf.ln(3)

    # ── Tabela 1: Sensibilidade ───────────────────────────────────────────────
    if gap.sensibilidade:
        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(*_A)
        pdf.cell(0, 5, limpar_texto(f"Análise de Sensibilidade  -  Pedidos que {gap.transp} Passaria a Liderar"), 0, 1)
        pdf.ln(1)

        col_w = [28, 52, 38, 38, 38]  # Desconto | Pedidos Ganhos | % do Total | Acum. Pedidos | Acum. %
        headers = ["Desconto", "Pedidos que Lideraria", "% do Total", "Acum. Pedidos", "Acum. %"]

        # Cabeçalho
        pdf.set_fill_color(*_A)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 7.5)
        for h, w in zip(headers, col_w):
            pdf.cell(w, 7, limpar_texto(h), 0, 0, "C", True)
        pdf.ln()

        acum_pedidos = 0
        for idx, row in enumerate(gap.sensibilidade):
            fill = idx % 2 == 0
            bg   = COR_ZEBRA_RGB if fill else (255, 255, 255)
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "", 8)

            ganhos      = row["pedidos_ganhos"]
            pct_total   = row["pct_total"]
            desconto    = row["desconto_pct"]
            # acumulado é o próprio ganhos (já inclui todos com gap <= desconto)
            acum_pedidos = ganhos
            acum_pct    = pct_total

            vals = [
                f"-{desconto}%",
                str(ganhos),
                f"{pct_total:.1f}%",
                str(acum_pedidos),
                f"{acum_pct:.1f}%",
            ]
            for v, w in zip(vals, col_w):
                pdf.cell(w, 6.5, limpar_texto(v), 0, 0, "C", fill)
            pdf.ln()

        pdf.ln(4)

    # ── Tabela 2: Competidores ────────────────────────────────────────────────
    if gap.competidores:
        if (297 - 18 - pdf.get_y()) < 45:
            pdf.add_page()

        pdf.set_font("Arial", "B", 8)
        pdf.set_text_color(*_A)
        pdf.cell(0, 5, limpar_texto(f"Competidores que Lideram vs {gap.transp}"), 0, 1)
        pdf.ln(1)

        col_c = [70, 42, 42, 40]
        _transp_abrev = gap.transp.split()[0] if gap.transp else "Foco"
        heads_c = ["Transportadora", f"Vitorias vs {_transp_abrev}", "Gap Medio R$", "Gap Medio %"]

        pdf.set_fill_color(*_A)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font("Arial", "B", 7.5)
        for h, w in zip(heads_c, col_c):
            pdf.cell(w, 7, limpar_texto(h), 0, 0, "C", True)
        pdf.ln()

        max_comp = 8
        for idx, comp in enumerate(gap.competidores[:max_comp]):
            fill = idx % 2 == 0
            bg   = COR_ZEBRA_RGB if fill else (255, 255, 255)
            pdf.set_fill_color(*bg)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "", 8)

            nome = str(comp.get("nome", ""))[:30]
            vit  = str(comp.get("vitorias_vs_tj", 0))
            gr   = f"R$ {comp.get('gap_medio_r', 0):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            gp   = f"{comp.get('gap_medio_pct', 0):.1f}%"

            for v, w in zip([nome, vit, gr, gp], col_c):
                pdf.cell(w, 6.5, limpar_texto(v), 0, 0, "C", fill)
            pdf.ln()

        pdf.ln(2)


def _narrativa_foco_regional(
    df: pd.DataFrame,
    regional_result: RegionalStrategyResult,
    foco_nome: str,
    foco_upper: set,
    gap_bid_result: Optional[BidGapResult] = None,
) -> List[str]:
    """Gera bullets textuais com posição, gap e análise de UF da foco por região."""
    from config.constants import REGIOES_BR, ORDEM_REGIOES

    scores_df = regional_result.scores_por_regiao
    if scores_df.empty or not foco_nome:
        return []

    mapa_uf_regiao = {uf: reg for reg, ufs in REGIOES_BR.items() for uf in ufs}

    # Inclui TODOS os pedidos da foco (com e sem base histórica) para contar volume por região.
    # O filtro tem_base é aplicado somente na análise de saving (mais abaixo).
    df_foco = df[
        df["Transp_Nova"].str.strip().str.upper().isin(foco_upper)
    ].copy()
    df_foco["_Regiao"] = df_foco["UF"].map(mapa_uf_regiao) if "UF" in df_foco.columns else ""

    # Conjunto de CEPs que a foco cotou (do gap_bid_result) — para distinguir
    # "cotada mas não competitiva" de "sem presença geográfica real"
    tj_ceps_cotados: set = set()
    if gap_bid_result is not None and gap_bid_result.df_posicao is not None:
        tj_ceps_cotados = set(
            gap_bid_result.df_posicao["CEP_Destino"].astype(str).str.zfill(8).unique()
        )

    # Mapa CEP→Região construído diretamente do df T1 (não depende de _dr_reg,
    # que só existe depois que a função é chamada dentro de _pagina_malha_regional).
    mapa_cep_regiao: dict = {}
    if "CEP_Destino" in df.columns and "UF" in df.columns:
        _df_cep_uf = df[["CEP_Destino", "UF"]].drop_duplicates()
        _df_cep_uf = _df_cep_uf.assign(
            _CEP8=_df_cep_uf["CEP_Destino"].astype(str).str.zfill(8),
            _Reg=_df_cep_uf["UF"].map(mapa_uf_regiao),
        )
        mapa_cep_regiao = dict(zip(_df_cep_uf["_CEP8"], _df_cep_uf["_Reg"]))

    linhas: List[str] = []
    regioes_nao_competitivas: List[str] = []
    regioes_sem_presenca: List[str] = []

    for regiao in ORDEM_REGIOES:
        scores_reg = (
            scores_df[scores_df["Regiao"] == regiao]
            .sort_values("Score", ascending=False)
            .reset_index(drop=True)
        )
        if scores_reg.empty:
            regioes_sem_presenca.append(regiao)
            continue

        foco_mask = scores_reg["Transp_Nova"].str.lower().str.contains(foco_nome, na=False)
        if not foco_mask.any():
            # Verifica se foco cotou nesta região (via intersecção de CEPs com mapa local)
            if tj_ceps_cotados and mapa_cep_regiao:
                ceps_nesta_regiao = {c for c, r in mapa_cep_regiao.items() if r == regiao}
                if ceps_nesta_regiao & tj_ceps_cotados:
                    regioes_nao_competitivas.append(regiao)
                else:
                    regioes_sem_presenca.append(regiao)
            else:
                regioes_sem_presenca.append(regiao)
            continue

        foco_idx  = int(scores_reg[foco_mask].index[0])
        foco_score = float(scores_reg.loc[foco_idx, "Score"]) * 100
        lider_score = float(scores_reg.iloc[0]["Score"]) * 100
        n_total   = len(scores_reg)
        posicao   = foco_idx + 1
        gap       = foco_score - lider_score  # negativo = atrás do líder

        # Pedidos da foco nesta região (todos — com e sem base histórica)
        df_reg_foco = df_foco[df_foco["_Regiao"] == regiao] if "_Regiao" in df_foco.columns else pd.DataFrame()
        # Subconjunto com base histórica — usado somente para cálculo de saving
        df_reg_foco_base = (
            df_reg_foco[df_reg_foco["Tem_Base"]]
            if "Tem_Base" in df_reg_foco.columns and not df_reg_foco.empty
            else df_reg_foco
        )

        partes_uf: List[str] = []
        if not df_reg_foco_base.empty and "Saving_Valor" in df_reg_foco_base.columns and "UF" in df_reg_foco_base.columns:
            uf_agg = (
                df_reg_foco_base.groupby("UF")["Saving_Valor"]
                .agg(saving="sum", qtd="count")
                .reset_index()
                .sort_values("saving", ascending=False)
            )
            positivas = uf_agg[uf_agg["saving"] > 0]
            negativas = uf_agg[uf_agg["saving"] < 0]

            if not positivas.empty:
                top = ", ".join(positivas.head(2)["UF"].tolist())
                # Em modo BID cru saving>0 indica vitórias T1, não diferencial vs contrato histórico
                partes_uf.append(f"presente em {top}")
            if not negativas.empty:
                bad = ", ".join(negativas.head(2)["UF"].tolist())
                n_neg = int(negativas["qtd"].sum())
                saving_neg_total = float(negativas["saving"].sum())
                custo_acima = abs(saving_neg_total / max(n_neg, 1))
                partes_uf.append(f"perda em {bad} (R${custo_acima:.0f}/ped acima do lider)")

        # Linha de cabeçalho da região
        if posicao == 1 and n_total == 1:
            cab = f"• {regiao} — LIDER  (Score: {foco_score:.0f} pts | único carrier com dados nesta região):"
        elif posicao == 1:
            cab = f"• {regiao} — LIDER  (Score: {foco_score:.0f} pts | {n_total} transp.):"
        else:
            cab = f"• {regiao} (Score: {foco_score:.0f} pts | #{posicao} de {n_total} | gap: {gap:+.0f} pts):"

        linhas.append(limpar_texto(cab))
        if partes_uf:
            linhas.append(limpar_texto("  " + "  —  ".join(partes_uf)))
        elif not df_reg_foco.empty:
            # Tem pedidos na região mas sem base histórica para comparação de saving
            n_ped_reg = len(df_reg_foco)
            linhas.append(limpar_texto(
                f"  {n_ped_reg} pedido(s) na região — sem contrato histórico comparável para análise de saving."
            ))
        else:
            linhas.append(limpar_texto("  Sem pedidos desta transportadora nesta região na simulação."))

    if regioes_nao_competitivas:
        # Conta cotações por região via intersecção CEP da foco x CEPs da região (não usa total geral).
        partes_reg: List[str] = []
        for _reg in regioes_nao_competitivas:
            _ceps_reg = {c for c, r in mapa_cep_regiao.items() if r == _reg}
            _n_reg = len(_ceps_reg & tj_ceps_cotados) if (_ceps_reg and tj_ceps_cotados) else 0
            partes_reg.append(f"{_reg} ({_n_reg} cotados)")
        linhas.append(limpar_texto(
            f"Presente mas não competitiva: {', '.join(partes_reg)}, 0 vitórias "
            "— negociação de preço necessária."
        ))
    if regioes_sem_presenca:
        linhas.append(
            limpar_texto(f"Expansão geográfica potencial: {', '.join(regioes_sem_presenca)} - ver Diretrizes.")
        )

    return linhas


def _pagina_malha_regional(
    pdf: PDFReport,
    df: pd.DataFrame,
    regional_result: RegionalStrategyResult,
    imagens: dict,
    transp_foco: Optional[List[str]] = None,
    gap_bid_result: Optional[BidGapResult] = None,
) -> None:
    """Seção 2: Malha Logística Recomendada."""
    # Sempre inicia em página própria para manter título, descrição e scores juntos.
    pdf.add_page()
    pdf.titulo_secao("2", "Malha Logística Recomendada")
    pdf.box_info(
        "METODOLOGIA DE RECOMENDAÇÃO:",
        [
            "Score por região calculado com base nos dados desta simulação: "
            "60% saving potencial e 40% representatividade de volume. "
            "Empate técnico (diferença < 5 pts) gera recomendação de Mix A + B para redundância.",
        ],
    )

    foco_nome  = transp_foco[0].lower() if transp_foco else ""
    foco_upper = {str(t).strip().upper() for t in transp_foco} if transp_foco else set()

    # Score visual nativo por região — 2 colunas (esq: 3 regiões, dir: 2 regiões)
    scores_df = regional_result.scores_por_regiao if not regional_result.scores_por_regiao.empty else pd.DataFrame()
    if not scores_df.empty and "Regiao" in scores_df.columns:
        from config.constants import ORDEM_REGIOES
        regioes_presentes = [r for r in ORDEM_REGIOES if r in scores_df["Regiao"].unique()]
        col_x    = [10, 105]   # x inicial de cada coluna
        col_w    = 90          # largura de cada coluna
        bar_max  = 44          # largura máx da barra de progresso (mm) — nome(30)+gap(1)+barra(44)+gap(1)+score(11)=87≤90
        row_h    = 7           # altura de cada linha de transportadora
        hdr_h    = 8           # altura do cabeçalho da região
        gap_blk  = 5           # espaço entre blocos de região

        # Distribui regiões: coluna 0 recebe as 3 primeiras, coluna 1 as demais
        col_regioes = [regioes_presentes[:3], regioes_presentes[3:]]
        y_start = pdf.get_y()
        y_ends  = [y_start, y_start]

        # Pré-calcula altura máxima de coluna; se não couber na página, força nova página
        _PAGE_BOTTOM = 282  # A4 (297mm) - margem inferior (~15mm)
        _col_heights = []
        for _regs in col_regioes:
            _h = sum(
                hdr_h + len(scores_df[scores_df["Regiao"] == r].head(5)) * row_h + 2 + gap_blk
                for r in _regs
            )
            _col_heights.append(_h)
        if _col_heights and y_start + max(_col_heights) > _PAGE_BOTTOM:
            pdf.add_page()
            y_start = pdf.get_y()
            y_ends = [y_start, y_start]

        for ci, regs in enumerate(col_regioes):
            cx = col_x[ci]
            y  = y_start
            for regiao in regs:
                df_r = scores_df[scores_df["Regiao"] == regiao].head(5).reset_index(drop=True)
                blk_h = hdr_h + len(df_r) * row_h + 2

                # Cabeçalho da região
                pdf.set_fill_color(*_A)
                pdf.rect(cx, y, col_w, hdr_h, "F")
                pdf.set_xy(cx + 3, y + 1.5)
                pdf.set_font("Arial", "B", 8.5)
                pdf.set_text_color(*_BR)
                pdf.cell(col_w - 6, 5, limpar_texto(regiao.upper()), 0, 1)

                # Linhas de transportadora com barra de progresso
                for ri, (_, r_row) in enumerate(df_r.iterrows()):
                    nome_raw = str(r_row["Transp_Nova"])
                    nome = limpar_texto(nome_raw[:28])
                    score = float(r_row["Score"])
                    is_foco = bool(foco_nome and foco_nome in nome_raw.lower())
                    ry = y + hdr_h + ri * row_h

                    # Fundo: verde claro para foco, zebra para demais
                    bg = COR_VERDE_CLARO if is_foco else (COR_ZEBRA_RGB if ri % 2 == 0 else _BR)
                    pdf.set_fill_color(*bg)
                    pdf.rect(cx, ry, col_w, row_h, "F")

                    # Nome da transportadora
                    pdf.set_xy(cx + 2, ry + 1)
                    pdf.set_font("Arial", "B" if is_foco else "", 7)
                    pdf.set_text_color(*(_V if is_foco else _C))
                    pdf.cell(30, 5, nome[:22], 0, 0, "L")

                    # Barra de progresso
                    bx = cx + 33
                    bw = bar_max * score
                    pdf.set_fill_color(220, 225, 230)
                    pdf.rect(bx, ry + 2, bar_max, 3, "F")
                    cor_bar = _V if is_foco else (100, 130, 160)
                    pdf.set_fill_color(*cor_bar)
                    if bw > 0:
                        pdf.rect(bx, ry + 2, bw, 3, "F")

                    # Score numérico
                    pdf.set_xy(bx + bar_max + 1, ry + 1)
                    pdf.set_font("Arial", "B" if is_foco else "", 7)
                    pdf.set_text_color(*(_V if is_foco else _C))
                    pdf.cell(10, 5, f"{score*100:.0f} pts", 0, 0, "L")

                # Borda do bloco
                pdf.set_draw_color(*_LN)
                pdf.set_line_width(0.3)
                pdf.rect(cx, y, col_w, blk_h, "D")
                pdf.set_line_width(0.2)
                y += blk_h + gap_blk
            y_ends[ci] = y

        pdf.set_y(max(y_ends) + 3)
    else:
        pdf.ln(5)

    # Mapa de score da transportadora FOCO por região (ponto 2: score da foco, não do vencedor)
    foco_score_map: dict = {}
    if foco_nome and not regional_result.scores_por_regiao.empty and "Regiao" in regional_result.scores_por_regiao.columns:
        df_scores = regional_result.scores_por_regiao
        df_foco_scores = df_scores[df_scores["Transp_Nova"].str.lower().str.contains(foco_nome)]
        if not df_foco_scores.empty:
            foco_score_map = (
                df_foco_scores.groupby("Regiao")["Score"]
                .max()
                .mul(100)
                .round(0)
                .to_dict()
            )

    # Tabela consolidada da malha — nova pagina para nao poluir os graficos
    malha = regional_result.malha_recomendada
    if not malha.empty:
        pdf.add_page()
        pdf.subtitulo("Malha Consolidada  -  Decisão por Região")
        # Ponto 1: removida coluna SLA Target (arbitrário, sem base contratual)
        # Ponto 5: coluna renomeada para "Custo Est." com nota explicativa
        col_w = [30, 75, 45, 20, 20]  # total = 190mm = página útil (10mm margens)
        pdf.tabela_header(
            col_w,
            ["Região", "Transp. Principal", "Transp. Backup", "Score Foco", "Custo Est."],
            ["L", "L", "L", "C", "R"],
        )
        # Gap 4: indica "s/vit." quando score é zero mas foco cotou pedidos
        sem_vitorias = (
            gap_bid_result is not None
            and gap_bid_result.total_pedidos > 0
            and gap_bid_result.pedidos_lider == 0
        )
        for i, (_, row) in enumerate(malha.iterrows()):
            regiao_str = str(row.get("Regiao", ""))
            foco_score_val = foco_score_map.get(regiao_str, 0)
            if foco_score_val > 0:
                score_display = f"{foco_score_val:.0f}"
            elif sem_vitorias:
                score_display = "s/vit."  # cotou mas não ganhou — sem score calculável
            else:
                score_display = "-"
            custo_t = row.get("Custo_Target_R$", 0)
            pdf.tabela_linha(
                col_w,
                [
                    regiao_str[:16],
                    limpar_texto(str(row.get("Transp_Principal", ""))[:58]),  # Gap 5: era [:44]
                    limpar_texto(str(row.get("Transp_Backup", ""))[:26]),
                    score_display,
                    f"R${custo_t:.0f}",
                ],
                ["L", "L", "L", "C", "R"],
                zebra=(i % 2 == 0),
            )
        # Ponto 5: nota explicativa sobre o custo estimado
        pdf.set_font("Arial", "I", 7)
        pdf.set_text_color(130, 135, 140)
        pdf.cell(0, 5, limpar_texto("* Custo Est. = custo médio da simulação com projeção de ganho de escala de 10-12% (estimativa, não contratual)."), 0, 1, "L")
        pdf.ln(1)

        # Box narrativo: posição e análise por UF da transportadora foco
        if foco_nome:
            bullets = _narrativa_foco_regional(df, regional_result, foco_nome, foco_upper,
                                                gap_bid_result=gap_bid_result)
            if bullets:
                titulo_foco = limpar_texto(
                    f"{transp_foco[0].upper()} - POSIÇÃO NA MALHA REGIONAL"
                )
                pdf.box_sucesso(titulo_foco, bullets, compact=True)

    # ── Comparativo: Foco vs Recomendado por Região ──────────────────────────
    malha_comp = regional_result.malha_recomendada
    if foco_nome and not malha_comp.empty and "UF" in df.columns and "Custo_Novo" in df.columns:
        from config.constants import REGIOES_BR as _RBR
        mapa_tmp = {uf: reg for reg, ufs in _RBR.items() for uf in ufs}
        df["_rtmp"] = df["UF"].map(mapa_tmp)
        linhas_comp = []
        for _, mrow in malha_comp.iterrows():
            regiao    = str(mrow.get("Regiao", ""))
            principal = str(mrow.get("Transp_Principal", ""))
            # Quando a foco É a recomendada, não há comparativo significativo
            principal_upper = principal.strip().upper()
            foco_e_recomendada = any(
                principal_upper.startswith(f) or f.startswith(principal_upper)
                for f in foco_upper
            )
            if foco_e_recomendada:
                foco_label_reg = transp_foco[0].upper() if transp_foco else "FOCO"
                linhas_comp.append(limpar_texto(
                    f"{regiao}: {foco_label_reg} é a transportadora recomendada nesta região."
                ))
                continue
            df_reg = df[df["_rtmp"] == regiao]
            df_f   = df_reg[df_reg["Transp_Nova"].str.strip().str.upper().isin(foco_upper)]
            df_p   = df_reg[df_reg["Transp_Nova"].str.strip() == principal]
            if df_f.empty or df_p.empty:
                continue  # sem dados para comparar — oportunidade tratada nas Diretrizes
            n_f      = len(df_f)
            if n_f < 5:
                # Amostra muito pequena: estatística não é confiável — omite o comparativo
                continue
            custo_f  = float(df_f["Custo_Novo"].mean())
            custo_p  = float(df_p["Custo_Novo"].mean())
            diff     = custo_f - custo_p
            pct_diff = diff / custo_p * 100 if custo_p > 0 else 0.0
            sinal    = "mais caro" if diff > 0 else "mais barato"
            princ_label = principal[:22]
            _aviso_n = "  [amostra reduzida]" if n_f < 10 else ""
            linhas_comp.append(limpar_texto(
                f"{regiao}: Foco R${custo_f:.2f}/ped vs {princ_label} R${custo_p:.2f}/ped"
                f" — {abs(pct_diff):.1f}% {sinal} ({n_f} ped).{_aviso_n}"
            ))
        df.drop(columns=["_rtmp"], inplace=True, errors="ignore")
        if linhas_comp:
            foco_label = transp_foco[0].upper() if transp_foco else "FOCO"
            pdf.box_info(
                limpar_texto(f"COMPARATIVO: {foco_label} vs RECOMENDADA POR REGIÃO (CUSTO MÉDIO/PEDIDO):"),
                linhas_comp + [limpar_texto(
                    "Médias calculadas sobre os pedidos T1 de cada carrier (conjuntos distintos — "
                    "não é comparação direta na mesma rota). Onde a foco é a recomendada, não há comparativo."
                )],
                compact=True,
            )

    # ── Diretrizes por Região — posicionamento da foco ────────────────────────
    if foco_nome and not regional_result.scores_por_regiao.empty:
        from config.constants import ORDEM_REGIOES as _OR, REGIOES_BR as _RBR2
        pdf.subtitulo(limpar_texto("Diretrizes por Região — Posicionamento da Foco"))
        pdf.set_font("Arial", "I", 8.5)
        pdf.set_text_color(100, 105, 110)
        pdf.cell(
            0, 5,
            limpar_texto("Posicionamento e oportunidade da transportadora foco por região:"),
            0, 1, "L",
        )
        pdf.ln(2)

        # Mapa UF→Região para calcular oportunidade nas regiões sem presença
        _mapa_uf_reg2 = {uf: reg for reg, ufs in _RBR2.items() for uf in ufs}
        if "UF" in df.columns:
            df["_dr_reg"] = df["UF"].map(_mapa_uf_reg2)

        s_df = regional_result.scores_por_regiao
        # margem inferior segura: rodapé começa em ~283mm; reservamos 18mm por entrada
        _MARGEM_DIRETRIZ = 265

        for regiao in _OR:
            s_reg = (
                s_df[s_df["Regiao"] == regiao]
                .sort_values("Score", ascending=False)
                .reset_index(drop=True)
            )

            # --- Verificação de espaço antes de cada região ---
            # Entrada com 2 linhas ocupa ~18mm; com 1 linha ~10mm
            fmask_pre = s_reg["Transp_Nova"].str.lower().str.contains(foco_nome, na=False) if not s_reg.empty else pd.Series([], dtype=bool)
            h_entrada = 18 if (s_reg.empty or not fmask_pre.any()) else 10
            if pdf.get_y() > _MARGEM_DIRETRIZ - h_entrada:
                pdf.add_page()
                pdf.subtitulo(limpar_texto("Diretrizes por Região — continuação"))
                pdf.ln(2)

            pdf.set_x(10)
            pdf.set_font("Arial", "", 8.5)
            pdf.set_text_color(*_C)

            if s_reg.empty:
                pdf.multi_cell(190, 6, limpar_texto(f"• {regiao}: sem dados suficientes nesta simulação."), 0, "L")
                pdf.ln(1)
                continue

            fmask = s_reg["Transp_Nova"].str.lower().str.contains(foco_nome, na=False)

            if not fmask.any():
                # Foco não ganhou pedidos nesta região — distingue "cotou mas perdeu" de "sem presença real"
                lider_nome  = str(s_reg.iloc[0]["Transp_Nova"])
                n_oport     = 0
                custo_lider = 0.0
                if "_dr_reg" in df.columns and "Custo_Novo" in df.columns:
                    df_reg_all  = df[df["_dr_reg"] == regiao]
                    n_oport     = len(df_reg_all)
                    df_lider_r  = df_reg_all[df_reg_all["Transp_Nova"].str.strip() == lider_nome]
                    custo_lider = float(df_lider_r["Custo_Novo"].mean()) if not df_lider_r.empty else 0.0

                # Gap 1&2: detectar se foco cotou nesta região mas não ganhou
                tj_cotou_nesta_regiao = False
                n_cotados_regiao = 0
                if (gap_bid_result is not None
                        and gap_bid_result.df_posicao is not None
                        and "_dr_reg" in df.columns):
                    tj_ceps = set(gap_bid_result.df_posicao["CEP_Destino"].astype(str).str.zfill(8))
                    ceps_reg = set(df[df["_dr_reg"] == regiao]["CEP_Destino"].astype(str).str.zfill(8))
                    comuns = tj_ceps & ceps_reg
                    tj_cotou_nesta_regiao = len(comuns) > 0
                    n_cotados_regiao = int(gap_bid_result.df_posicao[
                        gap_bid_result.df_posicao["CEP_Destino"].astype(str).str.zfill(8).isin(comuns)
                    ].shape[0]) if tj_cotou_nesta_regiao else 0

                if tj_cotou_nesta_regiao:
                    # Gap 1: mensagem correta — cotou mas não é competitiva
                    linha1 = limpar_texto(
                        f"• {regiao}: Foco cotada mas não competitiva — "
                        f"{n_cotados_regiao} pedidos cotados, 0 vitórias no BID."
                    )
                else:
                    # Sem presença geográfica real
                    linha1 = limpar_texto(
                        f"• {regiao}: Foco sem presença geográfica — "
                        f"{n_oport} pedidos na região sem cobertura atual."
                    )

                # Gap 3: referência com preço atual da foco + gap necessário
                if custo_lider > 0:
                    custo_foco_atual = (
                        gap_bid_result.ticket_medio_tj
                        if gap_bid_result and gap_bid_result.ticket_medio_tj > 0
                        else 0.0
                    )
                    if custo_foco_atual > 0:
                        gap_r = custo_foco_atual - custo_lider
                        gap_pct = gap_r / custo_lider * 100
                        linha2 = limpar_texto(
                            f"  Referência: {lider_nome[:28]} lidera com R${custo_lider:.2f}/ped. "
                            f"Foco pratica R${custo_foco_atual:.2f}/ped — "
                            f"precisa reduzir R${gap_r:.2f} ({gap_pct:.1f}%) para competir."
                        )
                    else:
                        linha2 = limpar_texto(
                            f"  Referência de entrada: {lider_nome[:28]} lidera com R${custo_lider:.2f}/ped."
                            f" Para competir, foco deve oferecer preço abaixo desse valor."
                        )
                else:
                    linha2 = limpar_texto(
                        f"  Líder da região: {lider_nome[:40]}. Levantar tabela de frete para avaliar entrada."
                    )
                pdf.multi_cell(190, 6, linha1, 0, "L")
                pdf.set_x(10)
                pdf.set_font("Arial", "I", 8)
                pdf.set_text_color(100, 105, 110)
                pdf.multi_cell(190, 5, linha2, 0, "L")
                pdf.set_font("Arial", "", 8.5)
                pdf.set_text_color(*_C)
            else:
                # Foco presente → mostrar posição e diretriz
                fi    = int(s_reg[fmask].index[0])
                fs    = float(s_reg.loc[fi, "Score"]) * 100
                ls    = float(s_reg.iloc[0]["Score"]) * 100
                gap   = fs - ls
                pos   = fi + 1
                n_tot = len(s_reg)
                if pos == 1 and n_tot == 1:
                    diretriz = (
                        f"• {regiao}: Foco LIDER (Score {fs:.0f} pts | único carrier com dados)"
                        f" - manter volume; avaliar competidores potenciais na região."
                    )
                elif pos == 1:
                    diretriz = (
                        f"• {regiao}: Foco LIDER (Score {fs:.0f} pts | {n_tot} transp.)"
                        f" - manter e expandir volume."
                    )
                elif pos == 2 and abs(gap) < 5:
                    diretriz = (
                        f"• {regiao}: Foco #{pos} em empate técnico (gap {gap:+.0f} pts)"
                        f" - candidata a transportadora principal."
                    )
                elif pos <= 3:
                    diretriz = (
                        f"• {regiao}: Foco #{pos} de {n_tot} (gap {gap:+.0f} pts)"
                        f" - candidata a backup operacional."
                    )
                else:
                    diretriz = (
                        f"• {regiao}: Foco #{pos} de {n_tot} (gap {gap:+.0f} pts)"
                        f" - uso complementar ou nichos específicos de CEP."
                    )
                pdf.multi_cell(190, 6, limpar_texto(diretriz), 0, "L")

            pdf.ln(1)

        df.drop(columns=["_dr_reg"], inplace=True, errors="ignore")



def _pagina_sla_risco(
    pdf: PDFReport,
    sla_result: SLAComplianceResult,
    imagens: dict,
) -> None:
    """Secao 11: Painel de SLA e Risco Operacional — 3 zonas."""
    pdf.add_page()
    pdf.titulo_secao("11", "Painel de SLA e Risco Operacional")

    comp  = sla_result.compliance_por_transp
    risco = sla_result.risco_por_transp

    # ── ZONA 1: 4 KPI cards ───────────────────────────────────────────────────
    n_critico = int((risco["Classificacao_Risco"] == ALTO_RISCO).sum())   if not risco.empty else 0
    n_atencao = int((risco["Classificacao_Risco"] == RISCO_MODERADO).sum()) if not risco.empty else 0
    n_ok      = int((risco["Classificacao_Risco"] == BAIXO_RISCO).sum())  if not risco.empty else 0
    global_pct = sla_result.compliance_global_pct
    melhor_row = comp.iloc[0] if not comp.empty else None
    melhor_nome = limpar_texto(str(melhor_row["Transp_Nova"])[:18]) if melhor_row is not None else "N/A"
    melhor_pct  = float(melhor_row["Pct_Compliance"]) if melhor_row is not None else 0.0
    cor_global  = (0, 120, 0) if global_pct >= 80 else ((160, 100, 0) if global_pct >= 50 else (180, 0, 0))

    _kpi_cards = [
        ("Compliance Global",        f"{global_pct:.1f}%",   cor_global),
        ("Transportadoras CRÍTICO",  str(n_critico),          (180, 0, 0)),
        ("Transportadoras ATENÇÃO",  str(n_atencao),          (160, 100, 0)),
        ("Melhor Performance",        melhor_nome,             (0, 120, 0)),
    ]
    _kpi_sub = ["", "", "", f"{melhor_pct:.0f}% SLA"]

    card_w, card_h, gap = 45, 30, 4
    y_c = pdf.get_y()
    for i, ((titulo, valor, cor), sub) in enumerate(zip(_kpi_cards, _kpi_sub)):
        cx = 8 + i * (card_w + gap)
        pdf.set_fill_color(210, 215, 220)
        pdf.rect(cx + 1.5, y_c + 1.5, card_w, card_h, "F")
        pdf.set_fill_color(255, 255, 255)
        pdf.rect(cx, y_c, card_w, card_h, "F")
        pdf.set_fill_color(*cor)
        pdf.rect(cx, y_c, card_w, 5, "F")
        # titulo
        pdf.set_xy(cx, y_c + 1)
        pdf.set_font("Arial", "B", 5.5)
        pdf.set_text_color(255, 255, 255)
        pdf.cell(card_w, 4, limpar_texto(titulo.upper()), 0, 0, "C")
        # valor principal
        pdf.set_xy(cx, y_c + 9)
        pdf.set_font("Arial", "B", 14 if len(valor) <= 6 else 10)
        pdf.set_text_color(*cor)
        pdf.cell(card_w, 9, limpar_texto(valor), 0, 1, "C")
        # subtitulo opcional
        if sub:
            pdf.set_xy(cx, y_c + 19)
            pdf.set_font("Arial", "", 7.5)
            pdf.set_text_color(100, 105, 110)
            pdf.cell(card_w, 4, limpar_texto(sub), 0, 1, "C")
        # borda
        pdf.set_draw_color(*cor)
        pdf.set_line_width(0.4)
        pdf.rect(cx, y_c, card_w, card_h, "D")
        pdf.set_line_width(0.2)
        pdf.set_draw_color(*_LN)

    pdf.set_y(y_c + card_h + 4)

    # ── Painel de detalhe: quais transportadoras estão em cada categoria ──────
    if not risco.empty:
        t_critico  = risco[risco["Classificacao_Risco"] == ALTO_RISCO]["Transp_Nova"].tolist()
        t_atencao  = risco[risco["Classificacao_Risco"] == RISCO_MODERADO]["Transp_Nova"].tolist()
        t_ok       = risco[risco["Classificacao_Risco"] == BAIXO_RISCO]["Transp_Nova"].tolist()

        panel_x, panel_y = 8, pdf.get_y()
        panel_w = 194
        col_w3  = panel_w / 3

        # Calcula altura necessária para o painel
        max_linhas = max(len(t_critico), len(t_atencao), len(t_ok), 1)
        panel_h = 7 + max_linhas * 5.5 + 4

        # Fundo do painel
        pdf.set_fill_color(250, 250, 252)
        pdf.rect(panel_x, panel_y, panel_w, panel_h, "F")
        pdf.set_draw_color(210, 215, 220)
        pdf.set_line_width(0.3)
        pdf.rect(panel_x, panel_y, panel_w, panel_h, "D")
        pdf.set_line_width(0.2)
        pdf.set_draw_color(*_LN)

        # Cabeçalho das 3 colunas
        _cols_cat = [
            ("CRÍTICO",   t_critico,  (180,   0,   0), (255, 242, 242)),
            ("ATENÇÃO",   t_atencao,  (160, 100,   0), (255, 250, 230)),
            ("OK",        t_ok,       (  0, 120,   0), (242, 252, 242)),
        ]
        for ci, (label, names, cor, cor_bg) in enumerate(_cols_cat):
            cx = panel_x + ci * col_w3
            # Barra colorida do cabeçalho
            pdf.set_fill_color(*cor_bg)
            pdf.rect(cx, panel_y, col_w3, panel_h, "F")
            pdf.set_fill_color(*cor)
            pdf.rect(cx, panel_y, col_w3, 6.5, "F")
            pdf.set_xy(cx, panel_y + 0.5)
            pdf.set_font("Arial", "B", 7)
            pdf.set_text_color(255, 255, 255)
            pdf.cell(col_w3, 5.5,
                     limpar_texto(f"{label}  ({len(names)})"),
                     0, 0, "C")
            # Lista de nomes
            for li, nome in enumerate(names):
                pdf.set_xy(cx + 2, panel_y + 7.5 + li * 5.5)
                pdf.set_font("Arial", "", 7)
                pdf.set_text_color(*cor)
                pdf.cell(col_w3 - 4, 5,
                         limpar_texto(str(nome)[:28]),
                         0, 0, "L")
            # Separador vertical entre colunas (exceto último)
            if ci < 2:
                pdf.set_draw_color(210, 215, 220)
                pdf.set_line_width(0.3)
                pdf.line(panel_x + (ci + 1) * col_w3, panel_y,
                         panel_x + (ci + 1) * col_w3, panel_y + panel_h)
                pdf.set_line_width(0.2)
                pdf.set_draw_color(*_LN)

        pdf.set_y(panel_y + panel_h + 3)

    # Nota metodologica compacta
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(120, 125, 130)
    pdf.multi_cell(
        0, 4,
        limpar_texto(
            "Targets de SLA (dias úteis): Sudeste 3d | Sul 4d | Centro-Oeste 5d | "
            "Nordeste 7d | Norte 8d.  Meta de mercado: 80% compliance.  "
            "Recomenda-se validar com SLAs contratuais antes de acionar ações corretivas."
        ),
        0, "L",
    )
    pdf.ln(2)

    # ── ZONA 2: Grafico de compliance — pagina propria ───────────────────────
    pdf.add_page()
    pdf.subtitulo("Ranking de Compliance SLA  (melhor ao pior)")
    pdf.set_font("Arial", "I", 7.5)
    pdf.set_text_color(120, 125, 130)
    pdf.multi_cell(
        0, 4,
        limpar_texto(
            "Transportadoras ordenadas do maior para o menor % dentro do SLA target regional.  "
            "Meta de mercado: 80%.  Verde = Dentro SLA  |  Vermelho = Fora SLA."
        ),
        0, "L",
    )
    pdf.ln(2)

    if "sla_compliance" in imagens:
        y_img = pdf.get_y()
        # Preenche toda a altura disponivel ate o rodape
        h_chart = max(80, int(279 - y_img - 6))
        pdf.image(imagens["sla_compliance"], x=8, y=y_img, w=194, h=h_chart)
        pdf.set_y(y_img + h_chart + 4)

    # ── ZONA 3: Tabela de priorizacao — nova pagina ───────────────────────────
    pdf.add_page()
    pdf.subtitulo("Tabela de Priorização Operacional")
    pdf.set_font("Arial", "I", 8)
    pdf.set_text_color(110, 115, 120)
    pdf.cell(
        0, 4,
        limpar_texto(
            "Ordenado do maior para o menor risco operacional.  "
            "Variabilidade = desvio padrão do prazo de entrega (dias)."
        ),
        0, 1, "L",
    )
    pdf.ln(2)

    col_w = [54, 22, 22, 26, 26, 30]
    hdrs  = ["Transportadora", "Pedidos", "% SLA", "Prazo Médio", "Variab. (d)", "Prioridade"]
    alns  = ["L", "C", "C", "C", "C", "C"]
    pdf.tabela_header(col_w, hdrs, alns)

    # Ordena pelo menor compliance (pior primeiro)
    if not risco.empty:
        tabela = risco[risco["Total_Pedidos"] >= 5].sort_values("Pct_Compliance", ascending=True).head(20)
    else:
        tabela = pd.DataFrame()

    for idx, (_, row) in enumerate(tabela.iterrows()):
        clas = row.get("Classificacao_Risco", BAIXO_RISCO)
        if clas == ALTO_RISCO:
            prioridade, cor_p = "CRÍTICO",   (180,   0,   0)
        elif clas == RISCO_MODERADO:
            prioridade, cor_p = "MONITORAR", (160, 100,   0)
        else:
            prioridade, cor_p = "OK",        (  0, 120,   0)

        pct = float(row.get("Pct_Compliance", 0))
        cor_pct = (0, 120, 0) if pct >= 80 else ((160, 100, 0) if pct >= 50 else (180, 0, 0))
        prazo_med = float(row.get("Prazo_Medio", 0))
        prazo_std = float(row.get("Prazo_Std", 0))

        zebra = (246, 249, 253) if idx % 2 == 0 else (255, 255, 255)
        pdf.set_fill_color(*zebra)

        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "", 8.5)
        pdf.cell(col_w[0], 7, limpar_texto(str(row["Transp_Nova"])[:30]), 0, 0, "L", True)
        pdf.cell(col_w[1], 7, str(int(row["Total_Pedidos"])), 0, 0, "C", True)

        # % SLA colorido
        pdf.set_text_color(*cor_pct)
        pdf.set_font("Arial", "B", 8.5)
        pdf.cell(col_w[2], 7, f"{pct:.1f}%", 0, 0, "C", True)

        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "", 8.5)
        pdf.cell(col_w[3], 7, f"{prazo_med:.1f}d", 0, 0, "C", True)
        pdf.cell(col_w[4], 7, limpar_texto(f"+/- {prazo_std:.1f}d"), 0, 0, "C", True)

        # Celula Prioridade colorida
        x_p, y_p = pdf.get_x(), pdf.get_y()
        pdf.set_fill_color(*zebra)
        pdf.cell(col_w[5], 7, "", 0, 0, "C", True)
        pdf.set_xy(x_p, y_p)
        pdf.set_font("Arial", "B", 7.5)
        pdf.set_text_color(*cor_p)
        pdf.cell(col_w[5], 7, limpar_texto(prioridade), 0, 1, "C", False)
        pdf.set_text_color(*_C)
        pdf.set_font("Arial", "", 8.5)

    # Compliance por regiao (compacto, mesma pagina)
    comp_reg = sla_result.compliance_por_regiao
    if not comp_reg.empty:
        pdf.ln(5)
        pdf.subtitulo("Compliance por Região")
        col_r = [60, 35, 35, 50]
        pdf.tabela_header(
            col_r,
            ["Região", "Total Pedidos", "Dentro SLA", "Compliance %"],
            ["L", "C", "C", "C"],
        )
        for i, (_, row) in enumerate(comp_reg.iterrows()):
            pct    = float(row.get("Pct_Compliance", 0))
            total  = int(row.get("Total", 0))
            dentro = int(row.get("Dentro_SLA", 0))
            if pct >= 80:
                sit, cor_s = "OK",      (0, 120, 0)
            elif pct >= 50:
                sit, cor_s = "ATENÇÃO", (160, 100, 0)
            else:
                sit, cor_s = "CRÍTICO", (180, 0, 0)
            zebra = (246, 249, 253) if i % 2 == 0 else (255, 255, 255)
            pdf.set_fill_color(*zebra)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "", 8.5)
            pdf.cell(col_r[0], 7, limpar_texto(str(row.get("Regiao", ""))), 0, 0, "L", True)
            pdf.cell(col_r[1], 7, str(total),  0, 0, "C", True)
            pdf.cell(col_r[2], 7, str(dentro), 0, 0, "C", True)
            x_s, y_s = pdf.get_x(), pdf.get_y()
            pdf.set_fill_color(*zebra)
            pdf.cell(col_r[3], 7, "", 0, 0, "C", True)
            pdf.set_xy(x_s, y_s)
            pdf.set_font("Arial", "B", 8.5)
            pdf.set_text_color(*cor_s)
            pdf.cell(col_r[3], 7, limpar_texto(f"{pct:.1f}%  [{sit}]"), 0, 1, "C", False)
            pdf.set_text_color(*_C)
            pdf.set_font("Arial", "", 8.5)
