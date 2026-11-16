---
name: fx-exit
description: >-
  Plan de salida de forex. Fija el stop y el objetivo antes de entrar, en pips y en precio, para compras y
  ventas. Stop en la mitad del rango por defecto (o al otro lado del rango, a N pips, a un multiplo del ATR
  diario o a un precio), objetivo a 2R, y una hora para cerrar pase lo que pase antes del rollover de las
  17:00 de Nueva York. Muestra el riesgo y el R netos de spread, y rechaza un stop mas cerca que 5 veces el
  spread. Escribe fx/plan.json. Usar cuando el usuario diga "donde pongo el stop", "stop y take profit",
  "cuantos pips de stop", "planifica la salida", "cual es mi R", "risk reward", o justo despues de /fx-entry.
argument-hint: "[--stop range-mid|range-far|pips:N|atr:X|PRECIO] [--target 2R]"
---

# fx-exit

```bash
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan                                   # fx/entry.json: stop range-mid, objetivo 2R
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop range-far --target 1.5R
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop pips:15
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop atr:0.25                   # 0.25 x ATR diario de 14 dias
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --stop 1.10650 --target 1.10200
python3 "${CLAUDE_SKILL_DIR}/exit.py" plan --pair EURUSD --side sell --entry 1.10509 --stop pips:12
```

## Las reglas

| cosa | regla |
| --- | --- |
| stop | del lado contrario: bajo la entrada en una compra, sobre ella en una venta. Se redondea alejandolo de la entrada |
| `range-mid` | la mitad del rango de la sesion (por defecto) |
| `range-far` | el otro extremo del rango: mas lejos, menos unidades |
| `pips:N`, `atr:X`, precio | distancia fija, multiplo del ATR diario, o tu precio |
| R | la distancia de la entrada al stop. Objetivo `2R` = el doble, a favor |
| spread | es un costo real. El plan muestra riesgo neto (stop + spread), objetivo neto (objetivo - spread) y R neto |
| stop minimo | `min_stop_spreads` (5) veces el spread. Mas cerca se rechaza: el spread solo lo tocaria |
| `flat_by` | 16:30 de Nueva York. A las 17:00 es el rollover: el spread se abre y se cobra el swap |

El spread sale de `fx/config.json` -> `spreads_pips`; si no esta, usa uno tipico (EURUSD 1.0, GBPUSD 1.5,
USDJPY 1.0, otros hasta 3.0). Pidele al usuario el de su broker.

## Pasos

1. Corre `exit.py plan`. Si se rechaza, di el motivo tal cual; no acerques el objetivo ni alejes el stop
   por tu cuenta para que pase.
2. Di entrada, stop, objetivo, los pips de cada uno, el R neto y la hora de cierre.
3. Sigue con `/fx-timemachine`.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
