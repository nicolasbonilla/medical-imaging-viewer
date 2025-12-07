# Medical Imaging Viewer - Guía de Despliegue Seguro

**ISO 27001:2022 Compliance Guide**
**Version:** 1.0.0
**Última actualización:** 2025-01-22

---

## Tabla de Contenidos

1. [Requisitos Previos](#requisitos-previos)
2. [Generación de Secretos Seguros](#generación-de-secretos-seguros)
3. [Configuración del Archivo .env](#configuración-del-archivo-env)
4. [Validación de Seguridad Pre-Despliegue](#validación-de-seguridad-pre-despliegue)
5. [Configuración de TLS/SSL](#configuración-de-tlsssl)
6. [Configuración de Redis Seguro](#configuración-de-redis-seguro)
7. [Variables de Entorno por Ambiente](#variables-de-entorno-por-ambiente)
8. [Procedimientos de Rotación de Claves](#procedimientos-de-rotación-de-claves)
9. [Monitoreo y Alertas de Seguridad](#monitoreo-y-alertas-de-seguridad)
10. [Checklist de Cumplimiento ISO 27001](#checklist-de-cumplimiento-iso-27001)
11. [Procedimientos de Respuesta a Incidentes](#procedimientos-de-respuesta-a-incidentes)

---

## Requisitos Previos

### Software Requerido
- Python 3.11+
- Redis 7.0+ (con soporte para TLS)
- Servidor web con soporte TLS 1.3 (nginx/Apache)
- Certificados SSL válidos (Let's Encrypt o CA comercial)

### Conocimientos Necesarios
- Administración de sistemas Linux/Windows
- Gestión de secretos y certificados
- Conceptos de criptografía (hash, cifrado simétrico)
- Protocolos de red seguros (TLS/SSL)

### Controles ISO 27001 Aplicables
- **A.9.2.4** - Gestión de información de autenticación secreta
- **A.9.4.2** - Procedimiento seguro de inicio de sesión
- **A.9.4.3** - Sistema de gestión de contraseñas
- **A.10.1.1** - Política de uso de controles criptográficos
- **A.10.1.2** - Gestión de claves

---

## Generación de Secretos Seguros

### 1. JWT Secret Key (CRÍTICO)

**Control ISO 27001:** A.9.2.4 - Gestión de información de autenticación secreta

El JWT Secret Key se utiliza para firmar y verificar tokens de autenticación. **NUNCA** use valores predeterminados en producción.

#### Generar JWT Secret Key (Recomendado: 64+ caracteres)

```bash
# Linux/macOS/Git Bash
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Windows PowerShell
python -c "import secrets; print(secrets.token_urlsafe(64))"

# Ejemplo de salida (NO USAR ESTE VALOR):
# kX9mP2nF7vR4sL8eQ1jW6tY3hG5bN0zA2cV8xK4mT9pD7fJ1sL6eR3nW8qH5vY2
```

#### Requisitos de Seguridad
- **Longitud mínima:** 32 caracteres (64+ recomendado para producción)
- **Entropía:** Generado con CSPRNG (Cryptographically Secure Pseudo-Random Number Generator)
- **Almacenamiento:** Variable de entorno, NUNCA en código fuente
- **Rotación:** Cada 90 días (configurable vía `KEY_ROTATION_DAYS`)

---

### 2. Encryption Master Key (CRÍTICO)

**Control ISO 27001:** A.10.1.2 - Gestión de claves

La Master Key se utiliza para cifrado de datos en reposo (IndexedDB, Redis).

#### Generar Encryption Master Key (256-bit/32 bytes)

```bash
# Generar clave de 256 bits y codificar en Base64
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"

# Ejemplo de salida (NO USAR ESTE VALOR):
# 3F2504E0-4F89-11D3-9A0C-0305E82C3301-B64ENCODED==
```

#### Requisitos de Seguridad
- **Longitud:** Exactamente 32 bytes (256 bits) antes de codificación Base64
- **Formato:** Base64-encoded
- **Derivación:** Usar PBKDF2 con 100,000+ iteraciones (configurado en `KDF_ITERATIONS`)
- **Algoritmo:** SHA-256 para KDF (configurado en `KDF_ALGORITHM`)
- **Rotación:** Cada 90 días con re-cifrado de datos

---

### 3. Redis Password

**Control ISO 27001:** A.9.4.1 - Restricción de acceso a la información

Redis almacena datos sensibles en caché (metadatos médicos, sesiones).

#### Generar Redis Password (32+ caracteres)

```bash
# Generar password seguro para Redis
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Ejemplo de salida (NO USAR ESTE VALOR):
# vR8mK2pL9jX4nF6sQ3tY7eW1hG5bN0zA
```

#### Configuración en Redis Server

```bash
# Editar redis.conf
sudo nano /etc/redis/redis.conf

# Agregar/modificar línea:
requirepass YOUR_REDIS_PASSWORD_HERE

# Reiniciar Redis
sudo systemctl restart redis
```

---

### 4. Database Encryption Key (Futuro - PHI)

**Control ISO 27001:** A.10.1.1 - Política de uso de controles criptográficos

Para cumplimiento HIPAA cuando se almacene PHI (Protected Health Information).

```bash
# Generar clave de cifrado de base de datos
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

---

## Configuración del Archivo .env

### Crear Archivo .env en Producción

**NUNCA** copiar el archivo `.env.example` directamente. Generar nuevos secretos para cada ambiente.

```bash
# Navegar al directorio backend
cd backend

# Crear archivo .env vacío
touch .env

# Establecer permisos restrictivos (Linux/macOS)
chmod 600 .env

# Verificar que .env está en .gitignore
grep -q "^.env$" .gitignore && echo "✅ .env protegido" || echo "❌ PELIGRO: .env NO está en .gitignore"
```

### Plantilla .env para Producción

```bash
# ============================================================================
# MEDICAL IMAGING VIEWER - PRODUCTION ENVIRONMENT CONFIGURATION
# ISO 27001 A.9.2.4, A.10.1.2
# ============================================================================

# ============================================================================
# ENVIRONMENT SETTINGS
# ============================================================================
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# ============================================================================
# JWT SECURITY (ISO 27001 A.9.4.2) - CRITICAL
# ============================================================================
# Generar con: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET_KEY=YOUR_GENERATED_JWT_SECRET_KEY_HERE_MIN_64_CHARS
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# ============================================================================
# PASSWORD POLICY (ISO 27001 A.9.4.3)
# ============================================================================
PASSWORD_MIN_LENGTH=12
PASSWORD_REQUIRE_UPPERCASE=true
PASSWORD_REQUIRE_LOWERCASE=true
PASSWORD_REQUIRE_DIGIT=true
PASSWORD_REQUIRE_SPECIAL=true
PASSWORD_MAX_AGE_DAYS=90
PASSWORD_HISTORY_COUNT=5

# ============================================================================
# ACCOUNT LOCKOUT POLICY (ISO 27001 A.9.4.2)
# ============================================================================
ACCOUNT_LOCKOUT_THRESHOLD=5
ACCOUNT_LOCKOUT_DURATION_MINUTES=30

# ============================================================================
# ENCRYPTION CONFIGURATION (ISO 27001 A.10.1.1, A.10.1.2)
# ============================================================================
# Generar con: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
ENCRYPTION_MASTER_KEY=YOUR_GENERATED_BASE64_32_BYTE_KEY_HERE
KDF_ITERATIONS=100000
KDF_ALGORITHM=SHA256
KEY_ROTATION_DAYS=90

# ============================================================================
# REDIS CONFIGURATION (Secure Cache)
# ============================================================================
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
# Generar con: python -c "import secrets; print(secrets.token_urlsafe(32))"
REDIS_PASSWORD=YOUR_REDIS_PASSWORD_HERE
REDIS_MAX_CONNECTIONS=50

# Cache TTL (segundos)
CACHE_DRIVE_FILES_TTL=300
CACHE_IMAGES_TTL=1800
CACHE_METADATA_TTL=600
CACHE_DEFAULT_TTL=3600

# ============================================================================
# CORS CONFIGURATION
# ============================================================================
# Producción: SOLO dominios específicos, NUNCA usar *
CORS_ORIGINS=https://your-production-domain.com,https://www.your-production-domain.com

# ============================================================================
# SERVER CONFIGURATION
# ============================================================================
HOST=0.0.0.0
PORT=8000

# ============================================================================
# GOOGLE DRIVE INTEGRATION (OAuth)
# ============================================================================
GOOGLE_DRIVE_CREDENTIALS_FILE=credentials.json
GOOGLE_DRIVE_TOKEN_FILE=token.json
GOOGLE_DRIVE_SCOPES=https://www.googleapis.com/auth/drive.readonly

# ============================================================================
# UPLOAD CONFIGURATION
# ============================================================================
MAX_UPLOAD_SIZE=524288000
ALLOWED_EXTENSIONS=.dcm,.nii,.nii.gz,.img,.hdr

# ============================================================================
# LOGGING CONFIGURATION (ISO 27001 A.12.4.1)
# ============================================================================
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=logs/app.log
LOG_MAX_BYTES=10485760
LOG_BACKUP_COUNT=10

# ============================================================================
# PERFORMANCE OPTIMIZATION FLAGS
# ============================================================================
ENABLE_BINARY_PROTOCOL=false
ENABLE_WEBSOCKET=false
WEBSOCKET_MAX_CONNECTIONS=100
WEBSOCKET_HEARTBEAT_INTERVAL=30

ENABLE_PREFETCHING=true
PREFETCH_SLICES=3
PREFETCH_PRIORITY=normal

USE_REDIS_SCAN=true
REDIS_SCAN_COUNT=100

ENABLE_CACHE_WARMING=false
CACHE_WARMING_ON_STARTUP=false
```

---

## Validación de Seguridad Pre-Despliegue

### Script de Validación Automatizada

Crear archivo `backend/scripts/validate_security.py`:

```python
#!/usr/bin/env python3
"""
Security Configuration Validator
ISO 27001 A.9.2.4, A.10.1.2 Compliance Check

Usage: python scripts/validate_security.py
"""

import os
import sys
import base64
from pathlib import Path

# Colores para output
RED = '\033[91m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
RESET = '\033[0m'

def check_env_file_exists():
    """Verificar que .env existe."""
    env_path = Path('.env')
    if not env_path.exists():
        print(f"{RED}❌ CRÍTICO: Archivo .env no encontrado{RESET}")
        return False
    print(f"{GREEN}✅ Archivo .env encontrado{RESET}")
    return True

def check_env_file_permissions():
    """Verificar permisos del archivo .env (solo Unix)."""
    if os.name == 'posix':
        env_path = Path('.env')
        stats = env_path.stat()
        perms = oct(stats.st_mode)[-3:]
        if perms != '600':
            print(f"{YELLOW}⚠️  ADVERTENCIA: .env tiene permisos {perms}, recomendado: 600{RESET}")
            return False
        print(f"{GREEN}✅ Permisos de .env correctos (600){RESET}")
    return True

def validate_jwt_secret():
    """Validar JWT_SECRET_KEY."""
    jwt_secret = os.getenv('JWT_SECRET_KEY', '')

    if not jwt_secret:
        print(f"{RED}❌ CRÍTICO: JWT_SECRET_KEY no configurado{RESET}")
        return False

    if len(jwt_secret) < 32:
        print(f"{RED}❌ CRÍTICO: JWT_SECRET_KEY demasiado corto ({len(jwt_secret)} chars, mínimo 32){RESET}")
        return False

    if jwt_secret in ['CHANGE_ME', 'test', 'development', 'secret']:
        print(f"{RED}❌ CRÍTICO: JWT_SECRET_KEY es un valor inseguro común{RESET}")
        return False

    if len(jwt_secret) < 64:
        print(f"{YELLOW}⚠️  ADVERTENCIA: JWT_SECRET_KEY tiene {len(jwt_secret)} chars, recomendado 64+{RESET}")
    else:
        print(f"{GREEN}✅ JWT_SECRET_KEY cumple requisitos de seguridad{RESET}")

    return True

def validate_encryption_key():
    """Validar ENCRYPTION_MASTER_KEY."""
    enc_key = os.getenv('ENCRYPTION_MASTER_KEY', '')

    if not enc_key:
        print(f"{RED}❌ CRÍTICO: ENCRYPTION_MASTER_KEY no configurado{RESET}")
        return False

    try:
        decoded = base64.b64decode(enc_key)
        if len(decoded) != 32:
            print(f"{RED}❌ CRÍTICO: ENCRYPTION_MASTER_KEY debe ser 32 bytes (256 bits), actual: {len(decoded)} bytes{RESET}")
            return False
        print(f"{GREEN}✅ ENCRYPTION_MASTER_KEY cumple requisitos (32 bytes/256 bits){RESET}")
        return True
    except Exception as e:
        print(f"{RED}❌ CRÍTICO: ENCRYPTION_MASTER_KEY no es Base64 válido: {e}{RESET}")
        return False

def validate_redis_password():
    """Validar REDIS_PASSWORD."""
    redis_pass = os.getenv('REDIS_PASSWORD', '')

    if not redis_pass:
        print(f"{YELLOW}⚠️  ADVERTENCIA: REDIS_PASSWORD no configurado (Redis sin autenticación){RESET}")
        return False

    if len(redis_pass) < 16:
        print(f"{YELLOW}⚠️  ADVERTENCIA: REDIS_PASSWORD corto ({len(redis_pass)} chars), recomendado 32+{RESET}")
        return False

    print(f"{GREEN}✅ REDIS_PASSWORD configurado correctamente{RESET}")
    return True

def validate_environment():
    """Validar configuración de entorno."""
    env = os.getenv('ENVIRONMENT', 'production')
    debug = os.getenv('DEBUG', 'false').lower()

    if env == 'production' and debug == 'true':
        print(f"{RED}❌ CRÍTICO: DEBUG=true en ENVIRONMENT=production{RESET}")
        return False

    print(f"{GREEN}✅ ENVIRONMENT={env}, DEBUG={debug}{RESET}")
    return True

def validate_cors_origins():
    """Validar CORS_ORIGINS."""
    cors = os.getenv('CORS_ORIGINS', '')

    if not cors:
        print(f"{YELLOW}⚠️  ADVERTENCIA: CORS_ORIGINS no configurado{RESET}")
        return False

    if '*' in cors:
        print(f"{RED}❌ CRÍTICO: CORS_ORIGINS contiene '*' (permite cualquier origen){RESET}")
        return False

    if 'localhost' in cors and os.getenv('ENVIRONMENT') == 'production':
        print(f"{YELLOW}⚠️  ADVERTENCIA: CORS_ORIGINS contiene 'localhost' en producción{RESET}")
        return False

    print(f"{GREEN}✅ CORS_ORIGINS configurado correctamente{RESET}")
    return True

def validate_password_policy():
    """Validar política de contraseñas."""
    min_length = int(os.getenv('PASSWORD_MIN_LENGTH', 12))

    if min_length < 12:
        print(f"{YELLOW}⚠️  ADVERTENCIA: PASSWORD_MIN_LENGTH={min_length}, recomendado 12+{RESET}")
        return False

    print(f"{GREEN}✅ Política de contraseñas cumple ISO 27001 A.9.4.3{RESET}")
    return True

def main():
    """Ejecutar todas las validaciones."""
    print("\n" + "="*70)
    print("VALIDACIÓN DE SEGURIDAD - ISO 27001 A.9.2.4, A.10.1.2")
    print("="*70 + "\n")

    # Cargar .env
    from dotenv import load_dotenv
    load_dotenv()

    checks = [
        check_env_file_exists(),
        check_env_file_permissions(),
        validate_jwt_secret(),
        validate_encryption_key(),
        validate_redis_password(),
        validate_environment(),
        validate_cors_origins(),
        validate_password_policy(),
    ]

    print("\n" + "="*70)
    passed = sum(checks)
    total = len(checks)

    if passed == total:
        print(f"{GREEN}✅ TODAS LAS VALIDACIONES PASARON ({passed}/{total}){RESET}")
        print("Sistema listo para despliegue en producción\n")
        sys.exit(0)
    else:
        print(f"{RED}❌ VALIDACIONES FALLIDAS ({total - passed}/{total}){RESET}")
        print("CORRIJA LOS ERRORES ANTES DE DESPLEGAR\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
```

### Ejecutar Validación

```bash
# Instalar dependencias
pip install python-dotenv

# Ejecutar validación
cd backend
python scripts/validate_security.py
```

**Resultado esperado:**
```
======================================================================
VALIDACIÓN DE SEGURIDAD - ISO 27001 A.9.2.4, A.10.1.2
======================================================================

✅ Archivo .env encontrado
✅ Permisos de .env correctos (600)
✅ JWT_SECRET_KEY cumple requisitos de seguridad
✅ ENCRYPTION_MASTER_KEY cumple requisitos (32 bytes/256 bits)
✅ REDIS_PASSWORD configurado correctamente
✅ ENVIRONMENT=production, DEBUG=false
✅ CORS_ORIGINS configurado correctamente
✅ Política de contraseñas cumple ISO 27001 A.9.4.3

======================================================================
✅ TODAS LAS VALIDACIONES PASARON (8/8)
Sistema listo para despliegue en producción
```

---

## Configuración de TLS/SSL

**Control ISO 27001:** A.13.1.1, A.13.2.3 - Controles de redes

### Requisitos TLS
- **Protocolo mínimo:** TLS 1.2 (recomendado TLS 1.3)
- **Cipher suites:** Solo suites seguras (FS - Forward Secrecy)
- **Certificados:** Válidos, renovados automáticamente

### Configuración nginx con TLS 1.3

```nginx
# /etc/nginx/sites-available/medical-imaging-viewer

server {
    listen 443 ssl http2;
    server_name your-domain.com;

    # Certificados SSL (Let's Encrypt)
    ssl_certificate /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;

    # Protocolo TLS
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    # Cipher suites seguros (Mozilla Intermediate)
    ssl_ciphers 'ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384';

    # HSTS (HTTP Strict Transport Security)
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # Seguridad headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # Proxy a FastAPI
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Redirección HTTP -> HTTPS
server {
    listen 80;
    server_name your-domain.com;
    return 301 https://$server_name$request_uri;
}
```

### Renovación Automática de Certificados

```bash
# Instalar Certbot
sudo apt install certbot python3-certbot-nginx

# Obtener certificado
sudo certbot --nginx -d your-domain.com

# Verificar renovación automática
sudo certbot renew --dry-run
```

---

## Configuración de Redis Seguro

### Configuración redis.conf para Producción

```bash
# /etc/redis/redis.conf

# Autenticación
requirepass YOUR_REDIS_PASSWORD_HERE

# Bind solo a localhost (si backend está en mismo servidor)
bind 127.0.0.1 ::1

# Proteger modo protegido
protected-mode yes

# Deshabilitar comandos peligrosos
rename-command FLUSHDB ""
rename-command FLUSHALL ""
rename-command CONFIG "CONFIG_b9d3f1a0c4e5"
rename-command DEBUG ""

# Logging
loglevel notice
logfile /var/log/redis/redis-server.log

# Persistencia (para caché médico crítico)
save 900 1
save 300 10
save 60 10000

# Seguridad: deshabilitar comandos administrativos vía red
rename-command SHUTDOWN ""
```

### TLS para Redis (Opcional - Alta Seguridad)

```bash
# Generar certificados para Redis
openssl req -x509 -newkey rsa:4096 -keyout redis-key.pem -out redis-cert.pem -days 365 -nodes

# Configurar TLS en redis.conf
tls-port 6380
port 0
tls-cert-file /etc/redis/certs/redis-cert.pem
tls-key-file /etc/redis/certs/redis-key.pem
tls-ca-cert-file /etc/redis/certs/ca-cert.pem
```

---

## Variables de Entorno por Ambiente

### Desarrollo (`.env.development`)
```bash
ENVIRONMENT=development
DEBUG=true
JWT_SECRET_KEY=dev_key_NEVER_USE_IN_PRODUCTION
ENCRYPTION_MASTER_KEY=dev_encryption_NEVER_USE_IN_PRODUCTION
REDIS_PASSWORD=
CORS_ORIGINS=http://localhost:5173,http://localhost:3000
LOG_LEVEL=DEBUG
```

### Staging (`.env.staging`)
```bash
ENVIRONMENT=staging
DEBUG=false
JWT_SECRET_KEY=<GENERATED_STAGING_KEY>
ENCRYPTION_MASTER_KEY=<GENERATED_STAGING_KEY>
REDIS_PASSWORD=<GENERATED_STAGING_PASSWORD>
CORS_ORIGINS=https://staging.your-domain.com
LOG_LEVEL=INFO
```

### Producción (`.env`)
```bash
ENVIRONMENT=production
DEBUG=false
JWT_SECRET_KEY=<GENERATED_PRODUCTION_KEY>
ENCRYPTION_MASTER_KEY=<GENERATED_PRODUCTION_KEY>
REDIS_PASSWORD=<GENERATED_PRODUCTION_PASSWORD>
CORS_ORIGINS=https://your-domain.com,https://www.your-domain.com
LOG_LEVEL=WARNING
```

---

## Procedimientos de Rotación de Claves

**Control ISO 27001:** A.10.1.2 - Gestión de claves

### Frecuencia de Rotación
- **JWT Secret Key:** Cada 90 días (configurable vía `KEY_ROTATION_DAYS`)
- **Encryption Master Key:** Cada 90 días + re-cifrado de datos
- **Redis Password:** Cada 180 días
- **TLS Certificates:** Renovación automática cada 90 días (Let's Encrypt)

### Procedimiento de Rotación JWT Secret Key

```bash
# 1. Generar nuevo JWT secret
NEW_JWT_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(64))")

# 2. Agregar nuevo secret a .env como JWT_SECRET_KEY_NEW
echo "JWT_SECRET_KEY_NEW=$NEW_JWT_SECRET" >> .env

# 3. Actualizar aplicación para soportar ambos secrets (período de transición)
# Modificar app/core/security/token_manager.py para validar con ambos secrets

# 4. Esperar 24-48 horas (todos los tokens antiguos expiran)

# 5. Reemplazar JWT_SECRET_KEY con JWT_SECRET_KEY_NEW
sed -i 's/JWT_SECRET_KEY=/JWT_SECRET_KEY_OLD=/g' .env
sed -i 's/JWT_SECRET_KEY_NEW=/JWT_SECRET_KEY=/g' .env

# 6. Remover JWT_SECRET_KEY_OLD después de 7 días
sed -i '/JWT_SECRET_KEY_OLD/d' .env

# 7. Reiniciar aplicación
sudo systemctl restart medical-imaging-backend
```

### Procedimiento de Rotación Encryption Master Key

```bash
# 1. Generar nuevo encryption key
NEW_ENC_KEY=$(python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")

# 2. Ejecutar script de re-cifrado (REQUIERE IMPLEMENTACIÓN)
python scripts/rotate_encryption_key.py \
    --old-key "$ENCRYPTION_MASTER_KEY" \
    --new-key "$NEW_ENC_KEY" \
    --backup-dir /secure/backups/$(date +%Y%m%d)

# 3. Actualizar .env
sed -i "s/ENCRYPTION_MASTER_KEY=.*/ENCRYPTION_MASTER_KEY=$NEW_ENC_KEY/" .env

# 4. Reiniciar servicios
sudo systemctl restart medical-imaging-backend
sudo systemctl restart redis
```

---

## Monitoreo y Alertas de Seguridad

**Control ISO 27001:** A.12.4.1 - Registro de eventos

### Eventos Críticos a Monitorear

1. **Intentos de autenticación fallidos** (> 5 en 10 minutos)
2. **Cambios en secretos/configuración**
3. **Acceso a endpoints sensibles** (PHI, credenciales)
4. **Errores de validación de tokens**
5. **Intentos de acceso no autorizado**
6. **Anomalías en uso de recursos** (DoS potencial)

### Configuración de Logging Estructurado

El sistema ya implementa logging estructurado JSON (ISO 27001 A.12.4.1).

**Ejemplo de log de evento de seguridad:**

```json
{
  "timestamp": "2025-01-22T10:30:45.123Z",
  "level": "WARNING",
  "event": "authentication_failed",
  "user_id": null,
  "ip_address": "192.168.1.100",
  "endpoint": "/api/v1/auth/login",
  "reason": "invalid_credentials",
  "attempt_count": 3,
  "lockout_remaining": 2
}
```

### Integración con SIEM (Opcional)

```bash
# Enviar logs a servidor Syslog/SIEM
# Configurar en app/core/logging/config.py

import logging.handlers

syslog_handler = logging.handlers.SysLogHandler(
    address=('siem.your-company.com', 514)
)
syslog_handler.setLevel(logging.WARNING)
logger.addHandler(syslog_handler)
```

---

## Checklist de Cumplimiento ISO 27001

### A.9.2.4 - Gestión de información de autenticación secreta

- [ ] JWT_SECRET_KEY generado con CSPRNG (64+ caracteres)
- [ ] ENCRYPTION_MASTER_KEY generado con CSPRNG (32 bytes/256 bits)
- [ ] Secretos almacenados en variables de entorno (nunca en código)
- [ ] Archivo .env con permisos restrictivos (600 en Unix)
- [ ] .env incluido en .gitignore
- [ ] Validación automática de secretos en pre-despliegue
- [ ] Procedimiento de rotación de claves documentado

### A.9.4.2 - Procedimiento seguro de inicio de sesión

- [ ] JWT con expiración configurada (60 minutos por defecto)
- [ ] Refresh tokens con expiración extendida (7 días)
- [ ] Account lockout después de 5 intentos fallidos
- [ ] Lockout duration de 30 minutos
- [ ] Logging de intentos de autenticación

### A.9.4.3 - Sistema de gestión de contraseñas

- [ ] Longitud mínima de contraseña: 12 caracteres
- [ ] Requerimientos de complejidad (mayúsculas, minúsculas, dígitos, especiales)
- [ ] Hashing con Argon2id (resistente a GPU)
- [ ] Historial de contraseñas (5 últimas contraseñas)
- [ ] Expiración de contraseñas (90 días)

### A.10.1.1 - Política de uso de controles criptográficos

- [ ] Algoritmo de cifrado: AES-256-GCM
- [ ] Algoritmo de hash: SHA-256
- [ ] KDF: PBKDF2 con 100,000+ iteraciones
- [ ] Protocolo TLS: 1.2+ (recomendado 1.3)

### A.10.1.2 - Gestión de claves

- [ ] Rotación de JWT secret cada 90 días
- [ ] Rotación de encryption key cada 90 días
- [ ] Procedimiento de rotación documentado y probado
- [ ] Backup seguro de claves antiguas
- [ ] Destrucción segura de claves obsoletas

### A.12.4.1 - Registro de eventos

- [ ] Logging estructurado (JSON)
- [ ] Registro de eventos de seguridad
- [ ] Timestamps UTC en todos los logs
- [ ] Rotación de logs (10 archivos de 10 MB)
- [ ] Logs protegidos contra modificación

### A.13.1.1 - Controles de redes

- [ ] TLS 1.2+ configurado
- [ ] Certificados SSL válidos
- [ ] HSTS habilitado
- [ ] CORS configurado con orígenes específicos (no *)

---

## Procedimientos de Respuesta a Incidentes

**Control ISO 27001:** A.16.1.5 - Respuesta a incidentes de seguridad

### Incidente: Compromiso de JWT Secret Key

1. **Detección:** Logs muestran tokens válidos desde IPs sospechosas
2. **Contención:** Rotar JWT_SECRET_KEY inmediatamente (procedimiento acelerado)
3. **Erradicación:** Invalidar todos los tokens activos
4. **Recuperación:** Forzar re-autenticación de todos los usuarios
5. **Lecciones aprendidas:** Auditoría de seguridad completa

### Incidente: Intentos de fuerza bruta

1. **Detección:** > 100 intentos fallidos en 5 minutos desde misma IP
2. **Contención:** Bloqueo automático de IP (firewall/fail2ban)
3. **Análisis:** Revisar logs para identificar patrón de ataque
4. **Notificación:** Alertar a equipo de seguridad

### Incidente: Fuga de archivo .env

1. **Detección:** Archivo .env encontrado en repositorio Git
2. **Contención inmediata:**
   - Rotar TODOS los secretos (JWT, Encryption, Redis)
   - Revocar accesos a Google Drive
   - Cambiar contraseñas de cuentas de servicio
3. **Erradicación:**
   - Eliminar .env del historial de Git: `git filter-branch --force --index-filter "git rm --cached --ignore-unmatch backend/.env" --prune-empty --tag-name-filter cat -- --all`
   - Push forzado: `git push origin --force --all`
4. **Notificación:** Informar a usuarios de posible compromiso
5. **Auditoría post-incidente:** Revisar todos los controles de seguridad

---

## Contacto y Soporte

Para soporte en despliegue seguro, contactar:
- **Equipo de Seguridad:** security@your-company.com
- **Documentación ISO 27001:** https://docs.your-company.com/iso27001
- **Repositorio:** https://github.com/your-org/medical-imaging-viewer

---

**Última revisión:** 2025-01-22
**Próxima revisión programada:** 2025-04-22 (90 días)
**Responsable:** Security Team
