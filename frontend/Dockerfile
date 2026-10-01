# Local full-stack packaging only.
# AWS production serves the Vite build from S3 + CloudFront — this image is NOT
# deployed to ECS.

FROM node:22-alpine AS build

WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# Same-origin API paths when served behind the local nginx proxy.
ENV VITE_API_URL=
RUN npm run build

FROM nginx:1.27-alpine AS runtime

COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
