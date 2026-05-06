"""MAX Logistics Intelligence Platform — Entry point.

Interface tkinter unificada: seleção de arquivos, configuração do estudo,
seleção de transportadora foco e geração de relatório em uma única janela.
"""

import sys
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import List, Optional

from config.settings import SLA_TARGETS
from exporters.chart_builder import criar_graficos
from exporters.pdf_builder import gerar_relatorio_final
from exporters.temp_manager import limpar_temporarios
from services.competitive_analyzer import analisar_competitividade
from services.data_processor import (
    calcular_derivados,
    carregar_e_processar,
    detectar_periodo,
)
from services.financial_analyzer import calcular_health_score, calcular_kpis_financeiros
from services.migration_analyzer import analisar_migracao
from services.regional_strategy import analisar_estrategia_regional
from services.sla_analyzer import analisar_sla
from utils.logger import get_logger

logger = get_logger(__name__)

_COR_VERDE     = "#006400"
_COR_AZUL      = "#1E3A5F"
_COR_CINZA_BG  = "#F4F6F8"
_COR_TEXTO     = "#4A4A4A"
_FONT_TITULO   = ("Arial", 13, "bold")
_FONT_SECAO    = ("Arial", 9, "bold")
_FONT_NORMAL   = ("Arial", 9)
_FONT_PEQUENA  = ("Arial", 7)

_TERMOS_BLOQUEADOS = {"NAN", "0", "NONE", "", "N/A", "NULL"}


