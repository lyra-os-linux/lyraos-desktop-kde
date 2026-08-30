# Lyra OS 1.0 Alpha 7 “Odisseia” — notas de lançamento

O Lyra OS Alpha 7 é a primeira candidata do Desktop 1.0 baseada no
openSUSE Leap 16.1. Esta versão concentra-se na qualificação da nova base e
na preservação do comportamento estável já validado na Alpha 6.

Esta versão **Alpha** destina-se a testes e homologação. Não é recomendada
para produção nem para computadores com dados sem backup.

## Destaques

- base migrada de openSUSE Leap 16.0 para Leap 16.1;
- todos os RPMs Lyra, Vega e Fina consumidos pela imagem publicados para o
  alvo `openSUSE_Leap_16.1`;
- pilha GStreamer oficial compatível com a versão 1.28 da base, com suporte a
  H.264, H.265, AAC, AC-3, DTS, MPEG, VP8, VP9 e AV1;
- compilações completas de FFmpeg e VLC fornecidas pelo Packman Essentials;
- remoção de repositórios vazios ou sem alvo 16.1 da composição da imagem;
- manutenção de Btrfs, Snapper, Secure Boot e recuperação pelo GRUB como
  contratos bloqueantes da release.

## Qualificação obrigatória da nova base

A migração somente pode ser promovida depois de repetir, sobre a mesma ISO
candidata, os testes de sessão live, instalação, primeiro boot, atualização,
Secure Boot, NVIDIA, áudio, codecs, rollback e matriz de hardware. Nenhum P0
ou P1 pode permanecer aberto.

A tag `v27.02-alpha6` é a referência de reversão para a base Leap 16.0. Ela
não deve ser movida ou reescrita.

## Requisitos e instalação

- computador ou máquina virtual `x86_64` com firmware UEFI;
- 8 GiB de RAM recomendados;
- disco dedicado ou virtual com espaço suficiente;
- conexão de rede recomendada para atualizações.

Inicialize a ISO em modo UEFI, aguarde a sessão live e siga o Lyra Installer.
O cenário coberto continua sendo instalação em disco inteiro.

## Limitações conhecidas

- a migração 16.0 → 16.1 ainda não deve ser anunciada como segura para
  instalações existentes antes do gate específico de upgrade e rollback;
- RAID, LVM, particionamento manual e instalação lado a lado não possuem
  cobertura de release;
- a matriz de hardware físico permanece limitada;
- integrações com NVIDIA e controles parentais precisam ser requalificadas na
  base 16.1.

## Integridade

Arquivo esperado:

```text
LyraOS-Desktop-1.0-alpha.7-x86_64.iso
```

Verifique o checksum fornecido junto da ISO:

```sh
sha256sum -c LyraOS-Desktop-1.0-alpha.7-x86_64.iso.sha256
```

Conforme a ADR 0005, a Alpha 7 usa SHA-256 sem assinatura GPG destacada da
ISO. Pacotes e repositórios continuam obrigatoriamente assinados. A assinatura
destacada dos artefatos passa a ser obrigatória na Beta 1.

## Relato de problemas

Informe modelo da máquina ou configuração da VM, firmware, etapa da falha e
logs disponíveis. Não publique senhas, chaves ou dados pessoais. O contrato
de go/no-go está em `docs/release-gate.md`.
