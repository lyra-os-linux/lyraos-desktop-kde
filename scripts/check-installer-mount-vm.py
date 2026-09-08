#!/usr/bin/env python3
"""Run the real Btrfs cleanup regression in QEMU on a disposable scratch disk."""
import argparse
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

REPO = Path(__file__).resolve().parents[1]
TEST = 'service::operations::mount_cleanup_tests::native_mount_cleanup_vm'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--modules-dir', type=Path, required=True)
    parser.add_argument('--log', type=Path, default=REPO / 'installer/target/mount-cleanup-vm.log')
    args = parser.parse_args()
    if not args.kernel.is_file() or not args.modules_dir.is_dir():
        parser.error('readable kernel and matching modules directory required')
    built = subprocess.run(['cargo', 'test', '--locked', '--no-run', '-p', 'lyra-installer-core',
                            '--lib', '--message-format=json'], cwd=REPO / 'installer',
                           capture_output=True, text=True, check=True)
    artifacts = [json.loads(line) for line in built.stdout.splitlines()]
    executable, = [Path(row['executable']) for row in artifacts
                   if row.get('executable') and row['target']['name'] == 'lyra_installer_core']
    with tempfile.TemporaryDirectory(prefix='lyra-mount-vm-') as directory:
        base = Path(directory)
        root = base / 'root'
        for name in ['usr/bin', 'dev', 'proc', 'sys', 'tmp', 'run', 'etc']:
            (root / name).mkdir(parents=True)
        (root / 'bin').symlink_to('usr/bin')
        if Path('/etc/ld.so.cache').is_file():
            shutil.copyfile('/etc/ld.so.cache', root / 'etc/ld.so.cache')

        def copy(source, destination):
            target = root / str(destination).lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            target.chmod(0o755)

        def binary(source, destination):
            copy(source, destination)
            linked = subprocess.check_output(['ldd', str(source)], text=True)
            for library in re.findall(r'(?:=>\s+|^\s*)(/[^\s]+)', linked, re.M):
                copy(library, library)
                if '/glibc-hwcaps/' in library:
                    dynamic = subprocess.check_output(['readelf', '-d', library], text=True)
                    soname = re.search(r'\(SONAME\).*\[([^]]+)\]', dynamic)
                    if soname:
                        baseline = Path(library.split('/glibc-hwcaps/')[0]) / soname[1]
                        copy(baseline, baseline)

        for name in ['bash', 'mount', 'umount', 'mkdir', 'modprobe', 'mkfs.btrfs', 'btrfs', 'chattr', 'systemctl']:
            source = shutil.which(name)
            if not source:
                parser.error('missing VM tool: ' + name)
            binary(source, '/usr/bin/' + name)
        binary(executable, '/test-installer')
        copy('/usr/share/zoneinfo/UTC', '/usr/share/zoneinfo/UTC')
        module_root = root / 'usr/lib/modules' / args.modules_dir.name
        module_root.mkdir(parents=True)
        (root / 'lib').mkdir(exist_ok=True)
        (root / 'lib/modules').symlink_to('../usr/lib/modules')
        for source in args.modules_dir.glob('modules.*'):
            shutil.copyfile(source, module_root / source.name)
        for name in ['btrfs', 'virtio_blk', 'virtio_pci']:
            # Only resolve dependencies here; modules are loaded inside QEMU.
            dependencies = subprocess.check_output(['modprobe', '--show-depends', '-S', args.modules_dir.name, name], text=True)
            for line in dependencies.splitlines():
                if line.startswith('insmod '):
                    source = Path(line.split()[1])
                    relative = source.resolve().relative_to(args.modules_dir.resolve())
                    target = module_root / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
        init = root / 'init'
        init.write_text(f'''#!/bin/bash
export PATH=/usr/bin:/bin
mount -t proc proc /proc || exit 1
mount -t sysfs sysfs /sys || exit 1
mount -t devtmpfs devtmpfs /dev || exit 1
modprobe btrfs || exit 1
modprobe virtio_pci || exit 1
modprobe virtio_blk || exit 1
/test-installer --ignored --exact {TEST} --nocapture --test-threads=1
result=$?
echo "LYRA_MOUNT_VM_EXIT=$result"
systemctl --force --force poweroff
''')
        init.chmod(0o755)
        files = b'\0'.join(str(path.relative_to(root)).encode() for path in root.rglob('*')) + b'\0'
        archive = subprocess.run(['cpio', '--null', '-o', '-H', 'newc', '--owner=0:0', '--quiet'],
                                 input=files, cwd=root, capture_output=True, check=True)
        initrd = base / 'initramfs.cpio.gz'
        with gzip.open(initrd, 'wb', compresslevel=1) as stream:
            stream.write(archive.stdout)
        disk = base / 'scratch.raw'
        with disk.open('wb') as stream:
            stream.truncate(512 * 1024 * 1024)
        args.log.parent.mkdir(parents=True, exist_ok=True)
        with args.log.open('w') as log:
            result = subprocess.run(['qemu-system-x86_64', '-accel', 'tcg', '-cpu', 'max', '-smp', '2', '-m', '1024',
                '-kernel', str(args.kernel.resolve()), '-initrd', str(initrd),
                '-append', 'rdinit=/init console=ttyS0 quiet panic=1 lyra.mount-cleanup-test=1',
                '-drive', f'file={disk},format=raw,if=none,id=scratch',
                '-device', 'virtio-blk-pci,drive=scratch,serial=lyra-mount-test-only',
                '-display', 'none', '-serial', 'stdio', '-monitor', 'none', '-nic', 'none', '-no-reboot'],
                stdout=log, stderr=subprocess.STDOUT, timeout=240)
        content = args.log.read_text(errors='replace')
        print(content[-10000:])
        if result.returncode or 'LYRA_MOUNT_VM_PASS ' not in content or 'LYRA_MOUNT_VM_EXIT=0' not in content:
            raise SystemExit('VM failed: ' + str(args.log))
        print('PASS: real Btrfs faults, cancellation and retry; evidence: ' + str(args.log))


if __name__ == '__main__':
    main()
