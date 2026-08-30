# Roadmap do Lyra OS

## Lyra Enterprise Linux

Fica registrada a decisão de criar futuramente o **Lyra Enterprise Linux**
nas edições **Desktop** e **Server**, ambas baseadas no **SUSE Linux
Enterprise**. Esta decisão não altera o escopo nem a base dos ciclos atuais do
Lyra OS; planejamento, versões e cronograma serão definidos separadamente.

## Lyra OS Desktop Alpha 4 a Alpha 8

A Alpha 4 foi publicada em 14/08/2026 como snapshot antecipado da
infraestrutura de i18n, do Lyra Installer em `en-US`/`pt-BR`/`es-ES` e da
primeira onda de pacotes em `pt-BR`/`en-US`.

- **Alpha 5 (14–28/08) — estabilização e contratos:** corrige primeiro os
  bloqueadores herdados do instalador e do release e especifica o Lyra
  Upgrade. Para o ECA Digital, fecha enquadramento jurídico, auditoria da
  referência BigLinux, qualificação upstream, UX no Vega, ADR e baseline de
  governança LTS. Os três idiomas e o fluxo NVIDIA pelo Vega já estão
  concluídos e validados.
- **Alpha 6 (28/08–11/09) — atualização e integração:** entrega o core,
  preflight, estado durável e serviço privilegiado do Lyra Upgrade para
  atualizações dentro da mesma release, com interface nos três idiomas,
  console sanitizado, recuperação e rollback. Integra também as novas telas do
  Welcome e a pilha ALSA explícita da imagem. O upgrade entre releases segue
  para a Alpha 7; o serviço parental permanece no marco 1.0, condicionado à
  revisão jurídica e à qualificação técnica.
- **Alpha 7 (11–25/09) — rebase e upgrade:** migra o Desktop
  1.0 para o openSUSE Leap 16.1 Beta 1 e requalifica pacotes, ABI, Secure
  Boot, instalação, atualização, rollback e hardware. Também conclui o fluxo
  controlado entre releases do Lyra Upgrade. O Desktop 1.0 não oferece
  suporte de produto a aplicativos Android ou Windows; essa trilha volta a ser
  avaliada somente em uma release futura definida pelo projeto. A integração parental só avança quando os
  gates jurídico e técnico do marco 1.0 estiverem satisfeitos.
- **Alpha 8 (25/09–13/10) — gate e estabilização:** automatiza update, upgrade,
  reboot, rollback e a matriz do ECA Digital; não recebe feature nova e depois
  corrige somente defeitos até a decisão da Beta 1.

A Beta 1 não começa por calendário com P0/P1 ou entrega obrigatória pendente.
O Lyra OS 1.0 oferece somente inglês dos Estados Unidos (`en-US`), português
do Brasil (`pt-BR`) e espanhol da Espanha (`es-ES`), com `en-US` como padrão e fallback.
Os projetos e seus RPMs já foram traduzidos e testados nos três idiomas.
Outros idiomas entram apenas em ciclo futuro.

O gate da funcionalidade exige detecção conservadora de hardware compatível,
confirmação explícita, Secure Boot verificado, snapshot Snapper antes da
mudança, pacotes meta que mantenham KMP, userspace e firmware em lockstep,
`dracut`, reinício orientado e rollback documentado. O fluxo não pode ser
declarado suportado com um P1 aberto; a pendência da Alpha 4 fica registrada
explicitamente na Alpha 5.

## NVIDIA em uma única ISO Desktop

A ISO NVIDIA dedicada foi cancelada. A instalação opcional via Vega foi
concluída na Desktop Alpha 5 e é o único fluxo proprietário: detecção do
hardware real, confirmação, verificação de Secure Boot, snapshot Snapper,
pacotes KMP/userspace em lockstep, `dracut`, reinício, validação e rollback.
As descobertas técnicas preservadas em [`nvidia-iso.md`](nvidia-iso.md) são
históricas e alimentam esse fluxo; não representam uma segunda imagem.

## Melhorias permitidas nas Betas da 1.0

A Desktop Beta 1 mantém 13/10/2026 como meta; Alpha 5, Alpha 6, Alpha 7 e
Alpha 8 continuam etapas obrigatórias do Desktop. Por decisão do mantenedor,
as Betas da 1.0 podem receber melhorias programadas quando o ganho esperado
compensar o risco. Cada mudança precisa de justificativa, análise de impacto,
testes de regressão e plano de reversão; os gates não são reduzidos para
cumprir calendário. A RC1 encerra essa exceção e inicia o congelamento estrito.

Correções de bugs, regressões, segurança, desempenho e traduções continuam
prioritárias. Melhorias não podem deixar P0/P1 aberto para a etapa seguinte.
Novos aplicativos e mudanças amplas de arquitetura ainda exigem decisão
explícita. A Beta 3 também faz QA linguístico e corrige catálogos.

O cronograma semanal, o inventário nominal de pacotes e os critérios de saída
estão em [`release-versioning.md`](release-versioning.md#cronograma-do-ciclo-lyra-os-10).

## Idiomas em ciclos futuros

A ampliação para outros idiomas começa somente depois da Lyra OS 1.0. A
infraestrutura criada na 1.0 deve aceitar novos catálogos com fallback para
`en-US`, mas isso não autoriza publicar traduções adicionais antes de uma
release futura que as qualifique.
Cada novo idioma terá inventário, revisão humana, fallback e gate linguístico
próprios antes de ser oferecido pelo instalador.
