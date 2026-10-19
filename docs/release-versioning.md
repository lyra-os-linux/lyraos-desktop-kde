# Versionamento de releases do Lyra OS

## Política oficial

Desde a decisão do mantenedor em 13/10/2026, a versão do Lyra OS segue a
versão do openSUSE Leap usado como base: o Lyra OS construído sobre o Leap
`16.1` é o Lyra OS `16.1`. O formato é `MAJOR.MINOR[.PATCH]`.

- `MAJOR.MINOR`: idêntico ao Leap base (`16.1`, `16.2`, ...);
- `PATCH`: correção, manutenção ou respin da mesma release, de uso
  exclusivo do Lyra (o Leap não tem patch level).

Uma versão nova do Leap determina a próxima versão minor do Lyra. Datas
pertencem ao roadmap ou ao `BUILD_ID`, nunca à versão comercial.

Até 18/10/2026 as edições eram numeradas `1.1`, com versionamento independente
do Leap. As imagens `1.1-alpha.*` já publicadas permanecem como registro
histórico e não são renomeadas; nenhuma candidata nova usa o esquema antigo.

## Geração atual

- geração: **Lyra OS 16 — Odisseia**;
- primeira versão estável planejada: **Lyra OS 16.1 — Odisseia**;
- base tecnológica da 16.1: **openSUSE Leap 16.1**;
- arquitetura inicial: **x86_64**.

O codename identifica toda a geração: qualquer release `16.x` continua sendo
Odisseia. Todas as edições Desktop compartilham essa identidade; a edição
KDE está pausada (o foco da 16.1 é o GNOME) e acompanha a numeração sem
build próprio até ser retomada.

## Pré-releases

| Comunicação | Identificador técnico |
|---|---|
| Lyra OS 16.1 Alpha 1 | `16.1-alpha.1` |
| Lyra OS 16.1 Beta 1 | `16.1-beta.1` |
| Lyra OS 16.1 RC1 | `16.1-rc.1` |
| Lyra OS 16.1 | `16.1` |

## Fonte canônica e metadados

`release.toml` separa versão, estágio, geração, base e identidade do artefato.
`scripts/release.py render` deriva o KIWI, a interface do instalador e
`/usr/lib/lyra-os/release`; arquivos gerados não devem ser editados à mão.

`VERSION_ID` contém a versão do produto, `VERSION_CODENAME` contém
`odisseia`, `BUILD_ID` identifica a data do build e `IMAGE_VERSION`
identifica a candidata completa. `LYRA_BASE_VERSION_ID` conserva a versão do
Leap base, que coincide com `MAJOR.MINOR` do Lyra.

ISOs usam `LyraOS-Desktop-KDE-16.1-rc.1-x86_64.iso` em candidatas e
`LyraOS-Desktop-KDE-16.1-x86_64.iso` na release estável.

## Compatibilidade, promoção e suporte

Tags, evidências e release notes já publicados com versões calendário ou com o
esquema `1.x` continuam como registros históricos. O upgrade deve aceitá-los
somente como origens legadas explícitas; nenhuma candidata nova usa os
esquemas antigos.

Uma versão é publicada quando passa pelos critérios de qualidade, não porque uma
data chegou. O suporte da base openSUSE, o suporte de uma release Lyra e o ciclo
da geração 16.x são distintos. Não há promessa de EOL ou suporte prolongado do
Lyra sem política formal e sustentável.

O Lyra OS 16.1 terá suporte comunitário, sem prazo contratual ou EOL prometido.
O lançamento está previsto para **5 de novembro de 2026**, sempre condicionado
ao gate completo. Artefatos legados serão preservados e republicados com nomes
semânticos, mantendo checksums, assinaturas e proveniência verificáveis.
