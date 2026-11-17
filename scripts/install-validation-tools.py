"""Install checksum-verified portable k6 and Compose CLI (no daemon) in the project runtime."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import urllib.request

runtime = Path(os.environ.get('PRODUCTSTAT_RUNTIME_ROOT', Path.home() / '.local/share/productstat'))
tools = runtime / 'tools'
tools.mkdir(parents=True, exist_ok=True)
def fetch(url):
    print('Downloading', url, flush=True)
    return subprocess.run(['curl', '-fsSL', '--retry', '1', '--connect-timeout', '15', '--max-time', '180', url],
                          check=True, stdout=subprocess.PIPE).stdout

versions = {}
for repository, name in [('grafana/k6', 'k6'), ('docker/compose', 'compose')]:
    release = json.loads(fetch(f'https://api.github.com/repos/{repository}/releases/latest'))
    assets = {asset['name']: asset['browser_download_url'] for asset in release['assets']}
    target = next(item for item in assets if item.endswith('-linux-amd64.tar.gz')) if name == 'k6' else 'docker-compose-linux-x86_64'
    checksum_file = next(item for item in assets if item.endswith('checksums.txt')) if name == 'k6' else 'checksums.txt'
    checksums = fetch(assets[checksum_file]).decode()
    expected = next(line.split()[0] for line in checksums.splitlines() if line.split()[-1].lstrip('*') == target)
    archive = tools / target
    archive.write_bytes(fetch(assets[target]))
    if hashlib.sha256(archive.read_bytes()).hexdigest() != expected:
        raise SystemExit(f'{name} checksum mismatch')
    if name == 'k6':
        with tarfile.open(archive) as tar:
            member = next(member for member in tar.getmembers() if member.isfile() and member.name.endswith('/k6'))
            (tools / 'k6').write_bytes(tar.extractfile(member).read())
        (tools / 'k6').chmod(0o755)
    else:
        archive.chmod(0o755)
    versions[name] = release['tag_name']
    print(name, release['tag_name'], 'verified and installed', flush=True)
(tools / 'versions.json').write_text(json.dumps(versions, indent=2))
