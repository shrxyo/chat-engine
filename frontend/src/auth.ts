/**
 * Auth.js (NextAuth v5) configuration.
 *
 * OAuth providers are registered only when their env vars are set so the app
 * starts cleanly in dev without credentials. On sign-in, the backend upserts
 * the user and returns a JWT signed with the shared SECRET_KEY.
 */
import NextAuth from 'next-auth'
import type { NextAuthConfig, User } from 'next-auth'
import GitHub from 'next-auth/providers/github'
import Google from 'next-auth/providers/google'

const backendUrl = process.env.BACKEND_URL ?? 'http://localhost:8000'

const providers: NextAuthConfig['providers'] = []

if (process.env.GITHUB_CLIENT_ID && process.env.GITHUB_CLIENT_SECRET) {
  providers.push(
    GitHub({
      clientId: process.env.GITHUB_CLIENT_ID,
      clientSecret: process.env.GITHUB_CLIENT_SECRET,
    }),
  )
}

if (process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET) {
  providers.push(
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET,
    }),
  )
}

interface SyncResponse {
  user_id: string
  access_token: string
}

async function syncUserWithBackend(user: User, provider: string, providerId: string) {
  const res = await fetch(`${backendUrl}/api/auth/sync`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: user.email,
      name: user.name ?? user.email,
      avatar_url: user.image ?? null,
      provider,
      provider_id: providerId,
    }),
  })

  if (!res.ok) {
    throw new Error(`Auth sync failed: ${res.status}`)
  }

  return (await res.json()) as SyncResponse
}

const config: NextAuthConfig = {
  providers,
  secret: process.env.NEXTAUTH_SECRET,
  session: { strategy: 'jwt' },
  pages: {
    signIn: '/auth/signin',
  },
  callbacks: {
    async signIn({ user, account }) {
      if (!account?.providerAccountId || !user.email) {
        return false
      }

      try {
        const data = await syncUserWithBackend(
          user,
          account.provider,
          account.providerAccountId,
        )
        user.id = data.user_id
        user.accessToken = data.access_token
        return true
      } catch {
        return false
      }
    },
    jwt({ token, user }) {
      if (user?.id) {
        token.sub = user.id
      }
      if (user?.accessToken) {
        token.accessToken = user.accessToken
      }
      return token
    },
    session({ session, token }) {
      if (token.sub) {
        session.user.id = token.sub
      }
      if (token.accessToken) {
        session.accessToken = token.accessToken as string
      }
      return session
    },
  },
}

export const { handlers, auth, signIn, signOut } = NextAuth(config)
