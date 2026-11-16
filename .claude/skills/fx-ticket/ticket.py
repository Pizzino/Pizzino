#!/usr/bin/env python3
"""Ticket y diario (fx-ticket). Muestra la orden en palabras simples para que TU la pongas en tu
broker, y lleva el diario que usa fx-risk para el limite diario. Esta herramienta no se conecta
a ningun broker y no puede enviar una orden.

    python3 ticket.py show                       # el ticket, LISTO o no
    python3 ticket.py opened --fill 1.10512      # la pusiste y se lleno a ese precio -> diario
    python3 ticket.py close --price 1.10300      # la cerraste a ese precio -> resultado en el diario
    python3 ticket.py close --price 1.10300 --id abc123   # si hay mas de una abierta
    python3 ticket.py status                     # el dia: operaciones, resultado, riesgo abierto

Un ticket esta LISTO solo si fx-risk dio PASA a esa orden exacta hace menos de 10 minutos.
Cuenta demo por defecto ("paper": true en fx/config.json). Pasar a dinero real es decision tuya.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fx-common"))
import fxlib as fx  # noqa: E402

FRESH_MIN = 10


def ready(order, risk, now):
    if not risk:
        return False, "fx-risk no ha revisado esta orden. Corre /fx-risk."
    v = next((x for x in risk.get("verdicts", []) if x.get("id") == order["id"]), None)
    if not v:
        return False, "fx-risk reviso otra orden, no esta. Corre /fx-risk de nuevo."
    if v["verdict"] != "PASA":
        return False, "fx-risk la bloqueo: %s" % " ".join(v["reasons"])
    age = (fx.ts_of(now) - risk.get("checked_utc", 0)) / 60.0
    if age > FRESH_MIN or age < 0:
        return False, "La revision de riesgo tiene mas de %d minutos. Corre /fx-risk de nuevo." % FRESH_MIN
    return True, ""


def load(a):
    d = fx.state_dir(a)
    doc = fx.read_json(os.path.join(d, "orders.json"))
    if not doc or not doc.get("orders"):
        raise fx.FxError("No hay ordenes en fx/orders.json. Corre /fx-budget primero.")
    return d, doc["orders"][0]


def cmd_show(a):
    cfg = fx.load_config(a)
    d, o = load(a)
    now = fx.resolve_now(a)
    ok, why = ready(o, fx.read_json(os.path.join(d, "risk.json")), now)
    pair, acct = o["pair"], o["account_currency"]
    verb = "COMPRAR" if o["side"] == "buy" else "VENDER"
    print("TICKET %s  [%s]  %s" % (o["id"], "CUENTA DEMO" if cfg["paper"] else "DINERO REAL", "LISTO" if ok else "NO LISTO"))
    if not ok:
        print("  %s" % why)
        return 1
    print("  %s %s unidades de %s (%.2f lotes) a mercado." % (verb, format(o["units"], ",").replace(",", "."), pair, o["lots"]))
    print("  Stop loss    %s" % fx.fmt(pair, o["stop_loss"]))
    print("  Take profit  %s" % fx.fmt(pair, o["take_profit"]))
    print("  Si salta el stop pierdes unos %.2f %s (cada pip vale %.2f). Margen %.2f %s." % (
        o["max_loss"], acct, o["pip_value"], o["margin"], acct))
    print("  Cerrar a mano a las %s de Nueva York si no toco ninguno." % o["flat_by"])
    print("Ponla tu en tu broker, con el stop y el take profit en la misma orden. Yo no puedo enviarla.")
    print("Cuando se llene: ticket.py opened --fill PRECIO.")
    return 0


def cmd_opened(a):
    d, o = load(a)
    now = fx.resolve_now(a)
    ok, why = ready(o, fx.read_json(os.path.join(d, "risk.json")), now)
    if not ok:
        raise fx.FxError("No se anota: %s" % why)
    path = os.path.join(d, "journal.json")
    j = fx.read_json(path, {"trades": []})
    if any(t["id"] == o["id"] for t in j["trades"]):
        raise fx.FxError("La orden %s ya esta en el diario." % o["id"])
    j["trades"].append({"id": o["id"], "day": o["date"], "pair": o["pair"], "side": o["side"], "units": o["units"],
                        "fill": a.fill, "stop": o["stop_loss"], "target": o["take_profit"], "max_loss": o["max_loss"],
                        "quote_to_account": o["quote_to_account"], "account_currency": o["account_currency"],
                        "flat_by": o["flat_by"], "opened": fx.stamp(now), "status": "open"})
    fx.write_json(path, j)
    print("Anotada: %s %s %s unidades, llenada a %s. Sigue: /fx-alerts para vigilar stop, objetivo y hora de cierre." % (
        "compra" if o["side"] == "buy" else "venta", o["pair"], format(o["units"], ",").replace(",", "."), fx.fmt(o["pair"], a.fill)))
    return 0


def cmd_close(a):
    d = fx.state_dir(a)
    path = os.path.join(d, "journal.json")
    j = fx.read_json(path, {"trades": []})
    open_ = [t for t in j["trades"] if t["status"] == "open" and (not a.id or t["id"] == a.id)]
    if not open_:
        raise fx.FxError("No hay una operacion abierta%s en el diario." % (" con ese id" if a.id else ""))
    if len(open_) > 1:
        raise fx.FxError("Hay %d abiertas: pasa --id (%s)." % (len(open_), ", ".join(t["id"] for t in open_)))
    t = open_[0]
    sign = 1 if t["side"] == "buy" else -1
    result = sign * (a.price - t["fill"]) * t["units"] * t["quote_to_account"]
    t.update(status="closed", exit=a.price, result=round(result, 2), closed=fx.stamp(fx.resolve_now(a)),
             R=round(result / t["max_loss"], 2) if t["max_loss"] else None)
    fx.write_json(path, j)
    print("Cerrada %s a %s: %+.2f %s (%+.2fR)." % (t["pair"], fx.fmt(t["pair"], a.price), t["result"], t["account_currency"], t["R"]))
    return 0


def cmd_status(a):
    cfg = fx.load_config(a)
    now = fx.resolve_now(a)
    day = fx.fx_day(now).isoformat()
    j = fx.read_json(os.path.join(fx.state_dir(a), "journal.json"), {"trades": []})
    today = [t for t in j["trades"] if t.get("day") == day]
    realized = sum(t.get("result", 0.0) for t in today if t["status"] == "closed")
    open_ = [t for t in j["trades"] if t["status"] == "open"]
    risk = sum(t["max_loss"] for t in open_)
    acct = cfg["account_currency"]
    print("Dia de forex %s: %d de %d operaciones. Resultado cerrado %+.2f %s. Riesgo abierto %.2f %s." % (
        day, len(today), cfg["max_trades_per_day"], realized, acct, risk, acct))
    print("Queda del limite diario: %.2f de %.2f %s." % (
        max(0.0, cfg["max_daily_loss"] - max(0.0, -realized) - risk), cfg["max_daily_loss"], acct))
    for t in open_:
        print("  abierta %s: %s %s %d unidades a %s, stop %s, objetivo %s, cerrar a las %s." % (
            t["id"], "compra" if t["side"] == "buy" else "venta", t["pair"], t["units"], fx.fmt(t["pair"], t["fill"]),
            fx.fmt(t["pair"], t["stop"]), fx.fmt(t["pair"], t["target"]), t["flat_by"]))
    return 0


def main():
    ap = fx.argparse.ArgumentParser(description="Ticket en palabras simples y diario de operaciones.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("show", "opened", "close", "status"):
        p = sub.add_parser(name)
        fx.common_args(p)
        if name == "opened":
            p.add_argument("--fill", type=float, required=True)
        if name == "close":
            p.add_argument("--price", type=float, required=True)
            p.add_argument("--id")
    a = ap.parse_args()
    return {"show": cmd_show, "opened": cmd_opened, "close": cmd_close, "status": cmd_status}[a.cmd](a)


if __name__ == "__main__":
    fx.run(main)
