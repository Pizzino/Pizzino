#!/usr/bin/env python3
"""Escaner de forex (fx-scanner). Lee los graficos de los 28 pares y lista los que cumplen una regla.

    python3 scan.py daily                      # cierres diarios, los 28 pares -> fx/watchlist.json
    python3 scan.py daily --pairs EURUSD,GBPJPY
    python3 scan.py daily --mine               # solo los pares de fx/config.json
    python3 scan.py session --session london   # ruptura del rango asiatico tras abrir Londres
    python3 scan.py session --session ny       # ruptura de la primera hora de Nueva York

Reglas diarias (sobre cierres; las dos direcciones):
  ruptura_20d_alcista / ruptura_20d_bajista   el ultimo cierre supera (o pierde) los 20 cierres anteriores
  recupera_ma20 / pierde_ma20                 cruza su media de 20 dias con el ultimo cierre
  sobrevendido / sobrecomprado                RSI 14 (Wilder) bajo 30 / sobre 70

Regla de sesion: la primera vela COMPLETA de 5 minutos que CIERRA fuera del rango.
Cierre sobre el maximo = compra; cierre bajo el minimo = venta.

Cumplir una regla describe el grafico. No dice que operar. Codigo 0 si hubo coincidencias, 1 si no.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fx-common"))
import fxlib as fx  # noqa: E402

LABEL = {
    "ruptura_20d_alcista": "cerro sobre sus 20 cierres anteriores",
    "ruptura_20d_bajista": "cerro bajo sus 20 cierres anteriores",
    "recupera_ma20": "volvio a cerrar sobre su media de 20 dias",
    "pierde_ma20": "cerro bajo su media de 20 dias",
    "sobrevendido": "sobrevendido (RSI bajo 30)",
    "sobrecomprado": "sobrecomprado (RSI sobre 70)",
}


def daily_setups(closes):
    out = []
    if len(closes) < 22:
        return out
    last, prev = closes[-1], closes[-2]
    window = closes[-21:-1]
    if last > max(window):
        out.append("ruptura_20d_alcista")
    if last < min(window):
        out.append("ruptura_20d_bajista")
    ma_now = fx.sma(closes, 20)
    ma_prev = fx.sma(closes[:-1], 20)
    if prev < ma_prev and last > ma_now:
        out.append("recupera_ma20")
    if prev > ma_prev and last < ma_now:
        out.append("pierde_ma20")
    r = fx.rsi(closes)
    if r is not None and r < 30:
        out.append("sobrevendido")
    if r is not None and r > 70:
        out.append("sobrecomprado")
    return out


def pick_pairs(a, cfg):
    if a.pairs:
        return [fx.norm_pair(p) for p in a.pairs.split(",") if p.strip()]
    return list(cfg["pairs"]) if a.mine else list(fx.PAIRS)


def cmd_daily(a):
    cfg = fx.load_config(a)
    pairs = pick_pairs(a, cfg)
    hits, failed, scanned, now, last_date = [], [], 0, None, None
    for p in pairs:
        try:
            res = fx.load_chart(p, "6mo", "1d", a.offline)
        except fx.FxError:
            failed.append(p)
            continue
        now = now or fx.resolve_now(a, res)
        bars = fx.bars_from(res, now, "1d")
        if len(bars) < 30:
            failed.append(p)
            continue
        scanned += 1
        closes = [b["c"] for b in bars]
        last_date = fx.utc_of(bars[-1]["t"] + 3600).date().isoformat()
        setups = daily_setups(closes)
        if setups:
            a14 = fx.atr(bars)
            hits.append({"pair": p, "setups": setups, "price": fx.rnd(p, closes[-1]),
                         "rsi": round(fx.rsi(closes), 1), "atr_pips": fx.to_pips(p, a14) if a14 else None,
                         "close_date": last_date})
    now = now or fx.utc_now()
    doc = {"mode": "daily", "as_of": fx.stamp(now), "universe": len(pairs), "scanned": scanned,
           "failed": failed, "hits": hits}
    if a.json:
        print(fx.json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print("Escaneo diario, %s, cierres hasta %s (Yahoo, velas diarias)." % (fx.stamp(now), last_date or "?"))
        print("Lei %d de %d pares%s." % (scanned, len(pairs),
              " (sin datos: %s)" % ", ".join(failed) if failed else ""))
        if not hits:
            print("Ningun par cumplio una regla.")
        else:
            print("%d pares cumplieron una regla:" % len(hits))
            for h in hits:
                print("  %-7s %10s  RSI %5.1f  ATR %6s pips  %s" % (
                    h["pair"], fx.fmt(h["pair"], h["price"]), h["rsi"],
                    h["atr_pips"], "; ".join(LABEL[s] for s in h["setups"])))
        print("Cumplir una regla describe el grafico; no es una senal de compra o venta.")
        print("Sigue: elige un par, luego /fx-calendar PAR y /fx-entry PAR.")
    if hits and not a.no_write:
        path = os.path.join(fx.state_dir(a), "watchlist.json")
        fx.write_json(path, doc)
        if not a.json:
            print("Escribi %s." % path)
    return 0 if hits else 1


def scan_session(pair, name, cfg, a, now=None):
    """Estado de la sesion de hoy para un par. Lo usan fx-scanner y fx-entry."""
    res = fx.load_chart(pair, "5d", "5m", a.offline)
    now = now or fx.resolve_now(a, res)
    bars = fx.bars_from(res, now, "5m")
    day = fx.session_day(name, now, cfg)
    rs, re_, eu = fx.session_window(name, day, cfg)
    tz = fx.session_def(name, cfg)["tz"]
    base = {"pair": pair, "session": name, "session_date": day.isoformat(), "tz": tz,
            "range_start": fx.hhmm(rs, tz), "range_end": fx.hhmm(re_, tz), "entries_until": fx.hhmm(eu, tz),
            "now": fx.stamp(now)}
    if not fx.market_open(re_):
        return dict(base, status="sin-datos", why=fx.closed_reason(re_)), now
    if now < re_:
        return dict(base, status="esperando", why="El rango se cierra a las %s de %s." % (
            fx.hhmm(re_, tz), fx.TZ_NAME[tz])), now
    rng = fx.range_of(bars, rs, re_)
    if not rng:
        return dict(base, status="sin-datos", why="Faltan velas del rango (dia fino o datos cortados)."), now
    base.update(range_high=fx.rnd(pair, rng["high"]), range_low=fx.rnd(pair, rng["low"]),
                range_pips=fx.to_pips(pair, rng["high"] - rng["low"]))
    seen = [b for b in bars if b["t"] + 300 <= fx.ts_of(now)]
    br = fx.find_break(seen, rng, re_, eu)
    if br:
        edge = rng["high"] if br["side"] == "buy" else rng["low"]
        return dict(base, status="activada", side=br["side"], price=fx.rnd(pair, br["price"]),
                    entry_bar=fx.hhmm(fx.utc_of(br["bar_t"]), tz), entry_time=fx.hhmm(fx.utc_of(br["close_t"]), tz),
                    entry_utc=br["close_t"], pips_beyond=fx.to_pips(pair, abs(br["price"] - edge))), now
    if now >= eu:
        return dict(base, status="vencida", why="Ninguna vela cerro fuera del rango antes de las %s." % fx.hhmm(eu, tz)), now
    last = seen[-1]["c"] if seen else None
    why = "Ninguna vela ha cerrado fuera del rango."
    if last:
        why += " Ultimo cierre %s: a %.1f pips del maximo y %.1f del minimo." % (
            fx.fmt(pair, last), fx.to_pips(pair, rng["high"] - last), fx.to_pips(pair, last - rng["low"]))
    return dict(base, status="esperando", why=why), now


def cmd_session(a):
    cfg = fx.load_config(a)
    pairs = pick_pairs(a, cfg)
    rows, failed, now = [], [], fx.parse_now(a.now) if a.now else None
    for p in pairs:
        try:
            row, now2 = scan_session(p, a.session, cfg, a, now)
            now = now or now2
            rows.append(row)
        except fx.FxError:
            failed.append(p)
    hits = [r for r in rows if r["status"] == "activada"]
    hits.sort(key=lambda r: r["entry_utc"])
    now = now or fx.utc_now()
    doc = {"mode": "session", "session": a.session, "as_of": fx.stamp(now), "universe": len(pairs),
           "scanned": len(rows), "failed": failed, "hits": hits,
           "others": [r for r in rows if r["status"] != "activada"]}
    if a.json:
        print(fx.json.dumps(doc, indent=2, ensure_ascii=False))
    else:
        print("Escaneo de sesion '%s', %s (Yahoo, velas de 5 minutos)." % (a.session, fx.stamp(now)))
        print("Lei %d de %d pares%s." % (len(rows), len(pairs), " (sin datos: %s)" % ", ".join(failed) if failed else ""))
        if rows and all(r["status"] == rows[0]["status"] and r["status"] != "activada" for r in rows):
            print("%s: %s" % (rows[0]["status"].capitalize(), rows[0].get("why", "")))
        elif not hits:
            print("Ningun par ha cerrado fuera de su rango.")
        for h in hits:
            print("  %s  %-7s %-6s %10s  rango %s a %s (%.1f pips)  %.1f pips fuera" % (
                h["entry_time"], h["pair"], "COMPRA" if h["side"] == "buy" else "VENTA", fx.fmt(h["pair"], h["price"]),
                fx.fmt(h["pair"], h["range_low"]), fx.fmt(h["pair"], h["range_high"]), h["range_pips"], h["pips_beyond"]))
        if hits:
            print("%d de %d pares cerraron fuera de su rango (hora de %s). Una ruptura vieja ya esta lejos del precio actual." % (
                len(hits), len(rows), fx.TZ_NAME[hits[0]["tz"]]))
            print("Sigue: elige un par, luego /fx-calendar PAR y /fx-entry PAR.")
    if hits and not a.no_write:
        path = os.path.join(fx.state_dir(a), "watchlist.json")
        fx.write_json(path, doc)
        if not a.json:
            print("Escribi %s." % path)
    return 0 if hits else 1


def main():
    ap = fx.argparse.ArgumentParser(description="Escaner de forex: 28 pares, reglas diarias y rupturas de sesion.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("daily", "session"):
        p = sub.add_parser(name)
        fx.common_args(p)
        p.add_argument("--pairs", help="lista separada por comas")
        p.add_argument("--mine", action="store_true", help="solo los pares de fx/config.json")
        p.add_argument("--no-write", action="store_true")
        if name == "session":
            p.add_argument("--session", default="london", choices=sorted(fx.SESSIONS))
    a = ap.parse_args()
    return cmd_daily(a) if a.cmd == "daily" else cmd_session(a)


if __name__ == "__main__":
    fx.run(main)
