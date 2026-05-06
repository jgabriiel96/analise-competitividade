"""Testes unitários básicos do projeto MAX Logistics Intelligence Platform.

Cobre:
- converter_monetario: casos edge de conversão de valores monetários.
- padronizar_uf: normalização de nomes de estados para siglas.
- Cálculo de SLA compliance com DataFrame sintético.
"""

import sys
import os
import unittest

import numpy as np
import pandas as pd

# Adiciona o diretório raiz ao path para importações
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.text_utils import converter_monetario
from services.data_processor import padronizar_uf
from services.sla_analyzer import analisar_sla, DENTRO_SLA, ALERTA_SLA, FORA_SLA


class TestConverterMonetario(unittest.TestCase):
    """Testes para a função converter_monetario."""

    def test_float_passthrough(self) -> None:
        """Valores float puros devem ser retornados sem alteração."""
        self.assertAlmostEqual(converter_monetario(1234.56), 1234.56)

    def test_int_passthrough(self) -> None:
        """Valores int puros devem ser convertidos para float corretamente."""
        self.assertAlmostEqual(converter_monetario(100), 100.0)

    def test_none_retorna_zero(self) -> None:
        """None deve retornar 0.0."""
        self.assertAlmostEqual(converter_monetario(None), 0.0)

    def test_string_vazia_retorna_zero(self) -> None:
        """String vazia deve retornar 0.0."""
        self.assertAlmostEqual(converter_monetario(""), 0.0)

    def test_traco_retorna_zero(self) -> None:
        """Traço ('-') deve retornar 0.0."""
        self.assertAlmostEqual(converter_monetario("-"), 0.0)

    def test_nan_string_retorna_zero(self) -> None:
        """String 'nan' deve retornar 0.0."""
        self.assertAlmostEqual(converter_monetario("nan"), 0.0)

    def test_formato_br_completo(self) -> None:
        """Formato brasileiro com R$, pontos de milhar e vírgula decimal."""
        self.assertAlmostEqual(converter_monetario("R$ 1.234,56"), 1234.56)

    def test_formato_br_sem_rs(self) -> None:
        """Formato BR sem prefixo R$."""
        self.assertAlmostEqual(converter_monetario("1.234,56"), 1234.56)

    def test_formato_us(self) -> None:
        """Formato US com ponto decimal."""
        self.assertAlmostEqual(converter_monetario("1234.56"), 1234.56)

    def test_virgula_simples(self) -> None:
        """Apenas vírgula como separador decimal."""
        self.assertAlmostEqual(converter_monetario("99,90"), 99.90)

    def test_valor_zero(self) -> None:
        """Zero string deve retornar 0.0."""
        self.assertAlmostEqual(converter_monetario("0"), 0.0)

    def test_valor_grande(self) -> None:
        """Valores grandes com múltiplos pontos de milhar."""
        self.assertAlmostEqual(converter_monetario("R$ 1.000.000,00"), 1_000_000.0)

    def test_string_invalida_retorna_zero(self) -> None:
        """String não-numérica deve retornar 0.0 sem exceção."""
        self.assertAlmostEqual(converter_monetario("abc"), 0.0)


class TestPadronizarUF(unittest.TestCase):
    """Testes para a função padronizar_uf."""

    def test_sigla_ja_correta(self) -> None:
        """Sigla já correta deve ser retornada sem alteração."""
        self.assertEqual(padronizar_uf("SP"), "SP")

    def test_sigla_minuscula(self) -> None:
        """Sigla em minúsculas deve ser normalizada para maiúsculas."""
        self.assertEqual(padronizar_uf("sp"), "SP")

    def test_nome_completo_sem_acento(self) -> None:
        """Nome completo sem acento deve ser convertido para sigla."""
        self.assertEqual(padronizar_uf("SAO PAULO"), "SP")

    def test_nome_completo_com_acento(self) -> None:
        """Nome completo com acento deve ser convertido para sigla."""
        self.assertEqual(padronizar_uf("SÃO PAULO"), "SP")

    def test_minas_gerais(self) -> None:
        """Minas Gerais deve retornar MG."""
        self.assertEqual(padronizar_uf("MINAS GERAIS"), "MG")

    def test_rio_de_janeiro(self) -> None:
        """Rio de Janeiro deve retornar RJ."""
        self.assertEqual(padronizar_uf("RIO DE JANEIRO"), "RJ")

    def test_rio_grande_do_sul(self) -> None:
        """Rio Grande do Sul deve retornar RS."""
        self.assertEqual(padronizar_uf("RIO GRANDE DO SUL"), "RS")

    def test_maranhao_com_acento(self) -> None:
        """Maranhão com acento deve retornar MA."""
        self.assertEqual(padronizar_uf("MARANHÃO"), "MA")

    def test_para_com_acento(self) -> None:
        """Pará com acento deve retornar PA."""
        self.assertEqual(padronizar_uf("PARÁ"), "PA")

    def test_ceara_com_acento(self) -> None:
        """Ceará com acento deve retornar CE."""
        self.assertEqual(padronizar_uf("CEARÁ"), "CE")

    def test_valor_desconhecido_retorna_original(self) -> None:
        """Valor não reconhecido deve ser retornado em maiúsculas."""
        self.assertEqual(padronizar_uf("DESCONHECIDO"), "DESCONHECIDO")

    def test_valor_numerico(self) -> None:
        """Valor numérico deve ser convertido para string e retornado em maiúsculas."""
        result = padronizar_uf(12)
        self.assertIsInstance(result, str)

    def test_espaços_extras(self) -> None:
        """Valor com espaços extras deve ser normalizado."""
        self.assertEqual(padronizar_uf("  SP  "), "SP")


