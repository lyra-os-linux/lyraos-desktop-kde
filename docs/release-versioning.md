# Versionamento de releases do Lyra OS

## Política oficial

O Lyra OS usa versionamento próprio no formato `MAJOR.MINOR.PATCH`. A versão
identifica o produto e é independente da versão do openSUSE Leap usada como
base.

- `MAJOR`: nova geração do Lyra OS;
- `MINOR`: evolução relevante e compatível dentro da geração;
- `PATCH`: correção, manutenção ou respin da mesma release.

Uma versão nova do Leap pode motivar uma release minor, mas não determina seu
número. Datas pertencem ao roadmap ou ao `BUILD_ID`, nunca à versão comercial.

## Geração atual

- geração: **Lyra OS 1 — Odisseia**;
- primeira versão estável planejada: **Lyra OS 1.0 — Odisseia**;
- base tecnológica da 1.0: **openSUSE Leap 16.1**;
- arquitetura inicial: **x86_64**.

O codename identifica toda a geração: qualquer release `1.x` continua sendo
Odisseia. Desktop e Server compartilham essa identidade, embora possuam gates e
ciclos de publicação independentes.

## Pré-releases

| Comunicação | Identificador técnico |
|---|---|
| Lyra OS 1.0 Alpha 1 | `1.0-alpha.1` |
| Lyra OS 1.0 Beta 1 | `1.0-beta.1` |
| Lyra OS 1.0 RC1 | `1.0-rc.1` |
| Lyra OS 1.0 | `1.0` |

## Fonte canônica e metadados

`release.toml` separa versão, estágio, geração, base e identidade do artefato.
`scripts/release.py render` deriva o KIWI, a interface do instalador e
`/usr/lib/lyra-os/release`; arquivos gerados não devem ser editados à mão.

`VERSION_ID` contém a versão do produto, `VERSION_CODENAME` contém
`odisseia`, `BUILD_ID` identifica a data do build e `IMAGE_VERSION`
identifica a candidata completa.

ISOs usam `LyraOS-Desktop-1.0-alpha.7-x86_64.iso` em desenvolvimento e
`LyraOS-Desktop-1.0-x86_64.iso` na release estável.

## Compatibilidade, promoção e suporte

Tags, evidências e release notes já publicados com versões calendário continuam
como registros históricos. O upgrade deve aceitá-los somente como origens
legadas explícitas; nenhuma candidata nova usa o esquema antigo.

Uma versão é publicada quando passa pelos critérios de qualidade, não porque uma
data chegou. O suporte da base openSUSE, o suporte de uma release Lyra e o ciclo
da geração 1.x são distintos. Não há promessa de EOL ou suporte prolongado do
Lyra sem política formal e sustentável.

O Lyra OS 1.0 terá suporte comunitário, sem prazo contratual ou EOL prometido.
O lançamento está previsto para **20 de fevereiro de 2027**, sempre condicionado
ao gate completo. Artefatos legados serão preservados e republicados com nomes
semânticos, mantendo checksums, assinaturas e proveniência verificáveis.
