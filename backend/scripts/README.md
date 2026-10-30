# Security Scripts - ISO 27001 Compliance Tools

Esta carpeta contiene scripts de utilidad para la gestión segura de secretos, validación de configuración de seguridad y rotación de claves, implementando los controles de **ISO 27001 A.9.2.4** (Gestión de información de autenticación secreta) y **A.10.1.2** (Gestión de claves).

---

## Scripts Disponibles

### 1. `generate_secrets.py` - Generador de Secretos Seguros

Genera secretos criptográficamente seguros para despliegue en producción usando CSPRNG (Cryptographically Secure Pseudo-Random Number Generator).

#### Uso

```bash
# Generar secretos para producción
python scripts/generate_secrets.py --environment production --output .env

# Generar secretos para staging
python scripts/generate_secrets.py --environment staging --output .env.staging

# Generar secretos para desarrollo
python scripts/generate_secrets.py --environment development --output .env.development

# Forzar sobrescritura sin confirmación
python scripts/generate_secrets.py --environment production --output .env --force
```

#### Opciones

| Opción | Valores | Descripción |
|--------|---------|-------------|
| `--environment` | `production`, `staging`, `development` | Ambiente de destino (default: `production`) |
| `--output` | path | Archivo de salida (default: `.env`) |
| `--force` | flag | Sobrescribir sin confirmación |

#### Secretos Generados

1. **JWT_SECRET_KEY**: 512 bits (64 bytes) - Firma de tokens JWT
2. **ENCRYPTION_MASTER_KEY**: 256 bits (32 bytes) - Cifrado de datos en reposo
3. **REDIS_PASSWORD**: 256 bits (32 bytes) - Autenticación Redis
4. **DATABASE_ENCRYPTION_KEY**: 256 bits (32 bytes) - Cifrado de base de datos (futuro PHI)

#### Características de Seguridad

- Usa `secrets.token_urlsafe()` y `os.urandom()` (CSPRNG)
- Genera claves de 256 bits para cifrado AES-256
- Configura permisos restrictivos (`chmod 600`) en Unix
- Incluye fecha de generación para tracking de rotación
- Personaliza configuración por ambiente (CORS, DEBUG, LOG_LEVEL)

#### Ejemplo de Salida

```
======================================================================
SECURE SECRETS GENERATOR
ISO 27001 A.9.2.4, A.10.1.2 Compliant
======================================================================

Generating secrets for: production
Output file: .env

Generating cryptographically secure secrets using CSPRNG...

✅ Secrets generated successfully!
✅ Configuration file created: .env
✅ File permissions set to 600 (owner read/write only)

======================================================================
GENERATED SECRETS SUMMARY
======================================================================

JWT Secret Key (length: 86 chars):
  kX9mP2nF7vR4sL8eQ1jW6tY3hG5bN0zA...H5vY2pqL

Encryption Master Key (Base64, 32 bytes / 256 bits):
  3F2504E0-4F89-11D3-9A0C-0305E8...B64ENCODED==

Redis Password (length: 43 chars):
  vR8mK2pL9jX4nF6s...jX4n

Database Encryption Key (Base64, 32 bytes / 256 bits):
  7G3607F1-5G90-22E4-0B1D-1416F9...C75FNCODED==

======================================================================
⚠️  SECURITY REMINDERS:
======================================================================
1. Store these secrets securely (password manager, secrets vault)
2. NEVER commit the .env file to version control
3. Use different secrets for each environment (dev/staging/prod)
4. Rotate secrets every 90 days (see KEY_ROTATION_DAYS)
5. Backup secrets securely before rotating
======================================================================
```

---

### 2. `validate_security.py` - Validador de Configuración de Seguridad

Valida que la configuración de seguridad cumple con los requisitos de ISO 27001 antes del despliegue.

#### Uso

```bash
cd backend
python scripts/validate_security.py
```

#### Validaciones Realizadas

1. **Archivo .env existe**: Verifica presencia de archivo de configuración
2. **Permisos de .env**: Valida permisos 600 en Unix (solo lectura/escritura del propietario)
3. **JWT Secret Key**:
   - Longitud mínima 32 caracteres (recomendado 64+)
   - No es un valor inseguro común (`CHANGE_ME`, `test`, etc.)
   - Tiene suficiente entropía
4. **Encryption Master Key**:
   - Es Base64 válido
   - Decodifica a exactamente 32 bytes (256 bits)
