"""
Box-art pack for the EverDrive N8 ROM info screen.

  python tools/art_pack.py build   [--out releases/EDFC-ARTPACK-NES.zip] [--jobs 8] [--limit N]
      Downloads the No-Intro NES DAT (libretro-database) and every box art in
      libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System/Named_Boxarts,
      converts each to the 2 KB NES art format (tools/nes_art.py) and writes one
      zip: boxart/<thumbnail name>.BIN + index.tsv (crc32 -> thumbnail name).
      PNGs are streamed and discarded; converted files are cached in .artcache/
      so an interrupted build resumes.

  python tools/art_pack.py install --pack releases/EDFC-ARTPACK-NES.zip --sd E:\\ [--roms E:\\]
      Scans the ROMs on the card, identifies each one by content (CRC-32 of the
      ROM without its iNES header, looked up in the No-Intro DAT; falls back to
      the file name), and writes EDFC/ARTS/<fingerprint>.BIN, where the
      fingerprint is what the console computes (CRC-32 of file bytes 512..2559).

The pack contains copyrighted cover art from libretro-thumbnails: it is for
personal use on your own card and is not committed to this repository.
"""
import argparse, concurrent.futures as cf, io, json, os, re, sys, time, urllib.parse, urllib.request, zipfile, zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nes_art

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMB_REPO = "libretro-thumbnails/Nintendo_-_Nintendo_Entertainment_System"
DAT_URL = ("https://raw.githubusercontent.com/libretro/libretro-database/master/metadat/no-intro/"
           "Nintendo%20-%20Nintendo%20Entertainment%20System.dat")
RAW = f"https://raw.githubusercontent.com/{THUMB_REPO}/master/Named_Boxarts/"
UA = {"User-Agent": "nes-everdrive-artpack"}
CACHE = os.path.join(REPO, ".artcache")


def http(url, tries=5):
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                return r.read()
        except Exception as e:
            if getattr(e, "code", None) == 404 or n == tries - 1:
                raise
            time.sleep(2 ** n)


def thumb_name(game):
    """libretro-thumbnails file naming: these characters become '_'."""
    return re.sub(r'[&*/:`<>?\\|"]', "_", game)


def parse_dat(text):
    """-> {crc32: game name} for both headered (.nes) and headerless (.unh) entries."""
    out = {}
    for m in re.finditer(r'game \(\s*name "((?:[^"\\]|\\.)*)".*?rom \( name "[^"]*" size \d+ crc ([0-9A-Fa-f]{8})', text, re.S):
        out.setdefault(int(m.group(2), 16), m.group(1))
    return out


def list_boxarts():
    tree = json.loads(http(f"https://api.github.com/repos/{THUMB_REPO}/git/trees/master"))
    sha = next(t["sha"] for t in tree["tree"] if t["path"] == "Named_Boxarts")
    sub = json.loads(http(f"https://api.github.com/repos/{THUMB_REPO}/git/trees/{sha}"))
    return sorted(t["path"][:-4] for t in sub["tree"] if t["path"].endswith(".png") and t["mode"] == "100644")


def _convert_png(png: bytes) -> bytes:
    """Runs in a worker process."""
    return nes_art.convert(io.BytesIO(png))


