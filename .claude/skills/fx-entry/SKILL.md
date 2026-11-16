---
name: fx-entry
description: >-
  Entrada de forex. Mira un par vela a vela y dice el momento de entrar: la primera vela completa de 5
  minutos que CIERRA fuera del rango de la sesion (rango asiatico para Londres, primera hora para Nueva York),
  o que cierra mas alla de un nivel que tu das. Funciona en las dos direcciones: compra y venta. Dice
  activada con la hora y el precio, esperando y a cuantos pips, vencida o sin datos, y escribe fx/entry.json.
  Nunca envia una orden. Usar cuando el usuario diga "avisame cuando entrar", "vigila el EURUSD", "ya rompio
  el rango", "senal de entrada", "watch GBPUSD", "has it broken out", o despues de /fx-scanner y /fx-calendar.
argument-hint: "PAR [--session london|ny]"
---

# fx-entry

```bash
python3 "${CLAUDE_SKILL_DIR}/entry.py" check EURUSD                 # sesion london (rango asiatico)
python3 "${CLAUDE_SKILL_DIR}/entry.py" check EURUSD --session ny    # primera hora de Nueva York
python3 "${CLAUDE_SKILL_DIR}/entry.py" check GBPUSD --setup level --level 1.3250 --side buy
python3 "${CLAUDE_SKILL_DIR}/entry.py" watch EURUSD --every 60      # repite hasta activarse o vencer
python3 "${CLAUDE_SKILL_DIR}/entry.py" watchlist                    # cada par de fx/watchlist.json
```

## La regla

- El rango es el maximo y el minimo de la ventana de la sesion (ver `/fx-scanner`).
- Se activa con la primera vela COMPLETA despues del rango que CIERRA fuera: sobre el maximo = compra, bajo
  el minimo = venta. Una mecha que sale y vuelve no cuenta.
- La hora de entrada es el cierre de esa vela y el precio es ese cierre.
- Vence si ninguna vela cierra fuera antes de `entries_until` (11:00 Londres o 12:00 Nueva York).
- `--setup level`: la primera vela del dia de forex (desde las 17:00 de Nueva York) que cierra sobre
  `--level` (`--side buy`) o bajo el (`--side sell`).

Estados: `activada`, `esperando`, `vencida`, `sin-datos`. Codigo 0 solo si esta activada.

## Pasos

1. Corre `entry.py check PAR` con la sesion que toca.
2. Activada: di el lado, el precio, la hora y cuantos pips cerro fuera. Di que el precio es indicativo y
   que mire el de su broker. Sigue con `/fx-exit`, ANTES de entrar.
3. Esperando: di a cuantos pips esta del maximo y del minimo. Ofrece `watch`.
4. Vencida: dilo tal cual. No busques otra razon para entrar.
5. Una senal de hace mas de 15 minutos ya es vieja: `/fx-risk` la bloquea.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
