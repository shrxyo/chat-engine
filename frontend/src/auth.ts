/**
 * Auth.js (NextAuth v5) configuration.
 *
 * OAuth providers are registered only when their env vars are set so the app
 * starts cleanly in dev without credentials. Full OAuth wiring (backend JWT
 * exchange, user upsert) is tracked as S3.1.
 */
import NextAuth from 'next-auth'
import type { NextAuthConfig } from 'next-auth'
import GitHub from 'next-auth/providers/github'
import Google from 'next-auth/providers/google'

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

const config: NextAuthConfig = {
  providers,
  callbacks: {
    jwt({ token, account }) {
      // Persist the OAuth provider's access token so we can forward it to the
      // backend as a Bearer token. S3.1 will replace this with a backend-issued
      // JWT once the /api/auth/callback exchange endpoint is implemented.
      if (account?.access_token) {
        token.accessToken = account.access_token
      }
      return token
    },
    session({ session, token }) {
      if (token.accessToken) {
        session.accessToken = token.accessToken as string
      }
      return session
    },
  },
}

export const { handlers, auth, signIn, signOut } = NextAuth(config)