class MainApp:
    """Janela principal única da plataforma MAX Logistics."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("MAX Logistics Intelligence Platform")
        self.root.geometry("660x720")
        self.root.resizable(False, False)
        self.root.configure(bg=_COR_CINZA_BG)

        # Estado interno
        self._dados: Optional[tuple] = None
        self._transportadoras: List[str] = []

        # Variáveis de formulário
        self.var_arq_sim   = tk.StringVar()
        self.var_arq_hist  = tk.StringVar()
        self.var_cliente   = tk.StringVar(value="Moveis Carraro")
        self.var_periodo   = tk.StringVar()
        self.var_usar_sla   = tk.BooleanVar(value=True)
        self.var_usar_reg   = tk.BooleanVar(value=True)
        self.var_usar_comp  = tk.BooleanVar(value=True)

        self._construir()

    # ── Construção da interface ────────────────────────────────────────────────

    def _construir(self) -> None:
        """Monta todos os widgets da janela."""
        self._header()

        scroll_canvas = tk.Canvas(self.root, bg=_COR_CINZA_BG, highlightthickness=0)
        vsb = tk.Scrollbar(self.root, orient="vertical", command=scroll_canvas.yview)
        scroll_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        scroll_canvas.pack(side="left", fill="both", expand=True)

        self._content = tk.Frame(scroll_canvas, bg=_COR_CINZA_BG)
        self._cw = scroll_canvas.create_window((0, 0), window=self._content, anchor="nw")

        self._content.bind("<Configure>",
                           lambda e: scroll_canvas.configure(
                               scrollregion=scroll_canvas.bbox("all")))
        scroll_canvas.bind("<Configure>",
                           lambda e: scroll_canvas.itemconfig(self._cw, width=e.width))

        pad = {"padx": 14, "pady": (0, 10)}
        self._secao_arquivos(**pad)
        self._secao_identificacao(**pad)
        self._secao_modulos(**pad)
        self._secao_foco(**pad)
        self._secao_gerar(**pad)

    def _header(self) -> None:
        frm = tk.Frame(self.root, bg=_COR_VERDE, height=52)
        frm.pack(fill="x")
        frm.pack_propagate(False)
        tk.Label(frm, text="Intelipost | MAX",
                 font=_FONT_TITULO, fg="white", bg=_COR_VERDE).pack(
            side="left", padx=16, pady=4)
        tk.Label(frm, text="Análise de Competitividade",
                 font=_FONT_NORMAL, fg="#AADDAA", bg=_COR_VERDE).pack(
            side="left", padx=0, pady=6, anchor="s")

    def _label_frame(self, titulo: str) -> tk.LabelFrame:
        return tk.LabelFrame(
            self._content, text=titulo,
            font=_FONT_SECAO, bg=_COR_CINZA_BG,
            fg=_COR_AZUL, padx=10, pady=8,
        )

    # ── Seção 1: Arquivos ──────────────────────────────────────────────────────

    def _secao_arquivos(self, **pack_kw) -> None:
        frm = self._label_frame("1.  Arquivos de Entrada")
        frm.pack(fill="x", **pack_kw)

        self._linha_arquivo(frm, 0, "Recotação (Simulado):", self.var_arq_sim,
                            self._sel_sim)
        self._linha_arquivo(frm, 1, "Cenário Atual (Histórico):", self.var_arq_hist,
                            self._sel_hist)

        tk.Button(
            frm, text="Carregar Dados",
            command=self._carregar_dados,
            bg=_COR_AZUL, fg="white", font=_FONT_SECAO,
            padx=14, pady=5, cursor="hand2",
        ).grid(row=2, column=0, columnspan=3, pady=(10, 2))

    def _linha_arquivo(self, parent: tk.Frame, row: int, label: str,
                       var: tk.StringVar, cmd) -> None:
        tk.Label(parent, text=label, bg=_COR_CINZA_BG,
                 font=_FONT_NORMAL, width=24, anchor="w").grid(
            row=row, column=0, sticky="w", pady=3)
        ent = tk.Entry(parent, textvariable=var, width=38, state="readonly",
                       readonlybackground="white", fg=_COR_TEXTO)
        ent.grid(row=row, column=1, sticky="w", padx=4)
        tk.Button(parent, text="Selecionar", command=cmd,
                  font=_FONT_PEQUENA, padx=6, pady=2).grid(
            row=row, column=2, padx=(0, 4))

    def _sel_sim(self) -> None:
        path = filedialog.askopenfilename(
            title="Recotação (Simulado)",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv")])
        if path:
            self.var_arq_sim.set(path)

    def _sel_hist(self) -> None:
        path = filedialog.askopenfilename(
            title="Cenário Atual (Histórico)",
            filetypes=[("Excel/CSV", "*.xlsx *.xls *.csv")])
        if path:
            self.var_arq_hist.set(path)

    # ── Seção 2: Identificação ─────────────────────────────────────────────────

    def _secao_identificacao(self, **pack_kw) -> None:
        frm = self._label_frame("2.  Identificação do Estudo")
        frm.pack(fill="x", **pack_kw)

        tk.Label(frm, text="Nome do Cliente:", bg=_COR_CINZA_BG,
                 font=_FONT_NORMAL, width=22, anchor="w").grid(
            row=0, column=0, sticky="w", pady=3)
        tk.Entry(frm, textvariable=self.var_cliente, width=34,
                 fg=_COR_TEXTO).grid(row=0, column=1, sticky="w", padx=4)

        tk.Label(frm, text="Período de Referência:", bg=_COR_CINZA_BG,
                 font=_FONT_NORMAL, width=22, anchor="w").grid(
            row=1, column=0, sticky="w", pady=3)
        tk.Entry(frm, textvariable=self.var_periodo, width=34,
                 fg=_COR_TEXTO).grid(row=1, column=1, sticky="w", padx=4)
        tk.Label(frm, text="detectado automaticamente ao carregar os dados",
                 font=_FONT_PEQUENA, fg="#999999", bg=_COR_CINZA_BG).grid(
            row=1, column=2, sticky="w", padx=4)

    # ── Seção 3: Módulos ───────────────────────────────────────────────────────

    def _secao_modulos(self, **pack_kw) -> None:
        frm = self._label_frame("3.  Módulos de Análise")
        frm.pack(fill="x", **pack_kw)

        modulos = [
            ("Estratégia Regional e Malha Logística", self.var_usar_reg),
            ("Competitividade Avançada e Target Price", self.var_usar_comp),
        ]
        for i, (txt, var) in enumerate(modulos):
            tk.Checkbutton(frm, text=txt, variable=var,
                           bg=_COR_CINZA_BG, font=_FONT_NORMAL,
                           fg=_COR_TEXTO, selectcolor="white",
                           activebackground=_COR_CINZA_BG).grid(
                row=i, column=0, sticky="w", pady=2)

    # ── Seção 4: Transportadora Foco ──────────────────────────────────────────

    def _secao_foco(self, **pack_kw) -> None:
        frm = self._label_frame("4.  Transportadora Foco")
        frm.pack(fill="x", **pack_kw)

        tk.Label(
            frm,
            text="Selecione a transportadora para análise competitiva detalhada.\n"
                 "O relatório dedicará uma seção completa a ela vs o benchmark de mercado.",
            bg=_COR_CINZA_BG, font=_FONT_PEQUENA, fg="#666666", justify="left",
        ).pack(anchor="w", pady=(0, 6))

        list_frame = tk.Frame(frm, bg=_COR_CINZA_BG)
        list_frame.pack(fill="x")

        vsb = tk.Scrollbar(list_frame, orient="vertical")
        self.lb_foco = tk.Listbox(
            list_frame, height=6,
            selectmode="single",
            yscrollcommand=vsb.set,
            font=_FONT_NORMAL,
            selectbackground=_COR_VERDE, selectforeground="white",
            activestyle="none", bg="white", fg=_COR_TEXTO,
            relief="solid", bd=1,
        )
        vsb.config(command=self.lb_foco.yview)
        self.lb_foco.pack(side="left", fill="x", expand=True)
        vsb.pack(side="right", fill="y")

        self.lbl_foco_hint = tk.Label(
            frm,
            text="Carregue os dados (seção 1) para ver as transportadoras disponíveis.",
            bg=_COR_CINZA_BG, font=_FONT_PEQUENA, fg="#AAAAAA",
        )
        self.lbl_foco_hint.pack(anchor="w", pady=(4, 0))

    # ── Seção 5: Status + Gerar ────────────────────────────────────────────────

    def _secao_gerar(self, **pack_kw) -> None:
        frm = tk.Frame(self._content, bg=_COR_CINZA_BG)
        frm.pack(fill="x", **pack_kw)

        self.lbl_status = tk.Label(
            frm,
            text="Aguardando carregamento dos arquivos...",
            bg=_COR_CINZA_BG, font=_FONT_PEQUENA, fg="#888888", anchor="w",
        )
        self.lbl_status.pack(fill="x", pady=(0, 6))

        self.btn_gerar = tk.Button(
            frm, text="Gerar Relatório PDF",
            command=self._gerar_relatorio,
            bg="#AAAAAA", fg="white", font=("Arial", 12, "bold"),
            pady=10, state="disabled", cursor="arrow",
        )
        self.btn_gerar.pack(fill="x")

    # ── Lógica: Carregar Dados ─────────────────────────────────────────────────

    def _carregar_dados(self) -> None:
        arq_sim  = self.var_arq_sim.get().strip()
        arq_hist = self.var_arq_hist.get().strip()

        if not arq_sim or not arq_hist:
            messagebox.showwarning(
                "Aviso", "Selecione os dois arquivos antes de carregar.",
                parent=self.root)
            return

        self._set_status("Carregando e processando dados... aguarde.")
        self.root.update()

        # Recotação crua: expande todas as transportadoras T1-T5 do BID
        resultado = carregar_e_processar(arq_sim, arq_hist)

        if resultado is None:
            messagebox.showerror(
                "Erro de Leitura",
                "Falha ao processar os arquivos.\n"
                "Verifique se os arquivos são válidos e tente novamente.",
                parent=self.root)
            self._set_status("Erro no carregamento.")
            return

        self._dados = resultado
        df = resultado[0]

        # Período automático (se ainda não preenchido)
        if not self.var_periodo.get():
            periodo = detectar_periodo(arq_sim)
            self.var_periodo.set(periodo or datetime.now().strftime("%B %Y"))

        # Popular lista de transportadoras
        transportadoras = sorted([
            str(t) for t in df["Transp_Nova"].unique().tolist()
            if str(t).upper() not in _TERMOS_BLOQUEADOS
        ])
        self._transportadoras = transportadoras

        self.lb_foco.delete(0, "end")
        for t in transportadoras:
            self.lb_foco.insert("end", t)

        n_tr = len(transportadoras)
        # df tem uma linha por (pedido × transportadora) — conta pedidos únicos pela chave de rota
        chave_cols = [c for c in ["CEP_Origem", "CEP_Destino", "Peso"] if c in df.columns]
        n_ped = df.drop_duplicates(subset=chave_cols).shape[0] if chave_cols else len(df)
        n_cot = len(df)
        status = (
            f"Dados carregados: {n_ped:,} pedidos | {n_cot:,} cotacoes | "
            f"{n_tr} transportadoras disponíveis."
        ).replace(",", ".")

        self.lbl_foco_hint.config(
            text=f"{n_tr} transportadora(s) disponível(is). Clique para selecionar a foco.",
            fg=_COR_AZUL,
        )
        self._set_status(status)
        self.btn_gerar.config(state="normal", bg=_COR_VERDE, cursor="hand2")
        logger.info("Dados carregados: %d pedidos, %d transportadoras", n_ped, n_tr)

    # ── Lógica: Gerar Relatório ────────────────────────────────────────────────

    def _gerar_relatorio(self) -> None:
        nome_cliente = self.var_cliente.get().strip()
        if not nome_cliente:
            messagebox.showwarning("Aviso", "Informe o nome do cliente.", parent=self.root)
            return

        # Bloqueio do default: força confirmação se o nome não foi alterado.
        # Evita relatório com cliente errado na capa por esquecimento de troca.
        if nome_cliente.upper() == "MOVEIS CARRARO":
            confirmar_default = messagebox.askyesno(
                "Confirmar nome do cliente",
                "O nome do cliente está como 'Moveis Carraro' (valor padrão).\n\n"
                "Esse nome aparecerá na capa e no cabeçalho do relatório.\n\n"
                "Deseja realmente gerar o relatório para 'Moveis Carraro'?",
                parent=self.root,
            )
            if not confirmar_default:
                return

        if self._dados is None:
            messagebox.showwarning("Aviso", "Carregue os dados primeiro.", parent=self.root)
            return

        # Transportadoras selecionadas no listbox
        indices = self.lb_foco.curselection()
        transp_foco = [self._transportadoras[i] for i in indices] if indices else []

        if not transp_foco:
            confirmar = messagebox.askyesno(
                "Sem Transportadora Foco",
                "Nenhuma transportadora foco selecionada.\n\n"
                "O relatório será gerado sem a seção de análise competitiva detalhada.\n\n"
                "Deseja continuar mesmo assim?",
                parent=self.root,
            )
            if not confirmar:
                return

        # Salvar PDF
        nome_arquivo = (
            f"Relatorio_MAX_{nome_cliente.replace(' ', '_')}"
            f"_{datetime.now().strftime('%Y%m%d')}.pdf"
        )
        save_path = filedialog.asksaveasfilename(
            title="Salvar Relatório PDF",
            defaultextension=".pdf",
            initialfile=nome_arquivo,
            filetypes=[("Arquivos PDF", "*.pdf")],
            parent=self.root,
        )
        if not save_path:
            return

        # Desempacota os dados completos (todas as carriers)
        (df_full, r_transp_full, r_saving_full, r_matriz_full,
         a_peso_full, a_uf_full, a_cep_vol_full, a_cep_sav_full,
         a_cep_perda_full, resumo_migracao_full) = self._dados

        # df         → 1 linha por pedido (T1 de cada ordem) — SLA, Visão Geral, PDF
        # df_mercado → todas as carriers (T1-T5) — análise de competitividade
        # df_foco_raw → linhas da carrier selecionada no df completo (painel foco)
        df_mercado = df_full
        chave_cols = [c for c in ["CEP_Origem", "CEP_Destino", "Peso"]
                      if c in df_full.columns]
        # Mantém apenas o registro mais barato por pedido (= T1 do BID)
        idx_t1 = (
            df_full[df_full["Custo_Novo"] > 0]
            .groupby(chave_cols)["Custo_Novo"]
            .idxmin()
        )
        df_t1 = df_full.loc[idx_t1].copy()
        resultado_t1 = calcular_derivados(df_t1)
        (df, r_transp, r_saving, r_matriz,
         a_peso, a_uf, a_cep_vol, a_cep_sav, a_cep_perda,
         resumo_migracao) = resultado_t1
        logger.info(
            "T1 do BID: %d pedidos únicos (de %d cotações) | %d carriers no T1.",
            len(df_t1), len(df_full), df_t1["Transp_Nova"].nunique(),
        )
        # Extrai linhas da carrier foco do df completo para o painel dedicado
        df_foco_raw = (
            df_full[df_full["Transp_Nova"].str.strip() == transp_foco[0]].copy()
            if transp_foco else None
        )

        imgs: dict = {}
        try:
            # ── Migração ──────────────────────────────────────────────────────
            self._set_status("Analisando migração de transportadoras...")
            migration_result = analisar_migracao(df, r_saving, r_transp)

            # ── SLA ───────────────────────────────────────────────────────────
            sla_result = None
            if self.var_usar_sla.get():
                self._set_status("Calculando SLA e risco de atraso...")
                sla_result = analisar_sla(df, SLA_TARGETS)

            # ── Regional ──────────────────────────────────────────────────────
            regional_result = None
            if self.var_usar_reg.get():
                self._set_status("Analisando estratégia regional...")
                sla_comp = sla_result.compliance_por_transp if sla_result else None
                regional_result = analisar_estrategia_regional(df, sla_comp, SLA_TARGETS)

            # ── Competitividade & Perfil BID ──────────────────────────────────
            # df_mercado contém todas as carriers — benchmark completo
            self._set_status("Calculando perfil BID e competitividade...")
            competitive_result = analisar_competitividade(
                df_mercado, transp_foco if transp_foco else None
            )

            # ── Gap para Liderar no BID ───────────────────────────────────────
            gap_bid_result = None
            if transp_foco:
                from services.competitive_analyzer import analisar_gap_bid, perfil_bid_de_gap_result
                self._set_status("Calculando gap para liderar no BID...")
                gap_bid_result = analisar_gap_bid(
                    self.var_arq_sim.get().strip(), transp_foco[0]
                )
                # Override do perfil BID: usa posição T1 como vitória real,
                # não a comparação vs contrato histórico (Custo_Antigo)
                if gap_bid_result and competitive_result:
                    competitive_result.perfil_bid = perfil_bid_de_gap_result(gap_bid_result)

            # ── Health Score ──────────────────────────────────────────────────
            self._set_status("Calculando Health Score...")
            kpis = calcular_kpis_financeiros(df, r_saving)
            health_score, health_class = calcular_health_score(
                kpis["saving_pct"],
                kpis["pct_ganho_total"],
                kpis["pct_regioes_saving"],
            )

            # ── Gráficos ──────────────────────────────────────────────────────
            # df (= T1 por pedido em modo cru) garante consistência com métricas
            # do PDF. df_mercado (todas as carriers) é repassado só para
            # _grafico_pricing, que precisa do benchmark completo.
            self._set_status("Gerando gráficos...")
            imgs = criar_graficos(
                df, r_transp, r_saving, r_matriz,
                a_peso, a_uf, a_cep_vol, a_cep_sav, a_cep_perda,
                resumo_migracao,
                sla_result=sla_result,
                regional_result=regional_result,
                transp_foco=transp_foco,
                df_mercado=df_mercado,
            )

            # ── PDF ───────────────────────────────────────────────────────────
            self._set_status("Montando PDF...")
            gerar_relatorio_final(
                df=df,
                r_transp=r_transp,
                resumo_saving=r_saving,
                resumo_matriz=r_matriz,
                imagens=imgs,
                save_path=save_path,
                transp_foco=transp_foco,
                nome_cliente=nome_cliente,
                periodo_referencia=self.var_periodo.get().strip(),
                health_score=health_score,
                health_classificacao=health_class,
                sla_result=sla_result,
                regional_result=regional_result,
                migration_result=migration_result,
                kpis=kpis,
                competitive_result=competitive_result,
                gap_bid_result=gap_bid_result,
                df_foco=df_foco_raw,
            )
            limpar_temporarios(imgs)

            self._set_status(
                f"PDF gerado com sucesso!  Health Score: {health_score:.0f}/100 ({health_class})")
            logger.info("Relatório gerado: %s | Health Score: %.0f", save_path, health_score)

            messagebox.showinfo(
                "Relatório Gerado",
                f"PDF gerado com sucesso!\n\n"
                f"Health Score : {health_score:.0f}/100 ({health_class})\n\n"
                f"Arquivo: {save_path}",
                parent=self.root,
            )

        except Exception as exc:
            limpar_temporarios(imgs)
            logger.exception("Erro ao gerar relatório: %s", exc)
            messagebox.showerror(
                "Erro", f"Falha ao gerar o relatório:\n{exc}", parent=self.root)
            self._set_status("Erro ao gerar o relatório.")

    # ── Utilitários ────────────────────────────────────────────────────────────

    def _set_status(self, msg: str) -> None:
        self.lbl_status.config(text=msg)
        self.root.update_idletasks()

    def run(self) -> None:
        self.root.mainloop()


# ── Entry Point ───────────────────────────────────────────────────────────────

def main() -> None:
    """Ponto de entrada principal da aplicação."""
    app = MainApp()
    app.run()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.exception("Erro crítico na aplicação: %s", exc)
        messagebox.showerror("Erro Crítico", f"Erro inesperado:\n{exc}")
        sys.exit(1)