5. **Redis Password**:
   - Está configurado (no vacío)
   - Longitud mínima 16 caracteres (recomendado 32+)
6. **Configuración de Entorno**:
   - DEBUG no está habilitado en producción
   - ENVIRONMENT configurado correctamente
7. **CORS Origins**:
   - No contiene '*' (wildcard inseguro)
   - No contiene 'localhost' en producción
8. **Política de Contraseñas**:
   - PASSWORD_MIN_LENGTH >= 12 caracteres
9. **.env en .gitignore**:
   - Verifica que .env está protegido contra commits accidentales

#### Ejemplo de Salida (Éxito)

```
======================================================================
VALIDACIÓN DE SEGURIDAD - ISO 27001 A.9.2.4, A.10.1.2
Medical Imaging Viewer - Security Configuration Validator
======================================================================

✅ Variables de entorno cargadas desde .env

Ejecutando validaciones de seguridad...

✅ Archivo .env encontrado
✅ Permisos de .env correctos (600)
✅ JWT_SECRET_KEY cumple requisitos de seguridad (86 chars)
✅ ENCRYPTION_MASTER_KEY cumple requisitos (32 bytes/256 bits)
✅ REDIS_PASSWORD configurado correctamente (43 chars)
✅ ENVIRONMENT=production, DEBUG=false
✅ CORS_ORIGINS configurado correctamente
✅ Política de contraseñas cumple ISO 27001 A.9.4.3 (min_length=12)
✅ .env está protegido en .gitignore

======================================================================
RESUMEN DE VALIDACIONES
======================================================================

✅ PASS - Archivo .env existe
✅ PASS - Permisos de .env
✅ PASS - JWT Secret Key
✅ PASS - Encryption Master Key
✅ PASS - Redis Password
✅ PASS - Configuración de entorno
✅ PASS - CORS Origins
✅ PASS - Política de contraseñas
✅ PASS - .env en .gitignore

======================================================================
✅ TODAS LAS VALIDACIONES PASARON (9/9)
Sistema listo para despliegue en producción
======================================================================
```

#### Ejemplo de Salida (Error)

```
======================================================================
VALIDACIÓN DE SEGURIDAD - ISO 27001 A.9.2.4, A.10.1.2
======================================================================

❌ CRÍTICO: JWT_SECRET_KEY demasiado corto (16 chars, mínimo 32)
❌ CRÍTICO: ENCRYPTION_MASTER_KEY no es Base64 válido
⚠️  ADVERTENCIA: REDIS_PASSWORD corto (8 chars), recomendado 32+
❌ CRÍTICO: DEBUG=true en ENVIRONMENT=production

======================================================================
RESUMEN DE VALIDACIONES
======================================================================

❌ FAIL - JWT Secret Key
❌ FAIL - Encryption Master Key
❌ FAIL - Redis Password
❌ FAIL - Configuración de entorno

======================================================================
❌ VALIDACIONES FALLIDAS: 4/9
CORRIJA LOS ERRORES ANTES DE DESPLEGAR EN PRODUCCIÓN
======================================================================
```

#### Exit Codes

- `0`: Todas las validaciones pasaron (listo para despliegue)
- `1`: Una o más validaciones fallaron (NO desplegar)

#### Integración CI/CD

```yaml
# .github/workflows/deploy.yml
- name: Validate Security Configuration
  run: |
    cd backend
    python scripts/validate_security.py
```

---

### 3. `rotate_encryption_key.py` - Rotación de Clave de Cifrado

Rota la clave maestra de cifrado y re-cifra todos los datos cifrados en Redis, cumpliendo con **ISO 27001 A.10.1.2** (política de rotación de claves cada 90 días).

#### ⚠️ IMPORTANTE

- **DETENER LA APLICACIÓN** antes de ejecutar este script
- **CREAR BACKUP COMPLETO** de la base de datos y Redis
- **PROBAR EN STAGING** antes de ejecutar en producción
- **PLANIFICAR VENTANA DE MANTENIMIENTO** (puede tomar varios minutos)

#### Uso

```bash
# Ejemplo completo
python scripts/rotate_encryption_key.py \
    --old-key "$(grep ENCRYPTION_MASTER_KEY .env | cut -d= -f2)" \
    --new-key "$(python -c 'import os, base64; print(base64.b64encode(os.urandom(32)).decode())')" \
    --backup-dir /secure/backups/$(date +%Y%m%d) \
    --redis-host localhost \
    --redis-password "$(grep REDIS_PASSWORD .env | cut -d= -f2)"

# Dry run (simulación sin cambios)
python scripts/rotate_encryption_key.py \
    --old-key "OLD_KEY_HERE" \
    --new-key "NEW_KEY_HERE" \
    --backup-dir /tmp/test \
    --dry-run
```

