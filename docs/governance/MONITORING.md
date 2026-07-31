# Monitoramento de modelos e agentes

## Três níveis

1. **Operação:** disponibilidade, latência, erro, timeout, throughput, tokens, custo,
   retries, fallback e rate limit.
2. **Modelo:** qualidade, groundedness, recusa, segurança, structured output,
   regressão, drift, versão, região e uso fora do escopo.
3. **Agente:** objetivo, plano, modelo, ferramentas, argumentos sanitizados, permissões,
   loops, delegações, approvals, ações bloqueadas, custo, tempo e mudança de estado.

## Eventos que devem bloquear ou interromper

- modelo, agente, ferramenta ou MCP não aprovado;
- classe de dado incompatível com o destino;
- ausência de aprovação humana obrigatória;
- custo, tempo, passos ou permissões acima do limite;
- mudança do plano após aprovação;
- ação irreversível ou fora do tenant;
- regressão abaixo do threshold de promoção;
- telemetria ou evidência obrigatória indisponível.

## Minimização

Telemetria operacional deve preferir IDs, digests, categorias, tempos e resultados.
Prompts, documentos, credenciais e respostas não são coletados por padrão. Exceções
precisam de finalidade, acesso, retenção e aprovação explícitos.
