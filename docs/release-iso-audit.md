# Auditoria de ISOs publicadas

Toda ISO candidata ou já publicada deve ser extraída integralmente e auditada
contra vazamentos do ambiente de build. O relatório registra o SHA-256, o
conteúdo de `/home` e `/root`, caches, logs e achados críticos sem copiar o
conteúdo potencialmente secreto para a evidência.

```sh
python3 scripts/audit-release-iso.py \
  /caminho/lyra-os.x86_64-1.0-alpha.7.iso \
  --output evidence/alpha5-iso-audit.json
```

O comando retorna zero apenas quando não encontra homes inesperados, caminhos
do host, nomes de arquivos sensíveis ou conteúdo com formato de chave/token.
`xorriso` e `unsquashfs` são obrigatórios. Os relatórios podem ser publicados;
o rootfs extraído é temporário e removido ao final.

Para a auditoria retrospectiva da Alpha 1 à Alpha 5, baixe cada ISO do diretório
público oficial, confira o checksum publicado quando disponível, execute o
comando acima e preserve um relatório por versão. Um resultado `fail` bloqueia
novas releases e exige retirada do artefato afetado e avaliação do incidente.

## Resultado retrospectivo em 25/08/2026

Os arquivos disponíveis no diretório público oficial foram baixados e seus
checksums publicados foram verificados antes da extração integral. Os
artefatos Alpha 1 e Alpha 2 foram apagados e, portanto, não podem ser
auditados retrospectivamente nem classificados como aprovados.

| Versão | Tamanho | SHA-256 | Resultado | Achados críticos |
|---|---:|---|---|---:|
| Alpha 1 | — | — | apagada; não auditável | — |
| Alpha 2 | — | — | apagada; não auditável | — |
| Alpha 3 | 1.605.474.304 | `9b177832f733e2a56d5c94f4329537f82cb56391dbece33b04927a0725310d50` | falhou | 79 |
| Alpha 4 | 2.042.578.944 | `fedf986ef4d14a5e12e4828df9eaaff28a00ff457fa1fdbc18f9a7c5a9d61e53` | falhou | 78 |
| Alpha 5 | 2.162.642.944 | `72fa2b0481e6053d5291faf5166dae44ef7d9a071ba79451a689d0fca00963f2` | falhou | 83 |

As três imagens disponíveis contêm caminhos absolutos do host de build, como
`/home/rbrito/Git/Lyra/kiwi/.kiwi/test-1001`, em arquivos do GRUB, bytecode
Python, logs do Zypper e outros arquivos empacotados. A varredura automatizada
não encontrou conteúdo com formato de chave privada, token ou credencial, nem
um home inesperado além de `/home/liveuser`; isso não elimina a exposição de
identidade e topologia do ambiente de build, que permanece bloqueadora.

Os relatórios completos e sanitizados estão em
[`evidence/release-iso-audit/`](../evidence/release-iso-audit/). Nenhum
artefato remoto foi alterado ou removido durante esta auditoria local.
