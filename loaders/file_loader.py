"""Leitura de arquivos CSV e Excel com tratamento robusto de erros.

Suporta múltiplos encodings e delimitadores para CSV, e leitura direta
de arquivos Excel (.xlsx/.xls).
"""

import logging
from pathlib import Path

import pandas as pd

from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)


def carregar_arquivo(caminho: str) -> pd.DataFrame:
    """Carrega um arquivo CSV ou Excel em um DataFrame pandas.

    Tenta múltiplos encodings para CSV (latin-1, utf-8, cp1252) e
    usa detecção automática de separador via engine='python'.

    Args:
        caminho: Caminho absoluto ou relativo para o arquivo.

    Returns:
        DataFrame com os dados brutos do arquivo.

    Raises:
        FileNotFoundError: Se o arquivo não existir no caminho informado.
        ValueError: Se o formato do arquivo não for suportado.
        RuntimeError: Se todas as tentativas de leitura falharem.
    """
    path = Path(caminho)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {caminho}")

    sufixo = path.suffix.lower()
    logger.info("Carregando arquivo: %s", path.name)

    if sufixo in (".xlsx", ".xls"):
        return _ler_excel(caminho)
    if sufixo == ".csv":
        return _ler_csv(caminho)

    raise ValueError(
        f"Formato '{sufixo}' não suportado. Use .xlsx, .xls ou .csv."
    )


def _ler_excel(caminho: str) -> pd.DataFrame:
    """Lê arquivo Excel (.xlsx ou .xls).

    Args:
        caminho: Caminho para o arquivo Excel.

    Returns:
        DataFrame com os dados lidos.

    Raises:
        RuntimeError: Se a leitura falhar.
    """
    try:
        df = pd.read_excel(caminho)
        logger.debug("Excel lido com sucesso: %d linhas, %d colunas", *df.shape)
        return df
    except Exception as exc:
        raise RuntimeError(f"Falha ao ler Excel '{caminho}': {exc}") from exc


def _ler_csv(caminho: str) -> pd.DataFrame:
    """Lê arquivo CSV tentando múltiplos encodings e separadores.

    Ordem de tentativa: latin-1, utf-8, cp1252. Em todas as tentativas
    usa sep=None com engine='python' para detecção automática de separador.

    Args:
        caminho: Caminho para o arquivo CSV.

    Returns:
        DataFrame com os dados lidos.

    Raises:
        RuntimeError: Se todas as tentativas de leitura falharem.
    """
    encodings = ["latin-1", "utf-8", "cp1252"]
    last_exc: Exception = Exception("Erro desconhecido")

    for encoding in encodings:
        try:
            df = pd.read_csv(
                caminho,
                encoding=encoding,
                sep=None,
                engine="python",
                on_bad_lines="skip",
            )
            logger.debug(
                "CSV lido com encoding '%s': %d linhas, %d colunas",
                encoding, *df.shape,
            )
            return df
        except Exception as exc:
            logger.debug("Falha com encoding '%s': %s", encoding, exc)
            last_exc = exc

    raise RuntimeError(
        f"Não foi possível ler o CSV '{caminho}' com nenhum encoding tentado. "
        f"Último erro: {last_exc}"
    ) from last_exc
