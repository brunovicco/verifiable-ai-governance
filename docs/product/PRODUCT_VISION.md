# Visão do produto

## Problema

Iniciativas de IA costumam nascer em documentos, planilhas e conversas desconectadas.
Isso dificulta saber quem responde pela solução, quais dados e fornecedores estão
envolvidos, onde o processamento ocorre, quais áreas precisam aprovar e se o sistema
continua operando dentro das condições aprovadas.

## Visão

Oferecer um workspace de governança compreensível para áreas de negócio e verificável
por equipes técnicas e de assurance. Cada iniciativa deve manter um encadeamento
explícito:

```text
Contexto → Risco → Controles → Aprovações → Evidências → Operação → Revisão
```

## Públicos

- solicitantes e Product Owners que descrevem a finalidade e respondem pela iniciativa;
- Governança de IA, que mantém taxonomias, controles, exceções e o portfólio;
- Segurança, Arquitetura, Infra, DevOps e Dados, que validam riscos técnicos;
- Privacidade, Jurídico e Compliance, que validam obrigações e impactos;
- Operações e Model Owners, que acompanham modelos e agentes em produção;
- auditoria e comitês, que verificam decisões e evidências sem alterar registros.

## Proposta de valor

1. Formulário guiado em linguagem não técnica.
2. Classificação explicável, nunca uma “caixa-preta” de risco.
3. Aprovações condicionais, evitando burocracia uniforme e lacunas de controle.
4. Evidência vinculada à decisão e histórico imutável por eventos.
5. Preparação para monitorar uso, mudanças, violações e incidentes em runtime.

## Escopo da versão 0.1

- cadastro e inventário de iniciativas;
- avaliação preliminar determinística;
- workflow de aprovação multidisciplinar;
- documentos requeridos por contexto;
- segregação de funções e trilha de auditoria;
- modelos de dados para o inventário técnico completo;
- portal de demonstração e execução local.

## Fora do escopo da versão 0.1

- parecer jurídico automatizado;
- certificação ISO ou declaração automática de conformidade;
- orquestração de processo regulatório oficial;
- execução de modelos ou agentes;
- coleta de telemetria de produção;
- assinatura digital ou armazenamento externo de documentos.

## Medidas de sucesso do MVP

- uma proposta completa é cadastrada em menos de dez minutos;
- 100% das propostas submetidas possuem owner, risco, policy version e gates registrados;
- nenhum owner consegue aprovar a própria iniciativa;
- nenhuma iniciativa é aprovada com gate obrigatório pendente ou rejeitado;
- cada decisão possui justificativa, evidência referenciada e evento de auditoria;
- uma alteração concorrente com versão desatualizada é rejeitada.
