FROM node:22.23.2-alpine3.23

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY index.html tsconfig.json vite.config.ts ./
COPY src ./src

CMD ["npm", "run", "dev", "--", "--host", "127.0.0.1"]
