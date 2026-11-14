# Administración de usuarios con imágenes en S3

Aplicación web en Flask para que un administrador gestione usuarios (crear, consultar, actualizar y eliminar). Los datos se guardan en PostgreSQL (AWS RDS) y las fotos de perfil se guardan en un bucket privado de Amazon S3.

## Características

- Inicio de sesión solo para administradores.
- CRUD completo de usuarios, con búsqueda por nombre de usuario o correo.
- Perfil propio del administrador, para editar sus datos y su foto.
- Fotos en S3 (png, jpg, jpeg, gif, webp; máximo 5 MB), mostradas con URLs firmadas temporales.
- Al reemplazar o eliminar un usuario, su foto anterior se borra de S3.
- Contraseñas con hash (Werkzeug).
- Despliegue con Docker en una instancia EC2 con rol IAM.

## Estructura

```
user-admin/
├── app.py                # Aplicación Flask, modelo, rutas y lógica de S3
├── templates_store.py    # Plantillas HTML embebidas
├── requirements.txt
├── Dockerfile
├── .dockerignore
└── .env                  # Configuración y secretos (no subir a Git ni a Docker Hub)
```

## Requisitos

- Python 3.10 o superior, o Docker.
- Una base de datos PostgreSQL en AWS RDS, accesible desde la EC2.
- Un bucket de S3 en la misma región que RDS y EC2.
- Una instancia EC2 con un rol IAM que tenga permisos sobre el bucket.

## Configuración

Crea un archivo `.env` en la raíz del proyecto. No pongas comentarios en la misma línea que un valor, porque Docker los incluiría en el valor.

```env
SECRET_KEY=valor-aleatorio-largo
DATABASE_URL=postgresql+psycopg2://USUARIO:PASSWORD_URL_ENCODED@ENDPOINT-RDS:5432/BASE?sslmode=require
S3_BUCKET=nombre-de-tu-bucket
AWS_REGION=us-east-1

ADMIN_USERNAME=admin
ADMIN_EMAIL=admin@tudominio.com
ADMIN_PASSWORD=UnaContrasenaSegura
```

| Variable | Descripción |
|---|---|
| `SECRET_KEY` | Clave de sesión de Flask. Genera una con `python -c "import secrets; print(secrets.token_hex(32))"` |
| `DATABASE_URL` | Cadena de conexión a RDS. Usa `postgresql+psycopg2://` (SQLAlchemy) |
| `S3_BUCKET` | Nombre exacto del bucket |
| `AWS_REGION` | Región del bucket, por ejemplo `us-east-1` |
| `ADMIN_USERNAME`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` | Administrador inicial. Se crea solo si no existe ningún administrador |

Las contraseñas con símbolos deben codificarse en URL (`@` → `%40`, `#` → `%23`, `$` → `%24`, `/` → `%2F`).

**No pongas claves de AWS en `.env`.** boto3 usa el rol IAM de la EC2 automáticamente.

## Configuración de AWS

### Bucket S3

| Opción | Valor |
|---|---|
| Región | La misma que RDS y EC2 |
| Object Ownership | ACLs deshabilitadas (Bucket owner enforced) |
| Block Public Access | Las cuatro opciones activadas |
| Versionado | Opcional |
| Cifrado | SSE-S3 (predeterminado) |

No agregues una política de acceso público.

### Rol IAM de la EC2

Adjunta esta política inline al rol de la instancia (reemplaza el nombre del bucket):

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "UserImagesObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject", "s3:GetObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::nombre-de-tu-bucket/users/*"
    }
  ]
}
```

Asigna el rol en **EC2 → Acciones → Seguridad → Modificar rol de IAM**.

### Redes

- **Security group de RDS:** TCP 5432 desde el security group de la EC2.
- **Security group de EC2:** HTTP (80) para la aplicación y SSH (22) solo desde tu IP.

## Ejecución local

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Abre `http://127.0.0.1:5000` e inicia sesión con `ADMIN_USERNAME` y `ADMIN_PASSWORD`.

Para la prueba local necesitas credenciales de AWS (`aws configure`) con permisos sobre el bucket.

## Docker

```bash
# Construir y subir (en tu equipo)
docker login -u <USUARIO_DOCKERHUB>
docker buildx build --platform linux/amd64 -t <USUARIO_DOCKERHUB>/user-admin:1.0 --push .

# Ejecutar en la EC2
docker pull <USUARIO_DOCKERHUB>/user-admin:1.0
docker run -d --name user-admin -p 80:8000 \
  --env-file ~/.env --restart unless-stopped \
  <USUARIO_DOCKERHUB>/user-admin:1.0
docker logs -f user-admin
```

Para eliminar el contenedor: `docker rm -f user-admin`.

## Solución de problemas

| Error | Causa probable | Solución |
|---|---|---|
| `Connection timed out` a RDS | Security group bloquea el puerto 5432 | Permite 5432 desde el security group de la EC2 |
| `InvalidAccessKeyId` | boto3 usa una clave que no existe | No definas claves en `.env` ni en el contenedor; revisa `~/.aws/credentials` |
| `NoCredentialsError` | La EC2 no tiene rol IAM | Asigna el rol en la consola de EC2 |
| `AccessDenied` en S3 | Falta la política sobre el bucket | Revisa el nombre del bucket y el recurso `users/*` |
| `NoSuchBucket` | Nombre o región incorrectos | Revisa `S3_BUCKET` y `AWS_REGION` |
| `permission denied ... docker.sock` | El usuario no está en el grupo `docker` | `sudo usermod -aG docker $USER` y vuelve a iniciar sesión |

## Limitaciones

- No hay HTTPS. Para producción, coloca la aplicación detrás de un balanceador o de Nginx con certificado.
- El servidor de desarrollo no debe usarse en producción; el contenedor usa gunicorn.
- Las imágenes se sirven con URLs firmadas que expiran en 1 hora.
