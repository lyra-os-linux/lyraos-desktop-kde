# Avaliação comparativa e evolução do Lyra OS

Este documento registra uma linha de base para mensurar a evolução do Lyra OS
frente a distribuições desktop com a mesma orientação geral: estabilidade,
integração, privacidade, suporte prolongado e baixa necessidade de manutenção.

Ele é um instrumento de acompanhamento, não material de marketing. A nota deve
subir somente quando houver evidência nova, reproduzível e compatível com o
estágio de release.

## Estado da linha de base

**Data:** 2026-08-19  
**Produto avaliado:** Lyra OS Desktop 1.0 Alpha 6
**Resultado:** **6,4/10 — promissor, mas ainda não recomendado para produção**

A nota atual é limitada pela maturidade comprovada. A arquitetura e o processo
de release, isoladamente, foram avaliados em aproximadamente 8,6/10. A Alpha 6
continua com status NO-GO até repetir as evidências do candidato final, conforme
[`docs/release-gate.md`](../release-gate.md).

## Escala de interpretação

| Faixa | Interpretação |
|---:|---|
| 0–2 | Inviável ou inseguro para o cenário avaliado |
| 2–4 | Funciona parcialmente; exige intervenção frequente |
| 4–6 | Utilizável em testes ou cenários controlados |
| 6–7 | Candidato funcional, com riscos relevantes conhecidos |
| 7–8 | Adequado para uso cotidiano com ressalvas documentadas |
| 8–9 | Produto maduro e previsível para a maioria dos usuários |
| 9–10 | Referência de excelência, com evidência ampla e contínua |

Uma distribuição em Alpha, Beta ou RC não pode receber nota de produto maduro
apenas por ter uma boa arquitetura. Evidência ausente é risco, não nota neutra.

## Critérios e pesos

| Critério | Peso | O que medir |
|---|---:|---|
| Estabilidade e previsibilidade | 25% | boot, sessão, atualização, suspensão, ausência de regressões e uso prolongado |
| Atualização e recuperação | 20% | snapshots, rollback, interrupção segura, upgrade e recuperação orientada |
| Integração de hardware | 15% | Intel, AMD, NVIDIA, notebooks, Wi-Fi, áudio, energia e periféricos |
| Experiência do usuário | 15% | instalação, primeiro boot, GNOME, tradução, acessibilidade e clareza dos fluxos |
| Maturidade e suporte | 15% | ciclo de suporte, comunidade, documentação, capacidade operacional e mirrors |
| Segurança, privacidade e release | 10% | assinaturas, Secure Boot, privilégio mínimo, SBOM, proveniência e telemetria |

### Cálculo

Para cada critério, atribua uma nota de 0 a 10 e registre a evidência. A nota
final é:

```text
nota = (estabilidade * 0,25) + (recuperação * 0,20) + (hardware * 0,15)
     + (experiência * 0,15) + (maturidade * 0,15)
     + (segurança * 0,10)
```

Arredonde somente a nota final para uma casa decimal. Não arredonde cada critério
antes do cálculo.

## Linha de base comparativa

Estas notas servem para contexto e devem ser revisadas quando houver uma nova
versão estável relevante. Não são uma auditoria equivalente ao gate do Lyra.

| Distribuição | Nota de referência | Principal vantagem comparativa |
|---|---:|---|
| Linux Mint 22.3 | 9,0 | maturidade, simplicidade e ferramentas desktop |
| Ubuntu LTS | 8,8 | compatibilidade, suporte e escala operacional |
| Zorin OS 18.1 | 8,7 | onboarding e migração do Windows |
| TUXEDO OS | 8,4 | integração em hardware TUXEDO |
| openSUSE Leap 16 | 8,2 | base técnica, empacotamento e recuperação |
| **Lyra OS Alpha 6** | **6,4** | integração planejada e processo de recuperação |

