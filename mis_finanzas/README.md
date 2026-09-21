# Mis Finanzas — *Tu dinero, en orden*

Aplicación web de finanzas personales que funciona **exclusivamente de manera
local** en tu computadora (Windows). No usa internet, servicios en la nube ni
proveedores de identidad externos: toda la información vive en un archivo
SQLite dentro de esta carpeta.

Esta primera etapa incluye únicamente el **sistema de acceso y seguridad**:

- Creación del primer usuario (sin usuarios ni contraseñas predeterminados).
- Inicio y cierre de sesión con contraseña protegida mediante hash
  (`werkzeug.security`).
- Código de recuperación local de un solo uso (también almacenado como hash).
- Bloqueo manual y bloqueo automático por inactividad (configurable).
- Protección contra intentos fallidos (5 intentos → 5 minutos de espera).
- Cambio de contraseña con invalidación de sesiones abiertas.
- Auditoría de eventos de seguridad.
- Respaldo y restauración local de la base de datos.

Los módulos financieros (cuentas, tarjetas, inversiones, movimientos, metas,
reportes) se agregarán en etapas posteriores sobre esta misma base.

---

## Requisitos

- **Python 3.10 o superior** (<https://www.python.org/downloads/>).
  En Windows marca la casilla *"Add Python to PATH"* durante la instalación.
- Un navegador moderno (Edge, Chrome o Firefox).

No se requiere conexión a internet para usar la aplicación; sólo para
instalar las dependencias la primera vez.

## Instalación

Abre una terminal (PowerShell o CMD) dentro de la carpeta `mis_finanzas` y
ejecuta:

```bash
python -m venv venv
```

Activa el entorno virtual:

```bat
venv\Scripts\activate
```

(En Linux/macOS: `source venv/bin/activate`).

Instala las dependencias:

```bash
pip install -r requirements.txt
```

Inicializa la base de datos (crea las tablas si no existen; nunca borra datos):

```bash
python database/init_db.py
```

## Ejecutar la aplicación

```bash
python app.py
```

Abre en el navegador:

```text
http://127.0.0.1:5000
```

o bien `http://localhost:5000`.

La primera vez la aplicación detecta que no hay usuarios y muestra la
pantalla **Crear usuario local**. Al terminar se mostrará **una sola vez** tu
código de recuperación (por ejemplo `A7K9-X2PM-81QD-Z6TR`): cópialo, guárdalo
como archivo o imprímelo antes de continuar.

### Detener la aplicación

En la terminal donde se ejecuta, presiona `Ctrl + C`.

### Reiniciar la aplicación

Vuelve a la carpeta, activa el entorno virtual y ejecuta `python app.py`
nuevamente. Tu usuario, configuración y auditoría se conservan en SQLite.

Para no repetir los pasos, puedes crear un archivo `iniciar.bat` con:

```bat
@echo off
cd /d %~dp0
call venv\Scripts\activate
python app.py
pause
```

---

## ¿Dónde se guarda la información?

| Qué                          | Dónde                                   |
| ---------------------------- | --------------------------------------- |
| Base de datos SQLite         | `database/finanzas.db`                  |
| Clave secreta de sesión      | `instance/secret_key` (se genera sola)  |
| Respaldos                    | `backups/`                              |

Ninguno de esos archivos se sube al repositorio (ver `.gitignore`).
La base de datos sólo contiene **hashes** de la contraseña y del código de
recuperación; nunca los valores originales.

Puedes cambiar la ubicación de la base de datos con la variable de entorno
`MIS_FINANZAS_DB` (ruta completa al archivo `.db`).

## Recuperar el acceso

Si olvidas tu contraseña:

1. En la pantalla de inicio de sesión elige **¿Olvidaste tu contraseña?**
2. Escribe tu código de recuperación y una nueva contraseña.
3. La aplicación invalida el código, cambia la contraseña, cierra todas las
   sesiones abiertas y registra el evento `RECUPERACION_ACCESO`.

El código sirve **una sola vez**. Después de usarlo (o en cualquier momento)
puedes generar uno nuevo desde **Configuración → Seguridad → Generar nuevo
código**, confirmando tu contraseña.

Si pierdes la contraseña **y** el código, la única opción es restaurar un
respaldo anterior o eliminar `database/finanzas.db` y empezar de cero.

## Cambiar la configuración

### Desde la aplicación (Configuración → Seguridad)

- **Cambiar contraseña** — requiere la contraseña actual; al cambiarla se
  cierran todas las sesiones y debes iniciar sesión otra vez.
- **Bloqueo por inactividad** — 5, 10, 15, 30 (predeterminado) o 60 minutos.
  Un minuto antes aparece un aviso con *Continuar sesión* / *Bloquear ahora*.
- **Código de recuperación** — genera uno nuevo (el anterior deja de servir).
- **Respaldos** — crear, descargar y restaurar copias de `finanzas.db`.
  Antes de restaurar se valida el archivo y se crea un respaldo automático
  del estado actual.
- **Actividad reciente** — últimos eventos de auditoría.

### Desde `config.py`

Todos los parámetros están centralizados en `config.py`:

| Parámetro                    | Predeterminado | Descripción                              |
| ---------------------------- | -------------- | ---------------------------------------- |
| `HOST` / `PORT`              | `127.0.0.1` / `5000` | Dirección local de la aplicación   |
| `PASSWORD_MIN_LENGTH`        | `10`           | Longitud mínima de la contraseña         |
| `MAX_INTENTOS_FALLIDOS`      | `5`            | Intentos antes del bloqueo temporal      |
| `BLOQUEO_MINUTOS`            | `5`            | Duración del bloqueo temporal            |
| `INACTIVIDAD_MINUTOS_DEFAULT`| `30`           | Bloqueo automático por inactividad       |
| `INACTIVIDAD_OPCIONES`       | `5,10,15,30,60`| Valores seleccionables en Configuración  |
| `INACTIVIDAD_AVISO_SEGUNDOS` | `60`           | Aviso previo al bloqueo automático       |
| `SESSION_COOKIE_*`           | `HttpOnly`, `Lax`, `Secure=False` | Cookies para HTTP local |

---

## Estructura del proyecto

```text
mis_finanzas/
├── app.py                  # Fábrica de la aplicación Flask y arranque
├── config.py               # Configuración centralizada
├── requirements.txt
├── README.md
├── database/
│   ├── schema.sql          # Tablas: usuarios, auditoria_seguridad, configuracion_usuario, estado_aplicacion
│   ├── db.py               # Conexión SQLite (WAL, claves foráneas)
│   ├── init_db.py          # Inicialización manual de la base de datos
│   └── finanzas.db         # (se crea al ejecutar; no se versiona)
├── models/usuario.py       # Acceso a datos con consultas parametrizadas
├── routes/
│   ├── auth.py             # /, /crear-usuario, /login, /logout, /bloquear, /desbloquear,
│   │                       # /cambiar-password, /recuperar-acceso, /sesion-expirada
│   └── main.py             # /inicio, /configuracion/seguridad, respaldos
├── services/
│   ├── auth_service.py     # Reglas de autenticación, intentos, recuperación
│   ├── session_service.py  # Sesión Flask, CSRF, inactividad, cabeceras de seguridad
│   └── backup_service.py   # Crear / validar / restaurar respaldos
├── templates/              # HTML (Jinja2)
├── static/css/styles.css
├── static/js/auth.js       # Mostrar contraseña, fortaleza, código, inactividad
├── backups/                # Respaldos locales (no se versionan)
└── tests/                  # Pruebas automatizadas (pytest)
```

Todas las tablas futuras (cuentas, tarjetas, inversiones, movimientos…) se
relacionarán con `usuarios.id` mediante una columna `usuario_id`.

## Eventos de auditoría

`USUARIO_CREADO`, `LOGIN_CORRECTO`, `LOGIN_FALLIDO`, `CUENTA_BLOQUEADA`,
`LOGOUT`, `APLICACION_BLOQUEADA`, `APLICACION_DESBLOQUEADA`, `SESION_EXPIRADA`,
`CAMBIO_PASSWORD`, `RECUPERACION_ACCESO`, `RECUPERACION_FALLIDA`,
`CODIGO_RECUPERACION_REGENERADO`, `CONFIGURACION_ACTUALIZADA`,
`RESPALDO_CREADO`, `RESPALDO_RESTAURADO`, `RESPALDO_RECHAZADO`.

La auditoría nunca guarda contraseñas ni códigos de recuperación.

## Pruebas

```bash
python -m pytest tests
```

Las pruebas cubren primera ejecución, creación de usuario, código de
recuperación, login correcto/incorrecto, intentos fallidos y bloqueo temporal,
protección de rutas privadas, logout y caché, bloqueo manual/automático,
cambio de contraseña, recuperación de acceso, invalidación de sesiones,
respaldos y persistencia tras reiniciar. Usan una base de datos temporal, así
que no tocan tus datos.