#### Opciones

| Opción | Requerido | Descripción |
|--------|-----------|-------------|
| `--old-key` | ✅ | Clave maestra actual (Base64) |
| `--new-key` | ✅ | Nueva clave maestra (Base64) |
| `--backup-dir` | ✅ | Directorio para backups |
| `--redis-host` | ❌ | Host de Redis (default: localhost) |
| `--redis-port` | ❌ | Puerto de Redis (default: 6379) |
| `--redis-db` | ❌ | Base de datos Redis (default: 0) |
| `--redis-password` | ❌ | Contraseña de Redis |
| `--key-pattern` | ❌ | Patrón de claves a rotar (default: `*encrypted*`) |
| `--env-file` | ❌ | Ruta al .env (default: `.env`) |
| `--skip-backup` | ❌ | Saltar backup (NO RECOMENDADO) |
| `--dry-run` | ❌ | Simular sin hacer cambios |

#### Proceso de Rotación

1. **Validación**: Verifica que las claves son válidas y diferentes
2. **Conexión Redis**: Establece conexión y verifica autenticación
3. **Backup**: Crea backup completo de Redis en JSON
4. **Escaneo**: Busca todas las claves que coinciden con el patrón
5. **Re-cifrado**: Para cada clave:
   - Descifra con clave antigua
   - Cifra con clave nueva
   - Actualiza en Redis preservando TTL
6. **Actualización .env**: Reemplaza `ENCRYPTION_MASTER_KEY` con nueva clave
7. **Validación**: Muestra resumen y próximos pasos

#### Ejemplo de Salida

```
======================================================================
ENCRYPTION KEY ROTATION - ISO 27001 A.10.1.2
======================================================================

🔧 Initializing key rotation manager...
✅ Rotation manager initialized

🔌 Connecting to Redis at localhost:6379...
✅ Redis connection established

📦 Creating Redis backup: /secure/backups/20250122/redis_backup_20250122_103045.json
   Found 1543 keys to backup
✅ Backup completed: 1543 keys saved

🔄 Rotating encrypted data in Redis (pattern: *encrypted*)
   Found 87 encrypted keys
   Progress: 100/87 keys rotated

✅ Rotation completed: 87 keys rotated, 0 errors

📝 Updating .env with new encryption key
   .env backed up to: /secure/backups/20250122/env_backup_20250122_103047
✅ .env updated successfully

======================================================================
KEY ROTATION SUMMARY
======================================================================
Old key: 3F2504E0-4F89-11D3...B64ENCODED==
New key: 7G3607F1-5G90-22E4...C75FNCODED==
Backup directory: /secure/backups/20250122
Keys rotated: 87
Dry run: False
======================================================================

✅ KEY ROTATION COMPLETED SUCCESSFULLY

NEXT STEPS:
1. Verify application functionality with new key
2. Run: python scripts/validate_security.py
3. Start application and monitor logs for errors
4. Keep old key secure for 30 days (disaster recovery)
5. Update key rotation tracking in documentation
6. Schedule next rotation in 90 days
```

#### Recuperación ante Errores

Si la rotación falla:

1. **NO PÁNICO**: Los backups están creados
2. **Revisar logs**: Identificar causa del error
3. **Restaurar backup**:
   ```bash
   # Restaurar Redis desde backup
   python scripts/restore_redis_backup.py --backup-file /path/to/backup.json
   ```
4. **Restaurar .env**:
   ```bash
   cp /secure/backups/20250122/env_backup_20250122_103047 .env
   ```
5. **Contactar equipo de seguridad** si persiste el problema

---

## Procedimiento Completo de Despliegue Seguro

### 1. Generar Secretos

```bash
cd backend

# Generar secretos para producción
python scripts/generate_secrets.py \
    --environment production \
    --output .env

# Revisar y editar .env (actualizar CORS_ORIGINS, etc.)
nano .env
```

### 2. Validar Configuración

```bash
# Instalar dependencias si es necesario
pip install python-dotenv

# Ejecutar validación
python scripts/validate_security.py
```

**Salida esperada**: `✅ TODAS LAS VALIDACIONES PASARON (9/9)`

### 3. Configurar Redis

