# PROMPT-LYRA-OS.md

## Contexto

Este documento é o prompt de implementação da distribuição **Lyra OS** —
projeto pessoal independente de Rodrigo Brito, não afiliado à W3TI.
Todas as decisões arquiteturais abaixo já foram tomadas e são
definitivas para a v1 (primeira ISO, codinome **Odisseia**). Não
questione ou reabra nenhuma delas — implemente exatamente como
especificado. Onde houver ambiguidade não coberta aqui, sinalize
explicitamente em vez de assumir.

## Identidade do produto

- **Nome oficial**: Lyra OS (usado em `/etc/os-release`, branding, site,
  documentação). "Lyra Linux" e "Lyra Enterprise Linux" são nomes
  históricos/descontinuados — não usar.
- **Slogan**: "Harmonia. Performance. Liberdade."
- **Codinome da release v1**: Odisseia (convenção de codinomes: obras
  literárias, não mais estrelas da constelação Lyra)
- **Mascote**: Lyro (chibi robot, capuz/capa escura, olhos azuis,
  headphones com logo de lira, estética cósmica/noturna) — usado em
  marketing e onboarding, não em componentes de sistema
- **Logo**: "L" estilizado em formato de lira, base curva tipo lua, 4
  cordas verticais, estrela de 4 pontas no canto superior direito

## Base do sistema

| Item | Decisão |
|---|---|
| Distribuição base | openSUSE Leap 16 |
| Kernel | `kernel-default` (padrão do Leap, sem customização) |
| Sistema de arquivos | Btrfs + Snapper (padrão do Leap, mantido) |
| Memória virtual | escolha no instalador: sem swap, partição swap de 8 GiB ou zram |
| Áudio | PipeWire (padrão do Leap, sem alteração) |
| Rede | NetworkManager (padrão do Leap, sem alteração) |
| Firewall | firewalld (padrão do Leap, sem alteração) |
| Arquitetura (v1) | x86_64 apenas — ARM64 fica para versão futura |
| Secure Boot | suporte padrão do Leap (shim assinado pela Microsoft) |
| Desktop environment | GNOME vanilla (edição inicial). KDE Plasma é
  uma segunda edição planejada para depois — não implementar nesta fase |
| Ferramenta de build de ISO | KIWI (ferramenta oficial de imagens do
  openSUSE) |

> Nota de arquitetura: o conceito de "Buffer de Estabilidade" (mitigação
> de instabilidade, herdado de uma fase anterior do projeto quando a base
> era Arch Linux) está **obsoleto e fora de escopo** — o modelo
> point-release do Leap já resolve esse problema. Não implementar
> nenhum mecanismo equivalente.

## Instalador

- **Lyra Installer nativo**, desenvolvido em **Rust + Tauri**, com interface
  HTML/CSS/JavaScript integrada ao WebKitGTK do sistema e ao restante do Lyra
  OS
- O frontend gráfico roda como o usuário da sessão live; somente o backend
  responsável por alterar discos e o sistema-alvo recebe privilégios via
  polkit. Não executar toda a interface como root
- Não usar instaladores de terceiros. A Beta 2 contém exclusivamente o Lyra
  Installer e só pode ser publicada depois da validação do candidato final
- Idioma/região: **en-US pré-selecionado**, com `pt-BR` e `es-ES` no Lyra
  Installer. Esses são os três únicos idiomas do Lyra OS 1.0; outros idiomas
  entram somente em um ciclo futuro com gate próprio. Os
  demais pacotes próprios têm gate integral mínimo em `en-US`/`pt-BR`
- Hostname padrão sugerido: `lyra-os`
- Conta de usuário: **root desabilitado**; usuário criado durante a
  instalação recebe privilégios administrativos via sudo (padrão
  desktop moderno)
- Sem tela de migração/onboarding especial no v1 além do fluxo padrão do
  Lyra Installer (o assistente de migração do Windows especificado
  separadamente é outro componente — não reimplementar aqui, apenas
  referenciar se necessário)

## Repositórios e canais de pacotes

**Repositórios de sistema habilitados por padrão:**
- Oficiais do Leap 16: OSS, Non-OSS e Updates
- Packman **Essentials** somente no desktop, limitado aos codecs multimídia

**Repositórios OBS do ecossistema Lyra** (hospedados em
build.opensuse.org, sob a conta `rodrigosbrito`):

| Repositório | Conteúdo | URL |
|---|---|---|
| `home:rodrigosbrito:lyra` | Pacotes gerais do Lyra (atualmente só tema) | https://build.opensuse.org/project/show/home:rodrigosbrito:lyra |
| `home:rodrigosbrito:vega` | Vega (também instalável standalone em outras distros) | https://build.opensuse.org/project/show/home:rodrigosbrito:vega |
| `home:rodrigosbrito:fina` | Fina (repositório próprio, dedicado) | https://build.opensuse.org/project/show/home:rodrigosbrito:fina |

