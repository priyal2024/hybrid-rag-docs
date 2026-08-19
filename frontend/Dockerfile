FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
# Placeholder auth config for build-time only — real values come from the
# Secret at runtime. NextAuth reads these at request time, not build time,
# but its module init throws if AUTH_SECRET is completely unset.
ENV AUTH_SECRET=build-time-placeholder

# NEXT_PUBLIC_* vars get inlined into the client JS bundle at build time,
# so this must be passed in as a build ARG (not just a runtime env var on
# Render) and set as ENV before `npm run build` runs.
ARG NEXT_PUBLIC_API_URL=https://hybrid-rag-backend-0ut8.onrender.com
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static

ENV HOSTNAME="0.0.0.0"
ENV PORT=10000

EXPOSE 10000
CMD ["node", "server.js"]