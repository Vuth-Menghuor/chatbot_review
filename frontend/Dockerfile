FROM node:22-alpine AS base

ENV PNPM_HOME=/pnpm
ENV PATH=$PNPM_HOME:$PATH
RUN corepack enable

WORKDIR /app

FROM base AS dependencies

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

FROM dependencies AS build

COPY . .

ARG NUXT_PUBLIC_GDCE_API_ENABLED=true
ARG NUXT_PUBLIC_GDCE_API_BASE_URL=http://localhost:8000
ARG NUXT_PUBLIC_GDCE_DEV_EMAIL=frontend-dev@example.com
ARG NUXT_PUBLIC_GDCE_DEV_PASSWORD=password123
ENV NUXT_PUBLIC_GDCE_API_ENABLED=$NUXT_PUBLIC_GDCE_API_ENABLED
ENV NUXT_PUBLIC_GDCE_API_BASE_URL=$NUXT_PUBLIC_GDCE_API_BASE_URL
ENV NUXT_PUBLIC_GDCE_DEV_EMAIL=$NUXT_PUBLIC_GDCE_DEV_EMAIL
ENV NUXT_PUBLIC_GDCE_DEV_PASSWORD=$NUXT_PUBLIC_GDCE_DEV_PASSWORD

RUN pnpm build

FROM node:22-alpine AS runtime

ENV NODE_ENV=production
ENV HOST=0.0.0.0
ENV PORT=3000

WORKDIR /app

RUN addgroup --system frontend && adduser --system --ingroup frontend frontend
COPY --from=build --chown=frontend:frontend /app/.output ./.output

USER frontend
EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:3000').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"

CMD ["node", ".output/server/index.mjs"]
