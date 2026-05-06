# MAX Logistics Intelligence Platform

Plataforma de consultoria estratégica logística desenvolvida para o Projeto MAX da Intelipost.
Refatoração modular do `teste18.py` com novas análises de SLA, malha regional e competitividade.

## Instalação

```bash
cd "Projeto - Cursor Analise de Competitividade"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Execução

```bash
python main.py
```

## Fluxo de Uso

1. **Arquivo de Recotação** (Simulado): planilha com colunas PESO, UF, Custo, Transportadora, Prazo
2. **Arquivo Histórico** (Atual): planilha com Custo, Prazo, Transportadora anteriores
3. **Configuração do Estudo**: nome do cliente, período, módulos ativos, SLA targets por região
4. **Seleção de Foco**: escolha as transportadoras para diagnóstico competitivo detalhado
5. **Salvar PDF**: relatório executivo gerado automaticamente

## Estrutura do Projeto

```
├── main.py                    # Entry point com interface tkinter evoluída
├── requirements.txt
├── config/
│   ├── constants.py           # Cores, mapeamentos, regiões BR
│   └── settings.py            # SLA targets, pesos de score, thresholds
├── loaders/
│   ├── file_loader.py         # Leitura CSV/Excel multi-encoding
│   └── data_validator.py      # Validação de colunas e qualidade
├── services/
│   ├── data_processor.py      # Merge, padronização UF, cálculos base
│   ├── financial_analyzer.py  # Saving, ticket médio, health score
│   ├── sla_analyzer.py        # NOVO: SLA compliance, risco de atraso
│   ├── regional_strategy.py   # NOVO: Malha recomendada por região
│   ├── competitive_analyzer.py # Win rate, target price, elasticidade
│   └── migration_analyzer.py  # Análise de churn de transportadoras
├── exporters/
│   ├── chart_builder.py       # Todos os gráficos matplotlib
│   ├── pdf_builder.py         # Montagem do PDF (17 páginas)
│   └── temp_manager.py        # Limpeza de arquivos temporários
├── utils/
│   ├── text_utils.py          # limpar_texto, converter_monetario
│   └── logger.py              # Logging estruturado
└── tests/
    └── test_basic.py          # Testes unitários
```

## Executar Testes

```bash
python -m pytest tests/ -v
# ou
python -m unittest tests.test_basic -v
```

## Seções do Relatório PDF

| Pág | Bloco | Conteúdo |
|-----|-------|----------|
| 1 | Capa | Cliente, período de referência, sumário das seções |
| 2 | Resumo Executivo | KPIs globais (saving, cobertura, health, lead time) + card da transportadora foco |
| 3 | Índice | Lista das seções por bloco |
| 4 | Em Análise — Painel Foco | KPIs da transportadora foco (vitórias T1, custo, prazo, posicionamento) + Top Rotas + narrativa |
| 5 | 1. Competitividade & Pricing | Tabela de Target Price por região (Custo Cotado vs Benchmark) + diagnóstico |
| 6 | Gap para Liderar no BID | Distribuição T1-T5, sensibilidade ao desconto, competidores que lideram |
| 7 | 2. Malha Logística Recomendada | Score por região (60% saving + 40% volume) com Top 5 carriers por região |
| 8 | Malha Consolidada + Diretrizes | Decisão por região (Principal/Backup) + posicionamento da foco + comparativos |
| 9 | 3. Presença Geográfica — Foco | Distribuição da foco por faixa de CEP (volume e saving) |
| 10 | 4. Visão Geral da Simulação | KPIs do cenário simulado + Resumo por transportadora |
| 11 | 5. Dinâmica de Troca | Pedidos migrados, saving da migração, principal destino |
| 12 | 5. Dinâmica — continuação | Fluxo de migração De/Para + insights estratégicos |
| 13 | 6. Análise Financeira | Saving operacional, custo base, variação de ticket médio |
| 14 | 7. Matriz de Decisão | Classificação GANHO TOTAL / TRADE-OFF / INVESTIMENTO / PERDA |
| 15 | 8. Heatmap de Competitividade | Custo por UF × transportadora |
| 16 | 9. Perfil de Carga | Líder de custo por faixa de peso |
| 17 | 10. Conclusão e Próximos Passos | Roadmap em 3 passos + síntese do estudo |
