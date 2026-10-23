# Lyra OS KDE Plasma 16.1 RC 1 “Odisseia” — notas de lançamento

Candidata de lançamento da edição KDE Plasma do Lyra OS 16.1 sobre **openSUSE
Leap 16.1**. Por decisão do mantenedor em 23/10/2026 (ADR 0017 do
`lyraos-desktop`), a edição KDE Plasma foi retomada e sai da Alpha 7 diretamente
para a RC 1, sem Beta. Ela não tem data de lançamento: será publicada quando
passar pelo mesmo gate da RC do Desktop GNOME, que segue seu próprio
cronograma. A RC 1 inicia o congelamento estrito: a partir dela só entram
correções de bugs, travamentos, segurança e performance crítica em pacotes já
distribuídos.

A identidade técnica é `16.1-rc.1`, arquivo `LyraOS-Desktop-KDE-16.1-rc.1-x86_64.iso`. A Alpha 7 foi publicada
como `1.1-alpha.7`; desde 19/10/2026 a numeração segue o Leap (`1.1` → `16.1`).
Estas notas acompanham a candidata; o commit, o SHA-256 e a decisão de GO são
preenchidos no bundle publicado.

## Mudanças desde a Alpha 7

- Vega atualizado: o baseline do projeto OBS `vega` é o mesmo do Desktop GNOME
  RC 1 (vegad 5.1.38, vega-cli, vega-web).
- Vega Qt 0.1.7: a interface passou a ser traduzida, com inglês como idioma-fonte e catálogos `pt-BR` e `es-ES`; os rótulos de serviços e hardware vêm do vegad no idioma da interface, e as datas de backup seguem o locale.
- Versão: identidade do produto alinhada ao Leap (`1.1` → `16.1`).
- Assinatura: o checksum da ISO passa a ser assinado pela chave oficial de
  release, como em toda candidata a partir da Beta.

## Escopo e limites

- Instalação nova apenas. A atualização de uma instalação Alpha 7 para a RC 1
  não é suportada; reinstale.
- Qualificação somente em máquinas virtuais; nenhum hardware físico faz parte
  do gate desta candidata.
- O controle parental, a verificação etária e o sinal etário para aplicativos
  não fazem parte da 16.1; a candidata não retém evidência etária (ECA
  Digital).
- RAID, LVM, particionamento manual e instalação lado a lado continuam fora
  do cenário coberto.
- Idiomas: `en-US`, `pt-BR` e `es-ES`, com `en-US` como fallback explícito.

## Qualificação obrigatória

A RC 1 repete o gate de `../release-gate.md` na ISO exata, em VM QEMU/KVM e
sobre o Leap 16.1: sessão live, instalação UEFI com NVRAM e Secure Boot, BIOS
legado e UEFI sem variáveis EFI, primeiro boot, rollback e `i18n`, além do
resultado `obs-repositories` do health check de release. Um defeito não
trivial interrompe a promoção e gera a RC 2; os critérios não são reduzidos.

## Integridade

Verifique o checksum com `sha256sum -c LyraOS-Desktop-KDE-16.1-rc.1-x86_64.iso.sha256` e a assinatura destacada
`LyraOS-Desktop-KDE-16.1-rc.1-x86_64.iso.sha256.asc` com a chave oficial de release (impressão digital
`01B6 3EED BE6B 0791 26A0 116E FA73 53A1 31EC EFEB`, publicada em
`docs/release-signing-key.asc`). Pacotes e repositórios continuam exigindo
assinatura válida.
