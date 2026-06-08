# di4health — Frontend

Decision Intelligence 4 Health. Built with Next.js 15, React 19, Tailwind 4, shadcn/ui, and Clerk.

## Local development

```bash
cp .env.example .env.local   # fill in real values (see below)
pnpm install
pnpm dev                     # http://localhost:3000
```

## Environment variables

Copy `.env.example` to `.env.local` and fill in:

| Variable | Description |
|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | Clerk publishable key (starts `pk_test_…`) |
| `CLERK_SECRET_KEY` | Clerk secret key (starts `sk_test_…`) |

Use the **same Clerk instance** as the backend (`CLERK_JWKS_URL` in `backend/.env`).
Never commit `.env.local`.

## Deploy (Vercel)

1. Import the repo in [vercel.com/new](https://vercel.com/new).
2. Set **Root Directory** to `frontend`.
3. Vercel auto-detects Next.js and pnpm — no build-command overrides needed.
4. Add the two environment variables above in **Project → Settings → Environment Variables**.
5. Deploy. Home (`/`) is public; `/llm` requires Clerk sign-in.

After deploy, add the Vercel origin to the backend CORS allow-list (hardening item).
