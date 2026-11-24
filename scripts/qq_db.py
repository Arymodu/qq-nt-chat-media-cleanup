"""QQ NT media usage / orphan tool.

Subcommands
    export   strip+export an encrypted NTQQ db to plain SQLite
    usage    per-group or per-friend media usage
    orphans  media files referenced by no surviving message
    delete   delete files listed in a CSV produced by `orphans`

All database commands need a decrypted (1024-byte header stripped) db and the
passphrase.  See ../README.md and ../docs/decryption.md for the walkthrough.
"""
import argparse
import binascii
import csv
import json
import os
import re
import sqlite3
import subprocess

HEADER = 1024
ALL_FOLDERS = ('Pic', 'Video', 'Emoji', 'Ptt', 'File')
HEX_RE = re.compile(rb'(?<![0-9A-Fa-f])[0-9A-Fa-f]{32}(?![0-9A-Fa-f])')
PRAGMAS = ("PRAGMA cipher_page_size=4096; PRAGMA key='{key}'; "
           "PRAGMA kdf_iter={kdf}; PRAGMA cipher_hmac_algorithm={hmac}; "
           "PRAGMA cipher_kdf_algorithm=PBKDF2_HMAC_SHA512; ")


def pragmas(key, kdf=4000, hmac='HMAC_SHA1'):
    return PRAGMAS.format(key=key.replace("'", "''"), kdf=kdf, hmac=hmac)


def run(exe, db, key, sql, kdf=4000, hmac='HMAC_SHA1'):
    p = subprocess.run([exe, db, pragmas(key, kdf, hmac) + sql],
                       capture_output=True, text=True, encoding='utf-8', errors='replace')
    if 'file is not a database' in (p.stdout + p.stderr):
        raise SystemExit('key or PRAGMA mismatch: ' + (p.stderr or p.stdout)[:200])
    return p.stdout


