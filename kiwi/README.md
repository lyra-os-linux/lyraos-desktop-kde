# Imagem KIWI do Lyra OS

`config.xml` é a descrição canônica da ISO live/instalável da Beta 2. A
imagem usa openSUSE Leap 16, GNOME, Btrfs/Snapper e o Lyra Installer em
Rust/Tauri como único instalador.

## Instalador na sessão live

O RPM `lyra-installer` fornece:

- `/usr/bin/lyra-installer`, executado como `liveuser`;
- `/usr/libexec/lyra-installer-service`, iniciado por `pkexec` somente após
  a confirmação do plano destrutivo;
- desktop entry, ícone, policy e regra polkit.

O overlay também fixa `lyra-install-lock`, launcher e ícone, mantidos idênticos
às fontes do RPM por testes automatizados. Assim, uma versão publicada
anteriormente não quebra o autostart ou a identidade visual enquanto o novo
RPM ainda está sendo promovido.

O overlay `root/etc/xdg/autostart/lyra-installer-autostart.desktop` abre a
interface depois do login automático no GNOME. A interface inteira nunca roda
como root. O sistema instalado remove conta, autostart, binários e privilégios
exclusivos da sessão live antes do primeiro snapshot.

Não existe segundo instalador, launcher alternativo ou regra polkit de
fallback na Beta 2.

## Build e teste

Dentro da sessão live, gere a evidência automatizada da #47 com:

```bash
lyra-live-smoke --output live-session-result.json
```

Repita sem conectividade usando `--expect-offline`. Entradas de journal com
prioridade 0..3 bloqueiam o resultado até serem corrigidas ou revisadas e
associadas explicitamente a uma issue/workaround com
`--acknowledge-journal`. O helper registra somente estado técnico, sem SSID ou
credenciais, e é removido do sistema-alvo pelo Lyra Installer.

No sistema instalado, execute o ensaio de atualização e rollback da #46. O
estado fica na ESP, fora dos snapshots Btrfs, para sobreviver ao rollback:

```bash
sudo lyra-update-smoke baseline --output baseline.json
sudo lyra-update-smoke update --output update.json
sudo reboot
sudo lyra-update-smoke verify-updated --output updated.json
sudo lyra-update-smoke prepare-rollback --output rollback-prepared.json
sudo reboot
sudo lyra-update-smoke verify-rollback --output rollback-result.json
```

Somente a última fase pode produzir `"status": "passed"` para o gate. As
fases anteriores produzem `incomplete`, e uma queda de rede, encerramento do
processo ou falha do Zypper deixa um estado persistente que não pode ser
validado silenciosamente. `baseline --restart` inicia deliberadamente um novo
ensaio; `--rollback-snapshot N` seleciona um snapshot inicial diferente quando
necessário. O comando `prepare-rollback` altera o subvolume padrão e deve ser
usado apenas na VM dedicada ao teste.

Para testar interrupção, desconecte a rede enquanto a fase `update` estiver
executando. Ela deve terminar com código diferente de zero, JSON `failed` e
estado `update-failed`; `verify-updated` também deve recusar esse estado.
Reconecte a rede e use `baseline --restart` somente depois de revisar o erro e
confirmar que a nova baseline passa em `zypper verify`, serviços, repositórios,
initramfs, GRUB e Snapper. Uma finalização abrupta pode deixar
`update-started` ou `update-running`, que também não são estados aprováveis.

Use o helper versionado:

```bash
./kiwi/test/build-and-run-vm.sh
```

Ele valida metadados, constrói a imagem, cria disco e estado UEFI descartáveis
e inicia a VM em QEMU/KVM. Cada chamada encerra a instância anterior criada
pelo helper e apaga seu disco/NVRAM. Para validar o sistema instalado, reinicie
o guest na mesma janela: a ISO só é priorizada no primeiro boot da execução.

O modo padrão é de desenvolvimento: compila o workspace `installer/` e fixa
seus binários na descrição KIWI temporária, com proveniência explícita dentro
da imagem. Para validar um candidato publicável, use
`--published-installer`; esse modo consome os RPMs assinados do instalador e
do Vega Qt no OBS. Para qualificar uma mudança local do instalador usando o
Vega Qt já publicado, use `--published-vega-qt`. Essa combinação produz uma
imagem de integração/teste. Uma imagem marcada como `local-installer-build`
não é artefato de release.

Consulte `docs/image-builds.md` para a fronteira
GitHub/OBS/SourceForge e `docs/installer-architecture.md` para o pipeline do
instalador.

Antes de publicar a Beta 2, o gate #11 deve comprovar instalação, primeiro
boot, UEFI, Secure Boot, Btrfs/Snapper, rollback, usuário/sudo e ausência de
artefatos da sessão live no target. A presença do instalador na ISO não
substitui esse teste destrutivo.

## Repositórios

Durante o build, os repositórios OBS Lyra, Vega e Fina usam prioridades 1, 2
e 3 para selecionar os pacotes revisados. O instalador rebaixa esses três
repositórios para prioridade 90 no target; os repositórios oficiais do Leap,
com prioridades 20 e 21, vencem futuras resoluções de nomes iguais. O gate
`scripts/obs-release.py validate` verifica os dois lados desse contrato.

O arquivo `config.xml` contém a lista única de pacotes. Não mantenha uma lista
paralela em scripts ou documentação.