Referências externas usadas nesta linha de base: [Linux Mint 22.3 e seu ciclo
LTS](https://www.linuxmint.com/rel_zena.php), [ciclo de suporte do Ubuntu
LTS](https://ubuntu.com/about/release-cycle), [detalhes técnicos do Zorin
OS 18.1](https://zorin.com/os/details/), [modelo de releases do TUXEDO
OS](https://www.tuxedocomputers.com/en/How-does-the-TUXEDO-OS-release-model-work.tuxedo)
e [notas do openSUSE Leap 16](https://doc.opensuse.org/release-notes/x86_64/openSUSE/Leap/16.0/release-notes-leap-160_color_en.pdf).

## Pontuação atual do Lyra

| Critério | Nota Alpha 6 | Justificativa resumida |
|---|---:|---|
| Estabilidade e previsibilidade | 5,5 | fluxo principal validado, mas ainda sem repetição final e uso prolongado |
| Atualização e recuperação | 7,0 | Snapper, GRUB rollback e Lyra Upgrade; upgrade entre releases pendente |
| Integração de hardware | 4,0 | matriz física limitada a uma máquina; restante em VM/QEMU |
| Experiência do usuário | 6,5 | instalador nativo, Welcome e três idiomas; escopo de instalação ainda restrito |
| Maturidade e suporte | 4,5 | Alpha, um mantenedor e ecossistema pequeno |
| Segurança, privacidade e release | 8,0 | privilégio mínimo, sem telemetria, RPMs assinados e gates fortes; ISO Alpha sem GPG |
| **Nota ponderada** | **6,4** | cálculo conforme os pesos acima |

## Metas por estágio

| Marco | Nota mínima desejável | Condições que não podem ser substituídas pela nota |
|---|---:|---|
| Alpha 6 atual | 6,0 | nenhum P0; P1 documentado e bloqueante para publicação |
| Beta 1 | 7,0 | assinatura da ISO, matriz mínima ampliada e nenhum P0/P1 aberto |
| RC | 7,8 | rollback, atualização, Secure Boot e hardware suportado repetidos no candidato |
| Lyra OS 1.0 | 8,0 | upgrade entre releases, publicação reproduzível, suporte definido e evidência longitudinal |
| release futura qualificada | 8,5 | redundância operacional, mais hardware, menor risco residual e comunidade ativa |

As metas não autorizam reduzir os critérios do release gate para alcançar uma
data. Um bloqueador P0/P1 mantém o resultado NO-GO independentemente da média.

## Evidência exigida para alterar a nota

Toda alteração deve registrar na tabela de histórico abaixo:

- versão, commit e data;
- critério alterado e nota anterior/nova;
- evidência (manifesto, log, teste físico, issue ou documento);
- cobertura e limitações conhecidas;
- responsável pela avaliação.

Não aumentar a nota por intenção, código não integrado, teste apenas unitário,
execução em uma única VM ou funcionalidade marcada como não suportada.

## Checklist de atualização

Antes de revisar a pontuação:

1. ler as notas da release e o release gate da versão;
2. confirmar o estado P0/P1 e o resultado GO/NO-GO;
3. agregar os resultados da matriz de hardware;
4. repetir instalação, primeiro boot, atualização, rollback e Secure Boot quando aplicável;
5. recalcular a média ponderada sem alterar os pesos silenciosamente;
6. registrar riscos residuais e comparar com a versão anterior;
7. atualizar a data e adicionar uma entrada no histórico.

## Histórico de avaliações

| Data | Versão | Nota | Mudança principal | Evidência |
|---|---|---:|---|---|
| 2026-08-19 | Desktop 1.0 Alpha 6 | 6,4 | linha de base inicial | README, release notes, gate e matriz de hardware |

## Próximas revisões recomendadas

As próximas revisões devem concentrar-se em três riscos que mais influenciam a
nota: cobertura física, upgrade entre releases e operação sustentada após várias
transações de atualização. Novos recursos não devem elevar a pontuação enquanto
esses riscos permanecerem sem evidência, especialmente após a Beta 1, quando o
escopo funcional estará congelado.
