"""Download and unpack the MSYS2 sqlcipher CLI on Windows.

Usage:
    python fetch_sqlcipher.py --dest C:\\tools\\sqlcipher

Downloads the packages that provide sqlcipher.exe and its runtime DLLs from
repo.msys2.org, extracts them with Windows' bundled bsdtar (zstd support) and
copies every exe/dll into <dest>\\bin.  Set HTTPS_PROXY if GitHub/MSYS2 needs a
proxy.
"""
import argparse
import os
import shutil
import subprocess
import sys
import urllib.request

BASE = 'https://repo.msys2.org/mingw/mingw64/'
PACKAGES = [
    'mingw-w64-x86_64-sqlcipher-4.6.1-2-any.pkg.tar.zst',
    'mingw-w64-x86_64-openssl-3.6.5-1-any.pkg.tar.zst',
    'mingw-w64-x86_64-zlib-1.4-2-any.pkg.tar.zst',
    'mingw-w64-x86_64-libiconv-1.19.1-1-any.pkg.tar.zst',
    'mingw-w64-x86_64-libwinpthread-git-12.0.0.r747.g1a99f8514-1-any.pkg.tar.zst',
    'mingw-w64-x86_64-libstdc%2B%2B-16.2.0-7-any.pkg.tar.zst',
    'mingw-w64-x86_64-readline-8.3.003-1-any.pkg.tar.zst',
    'mingw-w64-x86_64-ncurses-6.6-5-any.pkg.tar.zst',
    'mingw-w64-x86_64-pcre2-10.49-2-any.pkg.tar.zst',
    'mingw-w64-x86_64-termcap-1.3.1-8-any.pkg.tar.zst',
]


def opener():
    proxy = os.environ.get('HTTPS_PROXY') or os.environ.get('https_proxy')
    if proxy:
        return urllib.request.build_opener(
            urllib.request.ProxyHandler({'http': proxy, 'https': proxy}))
    return urllib.request.build_opener()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dest', required=True, help='output directory')
    ap.add_argument('--keep-packages', action='store_true')
    args = ap.parse_args()

    os.makedirs(args.dest, exist_ok=True)
    op = opener()
    for name in PACKAGES:
        path = os.path.join(args.dest, name)
        if os.path.exists(path):
            print('skip', name)
            continue
        print('download', name, flush=True)
        data = op.open(BASE + name, timeout=180).read()
        with open(path, 'wb') as f:
            f.write(data)

    for name in PACKAGES:
        subprocess.run(['tar', '-xf', os.path.join(args.dest, name), '-C', args.dest],
                       check=True)

    src = os.path.join(args.dest, 'mingw64', 'bin')
    dst = os.path.join(args.dest, 'bin')
    os.makedirs(dst, exist_ok=True)
    if not os.path.isdir(src):
        sys.exit('extraction failed: mingw64/bin not found')
    for fn in os.listdir(src):
        if fn.lower().endswith(('.dll', '.exe')):
            shutil.copy2(os.path.join(src, fn), os.path.join(dst, fn))

    if not args.keep_packages:
        for name in PACKAGES:
            try:
                os.remove(os.path.join(args.dest, name))
            except OSError:
                pass

    exe = os.path.join(dst, 'sqlcipher.exe')
    if not os.path.exists(exe):
        sys.exit('sqlcipher.exe missing after extraction')
    print('ok:', exe)


if __name__ == '__main__':
    main()
