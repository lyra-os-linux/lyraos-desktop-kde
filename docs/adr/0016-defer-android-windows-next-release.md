# ADR 0016: adiar compatibilidade Android e Windows para o release futura

- Estado: aceita
- Data: 2026-08-26
- Substitui: [ADR 0015](0015-optional-android-windows-compatibility.md)
- Relacionadas: issues #14, #15, #16, #17, #18, #19, #20 e #50

## Contexto

A Alpha 7 migrou o Lyra OS Desktop 1.1 para openSUSE Leap 16.1. A primeira
candidata iniciou com desempenho e fluidez melhores que o esperado, mas ainda
precisa concluir instalação, primeiro boot, atualização, rollback, Secure Boot
e matriz de hardware.

A ADR 0015 separou Android e Windows da ISO e autorizou somente um piloto
opcional de Bottles. A avaliação posterior confirmou que o Flatpak atual pede
permissões amplas, enquanto Waydroid ainda não possui target mantido para Leap
16.1 nem cadeia de imagem Android homologada. Mesmo um piloto consome tempo de
qualificação e cria pressão para integrar uma experiência que não pertence ao
objetivo principal desta candidata.

O mantenedor definiu que este trabalho volta a ser discutido no release futura.
Vinculá-lo à Alpha 8 apenas deslocaria silenciosamente uma funcionalidade ampla
para o mesmo ciclo 1.1, próximo do congelamento funcional da Beta 1.

## Decisão

Todo suporte de produto a aplicativos Android e Windows é retirado do ciclo
Desktop 1.1. Isso inclui:

- empacotamento e repositórios de runtimes;
- pré-instalação ou configuração de Bottles, Wine ou Waydroid;
- fluxo de descoberta, instalação e remoção no Vega;
- associações de `.exe`, `.msi` e `.apk`;
- serviços, módulos, imagens Android e permissões adicionais;
- promessa de compatibilidade ou matriz de aplicativos no 1.0.

As issues permanecem no backlog de uma **release futura**. Elas não recebem `alpha-8`,
pois a Alpha 8 ainda pertence ao 1.0 e deve concentrar-se no fechamento de
features e preparação da Beta 1.

A ADR 0015 continua como registro da avaliação técnica e de seus gates, mas sua
autorização de piloto na Alpha 7 deixa de valer. O coletor de evidências pode
permanecer no repositório como ferramenta inativa e testada; ele não entra na
ISO e não constitui compromisso de entrega.

## Reabertura no release futura

Antes de implementar, o mantenedor deve:

1. definir o calendário e os estágios internos do release futura;
2. atualizar a pesquisa de disponibilidade na base Leap escolhida;
3. revisar novamente permissões, supply chain, licenças e manutenção LTS;
4. registrar go/no-go independente para Android e Windows;
5. executar os protótipos apenas em staging e ambientes descartáveis;
6. demonstrar remoção e reversão antes de alterar a composição padrão;
7. decidir explicitamente entre instalação opcional e baseline, sem converter
   uma em outra por conveniência de implementação.

## Consequências

- a única entrega aberta da Alpha 7 passa a ser qualificar a candidata Leap
  16.1 acompanhada na issue #50;
- a ISO 1.0 não ganha permissões, serviços ou downloads de runtime adicionais;
- #14, #15, #16, #17, #18 e #19 ficam abertas e classificadas para uma release futura;
- o adiamento não transfere automaticamente as funcionalidades para Alpha 8,
  Beta 1 ou Beta 2;
- qualquer exceção no 1.0 exige nova decisão explícita, análise de risco,
  testes de regressão e plano de reversão.
