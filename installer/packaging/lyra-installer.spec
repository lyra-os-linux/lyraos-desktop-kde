#
# spec file for package lyra-installer
#
# Copyright (c) 2026 Rodrigo Brito
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#

Name:           lyra-installer
Version:        0.1.0
Release:        0
Summary:        Instalador nativo do Lyra OS
License:        GPL-3.0-only
Group:          System/Boot/Installation
URL:            https://github.com/lyra-os-linux/lyraos-desktop
Source0:        %{name}-%{version}.tar.zst
Source1:        vendor.tar.zst
Source2:        build-source.txt

BuildRequires:  appstream-glib
BuildRequires:  cargo
BuildRequires:  cargo-packaging
BuildRequires:  desktop-file-utils
BuildRequires:  gtk3-devel
BuildRequires:  libsoup-devel
BuildRequires:  pkgconfig
BuildRequires:  rust >= 1.85
BuildRequires:  webkit2gtk3-devel
BuildRequires:  zstd
# The privileged service invokes these packages' programs directly. Keep
# every provider as an RPM dependency so a minimal/onlyRequired live image
# cannot omit a command halfway through an installation.
Requires:       btrfsprogs
Requires:       coreutils
Requires:       dconf
Requires:       dosfstools
Requires:       dracut
Requires:       e2fsprogs
Requires:       gptfdisk
Requires:       grub2
Requires:       grub2-common
Requires:       lvm2
Requires:       mdadm
# polkit ships the action/rule loader this package's .policy/.rules need at
# runtime; Leap 16.1 ships the pkexec client in its own package.
Requires:       polkit
Requires:       pkexec
Requires:       shadow
Requires:       shim
Requires:       snapper
Requires:       squashfs
Requires:       systemd
Requires:       util-linux

%description
Lyra Installer é o instalador nativo do Lyra OS, escrito em Rust com Tauri
(interface) e um serviço privilegiado separado autorizado por polkit
(operações de disco). É o único instalador da sessão live na Beta 2. Veja
docs/installer-architecture.md no repositório para a arquitetura completa.

%prep
# -a1 extracts Source0, then unpacks Source1 (vendor.tar.zst) on top of it.
# Locally generated vendor tarballs embed the absolute path of the machine
# that produced them in .cargo/config.toml; rewrite it to a path relative
# to the extracted source, which is what actually exists on the OBS build
# worker (same fixup as this project's other Rust packages, e.g. beam).
%autosetup -a1
sed -i 's|^directory = .*|directory = "vendor"|' .cargo/config.toml
test -d vendor
test -s %{SOURCE2}

%build
export LYRA_SOURCE_COMMIT="$(sed -n 's/^commit=//p' %{SOURCE2})"
test -n "$LYRA_SOURCE_COMMIT"
%{cargo_build}

%install
install -Dm0755 target/release/lyra-installer \
    %{buildroot}%{_bindir}/lyra-installer
install -Dm0755 target/release/lyra-installer-service \
    %{buildroot}%{_libexecdir}/lyra-installer-service
install -Dm0755 packaging/lyra-install-lock \
    %{buildroot}%{_bindir}/lyra-install-lock
install -Dm0644 packaging/org.lyraos.LyraInstaller.desktop \
    %{buildroot}%{_datadir}/applications/org.lyraos.LyraInstaller.desktop
for size in 32 128 256 512; do
    install -Dm0644 src-tauri/icons/${size}x${size}.png \
        %{buildroot}%{_datadir}/icons/hicolor/${size}x${size}/apps/org.lyraos.LyraInstaller.png
done
install -Dm0644 %{SOURCE2} \
    %{buildroot}%{_datadir}/lyra-installer/build-source.txt
install -Dm0644 packaging/io.lyra.Installer.policy \
    %{buildroot}%{_datadir}/polkit-1/actions/io.lyra.Installer.policy
install -Dm0644 packaging/01-lyra-installer-service.rules \
    %{buildroot}%{_sysconfdir}/polkit-1/rules.d/01-lyra-installer-service.rules

# Rust keeps metadata sections that the generic RPM post-processing does not
# classify as debuginfo. Strip the two release executables explicitly so the
# shipped package contains no compiler symbols.
%{__strip} --strip-all %{buildroot}%{_bindir}/lyra-installer
%{__strip} --strip-all %{buildroot}%{_libexecdir}/lyra-installer-service

desktop-file-validate \
    %{buildroot}%{_datadir}/applications/org.lyraos.LyraInstaller.desktop

%check
# The GUI (src-tauri) and privileged service (service/) are thin binaries
# with no meaningful unit tests of their own; every real test lives in the
# shared lyra-installer-core library (storage discovery/plan, service
# engine/executor/operations).
cargo test --offline -p lyra-installer-core

%files
%license LICENSE
%doc README.md
%{_bindir}/lyra-installer
%{_bindir}/lyra-install-lock
%{_libexecdir}/lyra-installer-service
%{_datadir}/applications/org.lyraos.LyraInstaller.desktop
%{_datadir}/icons/hicolor/32x32/apps/org.lyraos.LyraInstaller.png
%{_datadir}/icons/hicolor/128x128/apps/org.lyraos.LyraInstaller.png
%{_datadir}/icons/hicolor/256x256/apps/org.lyraos.LyraInstaller.png
%{_datadir}/icons/hicolor/512x512/apps/org.lyraos.LyraInstaller.png
%dir %{_datadir}/lyra-installer
%{_datadir}/lyra-installer/build-source.txt
%{_datadir}/polkit-1/actions/io.lyra.Installer.policy
# The build root's directory-ownership check flagged /etc/polkit-1 and
# /etc/polkit-1/rules.d as unowned by any package present at build time
# (unlike /usr/share/polkit-1/actions, apparently already owned wherever
# polkit itself provides it) - claim them explicitly rather than assume.
%dir %{_sysconfdir}/polkit-1
%dir %{_sysconfdir}/polkit-1/rules.d
%config(noreplace) %{_sysconfdir}/polkit-1/rules.d/01-lyra-installer-service.rules

%changelog