**Canal de apps de terceiros (fora do ecossistema Lyra):**
- Flatpak (Flathub) como canal primário
- Sem equivalente ao AUR — não existe no openSUSE, não tentar recriar

**Codecs multimídia proprietários** (H.264, AAC etc.): fornecidos pelo Packman
Essentials no desktop; não habilitar o repositório Packman completo.

**Drivers de GPU (NVIDIA)**: sem detecção/instalação automática no
instalador e sem driver proprietário embutido na ISO padrão. A Desktop
Alpha 5 deve oferecer no Vega uma instalação opcional pós-instalação, com
detecção de hardware compatível, confirmação explícita, verificação de Secure
Boot, snapshot Snapper anterior à mudança e instalação transacional dos
pacotes meta que mantêm kernel module, userspace e firmware sincronizados.

## Apps pré-instalados (v1)

- **Vega** (frontend GTK4), **Sheliak** (dock do GNOME) e **Fina**
  pré-instalados na v1. O Lyra Tour segue em validação com usuários de
  teste e **não entra no v1**.
- **GNOME Terminal** (`gnome-terminal`) como terminal padrão, com o
  **GNOME Console** (`gnome-console`) também pré-instalado como alternativa
- **Firefox** como navegador padrão
- **LibreOffice** na imagem padrão com traduções para en-US, pt-BR e es-ES
- **CUPS** + drivers comuns, pré-instalado e habilitado (impressão/scanner)
- **GNOME Software** removido da imagem padrão; o gerenciamento gráfico de
  pacotes fica centralizado no Vega
- Conjunto de apps GNOME padrão: **curadoria aplicada** — remover apps
  redundantes ou pouco usados do conjunto default do GNOME (definir
  lista exata na implementação, mantendo o essencial: Arquivos, Textos,
  Configurações, Câmera, etc.)
- **Sem onboarding de primeiro boot no v1** — usuário cai direto no
  desktop após a instalação (o Lyra Tour, quando pronto, preencherá
  essa lacuna em versão futura)

## Branding e identidade visual

