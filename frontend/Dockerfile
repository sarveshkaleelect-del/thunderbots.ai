FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

# ROOT CAUSE FIX: Next.js inlines NEXT_PUBLIC_* variables into the client
# JS bundle at `next build` time — NOT at container start time. The previous
# Dockerfile had no ARG/ENV here, so docker-compose's runtime `environment:`
# block for the frontend service had zero effect on the actual built bundle;
# the code fell back to its hardcoded default ('http://localhost:8000'). In
# any deployment where the backend is not reachable at that literal address
# from the end user's browser (a real server, a custom domain, a different
# port), every single API call — Knowledge Base uploads, chat, settings —
# fails at the network level, surfaced as "Could not reach the server. Check
# that the backend is running and reachable at the configured API URL."
# Declaring these as build ARGs and exporting them as ENV before `npm run
# build` makes the value passed via docker-compose's `build.args` actually
# take effect in the compiled bundle.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}

RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
