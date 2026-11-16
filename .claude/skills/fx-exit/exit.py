#!/usr/bin/env python3
"""Salida (fx-exit). Fija el stop y el objetivo ANTES de entrar, en pips y en precio.

    python3 exit.py plan                                  # lee fx/entry.json: stop en la mitad del rango, objetivo 2R
    python3 exit.py plan --stop range-far --target 1.5R   # stop al otro lado del rango
    python3 exit.py plan --stop pips:15 --target 2R       # stop a 15 pips
    python3 exit.py plan --stop atr:0.25                  # stop a 0.25 veces el ATR diario de 14 dias
    python3 exit.py plan --stop 1.10650 --target 1.10200  # precios exactos
    python3 exit.py plan --pair EURUSD --side sell --entry 1.10509 --stop pips:12

Reglas:
  - El stop va del lado contrario a la operacion: bajo la entrada en una compra, sobre ella en una venta.
  - Se redondea alejandolo de la entrada, al ultimo decimal del par.
  - Un stop mas cerca que min_stop_spreads (5) veces el spread se rechaza: el spread solo lo tocaria.
  - R es la distancia al stop. Objetivo 2R = el doble de esa distancia, a favor.
  - El spread es un costo real: el plan muestra tambien el riesgo y el objetivo netos de spread.
  - flat_by (16:30 de Nueva York por defecto): hora para cerrar pase lo que pase, antes del
    rollover de las 17:00, cuando el spread se abre y se cobra el swap.

Escribe fx/plan.json para /fx-timemachine, /fx-budget y /fx-alerts. No envia ninguna orden.
"""
import datetime
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fx-common"))
import fxlib as fx  # noqa: E402


def away(pair, price, side, kind):
    """Redondea al decimal del par: el stop alejandose de la entrada, el objetivo acercandose."""
    k = 10 ** fx.digits(pair)
    up = (side == "buy") != (kind == "stop")
    v = price * k
    v = math.ceil(v - 1e-9) if up else math.floor(v + 1e-9)
    return v / k


def stop_from_rule(rule, pair, side, entry, rng_high, rng_low, atr_value=None):
    """rule: range-mid | range-far | pips:N | atr:X | PRECIO. Devuelve (precio, regla normalizada)."""
    long = side == "buy"
    r = str(rule).strip().lower()
    if r in ("range-mid", "range-far"):
        if rng_high is None or rng_low is None:
            raise fx.FxError("--stop %s necesita el rango de fx/entry.json. Usa pips:N o un precio." % r)
        raw = (rng_high + rng_low) / 2 if r == "range-mid" else (rng_low if long else rng_high)
    elif r.startswith("pips:"):
        n = _num(r[5:], "pips")
        raw = entry - n * fx.pip(pair) if long else entry + n * fx.pip(pair)
    elif r.startswith("atr:"):
        x = _num(r[4:], "el multiplo del ATR")
        if not atr_value:
            raise fx.FxError("No hay ATR diario para %s." % pair)
        raw = entry - x * atr_value if long else entry + x * atr_value
    else:
        raw = _num(r, "el stop")
    return away(pair, raw, side, "stop"), r


def _num(text, what):
    try:
        v = float(text)
        if v <= 0:
            raise ValueError
        return v
    except ValueError:
        raise fx.FxError("No entiendo %s: '%s'." % (what, text))


def flat_by_utc(entry_utc, clock):
    """La proxima vez que sea esa hora de Nueva York despues de la entrada, dentro del dia de forex."""
    ny = fx.to_local(entry_utc, "ny")
    cand = datetime.datetime.combine(ny.date(), clock)
    if cand <= ny:
        cand += datetime.timedelta(days=1)
    roll = datetime.datetime.combine(fx.fx_day(entry_utc), datetime.time(17, 0))
    if cand > roll:
        raise fx.FxError("La entrada (%s de Nueva York) es posterior a flat_by (%s). No queda tiempo hoy." % (
            ny.strftime("%H:%M"), clock.strftime("%H:%M")))
    return fx.local_to_utc(cand, "ny")