Fonte de verdade: repositório [lyra-os-linux/lyraos-desktop-theme](https://github.com/lyra-os-linux/lyraos-desktop-theme)
("Lyra Enterprise").

- **Abordagem**: Adwaita nativo para GNOME Shell, GTK4/libadwaita e
  GTK3 — não é um shell theme customizado à parte, é o Adwaita padrão
  com ícones e wallpapers da marca
- **Tema de ícones**: `Lyra-Enterprise-Icons` (vetorial, com fallback
  completo para Adwaita)
- **Wallpapers**: variantes dark e light, PNG + JPEG XL, 3840×2160
- **GRUB 2**: tema customizado com fundo Full HD e menu de boot Lyra
- **Plymouth**: tema de boot com o mesmo fundo/logo do GRUB
- **Fastfetch/Neofetch**: configs com logo ASCII da marca e paleta de
  cores oficial
- **GDM (tela de login): fora de escopo.** Decisão explícita — o GDM
  mantém o Adwaita padrão, sem branding Lyra. Não criar pacote nem
  etapa separada para isso.
- **Requisito**: GNOME 48 ou superior
- **Instalação**: via pacote RPM através do repositório OBS
  (`home:rodrigosbrito:lyra`), usando o fluxo de `install-rpm.sh` do
  repositório Lyra-Theme como referência de empacotamento
- Tanto a variante **dark** quanto a **light** devem ser instaladas
  juntas (ambas ficam disponíveis; a flag de instalação só define qual
  fica ativa por padrão via `color-scheme`)

**Paleta oficial** (dark-slate suave, "enterprise", substitui a paleta
antiga vibrante azul-safira→violeta):
- Dark: base `#16191d`/`#1c2025`, tons `#262b3d`, `#1e2b39`
- Light: base `#f4f5f7`/`#fcfcfd`, acento lavanda-azulado `#ced3f3`

## Atualizações do sistema

- Mecanismo exposto pelo Vega: **`zypper dup`** (distribution upgrade,
  recomendado para Leap) — não usar `zypper update`/`patch` tradicional
- **Snapshots do Snapper**: gerados automaticamente pelo Snapper em
  operações do zypper (comportamento padrão), mas **não expostos na UI
  do Vega no v1** — reversão de snapshot é feita apenas pelo boot menu
  do GRUB (botão de pânico já especificado em outro documento)
- **Upgrades de ponto de versão** (ex: 16.0 → 16.1): antes de liberar
  como seguro para os usuários, é necessário atualizar os repositórios
  OBS do Lyra (`lyra`, `vega`, `fina`) para incluir o novo
  alvo de build do Leap, testar, e só então anunciar a migração. Uma
  ideia em avaliação (não obrigatória para o v1) é um módulo do Vega
  que envolva o `opensuse-migration-tool` oficial, verificando primeiro
  se os repositórios do Lyra já suportam a versão-alvo antes de permitir
  o upgrade.

## Diagnóstico e telemetria

- **`lyra-report`**: ferramenta de relatório de diagnóstico/bug, gerada
  **apenas sob demanda do usuário**
- **Sem telemetria automática** de qualquer tipo no v1

## CI/CD e release

- Pipeline de CI para refresh mensal da ISO
- GRUB panic button (reversão via boot menu, ver Snapshots acima)
- Alpha 5 (14–28/08), Alpha 6 (28/08–11/09), Alpha 7 (11–25/09) e Alpha 8
  (25/09–13/10) são obrigatórias. Toda implementação funcional fecha até
  25/09; a Alpha 8 automatiza o gate e a semana de 06–13/10 é exclusiva para
  estabilização. P0/P1 interrompe
  a ampliação de escopo da Alpha corrente e nunca é transferido por calendário.
- A versão 1.0 oferece somente `en-US`, `pt-BR` e `es-ES`; todos os projetos e
  RPMs foram traduzidos e testados nos três idiomas. Outros idiomas são escopo
  de um ciclo futuro, com fallback `en-US`.
- Beta 1 começa somente após a última Alpha fechar todos os gates; 13/10/2026
  é a meta atual. Nas Betas da 1.0, melhorias estão autorizadas quando os
  ganhos compensarem os riscos, com benefício, impacto, testes de regressão e
  plano de reversão registrados. A RC1 inicia o congelamento estrito.
- O cronograma canônico e os critérios de promoção ficam em
  `docs/release-versioning.md`; o buffer final vai até aproximadamente 16 de
  fevereiro de 2027, sempre priorizando qualidade sobre prazo.
- O instalador opcional pós-instalação de driver NVIDIA via Vega foi concluído
  e validado na Desktop Alpha 5. A variante de ISO NVIDIA foi cancelada: o
  produto mantém uma única ISO Desktop.

## Fora de escopo nesta fase (não implementar)

- KDE edition (planejada, mas não faz parte do v1)
- Lyra Tour pré-instalado
- Onboarding/first-boot wizard
- Branding do GDM
- Telemetria/analytics
- Suporte ARM64
- Snapshots do Snapper na UI do Vega
- "Buffer de Estabilidade" ou qualquer mitigação de instabilidade
  equivalente à de distros rolling-release

## Checklist de validação

- [ ] ISO builda via KIWI, base Leap 16, kernel-default, Btrfs+Snapper, zram
- [ ] Lyra Installer em Rust/Tauri instala com en-US pré-selecionado, oferece
      en-US/pt-BR/es-ES na 1.0 e sugere o hostname `lyra-os`
- [ ] Root desabilitado; usuário criado tem sudo
- [ ] Repos habilitados por padrão: OSS/Non-OSS/Updates e Packman Essentials
- [ ] Repos OBS do Lyra (lyra/vega/fina) configurados e
      acessíveis, com os pacotes corretos instaláveis de cada um
- [ ] Flatpak/Flathub configurado como canal de apps de terceiros
- [ ] VLC e codecs FFmpeg/GStreamer completos pré-instalados no desktop
- [ ] Vega (GTK4), Sheliak e Fina pré-instalados e funcionais
- [ ] GNOME Terminal, GNOME Console, Firefox e CUPS pré-instalados
- [ ] LibreOffice pré-instalado e acompanhando o idioma selecionado
- [ ] GNOME Software e seus plugins ausentes da imagem padrão
- [ ] Curadoria de apps GNOME padrão aplicada (lista final documentada)
- [ ] Nenhum onboarding/wizard de primeiro boot presente
- [ ] Branding aplicado via Lyra-Theme: Adwaita + Lyra-Enterprise-Icons
      + wallpapers dark/light + GRUB + Plymouth + Fastfetch/Neofetch
- [ ] GDM permanece com Adwaita padrão, sem customização Lyra
- [ ] `/etc/os-release` reporta "Lyra OS" (não "Lyra Linux"/"Lyra
      Enterprise Linux")
- [ ] `zypper dup` funcional como mecanismo de atualização via Vega
- [ ] Snapshots do Snapper funcionando (automáticos), reversão
      disponível apenas via GRUB, sem tela correspondente no Vega
- [ ] `lyra-report` funcional sob demanda; nenhuma telemetria automática
      ativa
- [ ] Secure Boot funcional (shim padrão do Leap)
- [ ] Apenas imagem x86_64 gerada nesta fase
