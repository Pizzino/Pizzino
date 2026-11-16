---
name: fx-timemachine
description: >-
  Time Machine de forex. Repite la operacion antes de arriesgar dinero: 10.000 sesiones simuladas con las
  velas de 5 minutos del propio par en los ultimos 60 dias, mas cada dia pasado en que la misma regla se
  activo. Da la probabilidad de objetivo primero, stop primero o ninguno antes de la hora de cierre, el R
  promedio neto de spread, la historia real y un veredicto honesto. Usar cuando el usuario diga "corre el
  time machine", "que probabilidades tiene", "simula esta operacion", "monte carlo", "backtest de este
  setup", "es una moneda al aire", "what are the odds", o despues de /fx-exit y antes de /fx-budget.
argument-hint: "[--replays N] [--seed N]"
---

# fx-timemachine

El Time Machine va entre el plan y el dinero. Pregunta una sola cosa: si hoy se parece a los ultimos 60
dias de este par, cuantas veces este plan llega primero al objetivo, primero al stop, o a ninguno. Es una
simulacion con las velas recientes del par. No es una prediccion.

```bash
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run            # fx/plan.json, 10.000 repeticiones, semilla 19
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --write    # guarda fx/timemachine.json
python3 "${CLAUDE_SKILL_DIR}/timemachine.py" run --replays 20000 --seed 7
```

## Como funciona

1. **La bolsa de velas.** 60 dias de velas de 5 minutos, separadas por dia de forex (17:00 a 17:00 de Nueva
   York, 288 velas). Solo entran dias casi completos y anteriores al plan. Cada vela se guarda como maximo,
   minimo y cierre divididos por el cierre anterior.
2. **Una repeticion.** Empieza en la entrada. Para cada vela hasta `flat_by` saca al azar una vela pasada de
   la misma hora del dia (mas o menos 2 velas) y la aplica. Mira primero el stop y luego el objetivo: una
   vela que toca los dos cuenta como stop.
3. **10.000 repeticiones** dan tres probabilidades: objetivo primero, stop primero, ninguno (se cierra a `flat_by`).
4. **La historia.** La misma regla (mismo rango, misma regla de stop, mismo R) corre en cada dia pasado, en
   cualquier direccion y aparte en la direccion del plan. Eso paso de verdad.
5. **El veredicto**, con el spread descontado. Un objetivo de R neto necesita ganar 1 de cada (1 + R) veces
   de las que tocan un lado. A menos de 5 puntos de eso: "moneda al aire". De 5 a 15: "se inclina". Mas de
   15: "se inclina con fuerza".

**La semilla.** Mismo plan, mismos datos, misma semilla: mismos numeros. Dila con cada resultado.

## Limites que hay que decir

- 60 dias es una muestra chica, y 30 activaciones todavia mas.
- Las velas se sacan una a una: la simulacion no conserva tendencias ni rachas de volatilidad. Por eso suele
  dar menos operaciones "abiertas al cierre" que la historia.
- Un hueco de precio o un dato fuerte puede llenar el stop peor que -1R.
- Se niega, en una linea, con menos de 20 dias completos de velas.

## Pasos

1. Corre `timemachine.py run --write`.
2. Di, en este orden: las tres probabilidades, el R promedio neto, las dos lineas de historia, y el veredicto
   tal cual sale. Di la semilla.
3. Si es una moneda al aire, dilo asi. Si la historia y la simulacion no coinciden, dilo tambien.
4. Sigue con `/fx-budget`.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
