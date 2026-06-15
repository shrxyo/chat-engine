import type { DefaultSession } from 'next-auth'

declare module 'next-auth' {
  interface User {
    accessToken?: string
  }

  interface Session extends DefaultSession {
    /** Backend JWT forwarded as Authorization: Bearer on all API calls. */
    accessToken?: string
    user: {
      id: string
    } & DefaultSession['user']
  }
}

declare module 'next-auth/jwt' {
  interface JWT {
    accessToken?: string
  }
}
