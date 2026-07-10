FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM node:20-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY package*.json ./
RUN npm ci --omit=dev
COPY --from=builder /app/dist ./dist

# fly.io 볼륨 마운트 포인트 (seen_posts.json 영속 저장)
RUN mkdir -p /data
ENV DATA_DIR=/data

CMD ["node", "dist/index.js"]
