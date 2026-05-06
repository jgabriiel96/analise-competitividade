"""Configurações globais e thresholds operacionais do projeto MAX.

Centraliza parâmetros configuráveis: targets de SLA por região, pesos do
score de saúde, thresholds de risco e descontos de escala.
"""

from typing import Dict

# ── Targets de SLA por Região (dias úteis) ───────────────────────────────────
SLA_TARGETS: Dict[str, int] = {
    "Sudeste": 3,
    "Sul": 4,
    "Centro-Oeste": 5,
    "Nordeste": 7,
    "Norte": 8,
}

# ── Thresholds de Classificação SLA ──────────────────────────────────────────
SLA_ALERTA_MARGEM: int = 1          # dias acima do target para gerar ALERTA
SLA_COMPLIANCE_MIN_PCT: float = 80.0  # % mínimo de compliance para classificar BAIXO_RISCO

# ── Score de Saúde da Operação (pesos) ───────────────────────────────────────
HEALTH_SCORE_PESOS: Dict[str, float] = {
    "saving_pct": 0.40,
    "sla_compliance": 0.40,
    "cobertura_regional": 0.20,
}

# ── Pesos do Score de Recomendação Regional ──────────────────────────────────
# SLA removido: targets não refletem contratos reais — score baseado em saving e volume
REGIONAL_SCORE_PESOS: Dict[str, float] = {
    "saving_pct": 0.60,
    "sla_compliance_pct": 0.00,
    "volume_share": 0.40,
}

# ── Thresholds de Empate Técnico ─────────────────────────────────────────────
EMPATE_TECNICO_THRESHOLD: float = 5.0   # diferença < 5% → recomenda mix

# ── Ganho de Escala Estimado (consolidação regional) ─────────────────────────
GANHO_ESCALA_MIN: float = 0.10   # 10%
GANHO_ESCALA_MAX: float = 0.15   # 15%

# ── Target Price Calculator ───────────────────────────────────────────────────
TARGET_PRICE_DESCONTO: float = 0.03   # 3% abaixo do custo antigo para vencer

# ── Thresholds de Classificação de Risco ─────────────────────────────────────
RISCO_ALTO_THRESHOLD: float = 0.60    # índice de risco >= 0.60 → ALTO_RISCO
RISCO_MODERADO_THRESHOLD: float = 0.35  # índice de risco >= 0.35 → RISCO_MODERADO

# ── Limites de tabelas no PDF ─────────────────────────────────────────────────
PDF_MAX_ROWS_TABELA: int = 12
PDF_MAX_TRANSPORTADORAS_PIE: int = 9
PDF_MAX_TRANSPORTADORAS_HEATMAP: int = 8
PDF_MAX_TRANSPORTADORAS_PESO: int = 5

# ── DPI dos gráficos exportados ───────────────────────────────────────────────
CHART_DPI: int = 120
