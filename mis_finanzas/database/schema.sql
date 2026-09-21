-- Esquema de la base de datos local de Mis Finanzas.
-- Todas las tablas financieras futuras deberán relacionarse mediante usuario_id.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT NOT NULL UNIQUE,
    nombre TEXT,
    password_hash TEXT NOT NULL,
    recovery_code_hash TEXT,
    recovery_code_used INTEGER NOT NULL DEFAULT 0,
    activo INTEGER NOT NULL DEFAULT 1,
    intentos_fallidos INTEGER NOT NULL DEFAULT 0,
    bloqueado_hasta DATETIME,
    ultimo_acceso DATETIME,
    -- Se incrementa al cambiar/recuperar la contraseña para invalidar
    -- todas las sesiones abiertas.
    version_sesion INTEGER NOT NULL DEFAULT 1,
    fecha_creacion DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS auditoria_seguridad (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    evento TEXT NOT NULL,
    detalle TEXT,
    fecha DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id)
);

CREATE INDEX IF NOT EXISTS idx_auditoria_usuario_fecha
    ON auditoria_seguridad (usuario_id, fecha);

-- Preferencias por usuario (clave/valor). Ej.: inactividad_minutos.
CREATE TABLE IF NOT EXISTS configuracion_usuario (
    usuario_id INTEGER NOT NULL,
    clave TEXT NOT NULL,
    valor TEXT,
    PRIMARY KEY (usuario_id, clave),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
);

-- Estado interno de la aplicación (ej. control de intentos de recuperación).
CREATE TABLE IF NOT EXISTS estado_aplicacion (
    clave TEXT PRIMARY KEY,
    valor TEXT
);
