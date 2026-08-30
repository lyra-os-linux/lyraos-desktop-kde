# ADR 0008 — Sinal etário privado e supervisão parental

- Status: **Proposta — aprovação bloqueada pela #106**
- Data: 18/08/2026
- Issues: #105, #106, #108, #110, #111, #112, #114

## Contexto

O Lyra precisa acomodar obrigações relacionadas a sistema operacional, loja e
aplicativos sem criar uma base de identidade/vigilância nem concentrar
privilégios no Vega. O contrato definitivo depende do parecer jurídico #106 e
das orientações aplicáveis da ANPD.

A auditoria #112 rejeitou importar o BigLinux: sua API expõe faixa e atividade,
falha para `18+` em ausência/corrupção e usa helper privilegiado amplo. A #110
escolheu malcontent como candidato upstream, mas registrou ausência de pacote
oficial no Leap 16.0. A UX #108 exige informação, contestação, autonomia
progressiva e limitações claras.

Apple Declared Age Range e Microsoft Family Safety são referências, não prova
de conformidade. São aproveitáveis os conceitos de faixa em vez de nascimento,
origem da declaração, permissão por aplicativo, papéis separados e pedidos. O
Lyra não adotará conta cloud ou coleta comportamental por padrão.

## Decisões independentes do método etário

### Separação de componentes

```text
Vega (UI sem root)
  │ API versionada + autenticação
  v
serviço de políticas (root, persistente, mínimo)
  ├── adaptador AccountsService
  ├── adaptador malcontent/OARS
  ├── adaptador Vega/zypper/Flatpak
  ├── adaptador systemd/logind/PAM
  └── provedor de sinal etário (a definir)
```

Vega configura, explica e coleta confirmações. O serviço valida, persiste e
coordena. Adaptadores aplicam mecanismos upstream. A política permanece ativa
sem o Vega e sobrevive a crash, reboot, atualização e rollback.

### Papéis e autorização

- **Administrador técnico:** mantém o sistema; não recebe automaticamente
  acesso a faixa ou atividade.
- **Responsável autorizado:** configura contas vinculadas e responde pedidos.
- **Usuário supervisionado:** consulta regras próprias, pede mudanças e
  contesta/retifica.
- **Consumidor de sinal:** aplicativo autenticado, com capacidade e finalidade.

Um usuário pode acumular papéis, mas autorização é por capacidade, não apenas
por associação a `wheel`.

### Dados mínimos

O serviço pode persistir identificador local opaco da conta, vínculos de papel,
política versionada, referência/classe/validade do sinal quando aprovadas,
autorizações por consumidor/finalidade, pedidos/decisões mínimos e estado de
migração. Não persiste documento, biometria, nascimento exato, histórico web ou
lista de processos por padrão. Logs técnicos não contêm faixa ou justificativa.

### API mínima

Namespace provisório, sujeito a revisão upstream: `org.lyraos.ParentalPolicy1`.

- `GetOwnSupervisionState()`;
- `GetManagedAccountState(account)` para responsável vinculado;
- `RequestThreshold(capability, threshold, purpose)`, nunca consulta geral por UID;
- `SetPolicy(account, expected_revision, policy)`;
- `SubmitRequest(type, payload)` e `ResolveRequest(id, decision)`;
- `GetHealth()` sem dados pessoais;
- `Recover(revision/action)`.

Respostas incluem versão, revisão, confiança e código estruturado. Campos
desconhecidos falham fechado. Não existe método de comando, path ou JSON opaco.

### Defaults de falha

- ausente, expirado, revogado, corrompido ou indisponível → `Unknown`, nunca
  `Adult`;
- consumidor não autorizado → `Denied`, sem confirmar existência/faixa;
- adaptador obrigatório indisponível → `Degraded/Blocked`;
- escrita/migração parcial → manter última revisão válida;
- divergência entre cache e enforcement → não declarar política ativa;
- rollback incompatível → preservar bloqueio e orientar recuperação.

### Persistência

- arquivos root-only `0600`, `O_NOFOLLOW|O_CLOEXEC`;
- schema e revisão monotônica;
- temporário `create_new`, fsync de arquivo/diretório e rename;
- backup da última revisão válida e migração reversível;
- lock global e leitura consistente;
- corrupção gera recuperação, nunca configuração vazia.

### Enforcement em camadas

- Vega/vegad controlam instalação suportada e o serviço root revalida;
- malcontent/OARS é candidato para política de aplicativos;
- ACL e nftables são apenas reforços;
- systemd/logind/PAM podem aplicar agenda/quota após qualificação;
- cada adaptador publica saúde e limitações para a interface.

## Decisões bloqueadas pela #106

Permanecem indefinidos: método/provedor/base legal de aferição, valor de
declaração parental, retenção, limiares/faixas, regras regionais,
consentimento/revogação, evidências exigidas e enquadramento preciso do Vega
como loja. Nenhum código #114 pode materializar esses pontos antes do parecer.

## Alternativas rejeitadas

- **Importar BigLinux:** fail-open, leitura ampla, helper monolítico e Arch-specific.
- **Usar só malcontent:** não fornece aferição, sinal, papéis nem cobertura total.
- **Conta cloud obrigatória:** coleta/dependência sem lacuna demonstrada.
- **Faixa geral por UID:** facilita enumeração e correlação; preferir limiar/finalidade.
- **Declaração como “verificada”:** proibida sem conclusão jurídica.
- **Entregar proteção parcial como completa:** adiar é o fallback seguro.

## Modelo de ameaça mínimo

- aplicativo enumerando menores/faixas;
- administrador técnico sem papel de responsável e responsável coercitivo;
- evasão por CLI, cópia, interpretador, AppImage, container, VPN ou DoH;
- substituição de binário/política durante update;
- symlink, corrupção, rollback/downgrade e schema antigo;
- frontend comprometido solicitando operação excessiva;
- correlação entre consumidores e dispositivo compartilhado;
- indisponibilidade do aferidor e recuperação de responsável.

## Migração e rollback

O serviço nasce `Unconfigured`, não adulto. Migração só publica revisão após
validação completa e mantém a anterior até confirmação. O pacote lê ao menos
uma versão anterior, mas escreve apenas a atual. Downgrade incompatível preserva
estado e bloqueia alteração. Remover o pacote não apaga política ou recuperação.

## Consequências

O desenho minimiza dados, mantém enforcement fora da GUI e permite trocar
adaptadores. Em contrapartida, exige serviço, autorização fina, qualificação de
malcontent e testes extensos. A funcionalidade pode ser adiada da 1.0 se as
dependências jurídicas/upstream não fecharem antes do congelamento.

## Gate de aprovação

A ADR muda para `Aceita` somente quando #106 entregar parecer profissional, as
decisões bloqueadas forem preenchidas, #110/#112 forem aceitas, #108 for
revisada por privacidade/segurança/acessibilidade, houver revisão upstream e a
#114 tiver plano de teste/migração/reversão. Até lá, orienta pesquisa e
protótipos sem dados reais, mas não autoriza implementação funcional.
