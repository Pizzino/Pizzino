#!/usr/bin/env python3
"""Calendario economico (fx-calendar). Lo que mueve una divisa: tipos de interes, inflacion,
empleo, bancos centrales. Lee el calendario semanal gratuito de ForexFactory.

    python3 econ.py fetch                    # baja la semana -> fx/calendar.json (cache de 1 hora)
    python3 econ.py next                     # proximas 24 horas, impacto alto, tus pares
    python3 econ.py next EURUSD --hours 48   # solo EUR y USD
    python3 econ.py next --impact medium     # alto y medio
    python3 econ.py next --currencies USD,JPY

Fuente: https://nfs.faireconomy.media/ff_calendar_thisweek.json (gratis, no oficial, solo la
semana en curso). Las horas se muestran en hora de Nueva York. El feed pide no bajarlo
mas de una vez cada pocos minutos: por eso se guarda una hora.

Codigo 0 si hay eventos que mostrar, 1 si no.
"""
import datetime
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fx-common"))
import fxlib as fx  # noqa: E402

URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
RANK = {"high": 3, "medium": 2, "low": 1, "holiday": 0}
NAME = {"high": "ALTO", "medium": "medio", "low": "bajo", "holiday": "festivo"}
MAX_AGE_H = 12   # mas viejo que esto ya no sirve para el control de riesgo


def parse_feed(text):
    try:
        raw = fx.json.loads(text)
    except ValueError:
        raise fx.FxError("El calendario no llego como JSON (el feed limita las descargas; prueba en unos minutos).")
    out = []
    for e in raw if isinstance(raw, list) else []:
        try:
            dt = datetime.datetime.fromisoformat(e["date"])
            utc = dt.astimezone(datetime.timezone.utc).replace(tzinfo=None)
            cur = str(e["country"]).upper()
        except (KeyError, ValueError, TypeError):
            continue
        if cur not in fx.CCYS:
            continue
        out.append({"utc": utc.strftime("%Y-%m-%dT%H:%M"), "currency": cur, "title": e.get("title", ""),
                    "impact": str(e.get("impact", "")).lower(), "forecast": e.get("forecast", ""),
                    "previous": e.get("previous", "")})
    out.sort(key=lambda x: x["utc"])
    return out


def ev_utc(e):
    return datetime.datetime.strptime(e["utc"], "%Y-%m-%dT%H:%M")


def load(a, now, refresh=False):
    """El calendario guardado, o uno recien bajado si no hay o tiene mas de una hora."""
    path = os.path.join(fx.state_dir(a), "calendar.json")
    doc = fx.read_json(path)
    if a.offline:
        events = parse_feed(fx._read_file(a.offline))
        doc = {"fetched_utc": now.strftime("%Y-%m-%dT%H:%M"), "source": a.offline, "events": events}
        fx.write_json(path, doc)
        return doc
    if doc and not refresh and age_hours(doc, now) < 1:
        return doc
    try:
        events = parse_feed(fx._get(URL))
    except fx.FxError:
        raise
    except Exception as e:
        if doc:
            return doc
        raise fx.FxError("No pude bajar el calendario (%s)." % getattr(e, "reason", e))
    doc = {"fetched_utc": now.strftime("%Y-%m-%dT%H:%M"), "source": URL, "events": events}
    fx.write_json(path, doc)
    return doc


def age_hours(doc, now):
    try:
        t = datetime.datetime.strptime(doc["fetched_utc"], "%Y-%m-%dT%H:%M")
    except (KeyError, ValueError, TypeError):
        return 1e9
    return abs((now - t).total_seconds()) / 3600.0


def events_near(doc, pair, at_utc, minutes, min_impact="high"):
    """Eventos de las dos divisas del par a +-minutes de at_utc. Lo usa fx-risk."""
    curs = (pair[:3], pair[3:])
    lim = datetime.timedelta(minutes=minutes)
    return [e for e in doc.get("events", [])
            if e["currency"] in curs and RANK.get(e["impact"], 0) >= RANK[min_impact]
            and abs(ev_utc(e) - at_utc) <= lim]


def cmd_fetch(a):
    now = fx.resolve_now(a)
    doc = load(a, now, refresh=True)
    highs = sum(1 for e in doc["events"] if e["impact"] == "high")
    print("Calendario de la semana: %d eventos de las 8 divisas, %d de impacto alto. Bajado %s." % (
        len(doc["events"]), highs, fx.stamp(now)))
    print("Escribi %s." % os.path.join(fx.state_dir(a), "calendar.json"))
    return 0


def cmd_next(a):
    cfg = fx.load_config(a)
    now = fx.resolve_now(a)
    doc = load(a, now)
    if a.currencies:
        curs = [c.strip().upper() for c in a.currencies.split(",")]
    elif a.pair:
        p = fx.norm_pair(a.pair)
        curs = [p[:3], p[3:]]
    else:
        curs = sorted({c for p in cfg["pairs"] for c in (p[:3], p[3:])})
    end = now + datetime.timedelta(hours=a.hours)
    rows = [e for e in doc["events"] if e["currency"] in curs and now <= ev_utc(e) <= end
            and (RANK.get(e["impact"], 0) >= RANK[a.impact] or e["impact"] == "holiday")]
    if a.json:
        print(fx.json.dumps({"now": fx.stamp(now), "currencies": curs, "events": rows}, indent=2, ensure_ascii=False))
        return 0 if rows else 1
    print("Calendario, %s. Proximas %d horas, divisas %s, impacto %s o mayor." % (
        fx.stamp(now), a.hours, ", ".join(curs), NAME[a.impact]))
    if age_hours(doc, now) > MAX_AGE_H:
        print("AVISO: el calendario guardado tiene mas de %d horas. Corre 'econ.py fetch'." % MAX_AGE_H)
    if not rows:
        print("Nada en ese plazo. El feed solo trae la semana en curso.")
        return 1
    for e in rows:
        t = ev_utc(e)
        mins = int((t - now).total_seconds() // 60)
        extra = " (previsto %s, anterior %s)" % (e["forecast"] or "?", e["previous"] or "?") if e["forecast"] or e["previous"] else ""
        print("  %s  %s  %-7s %s%s  [en %dh %02dm]" % (
            fx.to_local(t, "ny").strftime("%a %d %H:%M"), e["currency"], NAME.get(e["impact"], e["impact"]),
            e["title"], extra, mins // 60, mins % 60))
    print("Horas en Nueva York. Alrededor de un dato de impacto alto el spread se abre y el precio salta:")
    print("fx-risk bloquea entradas a +-%d minutos de uno." % cfg["news_blackout_min"])
    return 0


def main():
    ap = fx.argparse.ArgumentParser(description="Calendario economico para forex.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("fetch")
    fx.common_args(p)
    p = sub.add_parser("next")
    fx.common_args(p)
    p.add_argument("pair", nargs="?")
    p.add_argument("--hours", type=int, default=24)
    p.add_argument("--impact", default="high", choices=["high", "medium", "low"])
    p.add_argument("--currencies")
    a = ap.parse_args()
    return cmd_fetch(a) if a.cmd == "fetch" else cmd_next(a)


if __name__ == "__main__":
    fx.run(main)
