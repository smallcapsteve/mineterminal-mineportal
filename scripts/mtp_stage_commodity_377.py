#!/usr/bin/env python3
"""Stage and commodity labels for the 377 companies added to MinePortal on 2026-09-23.

Justin (2026-09-24): "add all 377, taking producers and royalty companies from the list I
already built and the rest from their descriptions."

Data: mtp_stage_commodity_377.json (next to this script)
  * stages: one code per new ticker, the same scheme as MTP_STAGE_DESC_V1
    (P/D/A/E/R/U + confidence h/m/l). Producers and royalty companies come from the
    2026-09-23 coverage list; the rest were read from each company's exchange description.
  * commodity_overrides: 30 of the 68 new companies whose description names no commodity
    (e.g. Wheaton, OR Royalties), plus DEX, whose "diamond drill rigs" read as Diamonds.
    The other 38 stay "Unspecified" rather than guessed.

What it does
  * Only ADDS keys. A ticker already present in either file is left alone and reported.
  * --apply: copies both files to /root/mtp-backup-stage377-<stamp>/ first, writes each
    atomically (tmp + rename), reruns mtp-commodities.service, sends MTP's cache-clear, and
    reports the new companies' stage and commodity from the rebuilt cache.
  * Without --apply: reports what it would add; writes nothing.

Undo: copy the two files back from the backup folder, then
  systemctl start mtp-commodities.service
"""
import collections
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "mtp_stage_commodity_377.json")
STAGE = "/root/minetracker/scripts/stage_from_descriptions.json"
OVR = "/root/minetracker/scripts/commodity_overrides.json"
CACHE = "/root/minetracker/cache/company_commodities.json"
HOST = "mnt-scraper-01"
NOTE = ("2026-09-24: 377 companies added to MinePortal on 2026-09-23 - producers and royalty "
        "companies from the 2026-09-23 coverage list, the rest read from their exchange descriptions (Claude)")


def blob_sha(b):
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def write_atomic(path, text):
    tmp = path + ".tmp377"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def dump_stage(d):
    """Same layout as the file on disk: header keys one per line, stages 16 per line."""
    head = ['"marker":%s' % json.dumps(d["marker"]), '"made":%s' % json.dumps(d["made"]),
            '"revised":%s' % json.dumps(d["revised"])]
    extra = [k for k in d if k not in ("marker", "made", "revised", "how", "codes", "stages")]
    head += ['"%s":%s' % (k, json.dumps(d[k], ensure_ascii=False)) for k in extra]
    head += ['"how":%s' % json.dumps(d["how"], ensure_ascii=False),
             '"codes":%s' % json.dumps(d["codes"])]
    items = ['"%s":"%s"' % (k, v) for k, v in sorted(d["stages"].items())]
    rows = [",".join(items[i:i + 16]) for i in range(0, len(items), 16)]
    return "{" + ",\n".join(head) + ',\n"stages":{\n' + ",\n".join(rows) + "\n}}\n"


def main():
    apply = "--apply" in sys.argv
    if socket.gethostname() != HOST:
        sys.exit("refusing: not %s" % HOST)
    data = json.load(open(DATA))

    raw_s = open(STAGE, "rb").read()
    st = json.loads(raw_s)
    if st.get("marker") != "MTP_STAGE_DESC_V1":
        sys.exit("refusing: stage file marker is %r" % st.get("marker"))
    raw_o = open(OVR, "rb").read() if os.path.exists(OVR) else b"{}"
    ov = json.loads(raw_o or b"{}")
    print("stage file: %d entries, blob %s" % (len(st["stages"]), blob_sha(raw_s)))
    print("overrides:  %d entries, blob %s" % (len(ov), blob_sha(raw_o)))

    add_s = {k: v for k, v in data["stages"].items() if k not in st["stages"]}
    skip_s = sorted(k for k in data["stages"] if k in st["stages"])
    add_o = {k: v for k, v in data["commodity_overrides"].items() if k not in ov}
    skip_o = sorted(k for k in data["commodity_overrides"] if k in ov)
    bad = [k for k, v in add_s.items() if v[:1] not in st["codes"] or v[1:2] not in ("h", "m", "l")]
    if bad:
        sys.exit("refusing: bad codes %s" % bad)
    print("stages to add: %d  already present (left alone): %s" % (len(add_s), skip_s or "none"))
    print("  by code:", dict(collections.Counter(v[0] for v in add_s.values())))
    print("overrides to add: %d  already present (left alone): %s" % (len(add_o), skip_o or "none"))
    if not apply:
        print("dry run: nothing written")
        return

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bdir = "/root/mtp-backup-stage377-%s" % stamp
    os.makedirs(bdir)
    shutil.copy2(STAGE, bdir)
    if os.path.exists(OVR):
        shutil.copy2(OVR, bdir)
    print("backup:", bdir)

    st["stages"].update(add_s)
    st["revised"] = (st.get("revised") or "") + "; " + NOTE
    text_s = dump_stage(st)
    assert json.loads(text_s)["stages"] == st["stages"]
    write_atomic(STAGE, text_s)
    ov.update(add_o)
    text_o = json.dumps(ov, indent=2, ensure_ascii=False) + "\n"
    write_atomic(OVR, text_o)
    print("wrote stage file: %d entries, blob %s" % (len(st["stages"]), blob_sha(text_s.encode())))
    print("wrote overrides:  %d entries, blob %s" % (len(ov), blob_sha(text_o.encode())))

    t0 = time.time()
    r = subprocess.run(["timeout", "150", "systemctl", "start", "mtp-commodities.service"],
                       capture_output=True, text=True)
    print("mtp-commodities: rc=%s in %.0fs %s" % (r.returncode, time.time() - t0, (r.stderr or "").strip()[:200]))
    j = subprocess.run("journalctl -u mtp-commodities.service --since '-3 min' --no-pager -o cat | "
                       "grep -E 'overrides|stage|Exploration|Production|Development|Royalty|wrote|failed|Error' | tail -12",
                       shell=True, capture_output=True, text=True).stdout
    print(j.strip())
    r = subprocess.run(["/opt/mineportal/venv/bin/python", "-c",
                        "import mtp_notify; mtp_notify._send('admin.admin_bulk_create', table='companies')"],
                       cwd="/opt/mineportal", capture_output=True, text=True)
    print("MTP cache-clear sent: rc=%s" % r.returncode)

    cache = json.load(open(CACHE))
    comp = cache.get("companies", cache)
    print("cache written %s ago" % (int(time.time() - cache.get("fetchedAt", 0))))
    new = data["stages"]
    have = {k: comp[k] for k in new if k in comp}
    print("new companies in cache: %d/%d" % (len(have), len(new)))
    print("  stage:", dict(collections.Counter(v.get("stage") for v in have.values())))
    print("  stage_source:", dict(collections.Counter(v.get("stage_source") for v in have.values())))
    print("  primary Unspecified:", sum(1 for v in have.values() if v.get("primary") in (None, "Unspecified")))
    for k in ("K", "AGI", "HBM", "EDV", "WPM", "OR", "TFPM", "SKE", "NG", "AURM", "NDM", "EDM"):
        v = comp.get(k) or {}
        print("  %-5s %-22s %s" % (k, v.get("stage"), v.get("display")))
    if len(text_o) < 6000:
        print("---- overrides file now ----")
        print(text_o)


if __name__ == "__main__":
    main()
