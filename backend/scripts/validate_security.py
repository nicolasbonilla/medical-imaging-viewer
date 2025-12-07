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
    else:
        print(f"{YELLOW}ℹ️  Verificación de permisos omitida (Windows){RESET}")
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

    if jwt_secret in ['CHANGE_ME', 'test', 'development', 'secret', 'CHANGE_ME_IN_PRODUCTION']:
        print(f"{RED}❌ CRÍTICO: JWT_SECRET_KEY es un valor inseguro común{RESET}")
        return False

    if len(jwt_secret) < 64:
        print(f"{YELLOW}⚠️  ADVERTENCIA: JWT_SECRET_KEY tiene {len(jwt_secret)} chars, recomendado 64+{RESET}")
    else:
        print(f"{GREEN}✅ JWT_SECRET_KEY cumple requisitos de seguridad ({len(jwt_secret)} chars){RESET}")

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

    print(f"{GREEN}✅ REDIS_PASSWORD configurado correctamente ({len(redis_pass)} chars){RESET}")
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

    print(f"{GREEN}✅ Política de contraseñas cumple ISO 27001 A.9.4.3 (min_length={min_length}){RESET}")
    return True

def validate_gitignore():
    """Validar que .env está en .gitignore."""
    gitignore_path = Path('.gitignore')

    if not gitignore_path.exists():
        print(f"{RED}❌ CRÍTICO: .gitignore no encontrado{RESET}")
        return False

    with open(gitignore_path, 'r') as f:
        gitignore_content = f.read()

    if '.env' not in gitignore_content:
        print(f"{RED}❌ CRÍTICO: .env NO está en .gitignore (riesgo de fuga de secretos){RESET}")
        return False

    print(f"{GREEN}✅ .env está protegido en .gitignore{RESET}")
    return True

def main():
    """Ejecutar todas las validaciones."""
    print("\n" + "="*70)
    print("VALIDACIÓN DE SEGURIDAD - ISO 27001 A.9.2.4, A.10.1.2")
    print("Medical Imaging Viewer - Security Configuration Validator")
    print("="*70 + "\n")

    # Cargar .env
    try:
        from dotenv import load_dotenv
        load_dotenv()
        print(f"{GREEN}✅ Variables de entorno cargadas desde .env{RESET}\n")
    except ImportError:
        print(f"{YELLOW}⚠️  python-dotenv no instalado, usando variables de entorno del sistema{RESET}\n")

    print("Ejecutando validaciones de seguridad...\n")

    checks = [
        ("Archivo .env existe", check_env_file_exists()),
        ("Permisos de .env", check_env_file_permissions()),
        ("JWT Secret Key", validate_jwt_secret()),
        ("Encryption Master Key", validate_encryption_key()),
        ("Redis Password", validate_redis_password()),
        ("Configuración de entorno", validate_environment()),
        ("CORS Origins", validate_cors_origins()),
        ("Política de contraseñas", validate_password_policy()),
        (".env en .gitignore", validate_gitignore()),
    ]

    print("\n" + "="*70)
    print("RESUMEN DE VALIDACIONES")
    print("="*70 + "\n")

    passed = sum(1 for _, result in checks if result)
    total = len(checks)

    for name, result in checks:
        status = f"{GREEN}✅ PASS{RESET}" if result else f"{RED}❌ FAIL{RESET}"
        print(f"{status} - {name}")

    print("\n" + "="*70)

    if passed == total:
        print(f"{GREEN}✅ TODAS LAS VALIDACIONES PASARON ({passed}/{total}){RESET}")
        print(f"{GREEN}Sistema listo para despliegue en producción{RESET}\n")
        sys.exit(0)
    else:
        failed = total - passed
        print(f"{RED}❌ VALIDACIONES FALLIDAS: {failed}/{total}{RESET}")
        print(f"{RED}CORRIJA LOS ERRORES ANTES DE DESPLEGAR EN PRODUCCIÓN{RESET}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
