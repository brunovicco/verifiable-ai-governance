---
template_id: monitoring-plan
template_version: 1.0.0
status: draft
owner: Operations
---

# Plano de monitoramento de modelo e agente

## Baseline e escopo aprovado

- sistema, modelo/agente, versão e região;
- casos aprovados/proibidos, dados autorizados e autonomia;
- dataset de avaliação, período e limitações;
- owner operacional, on-call e kill switch.

## Indicadores

| Indicador | Baseline | Alerta | Bloqueio | Janela | Fonte | Owner |
|---|---:|---:|---:|---|---|---|
| Disponibilidade/latência/erro | | | | | | |
| Custo/tokens/retries | | | | | | |
| Qualidade/groundedness | | | | | | |
| Safety/privacy/policy violations | | | | | | |
| Tool/agent task success | | | | | | |
| Drift/regressão/versão | | | | | | |

## Eventos e resposta

Para cada evento, documentar detecção, severidade, contenção automática, pessoa
acionada, prazo, evidência, comunicação, rollback e critério de retorno.

## Privacidade da observabilidade

- atributos permitidos e proibidos;
- mascaramento e minimização;
- retenção e acesso;
- exceções para conteúdo e aprovação correspondente.

## Revisão

- frequência proporcional ao risco;
- eventos de reavaliação;
- data, participantes, decisão e versão.
