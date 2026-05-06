"""Utilitários de manipulação de texto e conversão de valores.

Extraídos e preservados do script original teste18.py, com type hints
e docstrings adicionados.
"""


def limpar_texto(texto: object) -> str:
    """Sanitiza texto para compatibilidade com encoding latin-1 do FPDF.

    Substitui caracteres especiais problemáticos e tenta re-codificar
    o resultado em latin-1 para garantir compatibilidade com a biblioteca PDF.

    Args:
        texto: Valor a ser convertido e sanitizado (qualquer tipo).

    Returns:
        String sanitizada, compatível com latin-1.
    """
    if not isinstance(texto, str):
        texto = str(texto)

    substituicoes: dict = {
        "\u2022": "-",    # bullet •
        "\u2023": "-",    # triangular bullet
        "\u2013": "-",    # en-dash –
        "\u2014": "-",    # em-dash —
        "\u2015": "-",    # horizontal bar ―
        "\u201c": '"',    # aspas "
        "\u201d": '"',    # aspas "
        "\u2018": "'",    # aspas simples '
        "\u2019": "'",    # apóstrofo '
        "\u2026": "...",  # reticências …
        "\u00a0": " ",    # espaço não-quebrável
        "\u00b7": ".",    # middle dot ·
        "\u00ae": "(R)",  # registered ®
        "\u00a9": "(C)",  # copyright ©
    }
    for orig, dest in substituicoes.items():
        texto = texto.replace(orig, dest)

    try:
        # "ignore" evita artefatos "?" — caracteres sem suporte são silenciosamente removidos
        return texto.encode("latin-1", "ignore").decode("latin-1")
    except Exception:
        return texto


def converter_monetario(val: object) -> float:
    """Converte valor monetário de múltiplos formatos para float.

    Suporta: float/int puros, strings com "R$", separadores BR e US,
    valores vazios/NaN/"-".

    Args:
        val: Valor a converter (int, float, str ou None).

    Returns:
        Valor numérico em float. Retorna 0.0 em caso de falha.

    Examples:
        >>> converter_monetario("R$ 1.234,56")
        1234.56
        >>> converter_monetario("-")
        0.0
        >>> converter_monetario(None)
        0.0
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)

    val_str = str(val).strip()
    if not val_str or val_str in ("-", "nan", "NaN", "None"):
        return 0.0

    val_str = val_str.replace("R$", "").replace("r$", "").strip()

    try:
        if "," in val_str and "." in val_str:
            # Formato BR: 1.234,56
            if val_str.find(".") < val_str.find(","):
                val_str = val_str.replace(".", "").replace(",", ".")
        elif "," in val_str:
            val_str = val_str.replace(",", ".")
        return float(val_str)
    except ValueError:
        return 0.0


def normalizar_nome_transp(nome: object) -> str:
    """Normaliza nome de transportadora para comparação de migração.

    Extrai apenas o primeiro token do nome, em minúsculas, para que
    variações como "JADLOG FRETE" e "jadlog" sejam tratadas como iguais.

    Args:
        nome: Nome da transportadora (qualquer tipo).

    Returns:
        Primeiro token do nome em minúsculas, ou "N/A" se inválido.

    Examples:
        >>> normalizar_nome_transp("JADLOG FRETE")
        'jadlog'
        >>> normalizar_nome_transp(None)
        'N/A'
    """
    if not isinstance(nome, str):
        return "N/A"
    return nome.split(" ")[0].strip().lower()


def formatar_monetario_br(valor: float) -> str:
    """Formata float para string monetária no padrão brasileiro.

    Args:
        valor: Valor numérico a formatar.

    Returns:
        String no formato "R$ 1.234,56".

    Examples:
        >>> formatar_monetario_br(1234.56)
        'R$ 1.234,56'
    """
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
