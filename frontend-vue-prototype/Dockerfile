FROM node:20-alpine AS build

WORKDIR /app
COPY frontend-vue-prototype/package.json frontend-vue-prototype/package-lock.json ./
RUN npm ci
COPY frontend-vue-prototype/ ./
RUN npm run build

FROM nginx:1.27-alpine

COPY frontend-vue-prototype/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=20s --timeout=5s --start-period=10s --retries=5 \
    CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
