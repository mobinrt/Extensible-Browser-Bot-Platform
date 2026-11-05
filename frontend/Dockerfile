FROM node:22-alpine AS build
WORKDIR /ui
ARG VITE_NOVNC_URL=http://localhost:7900
ENV VITE_NOVNC_URL=${VITE_NOVNC_URL}
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build
FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /ui/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=15s --timeout=5s --retries=3 CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
