# Desktop Alpha 7 release gate

> Alpha 8 adds four fail-closed results to this baseline: `upgrade-rehearsal`,
> `eca-digital`, `i18n` and `feature-freeze`. The build tooling selects these
> requirements from `release.toml`; Alpha 7 remains reproducible with its
> original seven-result gate.

This checklist is the versioned go/no-go contract for the standard Lyra OS
Desktop Alpha 7 ISO. A release coordinator may declare **GO** only when every blocking
item below has passed and its evidence is included in the final image evidence
manifest. Missing evidence is a failure, not an implicit exception.

## Severity and blocking policy

- **P0 — stop immediately:** data loss, credential disclosure, corrupted
  installation media, or an exploitable default configuration.
- **P1 — release blocker:** failure to boot the live or installed system;
  failure of the Lyra Installer; broken basic network, update, Snapper or
  rollback; invalid repository/package signatures; an unpublished mandatory
  package; or a regression without a safe workaround.
- **P2 — known issue:** degraded optional functionality with a tested,
  documented workaround. It must appear in the release notes.
- **P3 — follow-up:** cosmetic or low-impact defect that does not invalidate a
  supported scenario. It must have a tracking issue when not fixed.

No P0 or P1 issue may remain open at publication time. A P2 may be accepted
only when the decision record names its issue, workaround, owner and residual
risk.

## Candidate identity

- [ ] source tree is clean and the full commit is recorded;
- [ ] `release.toml`, KIWI metadata, ISO filename and installed `VERSION_ID`
  agree;
- [ ] the ISO package inventory contains exact OBS source revisions;
- [ ] every enabled RPM repository targets Leap 16.1 and no Leap 16.0 URL is
  present in the candidate;
- [ ] the candidate is tagged only after all blocking checks pass.

## Required evidence

Each file is structured JSON with schema 1 and top-level
`"status": "passed"`. `scripts/image-build.py artifact-manifest` also checks
the expected mode, nonempty passing checks, final rollback phase, OBS project
content and hardware coverage; a bare green status is rejected:

- [ ] `obs-repositories`: release projects published; provenance, repository
  metadata, keys and RPM signatures verified by `obs-release.py health`;
- [ ] `live-session`: autologin, GNOME, offline startup, basic devices and
  absence of critical journal failures;
- [ ] `installer`: Lyra Installer completes against the candidate ISO without
  a fallback installer;
- [ ] `first-boot`: installed disk boots, the created account works and no
  live-session artifact remains;
- [ ] `uefi-secure-boot`: supported UEFI and Secure Boot scenarios pass;
- [ ] `rollback`: update, Snapper snapshots and GRUB rollback pass;
- [ ] `hardware-matrix`: required real/virtual hardware scenarios are recorded.
- [ ] `v1.0-alpha.6` remains available as the immutable Leap 16.0 rollback
  baseline and the 16.0 → 16.1 upgrade/rollback rehearsal is recorded.

## Alpha 8 additions

- [ ] `upgrade-rehearsal`: a published baseline consumes a signed successor
  manifest, applies it offline, crosses reboot, verifies the target and restores
  the baseline through rollback; network loss, low space, UI termination,
  truncated state, RPM failure and initramfs failure are exercised;
- [ ] `eca-digital`: legal, security and privacy reviews are referenced, negative
  and evasion tests pass, and no document, biometric sample or unnecessary age
  history is retained;
- [ ] `i18n`: every supported Lyra-owned interface passes in `en-US`, `pt-BR`
  and Spanish (`es-ES`), with `en-US` as the explicit fallback;
- [ ] `feature-freeze`: every 1.0 feature is implemented or formally removed,
  documentation is consistent, and the recorded counts of open P0 and P1 are
  both zero. Any other result is `NO-GO`, and Alpha continues.

## Release signing key

Per [ADR 0005](adr/0005-release-signing-starts-at-beta1.md), Desktop Alpha 7
is published with SHA-256 but without a detached GPG signature. The release
key is created and made mandatory starting with Beta 1. RPM repository and
package signatures remain mandatory in every stage and are not affected by
this temporary artifact-signing exception.

From Beta 1 onward, the ISO checksum is signed with the release coordinator's
own GPG key, not a key this repository generates or holds. The key fingerprint
and public key must be added here before the first Beta 1 candidate; no
placeholder or disposable Alpha key is trusted. The canonical identity selected
before the first signed Beta 1 candidate is:

- **Fingerprint:** `01B6 3EED BE6B 0791 26A0  116E FA73 53A1 31EC EFEB`
- **UID:** `Lyra OS Release <rodrigo@lyraos.com.br>`
- **Public key:** [`docs/release-signing-key.asc`](release-signing-key.asc)

The unused draft identity `E765 8249 6F86 597D A854 7BA4 FE28 7BB5 4891
BA80` was replaced before any Beta artifact was signed because its private key
could not be recovered. It never authorized an official release signature.

Starting with Beta 1, verification instructions must name the canonical
fingerprint and public-key file. Any later rotation replaces both in the same
commit that publishes the first candidate signed by the new key.

## Artifact and publication checks

- [ ] ISO, package inventory, KIWI verification/report and both SBOM formats
  are present;
- [ ] SHA-256 is generated and independently verified; starting with Beta 1,
  it is also signed with the canonical release key and the signature verified;
- [ ] release notes list requirements, limitations, P2/P3 issues and tested
  workarounds;
- [ ] the evidence manifest is generated from a clean commit and contains all
  required green results;
- [ ] ISO and evidence are uploaded to SourceForge and downloaded again for
  checksum verification; signature verification is additionally mandatory
  from Beta 1 onward;
- [ ] #1 records coordinator, decision time, evidence URLs, accepted P2/P3
  risks and the exact source commit.

## Decision record

Record this block in #1 for every candidate:

```text
Decision: GO | NO-GO
Candidate commit:
ISO filename:
SHA-256:
Coordinator:
Decision time (UTC):
Evidence manifest:
Accepted P2/P3 issues and workarounds:
Residual risks:
```

## Current Desktop Alpha 7 state

**NO-GO enquanto a candidata limpa e as evidências da Alpha 7 não passarem.**
As validações da Alpha 6 continuam úteis como baseline, mas não substituem a
repetição completa sobre o Leap 16.1. O gate atual inclui explicitamente boot,
instalação, NVIDIA, áudio, codecs, upgrade e rollback. A Alpha 7 permanece sem
assinatura GPG destacada da ISO conforme a ADR 0005;
checksum, assinaturas de RPM/repositório e evidências estruturadas continuam
obrigatórios.

If a defect is found after publication, hide or remove the affected files on
SourceForge, record their checksums as withdrawn, stage and review the fix, and
publish a replacement candidate with a new evidence manifest. Never overwrite
an already distributed ISO while retaining its old checksum or decision record.
