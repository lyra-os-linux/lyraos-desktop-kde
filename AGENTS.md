# Princípios do projeto Lyra

## Estabilidade em primeiro lugar

O Lyra é uma distribuição Linux estável, sólida e confiável, voltada à
experiência de “instalar e ficar tranquilo”. O usuário não deve precisar
administrar constantemente o sistema para mantê-lo funcional, seguro e
previsível. Preserve esse objetivo em toda decisão de arquitetura,
implementação, empacotamento, atualização e release.

Prefira componentes maduros, atualizações conservadoras, compatibilidade de
longo prazo, padrões seguros, recuperação confiável e baixa necessidade de
manutenção. Evite trocar tecnologias ou ampliar funcionalidades apenas por
novidade quando isso aumentar a superfície de falhas, a carga operacional ou
o risco de regressão sem um benefício claro para o usuário.

## Lapidação sobre o openSUSE

O openSUSE é a fundação técnica do Lyra, não um detalhe a ser ocultado ou
substituído. Reaproveite seus componentes, empacotamento, mecanismos de
segurança, atualização e recuperação sempre que forem adequados. Evite criar
alternativas exclusivas do Lyra para problemas que a base já resolve bem.

O diferencial do Lyra é lapidar essa base como um produto coerente: integrar
hardware, drivers, energia, aplicativos, atualizações e rollback; identificar
combinações problemáticas; transformar incidentes reais em políticas e testes;
e remover a necessidade de intervenção técnica recorrente. A experiência de
uso confiável de distribuições como o TUXEDO OS é uma referência de qualidade
de integração, sem implicar copiar sua arquitetura ou ampliar o escopo do Lyra.

Ao avaliar uma mudança, prefira primeiro corrigir a integração, a configuração,
o empacotamento ou a qualificação da base existente. Introduza tecnologia nova
somente quando houver uma lacuna demonstrável e benefício suficiente para
compensar o custo de manutenção e o risco de regressão.

## Limite de escopo do ciclo de release

Ideias, mudanças de produto e novas funcionalidades podem ser propostas e
avaliadas durante as versões Alpha, sempre respeitando a prioridade de
estabilidade. A Beta 1 inicia o congelamento funcional do ciclo.

Da Beta 1 em diante, não introduza novos aplicativos, mudanças amplas de
arquitetura ou expansão do escopo do produto. Durante as Betas, aceite
refinamentos, estabilização e correções de bugs identificados. Aplicativos já
distribuídos também podem receber melhorias upstream quando o mantenedor
julgar explicitamente que elas fazem sentido para o Lyra e que o benefício é
compatível com o risco de regressão. Essa exceção não autoriza completar
silenciosamente partes incompletas do produto nem adicionar novos componentes.

### Exceção aprovada para o ciclo 1.0

No Desktop e no Server 1.0, o mantenedor autoriza programar melhorias durante
as Betas porque os ganhos esperados compensam os riscos. Cada melhoria ainda
deve ter benefício concreto registrado, impacto e risco avaliados, testes de
regressão proporcionais e plano de reversão. A autorização não dispensa os
gates, não permite promover com P0/P1 aberto e termina no início da RC1. Novos
aplicativos ou mudanças amplas de arquitetura continuam exigindo decisão
explícita do mantenedor.

A partir do início da RC1 — incluindo todas as RCs e a versão estável — pacotes
já distribuídos podem receber correções de bugs, de travamentos e de
segurança, além de melhorias de performance quando forem consideradas
críticas. Não aceite novas funcionalidades, melhorias funcionais amplas nem
atualizações que ampliem o comportamento ou o escopo; essas mudanças devem
aguardar o próximo ciclo.

Se uma solicitação feita após o início da Beta 1 contrariar esses limites,
alerte o mantenedor antes de agir. Fora da melhoria de aplicativo aprovada pelo
mantenedor durante uma Beta e das correções permitidas em pacotes já
distribuídos, uma exceção só deve avançar quando for necessária para corrigir
um problema bloqueante e vier acompanhada de análise de risco, testes de
regressão e plano de reversão.

Antes de executar uma solicitação que possa reduzir a estabilidade, a
confiabilidade, a segurança, a compatibilidade, a capacidade de recuperação
ou a previsibilidade do sistema:

1. alerte explicitamente o mantenedor sobre o risco e seu impacto provável;
2. proponha uma alternativa mais segura quando ela existir;
3. identifique as validações, o plano de reversão e as evidências necessárias;
4. não faça a mudança arriscada silenciosamente.

Não trate toda mudança como perigosa por padrão. O alerta deve ser concreto,
proporcional ao risco e fundamentado no comportamento técnico esperado.

## Significado dos estágios de release

O Lyra não promove uma versão porque chegou a uma data. O lançamento pode ser
adiado pelo tempo necessário; qualidade e confiança têm precedência sobre o
cronograma. Perfeição não é o critério de saída. O produto deve ser previsível
e “chato de tão confiável”: permitir uso cotidiano prolongado sem travar, sem
degradar, sem exigir administração recorrente e sem chamar atenção para o
próprio sistema.

- **Alpha:** desenvolvimento e avaliação das funcionalidades previstas para o
  ciclo. Mudanças ainda podem ocorrer, desde que justificadas e qualificadas.
- **Beta:** congelamento funcional do produto. Serve para encontrar e corrigir
  defeitos, regressões, problemas de desempenho, integração, acessibilidade e
  tradução do escopo já existente. Aplicativos já distribuídos podem receber
  melhorias upstream quando o mantenedor as aprovar explicitamente por fazerem
  sentido para o Lyra. Não serve para completar silenciosamente produto
  incompleto, adicionar aplicativos ou ampliar a arquitetura.
- **RC:** o produto já deve satisfazer os critérios de estabilidade. A RC é uma
  verificação final do candidato completo, dos artefatos e do processo de
  publicação. Se aparecer um defeito não trivial, interrompa a promoção, volte
  à estabilização e gere outra RC; não reduza os critérios para preservar uma
  data. A partir da RC1, atualize pacotes já distribuídos somente para corrigir
  bugs, travamentos, problemas de segurança ou performance crítica, nunca para
  adicionar funcionalidades.
- **Estável:** conteúdo funcional congelado, mas o sistema não é imutável: a
  série publicada continua mantida e atualizável. Pacotes já distribuídos podem
  receber correções de bugs, de travamentos, de segurança e melhorias de
  performance crítica quando necessárias, mas não novas funcionalidades,
  melhorias funcionais ou ampliação de comportamento. Essas mudanças pertencem
  ao próximo ciclo e devem percorrer novamente Alpha, Beta e RC.
