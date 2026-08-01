# ADR 0006 — Upload seguro de evidências

- Status: aceito
- Data: 2026-07-31

## Contexto

Uma referência digitada em uma aprovação não prova que um artefato foi recebido,
preservado ou verificado. O portal precisa aceitar arquivos de áreas não técnicas sem
transformar a API, o banco ou os logs em repositórios de conteúdo potencialmente
malicioso e sensível.

## Decisão

- manter referências de aprovação existentes como `trusted_source=false` e distinguir
  os uploads verificados;
- restringir upload ao owner da iniciativa ou administrador de governança;
- aceitar inicialmente PDF, PNG, JPEG, TXT, CSV e JSON, com extensão, media type,
  assinatura e estrutura textual validados no servidor;
- limitar o stream durante a leitura e calcular SHA-256 sobre os mesmos bytes enviados
  ao scanner e ao storage;
- limitar o corpo ASGI antes do parser multipart e do spooling temporário, inclusive
  quando `Content-Length` estiver ausente;
- exigir veredito limpo do ClamAV via `INSTREAM`; indisponibilidade, timeout, erro ou
  resposta ambígua bloqueiam a operação;
- usar chave aleatória `evidence/{initiative_id}/{evidence_id}`, nunca o nome informado
  pelo cliente;
- gravar o arquivo em bucket S3 privado, com criação automática permitida apenas em
  ambiente local e criptografia server-side obrigatória fora de local/teste;
- persistir metadados e audit event na mesma transação; se ela falhar depois do upload,
  executar rollback e remoção compensatória do objeto;
- não retornar bucket, chave ou URI interna na API e não registrar nome nem conteúdo no
  audit log;
- restringir upload e consulta dos metadados ao owner ou administrador;
- configurar tamanho, allowlist, endpoints, timeouts, bucket, região e credenciais por
  variáveis de ambiente.

O caso de uso define portas para stream, scanner, object storage, persistência,
auditoria e transação. FastAPI, SQLAlchemy, ClamAV e S3 permanecem adapters externos,
preservando Dependency Inversion e testabilidade.

## Consequências

- o fluxo falha fechado se scanner ou object storage estiverem indisponíveis;
- a validação estrutural lê no máximo o limite configurado em memória depois do
  spooling; o padrão é 10 MiB e o teto de configuração é 50 MiB;
- ClamAV detecta malware conhecido, mas não substitui content disarm and reconstruction
  nem análise humana; PDFs não são renderizados pelo portal;
- atualizações das assinaturas, retenção, versionamento/immutability do bucket e
  lifecycle continuam sendo responsabilidades operacionais;
- o bucket deve ser privado, usar credencial de menor privilégio e política de retenção;
  ClamAV deve permanecer em rede privada e o diretório temporário do runtime deve usar
  storage efêmero protegido;
- uma falha de remoção compensatória pode deixar objeto órfão; lifecycle e reconciliação
  do bucket devem removê-lo sem depender de listagem pública;
- download e autorização granular para revisores não fazem parte desta fatia e devem
  usar URLs assinadas curtas, nunca tornar o bucket público.
- as imagens de desenvolvimento usam tags de versão verificadas; deploys endurecidos
  devem fixar também seus digests e verificar SBOM/assinatura no pipeline de supply chain.
