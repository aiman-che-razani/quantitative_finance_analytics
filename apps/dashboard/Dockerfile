FROM node:26-alpine@sha256:143494b1da2945f061539253adc65e4f1569ddf07da2d384c022c791a9d90a4a AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ENV AXIOM_STANDALONE=1
RUN npm run build
FROM node:26-alpine@sha256:143494b1da2945f061539253adc65e4f1569ddf07da2d384c022c791a9d90a4a
WORKDIR /app
ENV NODE_ENV=production HOSTNAME=0.0.0.0 PORT=8821
COPY --from=builder --chown=node:node /app/.next/standalone ./
COPY --from=builder --chown=node:node /app/.next/static ./.next/static
USER node
EXPOSE 8821
CMD ["node","server.js"]