def iter_hex_lines(exe, db, key, sql, kdf=4000, hmac='HMAC_SHA1'):
    p = subprocess.Popen([exe, db, pragmas(key, kdf, hmac) + sql],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    for raw in p.stdout:
        line = raw.strip()
        if line and re.fullmatch(rb'[0-9A-Fa-f]+', line):
            yield line
    p.wait()


def strip_header(src, dst):
    with open(src, 'rb') as fi, open(dst, 'wb') as fo:
        fi.seek(HEADER)
        while True:
            chunk = fi.read(64 << 20)
            if not chunk:
                break
            fo.write(chunk)


def parse_folders(value):
    folders = tuple(x.strip() for x in (value or '').split(',') if x.strip())
    unknown = [x for x in folders if x not in ALL_FOLDERS]
    if unknown:
        raise SystemExit(f'unknown folder(s): {unknown}; choose from {ALL_FOLDERS}')
    return folders or ALL_FOLDERS


def build_index(ntqq, folders=ALL_FOLDERS):
    idx = {}
    for sub in folders:
        base = os.path.join(ntqq, 'nt_data', sub)
        if not os.path.isdir(base):
            continue
        for dp, _, files in os.walk(base):
            for f in files:
                stem = os.path.splitext(f)[0].lower()
                if stem.endswith('_0'):
                    stem = stem[:-2]
                if len(stem) == 32 and all(c in '0123456789abcdef' for c in stem):
                    path = os.path.join(dp, f)
                    try:
                        idx.setdefault(stem, []).append((path, os.path.getsize(path)))
                    except OSError:
                        pass
    return idx


def hashes_of(hex_line):
    try:
        blob = binascii.unhexlify(hex_line)
    except Exception:
        return ()
    return {m.group().decode().lower() for m in HEX_RE.finditer(blob)}


def group_names(group_info_plain):
    if not group_info_plain or not os.path.exists(group_info_plain):
        return {}
    con = sqlite3.connect(group_info_plain)
    try:
        return {r[0]: r[1] or '' for r in con.execute('select [60001],[60007] from group_list')}
    finally:
        con.close()


def friend_names(profile_plain):
    if not profile_plain or not os.path.exists(profile_plain):
        return {}
    con = sqlite3.connect(profile_plain)
    names = {}
    try:
        for table in ('profile_info_v2', 'profile_info_v6'):
            try:
                for uid, uin, nick in con.execute(
                        f'select [1000],[1002],[20002] from {table}'):
                    if uid and uid not in names:
                        names[uid] = (nick or '', uin or '')
            except sqlite3.Error:
                pass
        try:
            for uid, remark in con.execute('select [1000],[1001] from buddy_list'):
                if uid and remark:
                    names[uid] = (remark, names.get(uid, ('', ''))[1])
        except sqlite3.Error:
            pass
    finally:
        con.close()
    return names


def sum_hashes(idx, hashes):
    return sum(sum(size for _, size in idx[h]) for h in hashes)


def cmd_export(a):
    strip_header(a.src, a.clean)
    sql = (f"ATTACH DATABASE '{a.out}' AS plain KEY ''; "
           "SELECT sqlcipher_export('plain'); DETACH DATABASE plain;")
    run(a.sqlcipher, a.clean, a.key, sql, a.kdf, a.hmac)
    print('exported', a.out)


def cmd_usage(a):
    folders = parse_folders(a.folders)
    idx = build_index(a.ntqq, folders)
    print('media index:', len(idx), 'files; folders:', ','.join(folders), flush=True)
    rows = []
    if a.mode == 'groups':
        names = group_names(a.group_info)
        out = run(a.sqlcipher, a.db, a.key,
                  'select distinct [40027] from group_msg_table;', a.kdf, a.hmac)
        codes = sorted({int(x) for x in out.splitlines() if x.strip().isdigit()})
        print('groups:', len(codes), flush=True)
        for code in codes:
            seen = set()
            n = 0
            for line in iter_hex_lines(a.sqlcipher, a.db, a.key,
                                       f'select hex([40800]) from group_msg_table where [40027]={code};',
                                       a.kdf, a.hmac):
                n += 1
                seen |= {h for h in hashes_of(line) if h in idx}
            rows.append(dict(code=code, name=names.get(code, ''),
                             msgs=n, files=len(seen), bytes=sum_hashes(idx, seen)))
    else:
        names = friend_names(a.profile_db)
        per = {}
        proc = subprocess.Popen(
            [a.sqlcipher, a.db, pragmas(a.key, a.kdf, a.hmac) +
             'select [40021], hex([40800]) from c2c_msg_table;'],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        for raw in proc.stdout:
            line = raw.decode('utf-8', 'replace').strip()
            if '|' not in line:
                continue
            uid, hexblob = line.split('|', 1)
            d = per.setdefault(uid, [0, set()])
            d[0] += 1
            d[1] |= {h for h in hashes_of(hexblob.strip()) if h in idx}
        proc.wait()
        for uid, (n, seen) in per.items():
            nick, uin = names.get(uid, ('', ''))
            rows.append(dict(uid=uid, uin=uin, name=nick, msgs=n, files=len(seen),
                             bytes=sum_hashes(idx, seen)))

    rows.sort(key=lambda r: -r['bytes'])
    with open(a.out, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    gb = 1024 ** 3
    print(f'{"group/friend":<28}{"size":>10}  files   msgs')
    for r in rows[:20]:
        label = r.get('name') or r.get('code') or r.get('uid')
        print(f'{str(label)[:26]:<28}{r["bytes"]/gb:10.2f}  {r["files"]:6}  {r["msgs"]:6}')
    print('total %.2f GB -> %s' % (sum(r['bytes'] for r in rows) / gb, a.out))


def cmd_orphans(a):
    folders = parse_folders(a.folders)
    idx = build_index(a.ntqq, folders)
    print('media index:', len(idx), 'files; folders:', ','.join(folders), flush=True)
    refs = set()

    def add_from(sql):
        for line in iter_hex_lines(a.sqlcipher, a.db, a.key, sql, a.kdf, a.hmac):
            refs.update(h for h in hashes_of(line) if h in idx)

    out = run(a.sqlcipher, a.db, a.key,
              'select distinct [40027] from group_msg_table;', a.kdf, a.hmac)
    codes = sorted({int(x) for x in out.splitlines() if x.strip().isdigit()})
    print('groups:', len(codes), flush=True)
    for code in codes:
        add_from(f'select hex([40800]) from group_msg_table where [40027]={code};')
    add_from('select hex([40800]) from c2c_msg_table;')
    add_from('select hex([40800]) from dataline_msg_table;')

    orphans = []
    for stem, files in idx.items():
        if stem in refs:
            continue
        for path, size in files:
            orphans.append((path, size))
    orphans.sort(key=lambda x: -x[1])
    total = sum(s for _, s in orphans)
    with open(a.out, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['path', 'bytes'])
        w.writerows(orphans)
    print(f'orphans: {len(orphans)} files, {total/1024**3:.2f} GB -> {a.out}')


def cmd_delete(a):
    deleted = freed = 0
    failed = []
    with open(a.plan, encoding='utf-8-sig') as fin, open(a.log, 'w', encoding='utf-8-sig', newline='') as fout:
        r = csv.DictReader(fin)
        w = csv.writer(fout)
        w.writerow(['path', 'bytes'])
        for row in r:
            path = row['path']
            size = int(row['bytes'])
            if a.dry_run:
                deleted += 1
                freed += size
                continue
            try:
                os.remove(path)
            except OSError as e:
                failed.append(f'{path}\t{e}')
                continue
            w.writerow([path, size])
            deleted += 1
            freed += size
    print(('would delete' if a.dry_run else 'deleted'),
          f'{deleted} files, {freed/1024**3:.2f} GB, failed {len(failed)}')
    if failed:
        with open(a.log + '.failed', 'w', encoding='utf-8') as f:
            f.write('\n'.join(failed))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)

    def db_args(p):
        p.add_argument('--sqlcipher', required=True, help='path to sqlcipher.exe')
        p.add_argument('--key', required=True, help='passphrase of the database')
        p.add_argument('--kdf', type=int, default=4000)
        p.add_argument('--hmac', default='HMAC_SHA1')

    def folder_arg(p):
        p.add_argument('--folders', default=','.join(ALL_FOLDERS),
                       help='comma separated media folders: Pic,Video,Emoji,Ptt,File')

    e = sub.add_parser('export')
    e.add_argument('--src', required=True)
    e.add_argument('--clean', required=True)
    e.add_argument('--out', required=True)
    db_args(e)

    u = sub.add_parser('usage')
    u.add_argument('--ntqq', required=True, help='...\\nt_qq directory')
    u.add_argument('--db', required=True, help='stripped/decrypted nt_msg db')
    u.add_argument('--mode', choices=('groups', 'friends'), default='groups')
    u.add_argument('--group-info', help='plain group_info.db (optional names)')
    u.add_argument('--profile-db', help='plain profile_info.db (optional names)')
    u.add_argument('--out', default='usage.json')
    folder_arg(u)
    db_args(u)

    o = sub.add_parser('orphans')
    o.add_argument('--ntqq', required=True)
    o.add_argument('--db', required=True)
    o.add_argument('--out', default='orphans.csv')
    folder_arg(o)
    db_args(o)

    d = sub.add_parser('delete')
    d.add_argument('--plan', required=True)
    d.add_argument('--log', default='deleted.csv')
    d.add_argument('--dry-run', action='store_true')

    a = ap.parse_args()
    {'export': cmd_export, 'usage': cmd_usage,
     'orphans': cmd_orphans, 'delete': cmd_delete}[a.cmd](a)


if __name__ == '__main__':
    main()
