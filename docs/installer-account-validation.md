# Validação dos dados de conta

O serviço valida a configuração recebida por JSON antes de descobrir discos
ou construir operações. O motor repete a validação antes de executar o plano;
a criação da conta também rejeita dados inválidos antes de acessar o destino.
A interface exibe os mesmos erros em inglês, português e espanhol.

A senha mantém espaços, dois-pontos e Unicode. NUL é recusado porque trunca
strings C/PAM; LF é recusado porque inicia outro registro de `chpasswd`,
inclusive em CRLF. O nome completo não pode conter NUL, LF ou dois-pontos,
conforme o campo de comentário de `useradd`. Os erros contêm apenas chaves
fixas de tradução; não repetem nome ou senha fornecidos.

O mínimo existente de oito caracteres passa a contar pontos de código também
na interface. Os limites superiores contam bytes UTF-8: o registro completo
`usuário:senha\n` deve caber nos 8191 bytes úteis do buffer de `chpasswd`
(shadow/glibc); o comentário deve caber em um argumento Linux x86_64 de
131071 bytes mais NUL. Esses limites evitam rejeições determinísticas de
protocolo/argv, sem substituir a política PAM da imagem.

Referências da base examinada:
- [chpasswd shadow 4.19.4](https://github.com/shadow-maint/shadow/blob/4.19.4/src/chpasswd.c)
- [useradd shadow 4.19.4](https://github.com/shadow-maint/shadow/blob/4.19.4/src/useradd.c)
- [Limites de argumentos do execve](https://man7.org/linux/man-pages/man2/execve.2.html)

Validação automatizada:

```sh
cd installer
cargo test --locked -p lyra-installer-core -p lyra-installer-service
cd ..
python3 -m unittest discover -s tests -v
```

Os testes executam o serviço compilado diretamente por stdin, sem interface,
sem `pkexec` e sem dispositivo de destino. Verificam que a primeira e única
resposta é a recusa da configuração, antes da verificação do ambiente. Os
testes do motor confirmam que nenhuma operação foi chamada; os da interface
executam a função JavaScript real com entradas inválidas e senhas válidas.
Isso não equivale à qualificação de uma ISO ou instalação completa.

A correção pode ser revertida por commit, mas isso reabre a falha de criação
de contas; em caso de regressão, reter o candidato enquanto se corrige a
validação, preservando o último artefato publicado.
