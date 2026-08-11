# Passo a passo em cinco minutos

- **Status:** Current
- **Owner:** Produto e arquitetura
- **Last reviewed:** 2026-08-11
- **Review trigger:** Mudança na demo canônica, navegação do portal ou evidência de runtime

Este é o caminho mais curto para avaliar o que o Verifiable AI Governance comprova. Todo o cenário
usa dados sintéticos e separa evidência de UI, fixture determinística e provas de integração live.

## Minuto 0-1 - entenda a tese

Leia o início do `README.pt-BR.md` e mantenha esta cadeia em mente:

```text
Política
  → Aprovação
  → Autorização Assinada
  → Enforcement em Runtime
  → Violação / Runtime Assurance
  → Resposta Governada
  → Evidência
```

A principal decisão arquitetural é que autorização de runtime deriva do escopo revisado. Um modelo
ou agente não se torna confiável apenas porque a aplicação consegue tecnicamente chamá-lo.

## Minuto 1-2 - inspecione o estado de governança

No portal, abra a iniciativa canônica:

**`[DEMO-CANONICAL] Análise de Crédito PJ Assistida e Auditável`**

Observe:

- risco determinístico e controles aplicáveis;
- assessments estruturados submetidos;
- gates independentes de aprovação;
- o sistema de IA resultante;
- modelos e agentes revisados.

O GIF existente no README é uma captura real desse tipo de estado da demo, não uma ilustração de
marketing criada para representar comportamento inexistente.

## Minuto 2-3 - acompanhe a fronteira de runtime

O cenário canônico possui dois resultados de roteamento:

- decisão permitida: `1c384bfc-4126-5fda-8d58-bd63fd73aac4`;
- decisão bloqueada: `32f86499-5b44-5580-870c-9c5a13bf9ff3`.

O modelo aprovado possui ID `9a798288-ea72-5e4d-ac33-dfc7533d80cb`; o modelo propositalmente
fora do escopo possui `150df55c-7ca6-551b-826d-545ccbe1dff5`.

O ponto não é apenas que um roteador consegue retornar “deny”. A governança revalida o resultado
contra o escopo aprovado e preserva informações confiáveis do bloqueio fail-closed como evidência
de runtime.

## Minuto 3-4 - veja incidente e assurance

O caminho bloqueado de referência está correlacionado ao incidente:

`29629ff5-c689-5d4e-8b22-5812e2e07a65`

Use as telas de sistema/incidente e a documentação da API para verificar a relação entre ativo
governado, decisão de runtime e incidente.

Para o caminho operacional mais amplo, leia
[`P1_9_GOVERNED_ACTUATION_E2E.md`](../operations/P1_9_GOVERNED_ACTUATION_E2E.md). Essa prova cobre
a fronteira live entre repositórios para Router, telemetria e atuação governada. O seed canônico,
por desenho, usa um adapter local e determinístico de Router.

## Minuto 4-5 - verifique em vez de confiar na tela

Execute:

```bash
uv run python -m scripts.seed_canonical_demo --check
uv run python scripts/validate_repository_hygiene.py
```

Depois consulte os runbooks P2.0 de evidência de release. A cadeia vincula a fonte congelada a
segurança, provenance, benchmark/SLO de runtime, fresh install e um root final do release
candidate.

Antes da v0.2.0, a evidência final `0.2.0-rc2` é regenerada somente depois do source freeze público.
Assim, mudanças de README, documentação e workflows também pertencem ao commit que a evidência
afirma representar.

## Se tiver mais cinco minutos

Ordem recomendada:

1. [Matriz de capacidades](../product/CAPABILITY_MATRIX.md)
2. [Arquitetura](../architecture/ARCHITECTURE.md)
3. [Threat model](../security/THREAT_MODEL.md)
4. [Modelo de evidências](../governance/EVIDENCE_MODEL.md)
5. [Guia de desenvolvimento](../DEVELOPMENT.md)

## Execução local

Para executar portal e API localmente:

```bash
cp .env.example .env
docker compose up --build
make seed-demo
```

Abra `http://localhost:3000`. A primeira inicialização do ClamAV pode demorar enquanto as
assinaturas são preparadas; uploads de evidência continuam fail-closed até o scanner estar pronto.
