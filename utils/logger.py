"""Configuração de logging estruturado para o projeto MAX.

Fornece um factory function para obter loggers pré-configurados com
formatação padronizada, saída para console e arquivo rotativo.
"""

import logging
import logging.handlers
from pathlib import Path


def get_logger(name: str, log_dir: str = "logs") -> logging.Logger:
    """Retorna um logger configurado com handlers de console e arquivo.

    Args:
        name: Nome do módulo/componente que está logando.
        log_dir: Diretório onde o arquivo de log será salvo.

    Returns:
        Logger configurado e pronto para uso.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Handler de console (INFO+)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # Handler de arquivo rotativo (DEBUG+)
    try:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / "max_logistics.log",
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        # Em ambientes sem permissão de escrita, usa só o console
        pass

    return logger
