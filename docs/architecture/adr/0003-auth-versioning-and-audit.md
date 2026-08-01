# ADR 0003 — OIDC, versionamento e auditoria

- Status: aceito
- Data: 2026-07-31

## Decisão

- usar OIDC com validação de issuer, audience, assinatura e claim de áreas;
- permitir identidade por headers apenas em ambiente local explicitamente habilitado;
- usar optimistic locking por `expected_version` nos comandos de workflow;
- manter audit events append-only com hash do evento anterior e salt por ambiente;
- não armazenar prompts, respostas ou documentos no payload de auditoria.

## Limitações conhecidas

O encadeamento por hash torna adulteração detectável, mas não substitui WORM storage,
assinatura externa, SIEM ou timestamping confiável. Esses controles entram após o MVP.

A configuração de confiança, as fronteiras de Clean Architecture e a validação com
provedor real foram detalhadas posteriormente no ADR 0008.
