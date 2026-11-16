#!/usr/bin/env python3
"""Entrada (fx-entry). Mira un par vela a vela y dice el momento de entrar. Nunca envia una orden.

    python3 entry.py check EURUSD                    # ruptura del rango asiatico (sesion london)
    python3 entry.py check EURUSD --session ny       # ruptura de la primera hora de Nueva York
    python3 entry.py check GBPUSD --setup level --level 1.3250 --side buy
    python3 entry.py watch EURUSD --every 60         # una linea por consulta hasta que se active o venza
    python3 entry.py watchlist                       # cada par de fx/watchlist.json

Regla: la primera vela COMPLETA de 5 minutos, despues del rango, que CIERRA fuera de el.
Cierre sobre el maximo = compra. Cierre bajo el minimo = venta. Una mecha no cuenta.
La hora de entrada es el cierre de esa vela y el precio es ese cierre.

  level: la primera vela completa del dia de forex (desde las 17:00 de Nueva York) que cierra
         sobre --level (--side buy) o bajo --level (--side sell).

Estados: activada, esperando, vencida, sin-datos. Al activarse escribe fx/entry.json para /fx-exit.
Codigo 0 = activada, 1 = cualquier otra cosa.
"""
import datetime
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "fx-common"))
sys.path.insert(0, os.path.join(HERE, "..", "fx-scanner"))
import fxlib as fx  # noqa: E402
import scan  # noqa: E402


def check_level(pair, level, side, cfg, a):
    res = fx.load_chart(pair, "5d", "5m", a.offline)
    now = fx.resolve_now(a, res)
    bars = fx.bars_from(res, now, "5m")
    day = fx.fx_day(now)
    start = fx.local_to_utc(datetime.datetime.combine(day - datetime.timedelta(days=1), datetime.time(17, 0)), "ny")
    base = {"pair": pair, "setup": "level", "level": level, "session": "level", "tz": "ny",
            "session_date": day.isoformat(), "now": fx.stamp(now)}
    if not fx.market_open(now):
        return dict(base, status="sin-datos", why=fx.closed_reason(now))
    for b in bars:
        if b["t"] < fx.ts_of(start):
            continue
        if (side == "buy" and b["c"] > level) or (side == "sell" and b["c"] < level):
            ct = b["t"] + 300
            return dict(base, status="activada", side=side, price=fx.rnd(pair, b["c"]),
                        entry_bar=fx.hhmm(fx.utc_of(b["t"])), entry_time=fx.hhmm(fx.utc_of(ct)), entry_utc=ct,
                        pips_beyond=fx.to_pips(pair, abs(b["c"] - level)))
    return dict(base, status="esperando", why="Ninguna vela ha cerrado %s %s." % (
        "sobre" if side == "buy" else "bajo", fx.fmt(pair, level)))


def check(pair, a, cfg):
    if a.setup == "level":
        if a.level is None or a.side not in ("buy", "sell"):
            raise fx.FxError("--setup level necesita --level PRECIO y --side buy o sell.")
        return check_level(pair, a.level, a.side, cfg, a)
    row, _ = scan.scan_session(pair, a.session, cfg, a)
    row["setup"] = "session"
    return row


def say(r):
    p = r["pair"]
    if r["status"] == "activada":
        side = "COMPRA" if r["side"] == "buy" else "VENTA"
        where = ""
        if "range_high" in r:
            where = " Rango %s a %s (%.1f pips)." % (fx.fmt(p, r["range_low"]), fx.fmt(p, r["range_high"]), r["range_pips"])
        return "%s ACTIVADA: %s a %s, %s de %s (la vela de las %s cerro %.1f pips fuera).%s" % (
            p, side, fx.fmt(p, r["price"]), r["entry_time"], fx.TZ_NAME[r["tz"]], r["entry_bar"], r["pips_beyond"], where)
    return "%s %s: %s" % (p, r["status"], r.get("why", ""))


def save(r, a):
    doc = dict(r)
    doc["written"] = fx.stamp(fx.utc_now())
    path = os.path.join(fx.state_dir(a), "entry.json")
    fx.write_json(path, doc)
    return path


def cmd_check(a):
    cfg = fx.load_config(a)
    r = check(fx.norm_pair(a.pair), a, cfg)
    if a.json:
        print(fx.json.dumps(r, indent=2, ensure_ascii=False))
    else:
        print(say(r))
    if r["status"] == "activada":
        if not a.no_write:
            path = save(r, a)
            if not a.json:
                print("Escribi %s. Sigue: /fx-exit para fijar el stop y el objetivo ANTES de entrar." % path)
        if not a.json:
            print("Precio indicativo de Yahoo (puede ir con retraso). Mira el precio real en tu broker.")
        return 0
    return 1


def cmd_watch(a):
    cfg = fx.load_config(a)
    pair = fx.norm_pair(a.pair)
    simulated = bool(a.now or a.offline)
    while True:
        r = check(pair, a, cfg)
        print("%s  %s" % (r["now"], say(r)), flush=True)
        if r["status"] == "activada":
            if not a.no_write:
                print("Escribi %s. Sigue: /fx-exit." % save(r, a))
            return 0
        if r["status"] in ("vencida", "sin-datos") or simulated:
            return 1
        time.sleep(max(15, a.every))


def cmd_watchlist(a):
    cfg = fx.load_config(a)
    wl = fx.read_json(os.path.join(fx.state_dir(a), "watchlist.json"))
    if not wl or not wl.get("hits"):
        raise fx.FxError("No hay fx/watchlist.json con pares. Corre /fx-scanner primero.")
    any_hit = False
    for h in wl["hits"]:
        try:
            r = check(h["pair"], a, cfg)
        except fx.FxError as e:
            print("%s sin-datos: %s" % (h["pair"], e))
            continue
        any_hit = any_hit or r["status"] == "activada"
        print(say(r))
    print("Elige un par y corre 'entry.py check PAR' para escribir fx/entry.json. La eleccion es tuya.")
    return 0 if any_hit else 1


def main():
    ap = fx.argparse.ArgumentParser(description="Entrada: la primera vela que cierra fuera del rango.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "watch", "watchlist"):
        p = sub.add_parser(name)
        fx.common_args(p)
        if name != "watchlist":
            p.add_argument("pair")
        p.add_argument("--session", default="london", choices=sorted(fx.SESSIONS))
        p.add_argument("--setup", default="session", choices=["session", "level"])
        p.add_argument("--level", type=float)
        p.add_argument("--side", choices=["buy", "sell"])
        p.add_argument("--no-write", action="store_true")
        if name == "watch":
            p.add_argument("--every", type=int, default=60)
    a = ap.parse_args()
    return {"check": cmd_check, "watch": cmd_watch, "watchlist": cmd_watchlist}[a.cmd](a)


if __name__ == "__main__":
    fx.run(main)