def build(args):
    os.makedirs(os.path.join(CACHE, "boxart"), exist_ok=True)
    dat_path = os.path.join(CACHE, "nes.dat")
    if not os.path.exists(dat_path):
        print("downloading No-Intro DAT ...")
        open(dat_path, "wb").write(http(DAT_URL))
    dat = parse_dat(open(dat_path, encoding="utf-8", errors="replace").read())
    names = list_boxarts()
    if args.limit:
        names = names[:args.limit]
    print(f"{len(dat)} DAT CRCs, {len(names)} box arts")

    todo = [n for n in names if not os.path.exists(os.path.join(CACHE, "boxart", n + ".BIN"))]
    print(f"{len(names) - len(todo)} already cached, {len(todo)} to fetch "
          f"({args.jobs} download threads, {args.procs} convert processes)")

    # Downloads are I/O bound -> threads. Conversion is CPU bound pure Python
    # (palette search) -> separate processes, one per core, so the GIL does
    # not serialise it. Each download thread hands its PNG to the process pool.
    done = errors = 0
    t0 = time.time()
    with cf.ProcessPoolExecutor(args.procs) as procs, cf.ThreadPoolExecutor(args.jobs) as threads:
        def job(name):
            try:
                png = http(RAW + urllib.parse.quote(name) + ".png")
                art = procs.submit(_convert_png, png).result()
                dst = os.path.join(CACHE, "boxart", name + ".BIN")
                open(dst + ".tmp", "wb").write(art)
                os.replace(dst + ".tmp", dst)
                return name, "ok"
            except Exception as e:
                return name, f"error: {e}"

        for fut in cf.as_completed([threads.submit(job, n) for n in todo]):
            name, status = fut.result()
            done += 1
            if status.startswith("error"):
                errors += 1
                print(f"  [{done}/{len(todo)}] {name}: {status}", flush=True)
            elif done % 250 == 0 or done == len(todo):
                rate = done / max(time.time() - t0, 1e-6)
                eta = (len(todo) - done) / max(rate, 1e-6)
                print(f"  [{done}/{len(todo)}] {rate:.1f}/s, ~{eta / 60:.0f} min left", flush=True)

    have = {n for n in names if os.path.exists(os.path.join(CACHE, "boxart", n + ".BIN"))}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with zipfile.ZipFile(args.out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in sorted(have):
            z.write(os.path.join(CACHE, "boxart", n + ".BIN"), f"boxart/{n}.BIN")
        rows = [f"{crc:08X}\t{game}" for crc, game in sorted(dat.items()) if thumb_name(game) in have]
        z.writestr("index.tsv", "crc32\tname\n" + "\n".join(rows) + "\n")
        z.writestr("README.txt", "EverDrive N8 NES box-art pack (2 KB NES sprite art per game).\n"
                   "Source: libretro-thumbnails Named_Boxarts + No-Intro DAT (libretro-database).\n"
                   "Install with: python tools/art_pack.py install --pack <this zip> --sd <card>\n"
                   "Cover art is copyrighted by its owners; for personal use only.\n")
    print(f"pack: {args.out}  ({len(have)} arts, {len(rows)} CRC entries, {errors} download errors)")


GOODNES_REGIONS = {
    "U": "USA", "E": "Europe", "J": "Japan", "W": "World", "UE": "USA, Europe", "JU": "Japan, USA",
    "JE": "Japan, Europe", "F": "France", "G": "Germany", "S": "Spain", "I": "Italy", "Sw": "Sweden",
    "A": "Australia", "K": "Korea", "C": "China", "As": "Asia", "Ca": "Canada", "Unl": "Unl",
}
REGION_RANK = ["USA", "World", "Europe", "Japan"]


def _norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def _title(name):
    return _norm(re.sub(r"\s*[\(\[].*$", "", name))


def _rank(name):
    """lower = preferred cover: retail USA > World > Europe > Japan > rest."""
    tags = re.findall(r"\(([^)]*)\)", name)
    region = next((i for i, r in enumerate(REGION_RANK) for t in tags if r in t.split(", ")), len(REGION_RANK))
    bad = any(re.search(r"Beta|Proto|Sample|Demo|Hack|Pirate|Unl", t) for t in tags)
    return region + (10 if bad else 0)


def _name_candidates(filename):
    """No-Intro style names to try for a (possibly GoodNES-named) ROM file."""
    base = re.sub(r"\.(nes|unh|unf|fds)$", "", filename, flags=re.I)
    base = re.sub(r"\s*\[[^\]]*\]", "", base).strip()              # [!] [T+Por] [a1] [h..]
    out = [base]
    m = re.match(r"^(.*?)\s*\(([A-Za-z]+)\)(.*)$", base)
    if m and m.group(2) in GOODNES_REGIONS:
        out.append(f"{m.group(1)} ({GOODNES_REGIONS[m.group(2)]}){m.group(3)}")
        out.append(f"{m.group(1)} ({GOODNES_REGIONS[m.group(2)]})")
    return out


def install(args):
    z = zipfile.ZipFile(args.pack)
    by_crc = {}
    for line in z.read("index.tsv").decode("utf-8").splitlines()[1:]:
        crc, name = line.split("	", 1)
        by_crc[int(crc, 16)] = name
    arts = {n[len("boxart/"):-4] for n in z.namelist() if n.startswith("boxart/")}
    by_full, by_title = {}, {}
    for n in arts:
        by_full.setdefault(_norm(n), n)
        by_title.setdefault(_title(n), []).append(n)
    for t in by_title:
        by_title[t].sort(key=_rank)

    def by_name(filename):
        for c in _name_candidates(filename):
            if _norm(c) in by_full:
                return by_full[_norm(c)]
        best = by_title.get(_title(filename))
        return best[0] if best else None

    roms_root = args.roms or args.sd
    out_dir = os.path.join(args.sd, "EDFC", "ARTS")
    paths = []
    for dp, dn, fn in os.walk(roms_root):
        dn[:] = [d for d in dn if d.upper() != "EDFC"]
        paths += [os.path.join(dp, f) for f in fn if f.lower().endswith(".nes")]

    def scan(path):                       # file I/O + zlib release the GIL -> threads
        rom = open(path, "rb").read()
        if len(rom) < nes_art.FP_START + nes_art.FP_LEN:
            return None
        return path, nes_art.fingerprint(rom), nes_art.full_crc(rom), zlib.crc32(rom) & 0xFFFFFFFF

    plan, unmatched, total = {}, [], 0
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        for r in ex.map(scan, paths):
            if r is None:
                continue
            path, fp, crc_body, crc_file = r
            total += 1
            game = by_crc.get(crc_body) or by_crc.get(crc_file)
            name, how = (thumb_name(game), "crc") if game and thumb_name(game) in arts \
                else (by_name(os.path.basename(path)), "name")
            plan.setdefault(fp, []).append((path, name, how))

    # one cover per fingerprint (= base game: regions, revisions, translations
    # and most hacks share it). Prefer CRC-identified, then region, then majority.
    if not args.dry_run:
        os.makedirs(out_dir, exist_ok=True)
    written = shared = covered = 0
    for fp, items in sorted(plan.items()):
        named = [i for i in items if i[1]]
        if not named:
            unmatched += [i[0] for i in items]
            continue
        votes = {}
        for i in named:
            votes[i[1]] = votes.get(i[1], 0) + 1
        path, name, how = min(named, key=lambda i: (i[2] != "crc", _rank(i[1]), -votes[i[1]]))
        shared += len(votes) > 1
        covered += len(items)
        if not args.dry_run:
            open(os.path.join(out_dir, f"{fp:08X}.BIN"), "wb").write(z.read(f"boxart/{name}.BIN"))
        written += 1
        if args.verbose:
            others = len(items) - 1
            print(f"  {fp:08X}.BIN  [{how}]  {name}" + (f"   (+{others} other dumps)" if others else ""))
    verb = "would install" if args.dry_run else "installed"
    print(f"{verb} {written} arts into {out_dir}")
    print(f"  {covered}/{total} ROMs get a cover ({100 * covered / max(total, 1):.1f}%), "
          f"{len(unmatched)} without; {shared} fingerprints shared by several titles (best cover chosen)")
    if args.verbose and unmatched:
        print("  no art for:\n    " + "\n    ".join(unmatched))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build")
    b.add_argument("--out", default=os.path.join(REPO, "releases", "EDFC-ARTPACK-NES.zip"))
    b.add_argument("--jobs", type=int, default=16, help="parallel downloads (threads)")
    b.add_argument("--procs", type=int, default=os.cpu_count() or 4, help="parallel conversions (processes)")
    b.add_argument("--limit", type=int, default=0, help="only the first N box arts (testing)")
    i = sp.add_parser("install")
    i.add_argument("--pack", default=os.path.join(REPO, "releases", "EDFC-ARTPACK-NES.zip"))
    i.add_argument("--sd", required=True, help="SD card root (contains EDFC/)")
    i.add_argument("--roms", help="where to scan for ROMs (default: whole card)")
    i.add_argument("-v", "--verbose", action="store_true")
    i.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    i.add_argument("--jobs", type=int, default=16, help="parallel ROM reads (threads)")
    args = ap.parse_args()
    build(args) if args.cmd == "build" else install(args)


if __name__ == "__main__":
    main()
