"""Gerenciamento de arquivos temporários gerados durante a criação de gráficos.

Centraliza criação de nomes de arquivos temp e limpeza segura após uso.
"""

import logging
import os
from pathlib import Path
from typing import Dict

from utils.logger import get_logger

logger: logging.Logger = get_logger(__name__)


def get_temp_path(nome: str, diretorio: str = ".") -> str:
    """Retorna o caminho completo para um arquivo temporário.

    Args:
        nome: Nome base do arquivo (sem extensão).
        diretorio: Diretório onde o arquivo será criado.

    Returns:
        Caminho absoluto para o arquivo temporário .png.
    """
    Path(diretorio).mkdir(parents=True, exist_ok=True)
    return str(Path(diretorio) / f"temp_{nome}.png")


def limpar_temporarios(imagens: Dict[str, str]) -> None:
    """Remove todos os arquivos temporários após geração do PDF.

    Args:
        imagens: Dicionário {chave: caminho_arquivo} com os arquivos a remover.
    """
    removidos = 0
    erros = 0

    for chave, caminho in imagens.items():
        if os.path.exists(caminho):
            try:
                os.remove(caminho)
                removidos += 1
                logger.debug("Temporário removido: %s (%s)", chave, caminho)
            except OSError as exc:
                erros += 1
                logger.warning("Falha ao remover temporário '%s': %s", caminho, exc)

    logger.info(
        "Limpeza de temporários: %d removidos, %d erros", removidos, erros
    )
