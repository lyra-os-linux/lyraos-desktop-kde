# Handoff — KDE, Vega Qt e nova ISO de teste

Data da pausa: 2026-08-29.

## Estado concluído

- O KDE e o XFCE foram definidos pelo mantenedor como flavors oficiais do
  Lyra OS, não experimentais.
- A documentação do KDE foi atualizada e publicada no commit `88d2646`.
- A documentação do XFCE foi atualizada e publicada no commit `3daa1f6`.
- O Vega Qt recebeu correções para:
  - não bloquear a abertura enquanto consulta o Secret Service;
  - acompanhar em tempo real a troca de tema claro/escuro do Plasma;
  - preservar o override `--dark`.
- A correção principal do Vega Qt está no commit `949e66c`.
- Os metadados de empacotamento estão no commit `0dd719e`.
- O pacote OBS `home:rodrigosbrito:vega/vega-qt` foi atualizado; o build para
  `openSUSE_Leap_16.1/x86_64` terminou com sucesso e o repositório chegou ao
  estado `published`.

## Ponto da pausa

O build da nova ISO KDE foi iniciado com:

```bash
./kiwi/test/build-and-run-vm.sh --build-only --published-installer
```

O helper parou antes do KIWI porque `sudo` precisava de autenticação em um
terminal interativo. Nenhuma nova ISO foi gerada nessa tentativa.

Antes de retomar, autenticar no terminal:

```bash
sudo -v
```

Em seguida, executar novamente o build acima no repositório
`lyraos-desktop-kde` e acompanhar até as validações finais.

## Publicação pendente

- Validar que a ISO contém o RPM novo do `vega-qt` proveniente do OBS.
- Publicar a ISO KDE em um destino de teste próprio.
- Não usar diretamente o destino Desktop Alpha 7 herdado pelos scripts, pois
  isso pode sobrescrever a ISO GNOME.
- Baixar novamente o artefato publicado e conferir o SHA-256 antes de entregar
  o link ao mantenedor.

## Estado esperado dos repositórios

- `vega-qt`: `main` em `0dd719e`, sincronizada com o remoto.
- `lyraos-desktop-kde`: `main` em `88d2646` antes deste handoff.
- `lyraos-desktop-xfce`: `main` em `3daa1f6`, sincronizada com o remoto.