```bash
# Obtener password generado
REDIS_PASS=$(grep REDIS_PASSWORD .env | cut -d= -f2)

# Actualizar redis.conf
sudo nano /etc/redis/redis.conf
# Agregar línea: requirepass YOUR_REDIS_PASSWORD

# Reiniciar Redis
sudo systemctl restart redis

# Verificar autenticación
redis-cli -a "$REDIS_PASS" ping
# Debe retornar: PONG
```

### 4. Configurar TLS/SSL

Ver [DEPLOYMENT_SECURITY_GUIDE.md](../DEPLOYMENT_SECURITY_GUIDE.md#configuración-de-tlsssl) para detalles completos.

### 5. Desplegar Aplicación

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar aplicación
uvicorn app.main:app --host 0.0.0.0 --port 8000

# O usar systemd (recomendado producción)
sudo systemctl start medical-imaging-backend
```

### 6. Verificar Deployment

```bash
# Health check
curl https://your-domain.com/api/health

# Revisar logs
tail -f logs/app.log

# Verificar seguridad
python scripts/validate_security.py
```

---

## Rotación de Claves Programada (Cada 90 días)

### Crear Recordatorio

```bash
# Agregar a crontab para recordatorio mensual
crontab -e

# Agregar línea (revisar el 1 de cada mes si rotación es necesaria)
0 9 1 * * echo "REMINDER: Check if key rotation is due (90 days)" | mail -s "Security: Key Rotation Check" admin@your-domain.com
```

### Ejecutar Rotación

```bash
# 1. Programar ventana de mantenimiento
# 2. Notificar usuarios
# 3. Detener aplicación
sudo systemctl stop medical-imaging-backend

# 4. Crear backup completo
sudo -u postgres pg_dump medical_imaging > /secure/backups/db_backup_$(date +%Y%m%d).sql

# 5. Generar nueva clave
NEW_KEY=$(python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())")

# 6. Ejecutar rotación (dry-run primero)
python scripts/rotate_encryption_key.py \
    --old-key "$(grep ENCRYPTION_MASTER_KEY .env | cut -d= -f2)" \
    --new-key "$NEW_KEY" \
    --backup-dir /secure/backups/$(date +%Y%m%d) \
    --redis-password "$(grep REDIS_PASSWORD .env | cut -d= -f2)" \
    --dry-run

# 7. Si dry-run OK, ejecutar real
python scripts/rotate_encryption_key.py \
    --old-key "$(grep ENCRYPTION_MASTER_KEY .env | cut -d= -f2)" \
    --new-key "$NEW_KEY" \
    --backup-dir /secure/backups/$(date +%Y%m%d) \
    --redis-password "$(grep REDIS_PASSWORD .env | cut -d= -f2)"

# 8. Validar configuración
python scripts/validate_security.py

# 9. Iniciar aplicación
sudo systemctl start medical-imaging-backend

# 10. Monitorear logs
tail -f logs/app.log
```

---

## Requisitos de Dependencias

### Python Packages

```bash
pip install python-dotenv redis cryptography
```

O instalar desde `requirements.txt`:

```bash
pip install -r requirements.txt
```

### Sistema Operativo

- **Unix/Linux**: Verificación de permisos de archivos
- **Windows**: Scripts funcionan, pero omiten verificación de permisos

---

## Controles ISO 27001 Implementados

| Control | Descripción | Implementación |
|---------|-------------|----------------|
| **A.9.2.4** | Gestión de información de autenticación secreta | `generate_secrets.py`, `validate_security.py` |
| **A.9.4.2** | Procedimiento seguro de inicio de sesión | Validación de JWT, account lockout |
| **A.9.4.3** | Sistema de gestión de contraseñas | Política de contraseñas en config |
| **A.10.1.1** | Política de uso de controles criptográficos | AES-256-GCM, PBKDF2, Argon2id |
| **A.10.1.2** | Gestión de claves | `rotate_encryption_key.py`, rotación 90 días |
| **A.12.4.1** | Registro de eventos | Logging estructurado JSON |

---

## Soporte y Documentación

- **Guía de Despliegue Seguro**: [DEPLOYMENT_SECURITY_GUIDE.md](../DEPLOYMENT_SECURITY_GUIDE.md)
- **Configuración de Seguridad**: [app/core/config.py](../app/core/config.py)
- **Equipo de Seguridad**: security@your-company.com

---

**Última actualización**: 2025-01-22
**Controles orientados a ISO 27001:2022 — sin certificación ni auditoría externa (PRB-022, 2026-10-28)**
