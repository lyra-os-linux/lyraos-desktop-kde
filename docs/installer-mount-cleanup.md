# Limpeza da montagem temporária do instalador

`CreateSubvolumes` montava a raiz Btrfs e retornava imediatamente quando
`btrfs subvolume create`, `chattr` ou a preparação dos diretórios falhava.
Como o motor só desfaz operações concluídas, a montagem temporária ficava ativa.

Agora a operação reúne os passos posteriores à montagem em um bloco que retorna
um resultado e sempre tenta a desmontagem antes de devolvê-lo. O erro original
continua sendo o diagnóstico principal; se a desmontagem também falhar, os dois
erros aparecem, nessa ordem. Falha exclusiva da desmontagem também interrompe a
instalação. Falha do comando inicial de montagem não desmonta um recurso que a
operação não adquiriu.

O cancelamento continua cooperativo entre operações: um pedido durante a criação
aguarda a operação terminar e desmontar antes do próximo checkpoint. A correção
cobre os caminhos normais de retorno, incluindo erros de processos e de E/S;
não promete recuperação depois de SIGKILL, queda de energia ou abort do processo.
Subvolumes já criados permanecem no disco. A nova tentativa de instalação de
disco inteiro passa pela formatação existente antes de recriá-los.

## Validação

```sh
cargo test --locked --manifest-path installer/Cargo.toml -p lyra-installer-core -p lyra-installer-service
python3 -m unittest discover -s tests -v
python3 scripts/check-installer-mount-vm.py --kernel /caminho/vmlinuz --modules-dir /lib/modules/VERSAO
```

Seis regressões unitárias cobrem cada comando de criação/atributos do plano padrão,
erro de diretório, falha da montagem, falhas simultâneas, erro final de desmontagem
e cancelamento. A CI também executa o teste ignorado `native_mount_cleanup_vm`
em QEMU sem rede, com apenas um disco temporário de 512 MiB: Btrfs e executor
reais, falha injetada em cada comando, cancelamento no motor e nova tentativa.
O teste exige marcador do kernel e serial exclusivo do disco de ensaio; o
construtor não recebe caminho de disco do host nem executa montagem no host.
Após cada cenário, `/proc/self/mountinfo` precisa estar livre da montagem.

Esse ensaio qualifica o componente, não uma ISO nem a instalação completa do
produto. A entrega continua condicionada aos gates de identidade, empacotamento
e qualificação do artefato consumido por cada edição.

## Risco e reversão

A mudança afeta somente a montagem temporária da criação de subvolumes e a
composição de seus erros. A ordem do plano e o unwind das montagens finais
permanecem os existentes. Uma falha de desmontagem bloqueia avanço e informa
que a limpeza falhou; não se usa desmontagem forçada ou lazy para ocultá-la.
Se a qualificação do artefato regredir, reter o candidato e corrigir a regressão
antes de promover; a reversão do commit reintroduz o vazamento conhecido.
