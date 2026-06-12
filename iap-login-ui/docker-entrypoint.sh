#!/bin/sh

# Set default port if not provided
export PORT=${PORT:-8080}

# Replace environment variables in config template
envsubst "\$FIREBASE_API_KEY \$FIREBASE_AUTH_DOMAIN \$FIREBASE_PROJECT_ID \$FIREBASE_PROJECT_NUMBER" < /usr/share/nginx/html/config.template.js > /usr/share/nginx/html/config.js

# Setup runtime BASE_PATH (default to /login/)
export BASE_PATH=${BASE_PATH:-/login/}

# Normalize BASE_PATH to have leading and trailing slashes
case "$BASE_PATH" in
  /*) ;;
  *) BASE_PATH="/$BASE_PATH" ;;
esac
case "$BASE_PATH" in
  */) ;;
  *) BASE_PATH="$BASE_PATH/" ;;
esac

echo "Applying runtime BASE_PATH: $BASE_PATH"

# Replace the placeholder in the built HTML, CSS, and JS files
find /usr/share/nginx/html -type f \( -name "*.html" -o -name "*.js" -o -name "*.css" \) -exec sed -i "s|/__VITE_BASE_PATH__/|$BASE_PATH|g" {} +

# Replace environment variables in Nginx config template
envsubst "\$PORT \$FIREBASE_PROJECT_ID" < /etc/nginx/conf.d/default.conf.template > /etc/nginx/conf.d/default.conf

# Clean up template files from the serving directory so they are not served statically
rm -f /usr/share/nginx/html/config.template.js
rm -f /usr/share/nginx/html/nginx.conf.template

# Log the generated files to stdout for debugging
echo "--- Generated config.js ---"
cat /usr/share/nginx/html/config.js
echo "---------------------------"

echo "--- Generated default.conf ---"
cat /etc/nginx/conf.d/default.conf
echo "-------------------------------"

# Start Nginx
exec nginx -g "daemon off;"
