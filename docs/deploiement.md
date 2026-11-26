# Déploiement de l'API et de l'interface web

`todo serve` lance le serveur de **développement** de Flask : pratique pour essayer, pas pour un usage permanent (pas de
redémarrage automatique, pas de TLS, une seule adresse d'écoute, journaux sommaires). Ce guide décrit une installation durable
sur Debian/Ubuntu : **gunicorn** derrière un **proxy HTTPS**, lancé par **systemd**.

```
navigateur / curl / TUI ──HTTPS──► Caddy ou nginx ──HTTP local──► gunicorn (1 processus, N threads) ──► todo (CLI) ──► base DBM
```

Ce qui compte :

- **Un seul processus gunicorn** (`-w 1`) et plusieurs threads. Le serveur sérialise les écritures avec un verrou *de processus* et
  vérifie `If-Match` sous ce verrou ; avec plusieurs processus, deux écritures pourraient s'entrelacer entre la vérification et
  l'écriture. Le CLI garde de toute façon son propre verrou sur la base (pas de corruption), mais l'`ETag` ne serait plus
  garanti. Un seul processus suffit largement : chaque requête lance un `todo` en sous-processus.
- **Le proxy fait le HTTPS**, pas l'application : le jeton et le cookie de session ne doivent jamais circuler en clair.
- L'application n'écoute que sur `127.0.0.1` (ou une socket Unix) : seul le proxy est exposé.

## 1. Installation

```bash
sudo useradd --system --create-home --home-dir /var/lib/todo --shell /usr/sbin/nologin todo
sudo python3 -m venv /opt/todo
sudo /opt/todo/bin/pip install 'todo-cli[deploy]'      # Flask + gunicorn (depuis PyPI ou : pip install '/chemin/vers/todo-cli[deploy]')
sudo /opt/todo/bin/todo --version
```

La base vit dans `/var/lib/todo` (réglage `TODO_DB_DIR`), propriété de l'utilisateur `todo`.

## 2. Jeton et configuration

Générez un jeton long et gardez-le dans un fichier réservé à root (lu par systemd, jamais en argument de ligne de commande) :

```bash
sudo install -d -m 0750 /etc/todo
python3 -c 'import secrets; print("TODO_SERVER_TOKEN=" + secrets.token_urlsafe(32))' | sudo tee /etc/todo/todo.env >/dev/null
sudo tee -a /etc/todo/todo.env >/dev/null <<'EOT'
TODO_DB_DIR=/var/lib/todo
TODO_SERVER_PROXY=1
EOT
sudo chmod 0600 /etc/todo/todo.env
```

| Variable | Rôle |
|---|---|
| `TODO_SERVER_TOKEN` | jeton de l'API et mot de passe de l'interface web (obligatoire) |
| `TODO_DB_DIR` | dossier de la base |
| `TODO_SERVER_PROXY=1` | derrière un proxy HTTPS de confiance : lit `X-Forwarded-For/Proto/Host`, cookie de session « Secure » |
| `TODO_SERVER_WEB=0` | API seule (pas d'interface web) |
| `TODO_SERVER_TIMEOUT` | secondes accordées à une requête (30 par défaut) |
| `TODO_SERVER_MAX_BODY` | taille maximale d'un corps de requête (65536 octets) |

**N'activez `TODO_SERVER_PROXY=1` que derrière un proxy qui écrase les en-têtes `X-Forwarded-*` envoyés par les clients** (c'est
le cas des configurations ci-dessous) : sinon un client pourrait les falsifier. Changer le jeton déconnecte toutes les sessions web.

## 3. gunicorn

La fabrique `todo_cli.serveur:creer_application()` lit les réglages `[server]` et l'environnement :

```bash
/opt/todo/bin/gunicorn --workers 1 --threads 8 --timeout 60 --bind 127.0.0.1:8765 \
    --access-logfile - 'todo_cli.serveur:creer_application()'
```

- `--workers 1` : voir plus haut (indispensable).
- `--threads 8` : requêtes simultanées ; les lectures s'exécutent en parallèle, les écritures une par une.
- `--timeout 60` : doit **dépasser** `TODO_SERVER_TIMEOUT` (30 s), sinon gunicorn tue le processus avant la réponse 504 propre.
- Socket Unix à la place d'un port : `--bind unix:/run/todo/todo.sock` (et `proxy_pass http://unix:/run/todo/todo.sock` côté nginx).

## 4. Service systemd

`/etc/systemd/system/todo.service` :

```ini
[Unit]
Description=todo-cli : API REST et interface web
After=network.target

[Service]
User=todo
Group=todo
EnvironmentFile=/etc/todo/todo.env
WorkingDirectory=/var/lib/todo
ExecStart=/opt/todo/bin/gunicorn --workers 1 --threads 8 --timeout 60 \
    --bind 127.0.0.1:8765 --access-logfile - 'todo_cli.serveur:creer_application()'
Restart=on-failure
RestartSec=3

# Durcissement : le service ne peut écrire que dans sa base
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/todo
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX
LockPersonality=true

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now todo
systemctl status todo
journalctl -u todo -f                      # journaux (requêtes, erreurs)
curl -s http://127.0.0.1:8765/api/v1/health
```

**Hooks** : ils s'exécutent avec l'identité et le durcissement du service. Un script de hook doit être lisible par `todo`, et
ne peut écrire que dans `ReadWritePaths` (ajoutez-y d'autres dossiers si besoin). Les hooks et le webhook se configurent
dans le fichier de configuration de l'utilisateur `todo` (`/var/lib/todo/.config/todo/config.ini`) ou par `TODO_HOOKS_*` dans `todo.env`.

**Sans droits root** : un service utilisateur (`~/.config/systemd/user/todo.service`, sans `User=` ni durcissement système, puis
`systemctl --user enable --now todo` et `loginctl enable-linger $USER`) convient pour un usage personnel.

## 5. Proxy HTTPS

### Caddy (certificat Let's Encrypt automatique)

`/etc/caddy/Caddyfile` :

```
todo.example.org {
    request_body {
        max_size 64KB
    }
    reverse_proxy 127.0.0.1:8765 {
        transport http {
            response_header_timeout 60s
        }
    }
    header Strict-Transport-Security "max-age=31536000"
}
```

Caddy envoie `X-Forwarded-For/Proto/Host` et écrase ceux du client.

### nginx (+ certbot)

```nginx
server {
    listen 443 ssl http2;
    server_name todo.example.org;
    ssl_certificate     /etc/letsencrypt/live/todo.example.org/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/todo.example.org/privkey.pem;
    add_header Strict-Transport-Security "max-age=31536000" always;

    client_max_body_size 64k;

    # Freine les essais de jeton sur la page de connexion et l'API
    location = /login {
        limit_req zone=todo_login burst=5 nodelay;
        include /etc/nginx/snippets/todo-proxy.conf;
    }
    location / {
        include /etc/nginx/snippets/todo-proxy.conf;
    }
}
```

`/etc/nginx/snippets/todo-proxy.conf` (et, dans le bloc `http {}` : `limit_req_zone $binary_remote_addr zone=todo_login:10m rate=10r/m;`) :

```nginx
proxy_pass http://127.0.0.1:8765;
proxy_set_header Host              $host;
proxy_set_header X-Forwarded-For   $remote_addr;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_read_timeout 60s;
```

(`$remote_addr` et non `$proxy_add_x_forwarded_for` : on n'accepte pas la valeur envoyée par le client.)

Certificat : `sudo certbot --nginx -d todo.example.org`.

### Réduire la surface exposée

- **API seule, ou interface seule** : `TODO_SERVER_WEB=0` coupe l'interface web ; ou bien, côté proxy, ne publiez que `/api/` (ou
  que `/` hors `/api/`).
- **Pas d'Internet du tout** : laissez `127.0.0.1` et utilisez un tunnel SSH (`ssh -L 8765:127.0.0.1:8765 serveur`, puis
  `http://127.0.0.1:8765/` ou `todo tui`), WireGuard ou Tailscale. Aucun proxy ni certificat n'est alors nécessaire.
- **Pare-feu** : n'ouvrez que 443 (`sudo ufw allow 443/tcp`) ; le port 8765 reste local.

## 6. Vérifier l'installation

```bash
curl -s https://todo.example.org/api/v1/health                                   # {"ok":true,"version":"…"}
curl -s -o /dev/null -w '%{http_code}\n' https://todo.example.org/api/v1/tasks    # 401 : le jeton est exigé
curl -s -H "Authorization: Bearer $TODO_SERVER_TOKEN" https://todo.example.org/api/v1/tasks
curl -si https://todo.example.org/login | grep -i set-cookie                      # …; Secure; HttpOnly; SameSite=Lax
```

## 7. Sauvegardes

Tout est dans `/var/lib/todo` : la base de chaque projet, ses sauvegardes automatiques (`backups/`), `attachments/`, les vues
(`views.json`) et la file du webhook. Chaque écriture de l'API fait déjà une sauvegarde interne et reste annulable avec `todo undo`
(`sudo -u todo env TODO_DB_DIR=/var/lib/todo /opt/todo/bin/todo undo`), mais ces sauvegardes sont sur le même disque : faites aussi
une copie extérieure. Pour qu'elle soit cohérente, arrêtez le service pendant la copie (quelques secondes) :

```bash
sudo systemctl stop todo
sudo tar czf /srv/sauvegardes/todo-$(date +%F).tgz -C /var/lib todo
sudo systemctl start todo
```

(à mettre dans une tâche cron ou un timer systemd quotidien). Si vous préférez ne pas interrompre le service, copiez seulement le
dossier `backups/`, constitué de copies déjà figées.

## 8. Mise à jour

```bash
sudo /opt/todo/bin/pip install -U 'todo-cli[deploy]'
sudo systemctl restart todo
curl -s http://127.0.0.1:8765/api/v1/health            # la version a changé
```

## 9. OpenAPI

L'API est décrite par `todo_cli/openapi.json` (OpenAPI 3.0), servie **sans jeton** sur `GET /api/v1/openapi.json`. Quelques usages :

```bash
curl -s https://todo.example.org/api/v1/openapi.json > openapi.json
# Documentation interactive (Swagger UI) en local, sans rien installer d'autre que Docker :
docker run --rm -p 8080:8080 -e SWAGGER_JSON=/spec/openapi.json -v "$PWD":/spec swaggerapi/swagger-ui
# Client dans un autre langage :
npx @openapitools/openapi-generator-cli generate -i openapi.json -g typescript-fetch -o client-ts
```

Postman, Insomnia, Bruno et Redoc l'importent directement. Les tests du projet vérifient que le document décrit exactement les
routes réelles et que les réponses respectent ses schémas.

## 10. Limites à connaître

- Pas de TLS dans l'application, pas de limitation de débit intégrée (voir `limit_req` ci-dessus) : c'est le rôle du proxy.
- Un seul processus gunicorn (voir plus haut) ; chaque requête lance un sous-processus Python (quelques dizaines de ms) : adapté
  à un usage personnel ou d'équipe réduite, pas à une charge importante.
- Un seul jeton partagé (pas de comptes ni de rôles).
- L'interface web charge Bootstrap depuis jsDelivr : le navigateur a besoin d'Internet.
