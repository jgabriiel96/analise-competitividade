"""Teste headless — geração de PDF sem UI tkinter.

Espelha o pipeline de main.py. Útil para validação rápida e CI.

Configuração via variáveis de ambiente (ou argumentos CLI):
    MAX_ARQ_SIM     — caminho do arquivo de recotação (.xlsx)
    MAX_ARQ_ORIG    — caminho do cenário atual / histórico (.xlsx)
    MAX_TRANSP_FOCO — nome exato da transportadora foco (ex.: "Correios PAC")
    MAX_CLIENTE     — nome do cliente para a capa (ex.: "Tramontina")

Uso:
    # Via env vars
    MAX_ARQ_SIM=/path/recot.xlsx MAX_ARQ_ORIG=/path/atual.xlsx \\
    MAX_TRANSP_FOCO="Correios PAC" MAX_CLIENTE=Tramontina python run_test.py

    # Via CLI
    python run_test.py --sim /path/recot.xlsx --orig /path/atual.xlsx \\
                       --foco "Correios PAC" --cliente Tramontina
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from services.data_processor import (
    carregar_e_processar,
    calcular_derivados,
    detectar_periodo,
)
from services.financial_analyzer import calcular_health_score, calcular_kpis_financeiros
from services.migration_analyzer import analisar_migracao
from services.regional_strategy import analisar_estrategia_regional
from services.sla_analyzer import analisar_sla
from services.competitive_analyzer import (
    analisar_competitividade,
    analisar_gap_bid,
    perfil_bid_de_gap_result,
)
from exporters.chart_builder import criar_graficos
from exporters.pdf_builder import gerar_relatorio_final
from exporters.temp_manager import limpar_temporarios
from utils.logger import get_logger

logger = get_logger(__name__)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="MAX — gerador de PDF headless")
    p.add_argument("--sim", default=os.environ.get("MAX_ARQ_SIM"),
                   help="Arquivo de recotação (.xlsx). Env: MAX_ARQ_SIM")
    p.add_argument("--orig", default=os.environ.get("MAX_ARQ_ORIG"),
                   help="Arquivo do cenário atual (.xlsx). Env: MAX_ARQ_ORIG")
    p.add_argument("--foco", default=os.environ.get("MAX_TRANSP_FOCO", "Correios PAC"),
                   help="Nome exato da transportadora foco. Env: MAX_TRANSP_FOCO")
    p.add_argument("--cliente", default=os.environ.get("MAX_CLIENTE", "Cliente MAX"),
                   help="Nome do cliente para a capa. Env: MAX_CLIENTE")
    args = p.parse_args()
    if not args.sim or not args.orig:
        p.error("Informe --sim e --orig (ou MAX_ARQ_SIM e MAX_ARQ_ORIG).")
    return args


_args = _parse_args()
ARQ_SIM      = _args.sim
ARQ_ORIG     = _args.orig
TRANSP_FOCO  = [_args.foco]
NOME_CLIENTE = _args.cliente

SLA_TARGETS = {
    "Sudeste": 3,
    "Sul": 4,
    "Centro-Oeste": 5,
    "Nordeste": 7,
    "Norte": 8,
}

_slug = "".join(c if c.isalnum() else "_" for c in f"{NOME_CLIENTE}_{TRANSP_FOCO[0]}")
OUTPUT_PDF = str(
    Path(__file__).parent
    / f"Relatorio_MAX_{_slug}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
)


def main() -> None:
    print("=" * 60)
    print(f"  MAX — Teste Headless | {NOME_CLIENTE} / {TRANSP_FOCO[0]}")
    print("=" * 60)
    print(f"  Simulação : {Path(ARQ_SIM).name}")
    print(f"  Histórico : {Path(ARQ_ORIG).name}")
    print(f"  Cliente   : {NOME_CLIENTE}")
    print(f"  Foco      : {TRANSP_FOCO}")
    print("=" * 60)

    # 1. Carga
    print("\n[1/7] Carregando dados...")
    resultado = carregar_e_processar(ARQ_SIM, ARQ_ORIG)
    if resultado is None:
        print("ERRO: falha no processamento.")
        sys.exit(1)
    (df_full, _r_transp_full, _r_saving_full, _r_matriz_full,
     _a_peso_full, _a_uf_full, _a_cep_vol_full, _a_cep_sav_full,
     _a_cep_perda_full, _resumo_migracao_full) = resultado
    print(f"     {len(df_full):,} cotações | {df_full['Transp_Nova'].nunique()} carriers".replace(",", "."))

    periodo = detectar_periodo(ARQ_SIM) or datetime.now().strftime("%B %Y")

    # 2. Filtra T1 por pedido (replica main.py:417-426)
    print("\n[2/7] Filtrando T1 por pedido...")
    chave_cols = [c for c in ["CEP_Origem", "CEP_Destino", "Peso"] if c in df_full.columns]
    idx_t1 = (
        df_full[df_full["Custo_Novo"] > 0]
        .groupby(chave_cols)["Custo_Novo"]
        .idxmin()
    )
    df_t1 = df_full.loc[idx_t1].copy()
    resultado_t1 = calcular_derivados(df_t1)
    (df, r_transp, r_saving, r_matriz,
     a_peso, a_uf, a_cep_vol, a_cep_sav, a_cep_perda, resumo_migracao) = resultado_t1
    print(f"     {len(df):,} pedidos T1 | Saving total: R$ {r_saving.get('Saving_Valor', 0):,.2f}".replace(",", "."))

    # df_foco_raw — todas as linhas da foco no df completo
    df_foco_raw = df_full[
        df_full["Transp_Nova"].str.strip() == TRANSP_FOCO[0]
    ].copy()
    print(f"     df_foco_raw: {len(df_foco_raw):,} linhas (cotações de {TRANSP_FOCO[0]})".replace(",", "."))

    # 3. Migração + SLA + Regional
    print("\n[3/7] Migração / SLA / Regional...")
    migration_result = analisar_migracao(df, r_saving, r_transp)
    sla_result       = analisar_sla(df, SLA_TARGETS)
    regional_result  = analisar_estrategia_regional(
        df, sla_result.compliance_por_transp, SLA_TARGETS
    )
    print(f"     Migrados: {len(migration_result.df_migrados)} | "
          f"SLA global: {sla_result.compliance_global_pct:.1f}% | "
          f"Cobertura regional: {regional_result.cobertura_pct:.0f}%")

    # 4. Competitividade (sobre df_full)
    print("\n[4/7] Competitividade...")
    competitive_result = analisar_competitividade(df_full, TRANSP_FOCO)

    # 5. Gap BID
    print("\n[5/7] Gap para Liderar no BID...")
    gap_bid_result = analisar_gap_bid(ARQ_SIM, TRANSP_FOCO[0])
    if gap_bid_result and competitive_result:
        competitive_result.perfil_bid = perfil_bid_de_gap_result(gap_bid_result)
        print(f"     Cotados: {gap_bid_result.total_pedidos} | "
              f"Vitórias T1: {gap_bid_result.pedidos_lider} ({gap_bid_result.pct_lider:.1f}%)")

    # 6. KPIs + Health
    print("\n[6/7] Health Score...")
    kpis = calcular_kpis_financeiros(df, r_saving)
    health_score, health_class = calcular_health_score(
        kpis["saving_pct"], kpis["pct_ganho_total"], kpis["pct_regioes_saving"],
    )
    print(f"     Health Score: {health_score:.0f}/100 ({health_class})")

    # 7. Gráficos + PDF
    print("\n[7/7] Gerando gráficos e PDF...")
    imgs = criar_graficos(
        df, r_transp, r_saving, r_matriz, a_peso, a_uf,
        a_cep_vol, a_cep_sav, a_cep_perda, resumo_migracao,
        sla_result=sla_result,
        regional_result=regional_result,
        transp_foco=TRANSP_FOCO,
        df_mercado=df_full,
    )

    gerar_relatorio_final(
        df=df,
        r_transp=r_transp,
        resumo_saving=r_saving,
        resumo_matriz=r_matriz,
        imagens=imgs,
        save_path=OUTPUT_PDF,
        transp_foco=TRANSP_FOCO,
        nome_cliente=NOME_CLIENTE,
        periodo_referencia=periodo,
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

    print("\n" + "=" * 60)
    print(f"  PDF gerado: {OUTPUT_PDF}")
    print("=" * 60)
    os.startfile(OUTPUT_PDF)


if __name__ == "__main__":
    main()
