# Qualificação upstream de controles parentais

Status: resultado técnico da #6  
Data da consulta: 18/08/2026  
Alvo original: Lyra OS Desktop 1.0, openSUSE Leap 16.0, x86_64

> Esta qualificação registra a decisão tomada sobre a base 16.0. A migração
> para Leap 16.1 exige repetir a consulta de disponibilidade e os testes antes
> de promover qualquer componente de controle parental para a imagem.

## Resultado

`malcontent` é o candidato upstream preferencial para política de aplicativos
e integração com AccountsService/OARS. Ele **não está qualificado para entrar
na imagem da versão 1.0 neste momento**, porque não há pacote oficial para
openSUSE Leap 16.0. O portal oficial lista somente pacote comunitário 0.12.0
para Leap; Tumbleweed possui 0.13.1 oficial.

Consequentemente:

- não adicionar repositório comunitário à ISO;
- não copiar `libmalcontent` nem os helpers do BigLinux;
- não criar fork privado permanente;
- solicitar/manter o pacote pela cadeia GNOME/openSUSE e submetê-lo ao staging;
- bloquear #2 até existir pacote qualificado ou exceção formal documentada.

Referências:

- [estado do pacote no openSUSE Software](https://software.opensuse.org/package/malcontent);
- [fonte em GNOME:Factory](https://build.opensuse.org/package/show/GNOME%3AFactory/malcontent);
- [repositórios oficiais do Leap 16.0](https://build.opensuse.org/repositories/openSUSE%3ALeap%3A16.0).

## Componentes avaliados

| Componente | Uso possível | Situação no Leap 16 | Decisão |
|---|---|---|---|
| AccountsService | Identidade e tipo da conta local | Base existente do desktop | Usar como adaptador de conta, nunca como aferidor |
| malcontent core | Filtro por caminho, instalação e OARS | Sem pacote oficial | Candidato condicionado à promoção oficial |
| malcontent-control/UI | Interface upstream | Sem pacote oficial; UX será Vega | Não instalar; evitar duas interfaces concorrentes |
| GNOME Software plugin | Consumidor de filtro | Vega é o fluxo Lyra | Estudar interoperabilidade, não tornar dependência da UX |
| PAM `time.conf` | Agenda de login | Mecanismo maduro, mas escopo limitado | Avaliar apenas como camada de agenda |
| systemd/logind | Sessão e enforcement persistente | Base madura | Preferir APIs tipadas; testar encerramento/recuperação |
| polkit | Autorização administrativa | Base madura | Usar ações pequenas por capacidade |
| nftables | Camada de rede | Base madura | Complementar; não equivale a filtro web completo |
| ACL POSIX | Bloqueio por inode/caminho | Base madura | Complementar; não equivale a controle da instalação |

## Compatibilidade funcional do malcontent

Pontos adequados ao Lyra:

- integração com AccountsService e D-Bus;
- API para filtro de aplicações e metadados OARS;
- política consultada pelo consumidor em vez de depender da GUI;
- suporte existente no ecossistema GNOME/Flatpak;
- biblioteca e formato já mantidos fora do Lyra.

Limites que permanecem:

- consumidores precisam consultar e respeitar o filtro; ele não bloqueia todo
  executável ou canal automaticamente;
- OARS depende da qualidade e disponibilidade de metadados;
- filtro de aplicação não fornece aferição de idade nem sinal interoperável;
- agenda de sessão não substitui quota consolidada ou política multi-sessão;
- a versão futura 0.14 adiciona tempo de tela, mas não deve entrar na base LTS
  sem maturidade, pacote oficial e análise específica de segurança.

## Caminho recomendado para empacotamento

1. Abrir solicitação no projeto mantenedor GNOME do OBS para construir a versão
   estável suportada contra `openSUSE_Leap_16.0`.
2. Confirmar que o pacote usa somente dependências oficiais do Leap e preserva
   ABI/API durante o ciclo LTS.
3. Executar build no staging do Lyra sem adicionar repositório de usuário à
   imagem final.
4. Validar filtros com RPM, Flatpak, Vega e GNOME Software, inclusive ausência
   de metadados e falha do serviço.
5. Revisar política D-Bus/polkit, migração, downgrade e rollback.
6. Promover apenas após revisão de segurança e evidência reproduzível.

Se a promoção upstream não ocorrer antes do gate, a alternativa segura é
adiar a funcionalidade parental, não internalizar silenciosamente o pacote.

## Contrato de adaptadores para a ADR

A futura arquitetura deve separar:

- `AccountAdapter`: UID, papel local e ciclo de vida da conta via
  AccountsService;
- `ApplicationPolicyAdapter`: política upstream via malcontent;
- `StoreAdapter`: autorização efetiva nos fluxos Vega/zypper/Flatpak;
- `SessionAdapter`: agenda/quota com systemd/logind/PAM quando aprovado;
- `AgeSignalProvider`: interface mínima ainda indefinida pela #10/#111.

Falha em qualquer adaptador obrigatório deve produzir estado explícito
`Unavailable` ou `Blocked`, nunca liberação automática.

## Gate da #6

A pesquisa e a decisão de qualificação estão concluídas. A integração ainda
fica bloqueada pela ausência do pacote oficial. A #5 pode usar este resultado
para desenhar a arquitetura, mas a #2 só inicia quando o pacote estiver
qualificado ou houver exceção formal com proprietário, manutenção, testes e
plano de remoção.
