# Registros de decisão do Lyra OS

Os ADRs deste diretório registram decisões aceitas dos componentes do Lyra. Uma decisão
nova não apaga a anterior: cria outro ADR que a substitui e aponta para ela.

| ADR | Decisão | Estado |
|---|---|---|
| [0001](0001-tauri-frontend-unprivileged.md) | Tauri/WebKitGTK como frontend sem privilégio | Aceita |
| [0002](0002-json-lines-privileged-protocol.md) | Protocolo JSON Lines e plano versionado | Aceita |
| [0003](0003-storage-tools-behind-typed-operations.md) | Ferramentas nativas atrás de operações tipadas | Aceita |
| [0004](0004-rust-installer-only-in-beta-2.md) | Instalador Rust como único caminho da Beta 2 | Aceita |
| [0005](0005-guided-swap-policy-and-plan-v2.md) | Política guiada de swap e plano versão 2 | Aceita |
| [0006](0006-btrfs-mount-policy-and-plan-v3.md) | Política Btrfs global e NOCOW granular, plano versão 3 | Aceita |
| [0007](0007-lyra-upgrade-trust-boundaries.md) | Fronteiras, protocolo e persistência do Lyra Upgrade | Migrada para `lyraos-desktop-updater` |
| [0008](0008-private-age-signal-and-parental-supervision.md) | Sinal etário privado e supervisão parental | Proposta — bloqueada pela #106 |
| [0009](0009-server-edition-own-repository.md) | Edição Server migra para repositório próprio (lyraos-server) | Aceita |
| [0010](0010-welcome-own-repository.md) | Lyra Welcome migra para repositório próprio (lyraos-desktop-welcome) | Aceita |
| [0011](0011-upgrade-own-repository.md) | Lyra Upgrade migra para repositório próprio (lyraos-desktop-updater) | Aceita |
| [0012](0012-linuxtoys-own-repository.md) | Empacotamento do LinuxToys migra para repositório próprio (lyraos-desktop-linuxtoys) | Aceita |
| [0013](0013-zed-editor-baseline-package.md) | Zed passa a ser empacotado (zededitor) e instalado por padrão na ISO | Aceita |
| [0014](0014-vscode-repository-registration-only.md) | VS Code entra só como registro do repositório oficial da Microsoft (vscode-repo) | Aceita |
| [0015](0015-optional-android-windows-compatibility.md) | Compatibilidade Android e Windows permanece opcional e desacoplada da ISO | Substituída pela ADR 0016 |
| [0016](0016-defer-android-windows-next-release.md) | Compatibilidade Android e Windows é adiada para o release futura | Aceita |

Mudanças incompatíveis no formato do plano precisam incrementar
`INSTALL_PLAN_SCHEMA_VERSION`, atualizar o ADR 0002 por meio de um novo ADR e
adicionar testes de rejeição/compatibilidade antes de chegar ao serviço root.
