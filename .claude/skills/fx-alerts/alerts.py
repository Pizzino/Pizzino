#!/usr/bin/env python3
"""Alertas (fx-alerts). Suena cuando el precio toca un nivel, el stop, el objetivo o llega una hora.

    python3 alerts.py add --from-plan            # stop, objetivo y hora de cierre de fx/plan.json
    python3 alerts.py add EURUSD above 1.1080    # o below
    python3 alerts.py add --time 16:30 --label "cerrar todo"   # hora de Nueva York
    python3 alerts.py check                      # suena lo que se toco, una sola vez
    python3 alerts.py list
    python3 alerts.py clear

check mira las velas de 5 minutos desde que se creo la alerta: si alguna toco el nivel, suena
aunque el precio ya haya vuelto. Cada alerta suena una vez. Precios de Yahoo, indicativos y con
posible retraso: el stop de verdad es el que pusiste en tu broker, esto solo avisa.
Para vigilar seguido, programa 'check' cada pocos minutos (por ejemplo con /loop).

Codigo 0 si algo sono, 1 si no.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fx-common"))
import fxlib as fx  # noqa: E402


def path_of(a):
    return os.path.join(fx.state_dir(a), "alerts.json")


def add(doc, now, **kw):
    kw.update(id=max([x["id"] for x in doc["alerts"]] + [0]) + 1, created_utc=fx.ts_of(now), rung=None)
    doc["alerts"].append(kw)
    return kw


def describe(x):
    if x["kind"] == "time":
        return "%d  %s de Nueva York  %s" % (x["id"], fx.hhmm(fx.utc_of(x["at_utc"])), x["label"])
    return "%d  %s %s %s  %s" % (x["id"], x["pair"], "sobre" if x["kind"] == "above" else "bajo", fx.fmt(x["pair"], x["price"]), x["label"])


def cmd_add(a):
    now = fx.resolve_now(a)
    doc = fx.read_json(path_of(a), {"alerts": []})
    new = []
    if a.from_plan:
        p = fx.read_json(os.path.join(fx.state_dir(a), "plan.json"))
        if not p:
            raise fx.FxError("No hay fx/plan.json. Corre /fx-exit primero.")
        long = p["side"] == "buy"
        new.append(add(doc, now, kind="below" if long else "above", pair=p["pair"], price=p["stop"], label="STOP"))
        new.append(add(doc, now, kind="above" if long else "below", pair=p["pair"], price=p["target"], label="OBJETIVO"))
        new.append(add(doc, now, kind="time", at_utc=p["flat_by_utc"], label="cerrar %s (flat_by)" % p["pair"]))
    elif a.time:
        clock = fx.parse_clock(a.time)
        ny = fx.to_local(now, "ny")
        at = datetime.datetime.combine(ny.date(), clock)
        if at <= ny:
            at += datetime.timedelta(days=1)
        new.append(add(doc, now, kind="time", at_utc=fx.ts_of(fx.local_to_utc(at, "ny")), label=a.label or "hora"))
    else:
        if not (a.pair and a.kind in ("above", "below") and a.price):
            raise fx.FxError("Uso: add PAR above|below PRECIO, o add --from-plan, o add --time HH:MM.")
        new.append(add(doc, now, kind=a.kind, pair=fx.norm_pair(a.pair), price=a.price, label=a.label or "nivel"))
    fx.write_json(path_of(a), doc)
    for x in new:
        print("Alerta " + describe(x))
    return 0


def cmd_check(a):
    doc = fx.read_json(path_of(a), {"alerts": []})
    live = [x for x in doc["alerts"] if not x["rung"]]
    if not live:
        print("No hay alertas pendientes.")
        return 1
    now = fx.parse_now(a.now) if a.now else None
    charts, rang = {}, []
    for x in live:
        if x["kind"] == "time":
            continue
        if x["pair"] not in charts:
            try:
                res = fx.load_chart(x["pair"], "5d", "5m", a.offline)
                now = now or fx.resolve_now(a, res)
                charts[x["pair"]] = fx.bars_from(res, now, "5m")
            except fx.FxError as e:
                print("%s: %s" % (x["pair"], e))
                charts[x["pair"]] = []
        since = [b for b in charts[x["pair"]] if b["t"] + 300 > x["created_utc"]]
        hit = next((b for b in since if (b["h"] >= x["price"] if x["kind"] == "above" else b["l"] <= x["price"])), None)
        if hit:
            x["rung"] = fx.stamp(now)
            rang.append("SUENA %s: %s toco %s en la vela de las %s de Nueva York." % (
                x["label"], x["pair"], fx.fmt(x["pair"], x["price"]), fx.hhmm(fx.utc_of(hit["t"]))))
    now = now or fx.utc_now()
    for x in live:
        if x["kind"] == "time" and fx.ts_of(now) >= x["at_utc"]:
            x["rung"] = fx.stamp(now)
            rang.append("SUENA %s: ya son las %s de Nueva York." % (x["label"], fx.hhmm(fx.utc_of(x["at_utc"]))))
    fx.write_json(path_of(a), doc)
    for line in rang:
        print(line)
    if not rang:
        print("Nada sono. Revisado %s; %d alertas pendientes." % (fx.stamp(now), len(live)))
    return 0 if rang else 1


def cmd_list(a):
    doc = fx.read_json(path_of(a), {"alerts": []})
    if not doc["alerts"]:
        print("No hay alertas.")
    for x in doc["alerts"]:
        print(("[sono %s] " % x["rung"] if x["rung"] else "[pendiente] ") + describe(x))
    return 0


def cmd_clear(a):
    fx.write_json(path_of(a), {"alerts": []})
    print("Alertas borradas.")
    return 0


def main():
    ap = fx.argparse.ArgumentParser(description="Alertas de precio y de hora.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("add", "check", "list", "clear"):
        p = sub.add_parser(name)
        fx.common_args(p)
        if name == "add":
            p.add_argument("pair", nargs="?")
            p.add_argument("kind", nargs="?")
            p.add_argument("price", nargs="?", type=float)
            p.add_argument("--from-plan", action="store_true")
            p.add_argument("--time")
            p.add_argument("--label")
    a = ap.parse_args()
    return {"add": cmd_add, "check": cmd_check, "list": cmd_list, "clear": cmd_clear}[a.cmd](a)


if __name__ == "__main__":
    fx.run(main)
