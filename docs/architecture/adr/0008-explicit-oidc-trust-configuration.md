# ADR 0008 — Configuração explícita de confiança OIDC

- Status: aceito
- Data: 2026-08-01

## Contexto

A API precisa validar access tokens de provedores OIDC diferentes sem assumir uma URL
de JWKS específica de fornecedor. A implementação anterior derivava uma rota não
padronizada a partir do issuer, executava a obtenção de chaves de forma síncrona no
event loop e convertia qualquer valor truthy do claim administrativo em privilégio.
Também faltava uma validação integrada contra um provedor real e reproduzível.

## Decisão

- separar identidade, caso de uso de autenticação, verificador OIDC e transporte HTTP;
- exigir issuer, audience, JWKS URL e allowlist de algoritmos assimétricos explícitos;
- validar assinatura, `iss`, `aud`, `exp`, `iat` e `sub`, com clock skew limitado;
- limitar o tamanho do bearer token antes de qualquer acesso ao provedor;
- obter conjuntos JWKS com timeout e cache limitado fora do event loop da API, sem
  cache indefinido de chaves individuais;
- diferenciar token inválido (`401`) de indisponibilidade do provedor (`503`);
- aceitar caminhos aninhados de claims para grupos e ignorar papéis desconhecidos;
- conceder administração somente quando o claim configurado for o booleano JSON `true`;
- exigir HTTPS para issuer e JWKS fora de ambientes local e de teste;
- disponibilizar `/api/v1/auth/me` para verificar o mapeamento da identidade corrente;
- validar o contrato ponta a ponta com uma versão fixa de Keycloak e realm local
  importado declarativamente.

O Keycloak é apenas o provedor de teste de referência. O runtime permanece independente
de fornecedor porque confia somente no contrato JWT/JWKS configurado.

## Alternativas consideradas

- Derivar JWKS de `issuer/.well-known/jwks.json`: rejeitado porque essa rota não é o
  endpoint JWKS definido pelo discovery e não é portátil entre provedores.
- Fazer discovery OIDC em runtime: adiado; reduz configuração, mas adiciona outra
  dependência remota à inicialização e exige política própria de cache e mudança de
  metadados. A URL explícita torna a raiz de confiança auditável por ambiente.
- Usar introspecção para todo request: rejeitado para o MVP por aumentar latência,
  disponibilidade acoplada e exposição do token em chamadas adicionais.
- Aceitar algoritmos simétricos: rejeitado porque compartilharia segredo de assinatura
  com o resource server e ampliaria o impacto de comprometimento.

## Consequências

- deploys OIDC precisam fornecer mais configuração, mas não dependem de convenções de
  URL do provedor;
- rotação de chaves é absorvida pelo JWKS cache e seleção por `kid`;
- grupos fora da taxonomia de governança não concedem capacidade;
- o endpoint de identidade expõe apenas subject, e-mail e capacidades já pertencentes
  ao chamador, nunca o token ou claims arbitrários;
- o login interativo do portal continua fora deste incremento.

## Impacto de segurança e privacidade

O desenho reduz riscos de algorithm confusion, audience confusion, escalada por coerção
de tipos e negação de serviço por tokens sem limite. Tokens, chaves e payloads de claims
não são registrados. O e-mail retornado em `/auth/me` é dado pessoal e deve seguir os
mesmos controles de acesso e retenção dos logs HTTP. HTTP é permitido apenas no ambiente
local reproduzível; ambientes compartilhados falham na inicialização sem TLS.

## Impacto operacional

JWKS é uma dependência externa com timeout de dois segundos e cache de cinco minutos
por padrão. Indisponibilidade sem chave utilizável resulta em `503`, permitindo distinguir
falha operacional de credencial inválida sem revelar detalhes ao cliente. Alterações de
issuer, audience, claims ou endpoint exigem nova configuração do processo, coerente com
Twelve-Factor. O compose OIDC é opcional e não muda o caminho local padrão.

## Follow-up

- implementar authorization code com PKCE e sessão segura no portal;
- testar rotação real de chaves e comportamento durante indisponibilidade prolongada;
- integrar secrets manager e política organizacional de certificados/egress;
- avaliar discovery configurável caso múltiplos provedores justifiquem o custo;
- automatizar a validação Keycloak em CI com isolamento de portas.
