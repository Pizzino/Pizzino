---
name: fx-ticket
description: >-
  Ticket y diario de forex. Muestra la orden que paso el control de riesgo en palabras simples (comprar o
  vender, unidades y lotes, stop loss, take profit, perdida maxima, margen y hora de cierre) para que el
  usuario la ponga a mano en su broker, y lleva el diario de operaciones abiertas y cerradas que alimenta el
  limite diario. No se conecta a ningun broker y no puede enviar una orden. Usar cuando el usuario diga
  "muestrame el ticket", "que pongo en el broker", "ya la puse", "se lleno a", "cerre la operacion", "como voy
  hoy", "show the ticket", "close my trade", o despues de que /fx-risk diga PASA.
argument-hint: "[show | opened --fill P | close --price P | status]"
---

# fx-ticket

```bash
python3 "${CLAUDE_SKILL_DIR}/ticket.py" show                     # el ticket, LISTO o NO LISTO
python3 "${CLAUDE_SKILL_DIR}/ticket.py" opened --fill 1.10512    # el usuario la puso y se lleno ahi
python3 "${CLAUDE_SKILL_DIR}/ticket.py" close --price 1.10300    # la cerro a ese precio
python3 "${CLAUDE_SKILL_DIR}/ticket.py" status                   # el dia: operaciones, resultado, riesgo abierto
```

## Como funciona

- Un ticket esta LISTO solo si `/fx-risk` dio PASA a esa orden exacta hace menos de 10 minutos. Si no, dice
  por que y no muestra nada que copiar.
- El usuario pone la orden en su broker (MetaTrader, OANDA, cTrader, el que use), con el stop loss y el take
  profit en la misma orden. Esta skill no tiene conexion con ningun broker.
- `opened` anota la operacion en `fx/journal.json` con el precio al que se lleno. `close` anota el resultado
  en la divisa de la cuenta y en R. `/fx-risk` lee ese diario para el limite diario, el maximo de
  operaciones y las divisas ya comprometidas.
- Cuenta demo por defecto: el ticket lo dice arriba. Solo dice DINERO REAL si el usuario puso
  `"paper": false` en su configuracion.

## Pasos

1. Corre `ticket.py show` y muestra el ticket tal cual.
2. Pregunta al usuario si la puso y a que precio se lleno. Solo entonces corre `opened --fill PRECIO`. No
   anotes una operacion que el usuario no confirmo.
3. Sigue con `/fx-alerts` (`alerts.py add --from-plan`).
4. Al cerrar: `close --price PRECIO` con el precio real de cierre del broker, y luego `status`.
5. Nunca digas que la orden "se envio": la pone el usuario.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
