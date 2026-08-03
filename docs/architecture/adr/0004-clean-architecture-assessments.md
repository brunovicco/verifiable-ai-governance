# ADR 0004 - Clean Architecture para assessments estruturados

- Status: aceito
- Data: 2026-07-31

## Contexto

AIA, RIPD e análise de processamento internacional compartilham ciclo de vida,
autorização, versionamento e auditoria, mas possuem respostas e regras de aplicabilidade
diferentes. Vincular essas regras diretamente a FastAPI, Pydantic ou SQLAlchemy
dificultaria testes, evolução de schema e futuras entradas por fila ou integração GRC.

## Decisão

- representar cada definição por tipos imutáveis e versionados no domínio puro;
- concentrar aplicabilidade, cálculo do risco e transições em funções sem I/O;
- implementar criar/atualizar, listar e submeter como casos de uso coesos;
- declarar portas de store, auditoria e transação no módulo consumidor;
- implementar as portas com adapters SQLAlchemy ligados no composition root;
- mapear explicitamente DTOs Pydantic, valores de domínio e entidades ORM;
- traduzir erros tipados para HTTP somente na borda;
- exigir versão esperada nas mutações e unicidade de tipo por iniciativa no banco;
- manter audit events sem o conteúdo das respostas;
- documentar módulos, classes e operações públicas com docstrings.

Esse desenho aplica responsabilidade única e inversão de dependência. Novos adapters
podem ser adicionados sem alterar os casos de uso; novas definições exigem contrato e
versão explícitos, evitando schemas genéricos que ocultem mudanças materiais.

## Twelve-Factor

O módulo não introduz estado de processo nem configuração codificada. Sessão de banco,
identidade, clock e gerador de IDs entram pelas fronteiras existentes ou por injeção. A
API pode escalar horizontalmente, PostgreSQL permanece recurso anexado por configuração
e a auditoria continua emitindo eventos estruturados.

## Consequências

- regras podem ser testadas sem servidor HTTP ou banco;
- adapters e mappings acrescentam código, mas tornam fronteiras verificáveis;
- assessment submetido fica somente leitura até a implementação do workflow de revisão;
- criação concorrente é protegida pela constraint `uq_assessment_initiative_type`;
- adicionar uma definição requer atualizar a união tipada, schemas, adapter e portal de
  forma deliberada, incluindo uma nova versão de contrato.
