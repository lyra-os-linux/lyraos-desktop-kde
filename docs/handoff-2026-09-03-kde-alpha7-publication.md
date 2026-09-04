# Handoff — publicação KDE 1.1 Alpha 7

Data da pausa: 2026-09-03.

## Objetivo e restrições

- Publicar a edição KDE em:
  `https://sourceforge.net/projects/lyra/files/releases/1.1/alpha7/kde/`.
- Não alterar pacotes compartilhados nem o conteúdo da ISO candidata. A edição
  GNOME já foi publicada com esses pacotes.
- A ausência do tema GRUB do Lyra na edição KDE é intencional. O KDE não
  empacota esse tema e não deve passar a empacotá-lo.

## ISO candidata preservada

- Diretório de trabalho:
  `/tmp/lyraos-desktop-kde-alpha7-final-1001`
- ISO:
  `/tmp/lyraos-desktop-kde-alpha7-final-1001/iso/LyraOS-Desktop-KDE-1.1-alpha.7-x86_64.iso`
- Tamanho: `2982336512` bytes.
- SHA-256:
  `b22b9359a4313eca6d81e780f4445b2d9b32cf9b894ad5943bdc4b38d57cec7b`
- Commit gravado no manifesto da ISO:
  `1901a7108a4b7bd63db947fd3f3e21f81811c01b`.
- Disco da instalação validada:
  `/tmp/lyraos-desktop-kde-alpha7-final-1001/vm/lyra-os-install.qcow2`.

A ISO passou três leituras completas dos blocos comprimidos/SquashFS e a
auditoria de segurança não encontrou problemas.

## Evidências aprovadas

Diretório: `/tmp/kde-alpha7-evidence`.

- `obs-repositories-result.json`: `passed`; verificação somente leitura dos
  três projetos de release e 23 pacotes-fonte.
- `first-boot-result.json`: `passed`.
- `uefi-secure-boot-result.json`: `passed`; UEFI, Secure Boot, ESP e
  `BOOTX64.EFI` confirmados.
- `rollback-result.json`: `passed`, fase `rollback-verified`, 14/14 checks.
- `qemu-kde-alpha7.json`: cenário de hardware virtual `passed`.
- `hardware-matrix-result.json`: `passed`, ligado ao nome e SHA-256 exatos da
  ISO. Registra explicitamente que não houve hardware físico e que o retorno
  de S3 passou com VGA padrão; VirtIO VGA não reativou a tela.
- Áudio virtual: controlador Intel HDA detectado; `speaker-test` estéreo passou
  e o WAV capturado tem 1.006.160 bytes em
  `/tmp/lyraos-desktop-kde-alpha7-final-1001/vm/kde-audio.wav`.
- Desligamento ACPI, reboot, rede, atualização, rollback e suspensão/retorno
  foram exercitados de verdade.

## Pendências exatas

Restam somente duas evidências:

1. `live-session-result.json`: o arquivo atual é inválido apenas porque o
   helper antigo consultava `sddm.service`. Reexecutar na sessão live com o
   helper corrigido, que consulta `display-manager.service`.
2. `installer-result.json`: a instalação anterior terminou e iniciou
   corretamente, mas o frontend grava `~/lyra-installer-result.json` somente
   no usuário live. O arquivo não foi copiado antes do reboot e não existe no
   sistema instalado. Fazer uma instalação descartável e copiar o JSON antes
   de reiniciar. Não repetir os demais testes.

A VM live descartável foi encerrada antes do início da instalação. Seus
arquivos permanecem em `/tmp/lyraos-desktop-kde-alpha7-live-final`:

- disco vazio: `install.qcow2`;
- NVRAM Secure Boot: `ovmf-vars.bin`.

## Retomada amanhã

O receptor local é `/tmp/lyra_kde_upload_server.py`, porta `18081`. Ele serve
o helper corrigido em `/lyra-live-smoke` e recebe os JSONs em
`/live-session-result.json` e `/installer-result.json`. Confirmar que está no
ar ou reiniciá-lo com:

```console
python3 /tmp/lyra_kde_upload_server.py
```

Reabrir a VM descartável com a mesma ISO e Secure Boot. Na sessão live, cujo
teclado é `en-US`, abrir o Konsole e executar como `liveuser`, sem `sudo` e sem
`pkexec`:

```console
curl -fsS -o /tmp/lyra-live-smoke http://10.0.2.2:18081/lyra-live-smoke
python3 /tmp/lyra-live-smoke --output live-session-result.json
curl -f -T live-session-result.json http://10.0.2.2:18081/live-session-result.json
```

Validar no host que `status` é `passed` e todos os checks passaram. Em seguida,
concluir uma única instalação descartável. Na tela final, antes de qualquer
reboot, abrir/usar o terminal da sessão live e enviar:

```console
curl -f -T ~/lyra-installer-result.json http://10.0.2.2:18081/installer-result.json
```

Confirmar no host `status: passed`, `mode: installer`, `service-exit: passed`
e `completed-event: passed`. Depois a VM descartável pode ser encerrada sem
reiniciar o sistema instalado.

## Alterações locais de infraestrutura de teste

O repositório `lyraos-desktop-kde` está deliberadamente sujo com quatro
arquivos, sem mudança em pacotes:

- `kiwi/root/usr/bin/lyra-live-smoke`: usa a unidade canônica
  `display-manager.service`.
- `kiwi/root/usr/bin/lyra-update-smoke`: aceita corretamente edições que não
  empacotam o tema GRUB, desde que o GRUB também não o referencie.
- `tests/test_live_smoke.py` e `tests/test_update_smoke.py`: cobrem as duas
  correções.

Os 11 testes focados passaram. Após obter as duas evidências finais, rodar a
suíte completa, revisar o diff e fazer commit/push dessas correções de helper.
Não reconstruir a ISO por causa delas: são correções externas de validação e
não alteram o sistema candidato.

## Geração e upload

O uploader já existe em `scripts/upload-kde-alpha7-sourceforge.sh`, usa o
layout release-first e não faz teste de download. Antes do upload:

1. gerar o manifesto/artefatos finais com todas as sete evidências;
2. como a ISO foi criada no commit `1901a71`, usar uma worktree limpa nesse
   commit para o `artifact-manifest`, evitando rejeição por source mismatch;
3. executar o check-only duas vezes;
4. executar o uploader em terminal visível para a autenticação SSH.

Não publicar até os sete gates formais estarem verdes.

## Retomada em 2026-09-04

As duas evidências pendentes foram concluídas usando a mesma ISO candidata,
sem reconstrução ou alteração de conteúdo:

- `live-session-result.json`: `passed`, com 14/14 checks aprovados usando a
  unidade canônica `display-manager.service`;
- `installer-result.json`: `passed`, modo `installer`, com
  `service-exit: passed` e `completed-event: passed`.

O primeiro boot da VM descartável exigiu uma nova cópia do template NVRAM
Secure Boot porque a cópia anterior continha uma entrada de dispositivo PCI
obsoleta e caiu em PXE. O NVRAM anterior foi preservado. A ISO iniciou com a
topologia VirtIO padrão, a instalação terminou normalmente e a evidência foi
copiada antes do reboot. A VM foi encerrada sem iniciar o sistema instalado.

Os sete resultados exigidos por `image-build.toml` estão presentes e verdes
em `/tmp/kde-alpha7-evidence`. A suíte completa do repositório passou com 198
testes. O próximo passo é versionar as correções dos helpers, gerar o bundle
final em uma worktree limpa no commit da ISO (`1901a71`), executar o
`check-only` duas vezes e somente então publicar.
