"""Validação de qualidade e integridade dos DataFrames carregados.

Verifica presença de colunas obrigatórias, dados não-nulos e gera
relatório de qualidade com percentual de nulos por coluna.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List

import pandas as pd

from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)


@dataclass
class DataQualityReport:
    """Relatório de qualidade de um DataFrame validado.

    Attributes:
        is_valid: Indica se o DataFrame passou em todas as validações.
        missing_columns: Lista de colunas obrigatórias ausentes.
        null_percentages: Dicionário coluna → percentual de nulos.
        total_rows: Número total de linhas no DataFrame.
        warnings: Lista de avisos não-críticos identificados.
    """

    is_valid: bool = True
    missing_columns: List[str] = field(default_factory=list)
    null_percentages: Dict[str, float] = field(default_factory=dict)
    total_rows: int = 0
    warnings: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [
            f"Válido: {self.is_valid}",
            f"Total de linhas: {self.total_rows}",
        ]
        if self.missing_columns:
            lines.append(f"Colunas ausentes: {', '.join(self.missing_columns)}")
        if self.null_percentages:
            lines.append("Nulos por coluna:")
            for col, pct in self.null_percentages.items():
                if pct > 0:
                    lines.append(f"  {col}: {pct:.1f}%")
        if self.warnings:
            lines.append("Avisos:")
            for w in self.warnings:
                lines.append(f"  - {w}")
        return "\n".join(lines)


def validar_dataframe(
    df: pd.DataFrame,
    colunas_obrigatorias: List[str],
    nome_arquivo: str = "arquivo",
) -> DataQualityReport:
    """Valida um DataFrame contra as colunas obrigatórias esperadas.

    Realiza as seguintes verificações:
    1. DataFrame não está vazio.
    2. Todas as colunas obrigatórias estão presentes (após renomeação prévia).
    3. Gera relatório de nulos por coluna.

    Args:
        df: DataFrame a ser validado.
        colunas_obrigatorias: Lista de nomes de colunas que devem existir.
        nome_arquivo: Nome descritivo do arquivo, usado em mensagens de erro.

    Returns:
        DataQualityReport com resultado completo da validação.

    Raises:
        ValueError: Se o DataFrame estiver vazio ou tiver colunas obrigatórias ausentes.
    """
    report = DataQualityReport(total_rows=len(df))

    # Validação 1: DataFrame não vazio
    if df.empty:
        report.is_valid = False
        msg = f"O arquivo '{nome_arquivo}' está vazio após leitura."
        logger.error(msg)
        raise ValueError(msg)

    # Validação 2: Colunas obrigatórias presentes
    colunas_df = set(df.columns.tolist())
    ausentes = [col for col in colunas_obrigatorias if col not in colunas_df]

    if ausentes:
        report.is_valid = False
        report.missing_columns = ausentes
        msg = (
            f"Arquivo '{nome_arquivo}' está com colunas obrigatórias ausentes: "
            f"{ausentes}. Colunas encontradas: {sorted(colunas_df)}"
        )
        logger.error(msg)
        raise ValueError(msg)

    # Validação 3: Relatório de nulos
    for col in df.columns:
        pct_nulo = df[col].isna().mean() * 100
        if pct_nulo > 0:
            report.null_percentages[col] = round(pct_nulo, 2)

    # Avisos sobre colunas com alta taxa de nulos
    for col, pct in report.null_percentages.items():
        if pct > 50:
            report.warnings.append(
                f"Coluna '{col}' tem {pct:.1f}% de valores nulos — verifique os dados."
            )

    logger.info(
        "Validação concluída para '%s': %d linhas, %d colunas ausentes, %d avisos",
        nome_arquivo,
        report.total_rows,
        len(report.missing_columns),
        len(report.warnings),
    )

    return report


def inferir_colunas_presentes(
    df: pd.DataFrame,
    mapa_colunas: Dict[str, str],
) -> List[str]:
    """Retorna as colunas do mapa que efetivamente existem no DataFrame.

    Útil para validar quais colunas do mapeamento de renomeação foram
    encontradas antes de aplicar o rename.

    Args:
        df: DataFrame a verificar.
        mapa_colunas: Dicionário {nome_original: nome_destino}.

    Returns:
        Lista dos nomes originais presentes no DataFrame.
    """
    return [col for col in mapa_colunas if col in df.columns]