class TestSLACompliance(unittest.TestCase):
    """Testes para o módulo sla_analyzer com DataFrame sintético."""

    def _criar_df_sintetico(self) -> pd.DataFrame:
        """Cria DataFrame sintético para testes de SLA."""
        return pd.DataFrame({
            "Prazo_Novo": [2, 3, 4, 5, 10, 2, 7, 8],
            "UF": ["SP", "SP", "RS", "RS", "BA", "BA", "AM", "AM"],
            "Transp_Nova": ["A", "A", "B", "B", "A", "B", "A", "B"],
            "Custo_Novo": [100.0, 120.0, 80.0, 90.0, 200.0, 150.0, 300.0, 250.0],
            "Peso": [5.0, 10.0, 3.0, 7.0, 15.0, 20.0, 8.0, 12.0],
            "Tem_Base": [True] * 8,
        })

    def test_retorna_resultado(self) -> None:
        """analisar_sla deve retornar um objeto com todos os atributos."""
        df = self._criar_df_sintetico()
        sla_targets = {"Sudeste": 3, "Sul": 4, "Nordeste": 7, "Norte": 8, "Centro-Oeste": 5}
        result = analisar_sla(df, sla_targets)
        self.assertIsNotNone(result)
        self.assertFalse(result.df_com_sla.empty)

    def test_coluna_sla_status_criada(self) -> None:
        """DataFrame resultante deve ter coluna SLA_Status."""
        df = self._criar_df_sintetico()
        result = analisar_sla(df, {"Sudeste": 3, "Sul": 4, "Nordeste": 7, "Norte": 8, "Centro-Oeste": 5})
        self.assertIn("SLA_Status", result.df_com_sla.columns)

    def test_classificacoes_validas(self) -> None:
        """Todas as classificações devem ser DENTRO_SLA, ALERTA ou FORA_SLA."""
        df = self._criar_df_sintetico()
        result = analisar_sla(df, {"Sudeste": 3, "Sul": 4, "Nordeste": 7, "Norte": 8, "Centro-Oeste": 5})
        classificacoes_validas = {DENTRO_SLA, ALERTA_SLA, FORA_SLA}
        valores_unicos = set(result.df_com_sla["SLA_Status"].unique())
        self.assertTrue(valores_unicos.issubset(classificacoes_validas))

    def test_compliance_global_entre_0_e_100(self) -> None:
        """Compliance global deve ser um percentual entre 0 e 100."""
        df = self._criar_df_sintetico()
        result = analisar_sla(df, {"Sudeste": 3, "Sul": 4, "Nordeste": 7, "Norte": 8, "Centro-Oeste": 5})
        self.assertGreaterEqual(result.compliance_global_pct, 0.0)
        self.assertLessEqual(result.compliance_global_pct, 100.0)

    def test_prazo_dentro_target_classificado_corretamente(self) -> None:
        """Pedido com prazo = target deve ser classificado como DENTRO_SLA."""
        df = pd.DataFrame({
            "Prazo_Novo": [3],  # Igual ao target do Sudeste
            "UF": ["SP"],
            "Transp_Nova": ["A"],
            "Custo_Novo": [100.0],
            "Peso": [5.0],
            "Tem_Base": [True],
        })
        result = analisar_sla(df, {"Sudeste": 3})
        self.assertEqual(result.df_com_sla["SLA_Status"].iloc[0], DENTRO_SLA)

    def test_prazo_muito_acima_target_classificado_fora(self) -> None:
        """Pedido com prazo muito acima do target deve ser FORA_SLA."""
        df = pd.DataFrame({
            "Prazo_Novo": [15],  # Muito acima do target do Sudeste (3 dias)
            "UF": ["SP"],
            "Transp_Nova": ["A"],
            "Custo_Novo": [100.0],
            "Peso": [5.0],
            "Tem_Base": [True],
        })
        result = analisar_sla(df, {"Sudeste": 3})
        self.assertEqual(result.df_com_sla["SLA_Status"].iloc[0], FORA_SLA)

    def test_compliance_por_transp_nao_vazia(self) -> None:
        """compliance_por_transp deve ter pelo menos uma linha."""
        df = self._criar_df_sintetico()
        result = analisar_sla(df, {"Sudeste": 3, "Sul": 4, "Nordeste": 7, "Norte": 8, "Centro-Oeste": 5})
        self.assertFalse(result.compliance_por_transp.empty)

    def test_acoes_preventivas_geradas(self) -> None:
        """texto_acoes_preventivas deve ter pelo menos um item."""
        df = self._criar_df_sintetico()
        result = analisar_sla(df, {"Sudeste": 3, "Sul": 4, "Nordeste": 7, "Norte": 8, "Centro-Oeste": 5})
        self.assertGreater(len(result.texto_acoes_preventivas), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
