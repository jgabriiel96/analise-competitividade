"""Constantes globais do projeto MAX Logistics Intelligence Platform.

Centraliza cores, mapeamentos de colunas, faixas de peso e regiões do Brasil,
extraídas e preservadas do script original teste18.py.
"""

from typing import Dict, List

# ── Paleta de Cores (RGB) ────────────────────────────────────────────────────
COR_PRIMARIA_RGB: tuple = (0, 100, 0)           # #006400 Verde principal
COR_SECUNDARIA_RGB: tuple = (50, 50, 50)        # Cinza escuro (legado)
COR_AZUL_ESCURO_RGB: tuple = (30, 58, 95)       # #1E3A5F Azul profissional
COR_TEXTO_RGB: tuple = (74, 74, 74)             # #4A4A4A Cinza texto
COR_DESTAQUE_RGB: tuple = (255, 100, 0)         # Laranja
COR_VERMELHO_RGB: tuple = (192, 0, 0)           # Vermelho alerta
COR_FUNDO_TABELA: tuple = (30, 58, 95)          # Cabeçalho tabela (azul escuro)
COR_ZEBRA_RGB: tuple = (246, 249, 253)          # Listras zebra
COR_BOX_REC: tuple = (248, 248, 248)
COR_CINZA_CLARO: tuple = (240, 240, 240)
COR_VERDE_CLARO: tuple = (235, 252, 235)        # Fundo box verde suave
COR_AZUL_CLARO: tuple = (235, 242, 255)         # Fundo box azul suave
COR_ALERTA_RGB: tuple = (255, 243, 205)         # Fundo box alerta (amarelo)

# ── Paleta de Cores (HEX) ────────────────────────────────────────────────────
HEX_VERDE: str = "#006400"
HEX_AZUL_ESCURO: str = "#1E3A5F"
HEX_CINZA: str = "#808080"
HEX_CINZA_TEXTO: str = "#4A4A4A"
HEX_VERMELHO: str = "#C00000"
HEX_AMARELO: str = "#FFC000"
HEX_AZUL: str = "#2E75B6"

# ── Mapeamento de Colunas ────────────────────────────────────────────────────
MAPA_SIMULACAO: Dict[str, str] = {
    "PESO": "Peso",
    "UF": "UF",
    "Custo": "Custo_Novo",
    "Transportadora": "Transp_Nova",
    "Prazo": "Prazo_Novo",
    "Prazo em Dias": "Prazo_Novo",       # novo padrão de coluna
    "Valor total da NF": "Valor_NF",
    "CEP DESTINO": "CEP_Destino",
    "CEP Destino": "CEP_Destino",
    "Data de Criação": "Data_Criacao",   # novo padrão — data do pedido
}

MAPA_ORIGINAL: Dict[str, str] = {
    "Custo": "Custo_Antigo",
    "Prazo": "Prazo_Antigo",
    "Prazo em Dias": "Prazo_Antigo",     # novo padrão de coluna
    "Transportadora": "Transp_Antiga",
    "Data de Criação": "Data_Criacao",   # novo padrão — data do pedido
}

# ── Faixas de Peso ────────────────────────────────────────────────────────────
FAIXAS_PESO: List[float] = [0, 5, 10, 20, 30, 50, 100, 99999]
LABELS_PESO: List[str] = [
    "0-5kg", "5-10kg", "10-20kg", "20-30kg", "30-50kg", "50-100kg", "100kg+"
]

# ── Regiões do Brasil ─────────────────────────────────────────────────────────
REGIOES_BR: Dict[str, List[str]] = {
    "Sudeste": ["SP", "RJ", "MG", "ES"],
    "Sul": ["PR", "SC", "RS"],
    "Centro-Oeste": ["DF", "GO", "MT", "MS"],
    "Nordeste": ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"],
    "Norte": ["AC", "AP", "AM", "PA", "RO", "RR", "TO"],
}

ORDEM_REGIOES: List[str] = ["Sudeste", "Sul", "Centro-Oeste", "Nordeste", "Norte"]

# ── Dicionário de normalização UF ─────────────────────────────────────────────
DE_PARA_UF: Dict[str, str] = {
    "ACRE": "AC", "AMAPA": "AP", "AMAPÁ": "AP", "RORAIMA": "RR",
    "RONDÔNIA": "RO", "RONDONIA": "RO", "ALAGOAS": "AL", "AMAZONAS": "AM",
    "BAHIA": "BA", "CEARA": "CE", "CEARÁ": "CE", "DISTRITO FEDERAL": "DF",
    "ESPIRITO SANTO": "ES", "ESPÍRITO SANTO": "ES", "GOIAS": "GO", "GOIÁS": "GO",
    "MARANHAO": "MA", "MARANHÃO": "MA", "MATO GROSSO": "MT",
    "MATO GROSSO DO SUL": "MS", "MINAS GERAIS": "MG", "PARA": "PA", "PARÁ": "PA",
    "PARAIBA": "PB", "PARAÍBA": "PB", "PARANA": "PR", "PARANÁ": "PR",
    "PERNAMBUCO": "PE", "PIAUI": "PI", "PIAUÍ": "PI", "RIO DE JANEIRO": "RJ",
    "RIO GRANDE DO NORTE": "RN", "RIO GRANDE DO SUL": "RS",
    "SANTA CATARINA": "SC", "SAO PAULO": "SP", "SÃO PAULO": "SP",
    "SERGIPE": "SE", "TOCANTINS": "TO",
}

# ── Colunas obrigatórias por arquivo ─────────────────────────────────────────
COLUNAS_OBRIGATORIAS_SIM: List[str] = ["PESO", "UF", "Custo", "Transportadora", "Prazo"]
COLUNAS_OBRIGATORIAS_ORIG: List[str] = ["UF", "Custo", "Prazo", "Transportadora"]

# ── Classificações de pedido ──────────────────────────────────────────────────
CLASSIFICACOES: Dict[str, str] = {
    "GANHO_TOTAL": "GANHO TOTAL (Ouro)",
    "TRADE_OFF": "TRADE-OFF (Economia c/ Prazo Maior)",
    "INVESTIMENTO": "INVESTIMENTO (Mais rápido)",
    "PERDA": "PERDA (Mais caro e lento)",
    "SEM_BASE": "Sem Base Comparativa",
}

STATUS_MIGRACAO: Dict[str, str] = {
    "NOVO": "Novo Volume (Expansão)",
    "MANTIDO": "Mantido (Renegociação)",
    "MIGRADO": "Migrado (Troca)",
}

COLOR_MAP_CLASSIFICACAO: Dict[str, str] = {
    "GANHO TOTAL (Ouro)": HEX_VERDE,
    "TRADE-OFF (Economia c/ Prazo Maior)": HEX_AMARELO,
    "INVESTIMENTO (Mais rápido)": HEX_AZUL,
    "PERDA (Mais caro e lento)": HEX_VERMELHO,
    "Sem Base Comparativa": "#E0E0E0",
}