def build_plan(a, cfg):
    src = {}
    if not a.pair:
        src = fx.read_json(os.path.join(fx.state_dir(a), "entry.json"))
        if not src or src.get("status") != "activada":
            raise fx.FxError("No hay una entrada activada en fx/entry.json. Corre /fx-entry, o pasa --pair, --side y --entry.")
    pair = fx.norm_pair(a.pair or src["pair"])
    side = a.side or src.get("side")
    entry = a.entry if a.entry is not None else src.get("price")
    if side not in ("buy", "sell") or not entry:
        raise fx.FxError("Faltan --side (buy o sell) y --entry PRECIO.")
    entry = float(entry)
    long = side == "buy"
    entry_utc = fx.utc_of(src["entry_utc"]) if src.get("entry_utc") else fx.resolve_now(a)
    rh, rl = src.get("range_high"), src.get("range_low")
    atr_value = None
    if str(a.stop).lower().startswith("atr:"):
        res = fx.load_chart(pair, "6mo", "1d", a.offline)
        atr_value = fx.atr(fx.bars_from(res, entry_utc, "1d"))
    stop, rule = stop_from_rule(a.stop, pair, side, entry, rh, rl, atr_value)
    risk = (entry - stop) if long else (stop - entry)
    if risk <= 0:
        raise fx.FxError("El stop %s queda del lado equivocado de la entrada %s para una %s." % (
            fx.fmt(pair, stop), fx.fmt(pair, entry), "compra" if long else "venta"))
    sp = fx.spread_pips(pair, cfg)
    risk_pips = risk / fx.pip(pair)
    if risk_pips < cfg["min_stop_spreads"] * sp:
        raise fx.FxError("Stop a %.1f pips con un spread de %.1f: demasiado cerca (minimo %g veces el spread = %.1f pips). "
                         "Aleja el stop o deja pasar esta operacion." % (risk_pips, sp, cfg["min_stop_spreads"], cfg["min_stop_spreads"] * sp))
    t = str(a.target).strip().upper()
    if t.endswith("R"):
        r_mult = _num(t[:-1], "el objetivo")
        target = away(pair, entry + r_mult * risk if long else entry - r_mult * risk, side, "target")
    else:
        target = round(_num(t, "el objetivo"), fx.digits(pair))
    reward = (target - entry) if long else (entry - target)
    if reward <= 0:
        raise fx.FxError("El objetivo %s queda del lado equivocado de la entrada %s." % (fx.fmt(pair, target), fx.fmt(pair, entry)))
    clock = fx.parse_clock(a.flat_by or cfg["flat_by"], "flat_by")
    fb = flat_by_utc(entry_utc, clock)
    s = sp * fx.pip(pair)
    return {
        "pair": pair, "side": side, "entry": fx.rnd(pair, entry),
        "entry_time": fx.hhmm(entry_utc), "entry_utc": fx.ts_of(entry_utc), "date": fx.fx_day(entry_utc).isoformat(),
        "setup": src.get("setup", "manual"), "session": src.get("session"), "session_date": src.get("session_date"),
        "range_high": rh, "range_low": rl,
        "stop": stop, "stop_rule": rule, "stop_pips": round(risk_pips, 1),
        "target": target, "target_r": round(reward / risk, 2), "target_pips": fx.to_pips(pair, reward),
        "spread_pips": sp, "net_risk_pips": round(risk_pips + sp, 1), "net_target_pips": round(reward / fx.pip(pair) - sp, 1),
        "net_r": round((reward - s) / (risk + s), 2),
        "flat_by": clock.strftime("%H:%M"), "flat_by_utc": fx.ts_of(fb),
    }


def cmd_plan(a):
    cfg = fx.load_config(a)
    p = build_plan(a, cfg)
    if a.json:
        print(fx.json.dumps(p, indent=2, ensure_ascii=False))
    else:
        pair = p["pair"]
        print("Plan %s %s, entrada %s a las %s de Nueva York." % (
            "COMPRA" if p["side"] == "buy" else "VENTA", pair, fx.fmt(pair, p["entry"]), p["entry_time"]))
        print("  Stop      %s  (%s)  a %.1f pips = 1R" % (fx.fmt(pair, p["stop"]), p["stop_rule"], p["stop_pips"]))
        print("  Objetivo  %s  a %.1f pips = %.2fR" % (fx.fmt(pair, p["target"]), p["target_pips"], p["target_r"]))
        print("  Spread supuesto %.1f pips: riesgo neto %.1f pips, objetivo neto %.1f pips, R neto %.2f." % (
            p["spread_pips"], p["net_risk_pips"], p["net_target_pips"], p["net_r"]))
        print("  Cerrar a las %s de Nueva York pase lo que pase (antes del rollover de las 17:00)." % p["flat_by"])
    if not a.no_write:
        path = os.path.join(fx.state_dir(a), "plan.json")
        fx.write_json(path, p)
        if not a.json:
            print("Escribi %s. Sigue: /fx-timemachine, luego /fx-budget." % path)
    return 0


def main():
    ap = fx.argparse.ArgumentParser(description="Plan de salida: stop, objetivo y hora de cierre.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    fx.common_args(p)
    p.add_argument("--pair")
    p.add_argument("--side", choices=["buy", "sell"])
    p.add_argument("--entry", type=float)
    p.add_argument("--stop", default="range-mid")
    p.add_argument("--target", default="2R")
    p.add_argument("--flat-by")
    p.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    return cmd_plan(a)


if __name__ == "__main__":
    fx.run(main)
