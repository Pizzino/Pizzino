---
name: fx-scanner
description: >-
  Escaner de forex. Lee los graficos de los 28 pares de las 8 divisas principales y lista los que cumplen
  una regla: rupturas de 20 dias al alza o a la baja, cruces de la media de 20 dias, sobrecompra y sobreventa
  (RSI) en velas diarias, y rupturas del rango asiatico tras la apertura de Londres o de la primera hora de
  Nueva York en velas de 5 minutos. Escribe fx/watchlist.json. Usar cuando el usuario diga "escanea forex",
  "que pares se estan moviendo", "busca setups en divisas", "ruptura de Londres", "rango asiatico",
  "scan forex", "london breakout", "que miro hoy en forex", o al empezar el dia antes de /fx-calendar.
argument-hint: "[daily | session london | session ny] [pares]"
---

# fx-scanner

El escaner es el primer paso. Lee graficos gratuitos y lista los que cumplen una regla. Solo eso. Una
coincidencia describe el grafico: no dice que comprar ni que vender, y no predice nada.

```bash
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily                       # 28 pares, velas diarias -> fx/watchlist.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --mine                # solo los pares de fx/config.json
python3 "${CLAUDE_SKILL_DIR}/scan.py" daily --pairs EURUSD,GBPJPY
python3 "${CLAUDE_SKILL_DIR}/scan.py" session --session london    # ruptura del rango asiatico
python3 "${CLAUDE_SKILL_DIR}/scan.py" session --session ny        # ruptura de la primera hora de Nueva York
```

Otras opciones: `--now "2026-11-13 09:30"` (hora de Nueva York) fija el reloj, `--offline CARPETA` lee
respuestas guardadas, `--no-write`, `--json`. Codigo 0 si hubo coincidencias, 1 si no.

## Las reglas

Diarias, sobre cierres, en las dos direcciones:

| regla | que significa |
| --- | --- |
| `ruptura_20d_alcista` / `ruptura_20d_bajista` | el ultimo cierre supera, o pierde, los 20 cierres anteriores |
| `recupera_ma20` / `pierde_ma20` | el ultimo cierre cruza la media de 20 dias |
| `sobrevendido` / `sobrecomprado` | RSI 14 de Wilder bajo 30 o sobre 70 |

De sesion, en velas de 5 minutos. El rango es el maximo y el minimo de una ventana; la ruptura es la
primera vela COMPLETA que CIERRA fuera. Cierre sobre el maximo = compra, bajo el minimo = venta. Una mecha
no cuenta.

| sesion | rango | se buscan rupturas hasta |
| --- | --- | --- |
| `london` | 00:00 a 08:00 de Londres (la sesion asiatica) | 11:00 de Londres |
| `ny` | 08:00 a 09:00 de Nueva York (incluye los datos de las 8:30) | 12:00 de Nueva York |

Las ventanas se cambian en `fx/config.json` -> `sessions`. El horario de verano de Londres y de Nueva York
se calcula solo (cambian en fechas distintas).

## Datos y limites

- Velas de Yahoo (`EURUSD=X`), gratis, no oficiales, sin volumen y con posible retraso. Un par son una o
  dos peticiones; los 28 tardan unos 15 segundos.
- El forex abre el domingo a las 17:00 de Nueva York y cierra el viernes a las 17:00. Fuera de eso dice
  "cerrado" en una linea.
- Un dia al que le falta mas del 20 % de las velas del rango no se usa.

## Pasos

1. Antes de la sesion: `scan.py daily`. Di cuantos pares se leyeron, cuantos cumplieron una regla y cuales.
2. Tras la apertura de Londres (08:00 Londres) o de Nueva York (09:00 NY): `scan.py session`. Di la hora
   de cada ruptura y que una ruptura vieja ya esta lejos del precio de ahora.
3. El usuario elige un par. Pasalo a `/fx-calendar PAR` y luego a `/fx-entry PAR`. Nunca elijas por el.

## Reglas

- Di que se escaneo: cuantos pares, cuantos sin datos y la hora de los datos.
- Di "cumplio una regla", nunca "es una compra" ni "buena operacion".
- Nunca muestres una ganancia, un retorno ni un resultado esperado.

La cadena completa: `/fx-scanner` -> `/fx-calendar` -> `/fx-entry` -> `/fx-exit` -> `/fx-timemachine` -> `/fx-budget` -> `/fx-risk` -> `/fx-ticket`, y `/fx-alerts` mientras la operacion esta abierta.
Cada skill deja su archivo en la carpeta `fx/` del proyecto y la siguiente lo lee. `${CLAUDE_SKILL_DIR}` es la carpeta de esta skill.

## Seguridad

- Educacion y herramientas, no asesoria financiera. La mayoria de quienes hacen day trading pierden dinero, y el apalancamiento del forex lo acelera.
- Ninguna herramienta de este paquete se conecta a un broker ni puede enviar una orden. El usuario pone cada orden a mano.
- Cuenta demo por defecto (`"paper": true`). Pasar a dinero real es decision del usuario, en su propia configuracion.
- Los precios son de Yahoo: indicativos, sin bid ni ask, y pueden ir con retraso. El precio real es el del broker.
- Nunca digas que par operar ni en que direccion. El usuario elige; las herramientas describen y calculan.
- Nunca cambies un limite de `fx/config.json` para que una orden pase.
